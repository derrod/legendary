import os
import logging

from legendary.models.game import Game

if os.name == 'nt':
    from legendary.utils.windows_helpers import (
        query_registry_value, list_registry_values,
        remove_registry_value, set_registry_value,
        HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE,
        TYPE_DWORD, TYPE_STRING
    )

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
    else:
        raise NotImplementedError


def add_registry_entries(overlay_path, prefix=None):
    if os.name == 'nt':
        set_registry_value(HKEY_CURRENT_USER, EOS_OVERLAY_KEY, EOS_OVERLAY_VALUE,
                           overlay_path.replace('\\', '/'), TYPE_STRING)
        vk_32_path = os.path.join(overlay_path, 'EOSOverlayVkLayer-Win32.json').replace('/', '\\')
        vk_64_path = os.path.join(overlay_path, 'EOSOverlayVkLayer-Win64.json').replace('/', '\\')
        # the launcher only sets those in HKCU, th e service sets them in HKLM,
        # but it's not in use yet, so just do HKCU for now
        set_registry_value(HKEY_CURRENT_USER, VULKAN_OVERLAY_KEY, vk_32_path, 0, TYPE_DWORD)
        set_registry_value(HKEY_CURRENT_USER, VULKAN_OVERLAY_KEY, vk_64_path, 0, TYPE_DWORD)
    else:
        raise NotImplementedError


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
    else:
        raise NotImplementedError
