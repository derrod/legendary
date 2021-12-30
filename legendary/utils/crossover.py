import logging
import plistlib
import os
import subprocess

logger = logging.getLogger('CXHelpers')

# all the empty folders found in a freshly created bottle that we will need to create
EMPTY_BOTTLE_DIRECTORIES = [
    'Program Files/Common Files/Microsoft Shared/TextConv',
    'ProgramData/Microsoft/Windows/Start Menu/Programs/Administrative Tools',
    'ProgramData/Microsoft/Windows/Start Menu/Programs/StartUp',
    'ProgramData/Microsoft/Windows/Templates',
    'users/crossover/AppData/LocalLow',
    'users/crossover/Application Data/Microsoft/Windows/Themes',
    'users/crossover/Contacts',
    'users/crossover/Cookies',
    'users/crossover/Desktop',
    'users/crossover/Favorites',
    'users/crossover/Links',
    'users/crossover/Local Settings/Application Data/Microsoft',
    'users/crossover/Local Settings/History',
    'users/crossover/Local Settings/Temporary Internet Files',
    'users/crossover/NetHood',
    'users/crossover/PrintHood',
    'users/crossover/Recent',
    'users/crossover/Saved Games',
    'users/crossover/Searches',
    'users/crossover/SendTo',
    'users/crossover/Start Menu/Programs/Administrative Tools',
    'users/crossover/Start Menu/Programs/StartUp',
    'users/crossover/Temp',
    'users/Public/Desktop',
    'users/Public/Documents',
    'users/Public/Favorites',
    'users/Public/Music',
    'users/Public/Pictures',
    'users/Public/Videos',
    'windows/Fonts',
    'windows/help',
    'windows/logs',
    'windows/Microsoft.NET/DirectX for Managed Code',
    'windows/system32/mui',
    'windows/system32/spool/printers',
    'windows/system32/tasks',
    'windows/syswow64/drivers',
    'windows/syswow64/mui',
    'windows/tasks',
    'windows/temp'
]


def mac_get_crossover_version(app_path):
    try:
        plist = plistlib.load(open(os.path.join(app_path, 'Contents', 'Info.plist'), 'rb'))
        return plist['CFBundleShortVersionString']
    except Exception as e:
        logger.debug(f'Failed to load plist for "{app_path}" with {e!r}')
        return None


def mac_find_crossover_apps():
    paths = ['/Applications/CrossOver.app']
    try:
        out = subprocess.check_output(['mdfind', 'kMDItemCFBundleIdentifier="com.codeweavers.CrossOver"'])
        paths.extend(out.decode('utf-8', 'replace').strip().split('\n'))
    except Exception as e:
        logger.warning(f'Trying to find CrossOver installs via mdfind failed: {e!r}')

    valid = [p for p in paths if os.path.exists(os.path.join(p, 'Contents', 'Info.plist'))]
    found_tuples = set()

    for path in valid:
        version = mac_get_crossover_version(path)
        if not version:
            continue
        logger.debug(f'Found Crossover {version} at "{path}"')
        found_tuples.add((version, path))

    return sorted(found_tuples, reverse=True)


def mac_get_crossover_bottles():
    bottles_path = os.path.expanduser('~/Library/Application Support/CrossOver/Bottles')
    if not os.path.exists(bottles_path):
        return []
    return sorted(p for p in os.listdir(bottles_path) if
                  os.path.isdir(os.path.join(bottles_path, p)) and
                  os.path.exists(os.path.join(bottles_path, p, 'cxbottle.conf')))


def mac_is_valid_bottle(bottle_name):
    bottles_path = os.path.expanduser('~/Library/Application Support/CrossOver/Bottles')
    return os.path.exists(os.path.join(bottles_path, bottle_name, 'cxbottle.conf'))


def mac_is_crossover_running():
    try:
        out = subprocess.check_output(['launchctl', 'list'])
        return b'com.codeweavers.CrossOver' in out
    except Exception as e:
        logger.warning(f'Getting list of running application bundles failed: {e!r}')
        return True  # assume the worst
