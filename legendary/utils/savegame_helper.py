import logging
import os
import time
from hashlib import sha1
from io import BytesIO
from tempfile import TemporaryFile

from legendary.models.chunk import Chunk
from legendary.models.manifest import \
    Manifest, ManifestMeta, CDL, FML, CustomFields, FileManifest, ChunkPart, ChunkInfo


class SaveGameHelper:
    def __init__(self):
        self.files = dict()
        self.log = logging.getLogger('SGH')

    def finalize_chunk(self, chunk: Chunk):
        ci = ChunkInfo()
        ci.guid = chunk.guid
        ci.hash = chunk.hash
        ci.sha_hash = chunk.sha_hash
        # use a temporary file for uploading
        _tmp_file = TemporaryFile()
        self.files[ci.path] = _tmp_file
        # write() returns file size and also sets the uncompressed size
        ci.file_size = chunk.write(_tmp_file)
        ci.window_size = chunk.uncompressed_size
        _tmp_file.seek(0)
        return ci

    def package_savegame(self, input_folder: str, app_name: str = '',
                         epic_id: str = '', cloud_folder: str = ''):
        """
        :param input_folder: Folder to be packaged into chunks/manifest
        :param app_name: App name for savegame being stored
        :param epic_id: Epic account ID
        :param cloud_folder: Folder the savegame resides in (based on game metadata)
        :return:
        """
        m = Manifest()
        m.meta = ManifestMeta()
        m.chunk_data_list = CDL()
        m.file_manifest_list = FML()
        m.custom_fields = CustomFields()
        # create metadata for savegame
        m.meta.app_name = f'{app_name}{epic_id}'
        m.meta.build_version = time.strftime('%Y.%m.%d-%H.%M.%S')
        m.custom_fields['CloudSaveFolder'] = cloud_folder

        self.log.info(f'Packing savegame for "{app_name}", input folder: {input_folder}')
        files = []
        for _dir, _, _files in os.walk(input_folder):
            for _file in _files:
                files.append(os.path.join(_dir, _file))

        chunk_num = 0
        cur_chunk = None
        cur_buffer = None

        for _file in sorted(files, key=str.casefold):
            s = os.stat(_file)
            f = FileManifest()
            # get relative path for manifest
            f.filename = os.path.relpath(_file, input_folder).replace('\\', '/')
            self.log.debug(f'Processing file "{f.filename}"')
            f.file_size = s.st_size
            fhash = sha1()

            with open(_file, 'rb') as cf:
                while remaining := s.st_size - cf.tell():
                    if not cur_chunk:  # create new chunk
                        cur_chunk = Chunk()
                        if cur_buffer:
                            cur_buffer.close()
                        cur_buffer = BytesIO()
                        chunk_num += 1

                    # create chunk part and write it to chunk buffer
                    cp = ChunkPart(guid=cur_chunk.guid, offset=cur_buffer.tell(),
                                   size=min(remaining, 1024 * 1024 - cur_buffer.tell()))
                    _tmp = cf.read(cp.size)
                    cur_buffer.write(_tmp)
                    fhash.update(_tmp)  # update sha1 hash with new data
                    f.chunk_parts.append(cp)

                    if cur_buffer.tell() >= 1024 * 1024:
                        cur_chunk.data = cur_buffer.getvalue()
                        ci = self.finalize_chunk(cur_chunk)
                        self.log.info(f'Chunk #{chunk_num} "{ci.path}" created')
                        # add chunk to CDL
                        m.chunk_data_list.elements.append(ci)
                        cur_chunk = None

            f.hash = fhash.digest()
            m.file_manifest_list.elements.append(f)

        # write remaining chunk if it exists
        if cur_chunk:
            cur_chunk.data = cur_buffer.getvalue()
            ci = self.finalize_chunk(cur_chunk)
            self.log.info(f'Chunk #{chunk_num} "{ci.path}" created')
            m.chunk_data_list.elements.append(ci)
            cur_buffer.close()

        # Finally write/serialize manifest into another temporary file
        _m_filename = f'manifests/{m.meta.build_version}.manifest'
        _tmp_file = TemporaryFile()
        _m_size = m.write(_tmp_file)
        _tmp_file.seek(0)
        self.log.info(f'Manifest "{_m_filename}" written ({_m_size} bytes)')
        self.files[_m_filename] = _tmp_file

        # return dict with created files for uploading/whatever
        return self.files
