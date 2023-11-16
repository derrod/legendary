# -*- coding: utf-8 -*-

"""
Utilities for extracting information from PE (Portable Executable) files.
Adapted from https://github.com/robomotic/pemeta

Original credits:
__author__ = "Paolo Di Prodi"
__copyright__ = "Copyright 2017, LogstTotal Project"
__license__ = "Apache"
__version__ = "2.0"
__maintainer__ = "Paolo Di Prodi"
__email__ = "paolo@logstotal.com"
"""

import io
import logging
import struct

import pefile

from PIL import Image


class PEUtils(object):
    GRPICONDIRENTRY_format = ('GRPICONDIRENTRY',
                              ('B,Width', 'B,Height', 'B,ColorCount', 'B,Reserved',
                               'H,Planes', 'H,BitCount', 'I,BytesInRes', 'H,ID'))
    GRPICONDIR_format = ('GRPICONDIR',
                         ('H,Reserved', 'H,Type', 'H,Count'))
    RES_ICON = 1
    RES_CURSOR = 2

    def __init__(self, pe_file):
        self.pe = pefile.PE(pe_file, fast_load=True)
        self.pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT'],
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_TLS'],
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']
        ])

    def _find_resource_base(self, res_type):
        try:

            rt_base_idx = [entry.id for
                           entry in self.pe.DIRECTORY_ENTRY_RESOURCE.entries].index(
                pefile.RESOURCE_TYPE[res_type]
            )
        except AttributeError:
            rt_base_idx = None
        except ValueError:
            rt_base_idx = None

        if rt_base_idx is not None:
            return self.pe.DIRECTORY_ENTRY_RESOURCE.entries[rt_base_idx]

        return None

    def _find_resource(self, res_type, res_index):
        rt_base_dir = self._find_resource_base(res_type)

        if res_index < 0:
            try:
                idx = [entry.id for entry in rt_base_dir.directory.entries].index(-res_index)
            except:
                return None
        else:
            idx = res_index if res_index < len(rt_base_dir.directory.entries) else None

        if idx is None:
            return None

        test_res_dir = rt_base_dir.directory.entries[idx]
        res_dir = test_res_dir
        if test_res_dir.struct.DataIsDirectory:
            # another Directory
            # probably language take the first one
            res_dir = test_res_dir.directory.entries[0]
        if res_dir.struct.DataIsDirectory:
            # a directory there is no icon here
            return None

        return res_dir

    def _get_group_icons(self):
        rt_base_dir = self._find_resource_base('RT_GROUP_ICON')
        groups = list()

        if not hasattr(rt_base_dir, "directory"):
            return groups

        for res_index in range(0, len(rt_base_dir.directory.entries)):
            grp_icon_dir_entry = self._find_resource('RT_GROUP_ICON', res_index)

            if not grp_icon_dir_entry:
                continue

            data_rva = grp_icon_dir_entry.data.struct.OffsetToData
            size = grp_icon_dir_entry.data.struct.Size
            data = self.pe.get_memory_mapped_image()[data_rva:data_rva + size]
            file_offset = self.pe.get_offset_from_rva(data_rva)

            grp_icon_dir = pefile.Structure(self.GRPICONDIR_format, file_offset=file_offset)
            grp_icon_dir.__unpack__(data)

            if grp_icon_dir.Reserved != 0 or grp_icon_dir.Type != self.RES_ICON:
                continue
            offset = grp_icon_dir.sizeof()

            entries = list()
            for idx in range(0, grp_icon_dir.Count):
                grp_icon = pefile.Structure(self.GRPICONDIRENTRY_format, file_offset=file_offset + offset)
                grp_icon.__unpack__(data[offset:])
                offset += grp_icon.sizeof()
                entries.append(grp_icon)

            groups.append(entries)
        return groups

    def _get_icon(self, index):
        icon_entry = self._find_resource('RT_ICON', -index)
        if not icon_entry:
            return None

        data_rva = icon_entry.data.struct.OffsetToData
        size = icon_entry.data.struct.Size
        data = self.pe.get_memory_mapped_image()[data_rva:data_rva + size]

        return data

    def _export_raw(self, entries=None, index=None):
        if not entries:
            # just get the first group
            for entries in self._get_group_icons():
                if entries:
                    break
            else:
                return None

        if index is not None:
            entries = entries[index:index + 1]

        ico = struct.pack('<HHH', 0, self.RES_ICON, len(entries))
        data_offset = None
        data = []
        info = []
        for grp_icon in entries:
            if data_offset is None:
                data_offset = len(ico) + ((grp_icon.sizeof() + 2) * len(entries))

            nfo = grp_icon.__pack__()[:-2] + struct.pack('<L', data_offset)
            info.append(nfo)

            raw_data = self._get_icon(grp_icon.ID)
            if not raw_data:
                continue

            data.append(raw_data)
            data_offset += len(raw_data)

        return ico + b"".join(info) + b"".join(data)

    def get_icon(self, out_format='PNG', **format_kwargs):
        raw = self._export_raw()
        if not raw:
            return None

        img = Image.open(io.BytesIO(raw)).convert('RGBA')

        out = io.BytesIO()
        img.save(out, format=out_format, **format_kwargs)
        return out.getvalue()

    def close(self):
        self.pe.close()
