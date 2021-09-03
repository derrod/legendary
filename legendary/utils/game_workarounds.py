# coding: utf-8

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


def is_opt_enabled(app_name, version):
    if (versions := _optimize_default.get(app_name.lower())) is not None:
        if version in versions or not versions:
            return True
    return False


def update_workarounds(api_data):
    if 'reorder_optimization' in api_data:
        _optimize_default.clear()
        _optimize_default.update(api_data['reorder_optimization'])

