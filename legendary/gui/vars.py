import os
from distutils.util import strtobool
class args_obj:
    # install_parser
    base_path = ''
    game_folder = ''
    shared_memory = ''
    max_workers = ''
    override_manifest = ''
    override_old_manifest = ''
    override_delta_manifest = ''
    override_base_url = ''
    force = ''
    disable_patching = ''
    no_install = ''
    update_only = ''
    dlm_debug = ''
    platform_override = ''
    file_prefix = ''
    file_exclude_prefix = ''
    install_tag = ''
    order_opt = ''
    dl_timeout = ''
    save_path = ''
    repair_mode = ''
    repair_and_update = ''
    ignore_space = ''
    disable_delta = ''
    reset_sdl = ''
    # uninstall_parser
    keep_files = False
    # launch_parser
    offline = False
    skip_version_check = False
    user_name_override = ''
    language = ''
    wrapper = os.environ.get('LGDRY_WRAPPER', None)
    set_defaults = ''
    reset_defaults = ''
    wine_bin = os.environ.get('LGDRY_WINE_BINARY', None) if os.name != 'nt' else ''
    wine_pfx = os.environ.get('LGDRY_WINE_PREFIX', None) if os.name != 'nt' else ''
    no_wine = strtobool(os.environ.get('LGDRY_NO_WINE', 'False')) if os.name != 'nt' else True
    executable_override = ''
    # list_files_parser
    force_download = ''
    #platform_override = ''
    #override_manifest = ''
    csv = ''
    tsv = ''
    json = ''
    hashlist = ''
    #install_tag = ''
