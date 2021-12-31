import logging
import winreg

_logger = logging.getLogger('WindowsHelpers')

HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
TYPE_STRING = winreg.REG_SZ
TYPE_DWORD = winreg.REG_DWORD


def query_registry_value(hive, key, value):
    ret = None
    try:
        k = winreg.OpenKey(hive, key, reserved=0, access=winreg.KEY_READ)
    except FileNotFoundError:
        _logger.debug(f'Registry key "{key}" not found')
    else:
        try:
            ret, _ = winreg.QueryValueEx(k, value)
        except FileNotFoundError:
            _logger.debug(f'Registry value "{key}":"{value}" not found')
        winreg.CloseKey(k)

    return ret


def list_registry_values(hive, key, use_32bit_view=False):
    ret = []

    access = winreg.KEY_READ
    if use_32bit_view:
        access |= winreg.KEY_WOW64_32KEY

    try:
        k = winreg.OpenKey(hive, key, reserved=0, access=access)
    except FileNotFoundError:
        _logger.debug(f'Registry key "{key}" not found')
    else:
        idx = 0
        while True:
            try:
                ret.append(winreg.EnumValue(k, idx))
            except OSError:
                break
            idx += 1

    return ret


def remove_registry_value(hive, key, value, use_32bit_view=False):
    access = winreg.KEY_ALL_ACCESS
    if use_32bit_view:
        access |= winreg.KEY_WOW64_32KEY

    try:
        k = winreg.OpenKey(hive, key, reserved=0, access=access)
    except FileNotFoundError:
        _logger.debug(f'Registry key "{key}" not found')
    else:
        try:
            winreg.DeleteValue(k, value)
        except Exception as e:
            _logger.debug(f'Deleting "{key}":"{value}" failed with {repr(e)}')
        winreg.CloseKey(k)


def set_registry_value(hive, key, value, data, reg_type=winreg.REG_SZ, use_32bit_view=False):
    access = winreg.KEY_ALL_ACCESS
    if use_32bit_view:
        access |= winreg.KEY_WOW64_32KEY

    try:
        k = winreg.CreateKeyEx(hive, key, reserved=0, access=access)
    except Exception as e:
        _logger.debug(f'Failed creating/opening registry key "{key}" with {repr(e)}')
    else:
        try:
            winreg.SetValueEx(k, value, 0, reg_type, data)
        except Exception as e:
            _logger.debug(f'Setting "{key}":"{value}" to "{data}" failed with {repr(e)}')
        winreg.CloseKey(k)
