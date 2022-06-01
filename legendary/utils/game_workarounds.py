# coding: utf-8

from sys import platform

# games where the download order optimizations are enabled by default
# a set() of versions can be specified, empty set means all versions.
_optimize_default = {
    'wombat': {},  # world war z
    'snapdragon': {},  # metro exodus
    'honeycreeper': {},  # diabotical
    'bcc75c246fe04e45b0c1f1c3fd52503a': {  # pillars of eternity
        '1.0.2'  # problematic version
    }
}

# Some games use launchers that don't work with Legendary, these are overriden here
_exe_overrides = {
    'kinglet':  {
        'darwin': 'Base/Binaries/Win64EOS/CivilizationVI.exe',
        'linux': 'Base/Binaries/Win64EOS/CivilizationVI.exe',
        'win32': 'LaunchPad/LaunchPad.exe'
    }
}


def is_opt_enabled(app_name, version):
    if (versions := _optimize_default.get(app_name.lower())) is not None:
        if version in versions or not versions:
            return True
    return False


def get_exe_override(app_name):
    return _exe_overrides.get(app_name.lower(), {}).get(platform, None)


def update_workarounds(api_data):
    if 'reorder_optimization' in api_data:
        _optimize_default.clear()
        _optimize_default.update(api_data['reorder_optimization'])
    if 'executable_override' in api_data:
        _exe_overrides.clear()
        _exe_overrides.update(api_data['executable_override'])

