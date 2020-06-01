# coding: utf-8

import hashlib
import logging
import struct
import zlib

from base64 import b64encode
from io import BytesIO

logger = logging.getLogger('Manifest')


def read_fstring(bio):
    length = struct.unpack('<i', bio.read(4))[0]

    # if the length is negative the string is UTF-16 encoded, this was a pain to figure out.
    if length < 0:
        # utf-16 chars are 2 bytes wide but the length is # of characters, not bytes
        # todo actually make sure utf-16 characters can't be longer than 2 bytes
        length *= -2
        s = bio.read(length - 2).decode('utf-16')
        bio.seek(2, 1)  # utf-16 strings have two byte null terminators
    elif length > 0:
        s = bio.read(length - 1).decode('ascii')
        bio.seek(1, 1)  # skip string null terminator
    else:  # empty string, no terminators or anything
        s = ''

    return s


def write_fstring(bio, string):
    if not string:
        bio.write(struct.pack('<i', 0))
        return

    try:
        s = string.encode('ascii')
        bio.write(struct.pack('<i', len(string) + 1))
        bio.write(s)
        bio.write(b'\x00')
    except UnicodeEncodeError:
        s = string.encode('utf-16le')
        bio.write(struct.pack('<i', -(len(string) + 1)))
        bio.write(s)
        bio.write(b'\x00\x00')


def get_chunk_dir(version):
    # The lowest version I've ever seen was 12 (Unreal Tournament), but for completeness sake leave all of them in
    if version >= 15:
        return 'ChunksV4'
    elif version >= 6:
        return 'ChunksV3'
    elif version >= 3:
        return 'ChunksV2'
    else:
        return 'Chunks'


class Manifest:
    header_magic = 0x44BEC00C

    def __init__(self):
        self.header_size = 41
        self.size_compressed = 0
        self.size_uncompressed = 0
        self.sha_hash = ''
        self.stored_as = 0
        self.version = 18
        self.data = b''

        # remainder
        self.meta = None
        self.chunk_data_list = None
        self.file_manifest_list = None
        self.custom_fields = None

    @property
    def compressed(self):
        return self.stored_as & 0x1

    @classmethod
    def read_all(cls, data):
        _m = cls.read(data)
        _tmp = BytesIO(_m.data)

        _m.meta = ManifestMeta.read(_tmp)
        _m.chunk_data_list = CDL.read(_tmp, _m.meta.feature_level)
        _m.file_manifest_list = FML.read(_tmp)
        _m.custom_fields = CustomFields.read(_tmp)

        unhandled_data = _tmp.read()
        if unhandled_data:
            logger.warning(f'Did not read {len(unhandled_data)} remaining bytes in manifest! '
                           f'This may not be a problem.')

        # Throw this away since the raw data is no longer needed
        _tmp.close()
        del _tmp
        _m.data = b''

        return _m

    @classmethod
    def read(cls, data):
        bio = BytesIO(data)
        if struct.unpack('<I', bio.read(4))[0] != cls.header_magic:
            raise ValueError('No header magic!')

        _manifest = cls()
        _manifest.header_size = struct.unpack('<I', bio.read(4))[0]
        _manifest.size_uncompressed = struct.unpack('<I', bio.read(4))[0]
        _manifest.size_compressed = struct.unpack('<I', bio.read(4))[0]
        _manifest.sha_hash = bio.read(20)
        _manifest.stored_as = struct.unpack('B', bio.read(1))[0]
        _manifest.version = struct.unpack('<I', bio.read(4))[0]

        if bio.tell() != _manifest.header_size:
            logger.fatal(f'Did not read entire header {bio.tell()} != {_manifest.header_size}! '
                         f'Header version: {_manifest.version}, please report this on '
                         f'GitHub along with a sample of the problematic manifest!')
            raise ValueError('Did not read complete manifest header!')

        data = bio.read()
        if _manifest.compressed:
            _manifest.data = zlib.decompress(data)
            dec_hash = hashlib.sha1(_manifest.data).hexdigest()
            if dec_hash != _manifest.sha_hash.hex():
                raise ValueError('Hash does not match!')
        else:
            _manifest.data = data

        return _manifest

    def write(self, fp=None, compress=True):
        body_bio = BytesIO()

        self.meta.write(body_bio)
        self.chunk_data_list.write(body_bio)
        self.file_manifest_list.write(body_bio)
        self.custom_fields.write(body_bio)

        self.data = body_bio.getvalue()
        self.size_uncompressed = self.size_compressed = len(self.data)
        self.sha_hash = hashlib.sha1(self.data).digest()

        if self.compressed or compress:
            self.stored_as |= 0x1
            self.data = zlib.compress(self.data)
            self.size_compressed = len(self.data)

        if not fp:
            bio = BytesIO()
        else:
            bio = fp

        bio.write(struct.pack('<I', self.header_magic))
        bio.write(struct.pack('<I', self.header_size))
        bio.write(struct.pack('<I', self.size_uncompressed))
        bio.write(struct.pack('<I', self.size_compressed))
        bio.write(self.sha_hash)
        bio.write(struct.pack('B', self.stored_as))
        bio.write(struct.pack('<I', self.version))
        bio.write(self.data)

        if not fp:
            return bio.getvalue()
        else:
            return bio.tell()


class ManifestMeta:
    def __init__(self):
        self.meta_size = 0
        self.data_version = 0
        self.feature_level = 18
        self.is_file_data = False
        self.app_id = 0
        self.app_name = ''
        self.build_version = ''
        self.launch_exe = ''
        self.launch_command = ''
        self.prereq_ids = []
        self.prereq_name = ''
        self.prereq_path = ''
        self.prereq_args = ''
        # this build id is used for something called "delta file" which I guess I'll have to implement eventually
        self._build_id = ''

    @property
    def build_id(self):
        if self._build_id:
            return self._build_id
        # this took a while to figure out and get right and I'm still not sure if it'll work for all games :x
        s = hashlib.sha1()
        s.update(struct.pack('<I', self.app_id))
        s.update(self.app_name.encode('utf-8'))
        s.update(self.build_version.encode('utf-8'))
        s.update(self.launch_exe.encode('utf-8'))
        s.update(self.launch_command.encode('utf-8'))
        self._build_id = b64encode(s.digest()).decode('ascii').replace('+', '-').replace('/', '_').replace('=', '')
        return self._build_id

    @classmethod
    def read(cls, bio):
        _meta = cls()

        _meta.meta_size = struct.unpack('<I', bio.read(4))[0]
        _meta.data_version = struct.unpack('B', bio.read(1))[0]
        # Usually same as manifest version, but can be different
        # e.g. if JSON manifest has been converted to binary manifest.
        _meta.feature_level = struct.unpack('<I', bio.read(4))[0]
        # As far as I can tell this was used for very old manifests that didn't use chunks at all
        _meta.is_file_data = struct.unpack('B', bio.read(1))[0] == 1
        # 0 for most apps, generally not used
        _meta.app_id = struct.unpack('<I', bio.read(4))[0]
        _meta.app_name = read_fstring(bio)
        _meta.build_version = read_fstring(bio)
        _meta.launch_exe = read_fstring(bio)
        _meta.launch_command = read_fstring(bio)

        # This is a list though I've never seen more than one entry
        entries = struct.unpack('<I', bio.read(4))[0]
        for i in range(entries):
            _meta.prereq_ids.append(read_fstring(bio))

        _meta.prereq_name = read_fstring(bio)
        _meta.prereq_path = read_fstring(bio)
        _meta.prereq_args = read_fstring(bio)

        # apparently there's a newer version that actually stores *a* build id.
        if _meta.data_version > 0:
            _meta._build_id = read_fstring(bio)

        if bio.tell() != _meta.meta_size:
            raise ValueError('Did not read entire meta!')

        return _meta

    def write(self, bio):
        meta_start = bio.tell()

        bio.write(struct.pack('<I', 0))  # placeholder size
        bio.write(struct.pack('B', self.data_version))
        bio.write(struct.pack('<I', self.feature_level))
        bio.write(struct.pack('B', self.is_file_data))
        bio.write(struct.pack('<I', self.app_id))
        write_fstring(bio, self.app_name)
        write_fstring(bio, self.build_version)
        write_fstring(bio, self.launch_exe)
        write_fstring(bio, self.launch_command)

        bio.write(struct.pack('<I', len(self.prereq_ids)))
        for preqre_id in self.prereq_ids:
            write_fstring(bio, preqre_id)

        write_fstring(bio, self.prereq_name)
        write_fstring(bio, self.prereq_path)
        write_fstring(bio, self.prereq_args)

        if self.data_version > 0:
            write_fstring(bio, self.build_id)

        meta_end = bio.tell()
        bio.seek(meta_start)
        bio.write(struct.pack('<I', meta_end - meta_start))
        bio.seek(meta_end)


class CDL:
    def __init__(self):
        self.version = 0
        self.size = 0
        self.count = 0
        self.elements = []
        self._manifest_version = 18
        self._guid_map = None
        self._guid_int_map = None
        self._path_map = None

    def get_chunk_by_path(self, path):
        if not self._path_map:
            self._path_map = dict()
            for index, chunk in enumerate(self.elements):
                self._path_map[chunk.path] = index

        index = self._path_map.get(path, None)
        if index is None:
            raise ValueError(f'Invalid path! "{path}"')
        return self.elements[index]

    def get_chunk_by_guid(self, guid):
        """
        Get chunk by GUID string or number, creates index of chunks on first call

        Integer GUIDs are usually faster and require less memory, use those when possible.

        :param guid:
        :return:
        """
        if isinstance(guid, int):
            return self.get_chunk_by_guid_num(guid)
        else:
            return self.get_chunk_by_guid_str(guid)

    def get_chunk_by_guid_str(self, guid):
        if not self._guid_map:
            self._guid_map = dict()
            for index, chunk in enumerate(self.elements):
                self._guid_map[chunk.guid_str] = index

        index = self._guid_map.get(guid.lower(), None)
        if index is None:
            raise ValueError(f'Invalid GUID! {guid}')
        return self.elements[index]

    def get_chunk_by_guid_num(self, guid_int):
        if not self._guid_int_map:
            self._guid_int_map = dict()
            for index, chunk in enumerate(self.elements):
                self._guid_int_map[chunk.guid_num] = index

        index = self._guid_int_map.get(guid_int, None)
        if index is None:
            raise ValueError(f'Invalid GUID! {hex(guid_int)}')
        return self.elements[index]

    @classmethod
    def read(cls, bio, manifest_version=18):
        cdl_start = bio.tell()
        _cdl = cls()
        _cdl._manifest_version = manifest_version

        _cdl.size = struct.unpack('<I', bio.read(4))[0]
        _cdl.version = struct.unpack('B', bio.read(1))[0]
        _cdl.count = struct.unpack('<I', bio.read(4))[0]

        # the way this data is stored is rather odd, maybe there's a nicer way to write this...

        for i in range(_cdl.count):
            _cdl.elements.append(ChunkInfo(manifest_version=manifest_version))

        # guid, doesn't seem to be a standard like UUID but is fairly straightfoward, 4 bytes, 128 bit.
        for chunk in _cdl.elements:
            chunk.guid = struct.unpack('<IIII', bio.read(16))

        # hash is a 64 bit integer, no idea how it's calculated but we don't need to know that.
        for chunk in _cdl.elements:
            chunk.hash = struct.unpack('<Q', bio.read(8))[0]

        # sha1 hash
        for chunk in _cdl.elements:
            chunk.sha_hash = bio.read(20)

        # group number, seems to be part of the download path
        for chunk in _cdl.elements:
            chunk.group_num = struct.unpack('B', bio.read(1))[0]

        # window size is the uncompressed size
        for chunk in _cdl.elements:
            chunk.window_size = struct.unpack('<I', bio.read(4))[0]

        # file size is the compressed size that will need to be downloaded
        for chunk in _cdl.elements:
            chunk.file_size = struct.unpack('<q', bio.read(8))[0]

        if bio.tell() - cdl_start != _cdl.size:
            raise ValueError('Did not read entire chunk data list!')

        return _cdl

    def write(self, bio):
        cdl_start = bio.tell()
        bio.write(struct.pack('<I', 0))  # placeholder size
        bio.write(struct.pack('B', self.version))
        bio.write(struct.pack('<I', len(self.elements)))

        for chunk in self.elements:
            bio.write(struct.pack('<IIII', *chunk.guid))
        for chunk in self.elements:
            bio.write(struct.pack('<Q', chunk.hash))
        for chunk in self.elements:
            bio.write(chunk.sha_hash)
        for chunk in self.elements:
            bio.write(struct.pack('B', chunk.group_num))
        for chunk in self.elements:
            bio.write(struct.pack('<I', chunk.window_size))
        for chunk in self.elements:
            bio.write(struct.pack('<q', chunk.file_size))

        cdl_end = bio.tell()
        bio.seek(cdl_start)
        bio.write(struct.pack('<I', cdl_end - cdl_start))
        bio.seek(cdl_end)


class ChunkInfo:
    def __init__(self, manifest_version=18):
        self.guid = None
        self.hash = 0
        self.sha_hash = b''
        self.window_size = 0
        self.file_size = 0

        self._manifest_version = manifest_version
        # caches for things that are "expensive" to compute
        self._group_num = None
        self._guid_str = None
        self._guid_num = None

    def __repr__(self):
        return '<ChunkInfo (guid={}, hash={}, sha_hash={}, group_num={}, window_size={}, file_size={})>'.format(
            self.guid_str, self.hash, self.sha_hash.hex(), self.group_num, self.window_size, self.file_size
        )

    @property
    def guid_str(self):
        if not self._guid_str:
            self._guid_str = '-'.join('{:08x}'.format(g) for g in self.guid)

        return self._guid_str

    @property
    def guid_num(self):
        if not self._guid_num:
            self._guid_num = self.guid[3] + (self.guid[2] << 32) + (self.guid[1] << 64) + (self.guid[0] << 96)
        return self._guid_num

    @property
    def group_num(self):
        if self._guid_num is not None:
            return self._group_num

        self._group_num = (zlib.crc32(
            struct.pack('<I', self.guid[0]) +
            struct.pack('<I', self.guid[1]) +
            struct.pack('<I', self.guid[2]) +
            struct.pack('<I', self.guid[3])
        ) & 0xffffffff) % 100
        return self._group_num

    @group_num.setter
    def group_num(self, value):
        self._group_num = value

    @property
    def path(self):
        return '{}/{:02d}/{:016X}_{}.chunk'.format(
            get_chunk_dir(self._manifest_version), self.group_num,
            self.hash, ''.join('{:08X}'.format(g) for g in self.guid))


class FML:
    def __init__(self):
        self.version = 0
        self.size = 0
        self.count = 0
        self.elements = []

        self._path_map = dict()

    def get_file_by_path(self, path):
        if not self._path_map:
            self._path_map = dict()
            for index, fm in enumerate(self.elements):
                self._path_map[fm.filename] = index

        index = self._path_map.get(path, None)
        if index is None:
            raise ValueError(f'Invalid path! {path}')
        return self.elements[index]

    @classmethod
    def read(cls, bio):
        fml_start = bio.tell()
        _fml = cls()
        _fml.size = struct.unpack('<I', bio.read(4))[0]
        _fml.version = struct.unpack('B', bio.read(1))[0]
        _fml.count = struct.unpack('<I', bio.read(4))[0]

        for i in range(_fml.count):
            _fml.elements.append(FileManifest())

        for fm in _fml.elements:
            fm.filename = read_fstring(bio)

        # never seen this used in any of the manifests I checked but can't wait for something to break because of it
        for fm in _fml.elements:
            fm.symlink_target = read_fstring(bio)

        # For files this is actually the SHA1 instead of whatever it is for chunks...
        for fm in _fml.elements:
            fm.hash = bio.read(20)

        # Flags, the only one I've seen is for executables
        for fm in _fml.elements:
            fm.flags = struct.unpack('B', bio.read(1))[0]

        # install tags, no idea what they do, I've only seen them in the Fortnite manifest
        for fm in _fml.elements:
            _elem = struct.unpack('<I', bio.read(4))[0]
            for i in range(_elem):
                fm.install_tags.append(read_fstring(bio))

        # Each file is made up of "Chunk Parts" that can be spread across the "chunk stream"
        for fm in _fml.elements:
            _elem = struct.unpack('<I', bio.read(4))[0]
            for i in range(_elem):
                chunkp = ChunkPart()
                _size = struct.unpack('<I', bio.read(4))[0]
                chunkp.guid = struct.unpack('<IIII', bio.read(16))
                chunkp.offset = struct.unpack('<I', bio.read(4))[0]
                chunkp.size = struct.unpack('<I', bio.read(4))[0]
                fm.chunk_parts.append(chunkp)

        # we have to calculate the actual file size ourselves
        for fm in _fml.elements:
            fm.file_size = sum(c.size for c in fm.chunk_parts)

        if bio.tell() - fml_start != _fml.size:
            raise ValueError('Did not read entire chunk data list!')

        return _fml

    def write(self, bio):
        fml_start = bio.tell()
        bio.write(struct.pack('<I', 0))  # placeholder size
        bio.write(struct.pack('B', self.version))
        bio.write(struct.pack('<I', len(self.elements)))

        for fm in self.elements:
            write_fstring(bio, fm.filename)
        for fm in self.elements:
            write_fstring(bio, fm.symlink_target)
        for fm in self.elements:
            bio.write(fm.hash)
        for fm in self.elements:
            bio.write(struct.pack('B', fm.flags))
        for fm in self.elements:
            bio.write(struct.pack('<I', len(fm.install_tags)))
            for tag in fm.install_tags:
                write_fstring(bio, tag)

        # finally, write the chunk parts
        for fm in self.elements:
            bio.write(struct.pack('<I', len(fm.chunk_parts)))
            for cp in fm.chunk_parts:
                # size is always 28 bytes (4 size + 16 guid + 4 offset + 4 size)
                bio.write(struct.pack('<I', 28))
                bio.write(struct.pack('<IIII', *cp.guid))
                bio.write(struct.pack('<I', cp.offset))
                bio.write(struct.pack('<I', cp.size))

        fml_end = bio.tell()
        bio.seek(fml_start)
        bio.write(struct.pack('<I', fml_end - fml_start))
        bio.seek(fml_end)


class FileManifest:
    def __init__(self):
        self.filename = ''
        self.symlink_target = ''
        self.hash = b''
        self.flags = 0
        self.install_tags = []
        self.chunk_parts = []
        self.file_size = 0

    @property
    def read_only(self):
        return self.flags & 0x1

    @property
    def compressed(self):
        return self.flags & 0x2

    @property
    def executable(self):
        return self.flags & 0x4

    @property
    def sha_hash(self):
        return self.hash

    def __repr__(self):
        if len(self.chunk_parts) <= 20:
            cp_repr = ', '.join(repr(c) for c in self.chunk_parts)
        else:
            _cp = [repr(cp) for cp in self.chunk_parts[:20]]
            _cp.append('[...]')
            cp_repr = ', '.join(_cp)

        return '<FileManifest (filename="{}", symlink_target="{}", hash={}, flags={}, ' \
               'install_tags=[{}], chunk_parts=[{}], file_size={})>'.format(
            self.filename, self.symlink_target, self.hash.hex(), self.flags,
            ', '.join(self.install_tags), cp_repr, self.file_size
        )


class ChunkPart:
    def __init__(self, guid=None, offset=0, size=0):
        self.guid = guid
        self.offset = offset
        self.size = size
        # caches for things that are "expensive" to compute
        self._guid_str = None
        self._guid_num = None

    @property
    def guid_str(self):
        if not self._guid_str:
            self._guid_str = '-'.join('{:08x}'.format(g) for g in self.guid)
        return self._guid_str

    @property
    def guid_num(self):
        if not self._guid_num:
            self._guid_num = self.guid[3] + (self.guid[2] << 32) + (self.guid[1] << 64) + (self.guid[0] << 96)
        return self._guid_num

    def __repr__(self):
        guid_readable = '-'.join('{:08x}'.format(g) for g in self.guid)
        return '<ChunkPart (guid={}, offset={}, size={})>'.format(
            guid_readable, self.offset, self.size)


class CustomFields:  # this could probably be replaced with just a dict
    def __init__(self):
        self.size = 0
        self.version = 0
        self.count = 0

        self._dict = dict()

    def __getitem__(self, item):
        return self._dict.get(item, None)

    def __setitem__(self, key, value):
        self._dict[key] = value

    def __str__(self):
        return str(self._dict)

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    @classmethod
    def read(cls, bio):
        _cf = cls()

        cf_start = bio.tell()
        _cf.size = struct.unpack('<I', bio.read(4))[0]
        _cf.version = struct.unpack('B', bio.read(1))[0]
        _cf.count = struct.unpack('<I', bio.read(4))[0]

        _keys = []
        _values = []

        for i in range(_cf.count):
            _keys.append(read_fstring(bio))

        for i in range(_cf.count):
            _values.append(read_fstring(bio))

        _cf._dict = dict(zip(_keys, _values))

        if bio.tell() - cf_start != _cf.size:
            raise ValueError('Did not read entire custom fields list!')

        return _cf

    def write(self, bio):
        cf_start = bio.tell()
        bio.write(struct.pack('<I', 0))  # placeholder size
        bio.write(struct.pack('B', self.version))
        bio.write(struct.pack('<I', len(self._dict)))

        for key in self.keys():
            write_fstring(bio, key)

        for value in self.values():
            write_fstring(bio, value)

        cf_end = bio.tell()
        # write proper size
        bio.seek(cf_start)
        bio.write(struct.pack('<I', cf_end - cf_start))
        bio.seek(cf_end)


class ManifestComparison:
    def __init__(self):
        self.added = set()
        self.removed = set()
        self.changed = set()
        self.unchanged = set()

    @classmethod
    def create(cls, manifest, old_manifest=None):
        comp = cls()

        if not old_manifest:
            comp.added = set(fm.filename for fm in manifest.file_manifest_list.elements)
            return comp

        old_files = {fm.filename: fm.hash for fm in old_manifest.file_manifest_list.elements}

        for fm in manifest.file_manifest_list.elements:
            old_file_hash = old_files.pop(fm.filename, None)
            if old_file_hash:
                if fm.hash == old_file_hash:
                    comp.unchanged.add(fm.filename)
                else:
                    comp.changed.add(fm.filename)
            else:
                comp.added.add(fm.filename)

        # any remaining old files were removed
        if old_files:
            comp.removed = set(old_files.keys())

        return comp
