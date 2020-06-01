# coding: utf-8

import json
import struct

from copy import deepcopy

from legendary.models.manifest import (
    Manifest, ManifestMeta, CDL, ChunkPart, ChunkInfo, FML, FileManifest, CustomFields
)


def blob_to_num(in_str):
    """
    The JSON manifest use a rather strange format for storing numbers.

    It's essentially %03d for each char concatenated to a string.
    ...instead of just putting the fucking number in the JSON...

    Also it's still little endian so we have to bitshift it.

    """
    num = 0
    shift = 0
    for i in range(0, len(in_str), 3):
        num += (int(in_str[i:i + 3]) << shift)
        shift += 8
    return num


def guid_from_json(in_str):
    return struct.unpack('>IIII', bytes.fromhex(in_str))


class JSONManifest(Manifest):
    """
    Manifest-compatible reader for JSON based manifests

    """
    def __init__(self):
        super().__init__()
        self.json_data = None

    @classmethod
    def read_all(cls, manifest):
        _m = cls.read(manifest)
        _tmp = deepcopy(_m.json_data)

        _m.meta = JSONManifestMeta.read(_tmp)
        _m.chunk_data_list = JSONCDL.read(_tmp, manifest_version=_m.version)
        _m.file_manifest_list = JSONFML.read(_tmp)
        _m.custom_fields = CustomFields()
        _m.custom_fields._dict = _tmp.pop('CustomFields', dict())

        if _tmp.keys():
            print(f'Did not read JSON keys: {_tmp.keys()}!')

        # clear raw data after manifest has been loaded
        _m.data = b''
        _m.json_data = None

        return _m

    @classmethod
    def read(cls, manifest):
        _manifest = cls()
        _manifest.data = manifest
        _manifest.json_data = json.loads(manifest.decode('utf-8'))

        _manifest.stored_as = 0  # never compressed
        _manifest.version = blob_to_num(_manifest.json_data.get('ManifestFileVersion', '013000000000'))

        return _manifest

    def write(self, *args, **kwargs):
        # The version here only matters for the manifest header,
        # the feature level in meta determines chunk folders etc.
        # So all that's required for successful serialization is
        # setting it to something high enough to be a binary manifest
        self.version = 18
        return super().write(*args, **kwargs)


class JSONManifestMeta(ManifestMeta):
    def __init__(self):
        super().__init__()

    @classmethod
    def read(cls, json_data):
        _meta = cls()

        _meta.feature_level = blob_to_num(json_data.pop('ManifestFileVersion', '013000000000'))
        _meta.is_file_data = json_data.pop('bIsFileData', False)
        _meta.app_id = blob_to_num(json_data.pop('AppID', '000000000000'))
        _meta.app_name = json_data.pop('AppNameString', '')
        _meta.build_version = json_data.pop('BuildVersionString', '')
        _meta.launch_exe = json_data.pop('LaunchExeString', '')
        _meta.launch_command = json_data.pop('LaunchCommand', '')
        _meta.prereq_ids = json_data.pop('PrereqIds', list())
        _meta.prereq_name = json_data.pop('PrereqName', '')
        _meta.prereq_path = json_data.pop('PrereqPath', '')
        _meta.prereq_args = json_data.pop('PrereqArgs', '')

        return _meta


class JSONCDL(CDL):
    def __init__(self):
        super().__init__()

    @classmethod
    def read(cls, json_data, manifest_version=13):
        _cdl = cls()
        _cdl._manifest_version = manifest_version
        _cdl.count = len(json_data['ChunkFilesizeList'])

        cfl = json_data.pop('ChunkFilesizeList')
        chl = json_data.pop('ChunkHashList')
        csl = json_data.pop('ChunkShaList')
        dgl = json_data.pop('DataGroupList')
        _guids = list(cfl.keys())

        for guid in _guids:
            _ci = ChunkInfo(manifest_version=manifest_version)
            _ci.guid = guid_from_json(guid)
            _ci.file_size = blob_to_num(cfl.pop(guid))
            _ci.hash = blob_to_num(chl.pop(guid))
            _ci.sha_hash = bytes.fromhex(csl.pop(guid))
            _ci.group_num = blob_to_num(dgl.pop(guid))
            _ci.window_size = 1024*1024
            _cdl.elements.append(_ci)

        for _dc in (cfl, chl, csl, dgl):
            if _dc:
                print(f'Non-consumed CDL stuff: {_dc}')

        return _cdl


class JSONFML(FML):
    def __init__(self):
        super().__init__()

    @classmethod
    def read(cls, json_data):
        _fml = cls()
        _fml.count = len(json_data['FileManifestList'])

        for _fmj in json_data.pop('FileManifestList'):
            _fm = FileManifest()
            _fm.filename = _fmj.pop('Filename', '')
            _fm.hash = blob_to_num(_fmj.pop('FileHash')).to_bytes(160//8, 'little')
            _fm.flags |= int(_fmj.pop('bIsReadOnly', False))
            _fm.flags |= int(_fmj.pop('bIsCompressed', False)) << 1
            _fm.flags |= int(_fmj.pop('bIsUnixExecutable', False)) << 2
            _fm.file_size = 0
            _fm.chunk_parts = []
            _fm.install_tags = _fmj.pop('InstallTags', list())

            for _cpj in _fmj.pop('FileChunkParts'):
                _cp = ChunkPart()
                _cp.guid = guid_from_json(_cpj.pop('Guid'))
                _cp.offset = blob_to_num(_cpj.pop('Offset'))
                _cp.size = blob_to_num(_cpj.pop('Size'))
                _fm.file_size += _cp.size
                if _cpj:
                    print(f'Non-read ChunkPart keys: {_cpj.keys()}')
                _fm.chunk_parts.append(_cp)

            if _fmj:
                print(f'Non-read FileManifest keys: {_fmj.keys()}')

            _fml.elements.append(_fm)

        return _fml
