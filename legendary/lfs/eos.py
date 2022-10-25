import os
import logging

from legendary.models.game import Game

if os.name == 'nt':
    from legendary.lfs.windows_helpers import *

logger = logging.getLogger('EOSUtils')
# Dummy Game objects to use with Core methods that expect them
# Overlay
EOSOverlayApp = Game(app_name='98bc04bc842e4906993fd6d6644ffb8d',
                     app_title='Epic Online Services Overlay',
                     metadata=dict(namespace='302e5ede476149b1bc3e4fe6ae45e50e',
                                   id='cc15684f44d849e89e9bf4cec0508b68'))
# EOS Windows service
EOSHApp = Game(app_name='c9e2eb9993a1496c99dc529b49a07339',
               app_title='Epic Online Services Helper (EOSH)',
               metadata=dict(namespace='302e5ede476149b1bc3e4fe6ae45e50e',
                             id='1108a9c0af47438da91331753b22ea21'))

EOS_OVERLAY_KEY = r'SOFTWARE\Epic Games\EOS'
WINE_EOS_OVERLAY_KEY = EOS_OVERLAY_KEY.replace('\\', '\\\\')
EOS_OVERLAY_VALUE = 'OverlayPath'
VULKAN_OVERLAY_KEY = r'SOFTWARE\Khronos\Vulkan\ImplicitLayers'


def query_registry_entries(prefix=None):
    if os.name == 'nt':
        # Overlay location for the EOS SDK to load
        overlay_path = query_registry_value(HKEY_CURRENT_USER, EOS_OVERLAY_KEY, EOS_OVERLAY_VALUE)
        # Vulkan Layers
        # HKCU
        vulkan_hkcu = [i[0] for i in
                       list_registry_values(HKEY_CURRENT_USER, VULKAN_OVERLAY_KEY)
                       if 'EOS' in i[0]]
        # HKLM 64 & 32 bit
        vulkan_hklm = [i[0] for i in
                       list_registry_values(HKEY_LOCAL_MACHINE, VULKAN_OVERLAY_KEY)
                       if 'EOS' in i[0]]
        vulkan_hklm += [i[0] for i in
                        list_registry_values(HKEY_LOCAL_MACHINE, VULKAN_OVERLAY_KEY, use_32bit_view=True)
                        if 'EOS' in i[0]]

        return dict(overlay_path=overlay_path,
                    vulkan_hkcu=vulkan_hkcu,
                    vulkan_hklm=vulkan_hklm)
    elif prefix:
        # Only read HKCU since we don't really care for the Vulkan stuff (doesn't work in WINE)
        use_reg_file = os.path.join(prefix, 'user.reg')
        if not os.path.exists(use_reg_file):
            raise ValueError('No user.reg file, invalid path')

        reg_lines = open(use_reg_file, 'r', encoding='utf-8').readlines()
        for line in reg_lines:
            if EOS_OVERLAY_VALUE in line:
                overlay_path = line.partition('=')[2].strip().strip('"')
                break
        else:
            overlay_path = None

        if overlay_path:
            if overlay_path.startswith('C:'):
                overlay_path = os.path.join(prefix, 'drive_c', overlay_path[3:])
            elif overlay_path.startswith('Z:'):
                overlay_path = overlay_path[2:]

        return dict(overlay_path=overlay_path,
                    vulkan_hkcu=list(),
                    vulkan_hklm=list())
    else:
        raise ValueError('No prefix specified on non-Windows platform')


def add_registry_entries(overlay_path, prefix=None):
    if os.name == 'nt':
        logger.debug(f'Settings HKCU EOS Overlay Path: {overlay_path}')
        set_registry_value(HKEY_CURRENT_USER, EOS_OVERLAY_KEY, EOS_OVERLAY_VALUE,
                           overlay_path.replace('\\', '/'), TYPE_STRING)
        vk_32_path = os.path.join(overlay_path, 'EOSOverlayVkLayer-Win32.json').replace('/', '\\')
        vk_64_path = os.path.join(overlay_path, 'EOSOverlayVkLayer-Win64.json').replace('/', '\\')
        # the launcher only sets those in HKCU, th e service sets them in HKLM,
        # but it's not in use yet, so just do HKCU for now
        logger.debug(f'Settings HKCU 32-bit Vulkan Layer: {vk_32_path}')
        set_registry_value(HKEY_CURRENT_USER, VULKAN_OVERLAY_KEY, vk_32_path, 0, TYPE_DWORD)
        logger.debug(f'Settings HKCU 64-bit Vulkan Layer: {vk_32_path}')
        set_registry_value(HKEY_CURRENT_USER, VULKAN_OVERLAY_KEY, vk_64_path, 0, TYPE_DWORD)
    elif prefix:
        # Again only care for HKCU OverlayPath because Windows Vulkan layers don't work anyway
        use_reg_file = os.path.join(prefix, 'user.reg')
        if not os.path.exists(use_reg_file):
            raise ValueError('No user.reg file, invalid path')

        reg_lines = open(use_reg_file, 'r', encoding='utf-8').readlines()

        overlay_path = overlay_path.replace('\\', '/')
        if overlay_path.startswith('/'):
            overlay_path = f'Z:{overlay_path}'

        overlay_line = f'"{EOS_OVERLAY_VALUE}"="{overlay_path}"\n'
        overlay_idx = None
        section_idx = None

        for idx, line in enumerate(reg_lines):
            if EOS_OVERLAY_VALUE in line:
                reg_lines[idx] = overlay_line
                break
            elif WINE_EOS_OVERLAY_KEY in line:
                section_idx = idx
        else:
            if section_idx:
                reg_lines.insert(section_idx + 1, overlay_line)
            else:
                reg_lines.append(f'[{WINE_EOS_OVERLAY_KEY}]\n')
                reg_lines.append(overlay_line)

        open(use_reg_file, 'w', encoding='utf-8').writelines(reg_lines)
    else:
        raise ValueError('No prefix specified on non-Windows platform')


def remove_registry_entries(prefix=None):
    entries = query_registry_entries(prefix)

    if os.name == 'nt':
        if entries['overlay_path']:
            logger.debug('Removing HKCU EOS OverlayPath')
            remove_registry_value(HKEY_CURRENT_USER, EOS_OVERLAY_KEY, EOS_OVERLAY_VALUE)
        for value in entries['vulkan_hkcu']:
            logger.debug(f'Removing HKCU Vulkan Layer: {value}')
            remove_registry_value(HKEY_CURRENT_USER, VULKAN_OVERLAY_KEY, value)
        for value in entries['vulkan_hklm']:
            logger.debug(f'Removing HKLM Vulkan Layer: {value}')
            remove_registry_value(HKEY_LOCAL_MACHINE, VULKAN_OVERLAY_KEY, value)
            remove_registry_value(HKEY_LOCAL_MACHINE, VULKAN_OVERLAY_KEY, value, use_32bit_view=True)
    elif prefix:
        # Same as above, only HKCU.
        use_reg_file = os.path.join(prefix, 'user.reg')
        if not os.path.exists(use_reg_file):
            raise ValueError('No user.reg file, invalid path')

        if entries['overlay_path']:
            reg_lines = open(use_reg_file, 'r', encoding='utf-8').readlines()
            filtered_lines = [line for line in reg_lines if EOS_OVERLAY_VALUE not in line]
            open(use_reg_file, 'w', encoding='utf-8').writelines(filtered_lines)
    else:
        raise ValueError('No prefix specified on non-Windows platform')
