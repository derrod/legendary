# coding: utf-8

import struct
import zlib

from hashlib import sha1
from io import BytesIO
from uuid import uuid4

from legendary.utils.rolling_hash import get_hash


class Chunk:
    header_magic = 0xB1FE3AA2

    def __init__(self):
        self.header_version = 3
        self.header_size = 0
        self.compressed_size = 0
        self.hash = 0
        self.stored_as = 0
        self.guid = struct.unpack('>IIII', uuid4().bytes)

        # 0x1 = rolling hash, 0x2 = sha hash, 0x3 = both
        self.hash_type = 0
        self.sha_hash = None
        self.uncompressed_size = 1024 * 1024

        self._guid_str = ''
        self._guid_num = 0
        self._bio = None
        self._data = None

    @property
    def data(self):
        if self._data:
            return self._data

        if self.compressed:
            self._data = zlib.decompress(self._bio.read())
        else:
            self._data = self._bio.read()

        # close BytesIO with raw data since we no longer need it
        self._bio.close()
        self._bio = None

        return self._data

    @data.setter
    def data(self, value: bytes):
        if len(value) > 1024*1024:
            raise ValueError('Provided data is too large (> 1 MiB)!')
        # data is now uncompressed
        if self.compressed:
            self.stored_as ^= 0x1
        # pad data to 1 MiB
        if len(value) < 1024 * 1024:
            value += b'\x00' * (1024 * 1024 - len(value))
        # recalculate hashes
        self.hash = get_hash(value)
        self.sha_hash = sha1(value).digest()
        self.hash_type = 0x3
        self._data = value

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
    def compressed(self):
        return self.stored_as & 0x1

    @classmethod
    def read_buffer(cls, data):
        _sio = BytesIO(data)
        return cls.read(_sio)

    @classmethod
    def read(cls, bio):
        head_start = bio.tell()

        if struct.unpack('<I', bio.read(4))[0] != cls.header_magic:
            raise ValueError('Chunk magic doesn\'t match!')

        _chunk = cls()
        _chunk._bio = bio
        _chunk.header_version = struct.unpack('<I', bio.read(4))[0]
        _chunk.header_size = struct.unpack('<I', bio.read(4))[0]
        _chunk.compressed_size = struct.unpack('<I', bio.read(4))[0]
        _chunk.guid = struct.unpack('<IIII', bio.read(16))
        _chunk.hash = struct.unpack('<Q', bio.read(8))[0]
        _chunk.stored_as = struct.unpack('B', bio.read(1))[0]

        if _chunk.header_version >= 2:
            _chunk.sha_hash = bio.read(20)
            _chunk.hash_type = struct.unpack('B', bio.read(1))[0]

        if _chunk.header_version >= 3:
            _chunk.uncompressed_size = struct.unpack('<I', bio.read(4))[0]

        if bio.tell() - head_start != _chunk.header_size:
            raise ValueError('Did not read entire chunk header!')

        return _chunk

    def write(self, fp=None, compress=True):
        if not fp:
            bio = BytesIO()
        else:
            bio = fp

        self.uncompressed_size = self.compressed_size = len(self.data)
        if compress or self.compressed:
            self._data = zlib.compress(self.data)
            self.stored_as |= 0x1
            self.compressed_size = len(self._data)

        bio.write(struct.pack('<I', self.header_magic))
        # we only serialize the latest version so version/size are hardcoded to 3/66
        bio.write(struct.pack('<I', 3))
        bio.write(struct.pack('<I', 66))
        bio.write(struct.pack('<I', self.compressed_size))
        bio.write(struct.pack('<IIII', *self.guid))
        bio.write(struct.pack('<Q', self.hash))
        bio.write(struct.pack('<B', self.stored_as))

        # header version 2 stuff
        bio.write(self.sha_hash)
        bio.write(struct.pack('B', self.hash_type))

        # header version 3 stuff
        bio.write(struct.pack('<I', self.uncompressed_size))

        # finally, add the data
        bio.write(self._data)

        if not fp:
            return bio.getvalue()
        else:
            return bio.tell()
