import logging
import plistlib
import os
import subprocess

_logger = logging.getLogger('CXHelpers')


def mac_get_crossover_version(app_path):
    try:
        plist = plistlib.load(open(os.path.join(app_path, 'Contents', 'Info.plist'), 'rb'))
        return plist['CFBundleShortVersionString']
    except Exception as e:
        _logger.debug(f'Failed to load plist for "{app_path}" with {e!r}')
        return None


def mac_find_crossover_apps():
    paths = ['/Applications/CrossOver.app']
    try:
        out = subprocess.check_output(['mdfind', 'kMDItemCFBundleIdentifier="com.codeweavers.CrossOver"'])
        paths.extend(out.decode('utf-8', 'replace').strip().split('\n'))
    except Exception as e:
        _logger.warning(f'Trying to find CrossOver installs via mdfind failed: {e!r}')

    valid = [p for p in paths if os.path.exists(os.path.join(p, 'Contents', 'Info.plist'))]
    found_tuples = set()

    for path in valid:
        version = mac_get_crossover_version(path)
        if not version:
            continue
        _logger.debug(f'Found Crossover {version} at "{path}"')
        found_tuples.add((version, path))

    return sorted(found_tuples, reverse=True)


def mac_get_crossover_bottles():
    bottles_path = os.path.expanduser('~/Library/Application Support/CrossOver/Bottles')
    if not os.path.exists(bottles_path):
        return []
    return sorted(p for p in os.listdir(bottles_path) if mac_is_valid_bottle(p))


def mac_is_valid_bottle(bottle_name):
    bottles_path = os.path.expanduser('~/Library/Application Support/CrossOver/Bottles')
    return os.path.exists(os.path.join(bottles_path, bottle_name, 'cxbottle.conf'))


def mac_get_bottle_path(bottle_name):
    bottles_path = os.path.expanduser('~/Library/Application Support/CrossOver/Bottles')
    return os.path.join(bottles_path, bottle_name)


def mac_is_crossover_running():
    try:
        out = subprocess.check_output(['launchctl', 'list'])
        return b'com.codeweavers.CrossOver.' in out
    except Exception as e:
        _logger.warning(f'Getting list of running application bundles failed: {e!r}')
        return True  # assume the worst
