# coding: utf-8

# games where the download order optimizations are enabled by default
_optimize_default = {
    'wombat'
}


def is_opt_enabled(app_name):
    return app_name.lower() in _optimize_default
