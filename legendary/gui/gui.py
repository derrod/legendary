#!/usr/bin/env python3

import gi
import webbrowser
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import legendary.core
core = legendary.core.LegendaryCore()

def log_gtk(msg):
    dialog = Gtk.Dialog(title="Legendary Log")
    dialog.log = Gtk.Label(label=msg)
    dialog.log.set_selectable(True)
    box = dialog.get_content_area()
    box.add(dialog.log)
    dialog.show_all()

def is_installed(app_name):
    if core.get_installed_game(app_name) == None:
        return "No"
    else:
        return "Yes"

def installed_size(app_name):
    g = core.get_installed_game(app_name)
    if g == None:
        return ""
    else:
        return f"{g.install_size / (1024*1024*1024):.02f} GiB"

def update_avail(app_name):
    print_version = False # temporary, this will be in the config
    g = core.get_installed_game(app_name)
    if g != None:
        try:
            version = core.get_asset(app_name).build_version
        except ValueError:
            log_gtk(f'Metadata for "{game.app_name}" is missing, the game may have been removed from '
                           f'your account or not be in legendary\'s database yet, try rerunning the command '
                           f'with "--check-updates".')
        if version != g.version:
            if print_version: # for future config
                return f"Yes (Old: {g.version}; New: {version})"
            else:
                return f"Yes"
        else:
            return "No"
    else:
        return ""

def install_gtk(app_name, app_title, parent):
    install_dialog = Gtk.MessageDialog( parent=parent,
                                        destroy_with_parent=True,
                                        message_type=Gtk.MessageType.QUESTION,
                                        buttons=Gtk.ButtonsType.OK_CANCEL,
                                        text=f"Install {app_title} (Leave entries blank to use the default)"
                                      )
    install_dialog.set_title(f"Install {app_title}")
    install_dialog.set_default_size(400, 0)
 #   install_dialog.remove(install_dialog.get_content_area())

    vbox = install_dialog.get_content_area()
    #box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

    # advanced options declaration
    show_advanced = False
    show_advanced_check_button = Gtk.CheckButton(label="Show advanced options")
    vbox.add(show_advanced_check_button)
    advanced_options = Gtk.VBox(spacing=5)

    # --base-path <path>
    base_path_box = Gtk.HBox()
    base_path_label = Gtk.Label(label="Base Path")
    base_path_entry = Gtk.Entry()
    base_path_box.pack_start(base_path_label, False, False, 10)
    base_path_box.pack_start(base_path_entry, True, True, 0)
    vbox.add(base_path_box)

    # --game-folder <path>
    game_folder_box = Gtk.HBox()
    game_folder_label = Gtk.Label(label="Game Folder")
    game_folder_entry = Gtk.Entry()
    game_folder_box.pack_start(game_folder_label, False, False, 10)
    game_folder_box.pack_start(game_folder_entry, True, True, 0)
    vbox.add(game_folder_box)

    # --max-shared-memory <size> (in MiB)
    max_shm_box = Gtk.HBox()
    max_shm_label = Gtk.Label(label="Max Shared Memory")
    max_shm_entry = Gtk.Entry()
    max_shm_box.pack_start(game_folder_label, False, False, 10)
    max_shm_box.pack_start(game_folder_entry, True, True, 0)
    advanced_options.add(max_shm_box)

    # --max-workers <num>
    max_workers_box = Gtk.HBox()
    max_workers_label = Gtk.Label(label="Max Workers")
    max_workers_entry = Gtk.Entry()
    max_workers_box.pack_start(max_workers_label, False, False, 10)
    max_workers_box.pack_start(max_workers_entry, True, True, 0)
    advanced_options.add(max_workers_box)

    # --manifest <uri>
    override_manifest_box = Gtk.HBox()
    override_manifest_label = Gtk.Label(label="Manifest")
    override_manifest_entry = Gtk.Entry()
    override_manifest_box.pack_start(override_manifest_label, False, False, 10)
    override_manifest_box.pack_start(override_manifest_entry, True, True, 0)
    advanced_options.add(override_manifest_box)

    # --old-manifest <uri>
    override_old_manifest_box = Gtk.HBox()
    override_old_manifest_label = Gtk.Label(label="Old Manifest")
    override_old_manifest_entry = Gtk.Entry()
    override_old_manifest_box.pack_start(override_old_manifest_label, False, False, 10)
    override_old_manifest_box.pack_start(override_old_manifest_entry, True, True, 0)
    advanced_options.add(override_old_manifest_box)

    # --delta-manifest <uri>
    override_delta_manifest_box = Gtk.HBox()
    override_delta_manifest_label = Gtk.Label(label="Delta Manifest")
    override_delta_manifest_entry = Gtk.Entry()
    override_delta_manifest_box.pack_start(override_delta_manifest_label, False, False, 10)
    override_delta_manifest_box.pack_start(override_delta_manifest_entry, True, True, 0)
    advanced_options.add(override_delta_manifest_box)

    # --base-url <url>
    override_base_url_box = Gtk.HBox()
    override_base_url_label = Gtk.Label(label="Base Url")
    override_base_url_entry = Gtk.Entry()
    override_base_url_box.pack_start(override_base_url_label, False, False, 10)
    override_base_url_box.pack_start(override_base_url_entry, True, True, 0)
    advanced_options.add(override_base_url_box)

    # --force
    force = False
    force_check_button = Gtk.CheckButton(label="Force install")
    def force_button_toggled(button, name):
        if button.get_active():
            force = False
        else:
            force = True
        print(name, "is now", force)
    force_check_button.connect("toggled", force_button_toggled, "force")
    advanced_options.add(force_check_button)

    # --disable-patching
    disable_patching = False
    disable_patching_check_button = Gtk.CheckButton(label="Disable patching")
    def disable_patching_button_toggled(button, name):
        if button.get_active():
            disable_patching = False
        else:
            disable_patching = True
        print(name, " is now ", state)
    disable_patching_check_button.connect("toggled", disable_patching_button_toggled, "disable_patching")
    advanced_options.add(disable_patching_check_button)

    # --download-only, --no-install
    download_only = False
    download_only_check_button = Gtk.CheckButton(label="Download only")
    def download_only_button_toggled(button, name):
        if button.get_active():
            download_only = False
        else:
            download_only = True
        print(name, "is now", download_only)
    download_only_check_button.connect("toggled", download_only_button_toggled, "download_only")
    advanced_options.add(download_only_check_button)

    # --update-only
    update_only = False
    update_only_check_button = Gtk.CheckButton(label="Update only")
    def update_only_button_toggled(button, name):
        if button.get_active():
            update_only = False
        else:
            update_only = True
        print(name, "is now", update_only)
    update_only_check_button.connect("toggled", update_only_button_toggled, "update_only")
    advanced_options.add(update_only_check_button)

    # --dlm-debug
    glm_debug = False
    glm_debug_check_button = Gtk.CheckButton(label="Downloader debug messages")
    def glm_debug_button_toggled(button, name):
        if button.get_active():
            glm_debug = False
        else:
            glm_debug = True
        print(name, "is now", glm_debug)
    glm_debug_check_button.connect("toggled", glm_debug_button_toggled, "glm_debug")
    advanced_options.add(glm_debug_check_button)
    
	# --platform <Platform>
    platform_override_box = Gtk.HBox()
    platform_override_label = Gtk.Label(label="Platform")
    platform_override_entry = Gtk.Entry()
    platform_override_box.pack_start(platform_override_label, False, False, 10)
    platform_override_box.pack_start(platform_override_entry, True, True, 0)
    advanced_options.add(platform_override_box)
    
	# --prefix <prefix>
    file_prefix_filter_box = Gtk.HBox()
    file_prefix_filter_label = Gtk.Label(label="File prefix filter")
    file_prefix_filter_entry = Gtk.Entry()
    file_prefix_filter_box.pack_start(file_prefix_filter_label, False, False, 10)
    file_prefix_filter_box.pack_start(file_prefix_filter_entry, True, True, 0)
    advanced_options.add(file_prefix_filter_box)
    
	# --exclude <prefix>
    file_exclude_filter_box = Gtk.HBox()
    file_exclude_filter_label = Gtk.Label(label="File exclude filter")
    file_exclude_filter_entry = Gtk.Entry()
    file_exclude_filter_box.pack_start(file_exclude_filter_label, False, False, 10)
    file_exclude_filter_box.pack_start(file_exclude_filter_entry, True, True, 0)
    advanced_options.add(file_exclude_filter_box)
    
	# --install-tag <tag>
    file_install_tag_box = Gtk.HBox()
    file_install_tag_label = Gtk.Label(label="Install tag")
    file_install_tag_entry = Gtk.Entry()
    file_install_tag_box.pack_start(file_install_tag_label, False, False, 10)
    file_install_tag_box.pack_start(file_install_tag_entry, True, True, 0)
    advanced_options.add(file_install_tag_box)
    
	# --enable-reordering
    enable_reordering = False
    enable_reordering_check_button = Gtk.CheckButton(label="Enable reordering optimization")
    def enable_reordering_button_toggled(button, name):
        if button.get_active():
            enable_reordering = False
        else:
            enable_reordering = True
        print(name, "is now", enable_reordering)
    enable_reordering_check_button.connect("toggled", enable_reordering_button_toggled, "enable_reordering")
    advanced_options.add(enable_reordering_check_button)
    
	# --dl-timeout <sec>
    dl_timeout_box = Gtk.HBox()
    dl_timeout_label = Gtk.Label(label="Downloader timeout")
    dl_timeout_entry = Gtk.Entry()
    dl_timeout_box.pack_start(dl_timeout_label, False, False, 10)
    dl_timeout_box.pack_start(dl_timeout_entry, True, True, 0)
    advanced_options.add(dl_timeout_box)
    
	# --save-path <path>
    save_path_box = Gtk.HBox()
    save_path_label = Gtk.Label(label="Save path")
    save_path_entry = Gtk.Entry()
    save_path_box.pack_start(save_path_label, False, False, 10)
    save_path_box.pack_start(save_path_entry, True, True, 0)
    advanced_options.add(save_path_box)
    
	# --repair
    repair = False
    repair_check_button = Gtk.CheckButton(label="Repair")
    def repair_button_toggled(button, name):
        if button.get_active():
            repair = False
        else:
            repair = True
        print(name, "is now", repair)
    repair_check_button.connect("toggled", repair_button_toggled, "repair")
    advanced_options.add(repair_check_button)
    
	# --repair-and-update
    repair_and_update = False # or repair_use_latest
    repair_and_update_check_button = Gtk.CheckButton(label="Repair and Update")
    def repair_and_update_button_toggled(button, name):
        if button.get_active():
            repair_and_update = False
        else:
            repair_and_update = True
        print(name, "is now", repair_and_update)
    repair_and_update_check_button.connect("toggled", repair_and_update_button_toggled, "repair_and_update")
    advanced_options.add(repair_and_update_check_button)
    
	# --ignore-free-space
    ignore_space_req = False
    ignore_space_req_check_button = Gtk.CheckButton(label="Ignore space requirements")
    def ignore_space_req_button_toggled(button, name):
        if button.get_active():
            ignore_space_req = False
        else:
            ignore_space_req = True
        print(name, "is now", ignore_space_req)
    ignore_space_req_check_button.connect("toggled", ignore_space_req_button_toggled, "ignore_space_req")
    advanced_options.add(ignore_space_req_check_button)
    
	# --disable-delta-manifests
    override_delta_manifest = False
    override_delta_manifest_check_button = Gtk.CheckButton(label="Disable delta manifests")
    def override_delta_manifest_button_toggled(button, name):
        if button.get_active():
            override_delta_manifest = False
        else:
            override_delta_manifest = True
        print(name, "is now", override_delta_manifest)
    override_delta_manifest_check_button.connect("toggled", override_delta_manifest_button_toggled, "override_delta_manifest")
    advanced_options.add(override_delta_manifest_check_button)
    
	# --reset-sdl
    reset_sdl = False
    reset_sdl_check_button = Gtk.CheckButton(label="Reset selective downloading choices")
    def reset_sdl_button_toggled(button, name):
        if button.get_active():
            reset_sdl = False
        else:
            reset_sdl = True
        print(name, "is now", reset_sdl)
    reset_sdl_check_button.connect("toggled", reset_sdl_button_toggled, "reset_sdl")
    advanced_options.add(reset_sdl_check_button)


    vbox.add(advanced_options)
    # advanced_options function
    def show_advanced_button_toggled(button, name):
        if button.get_active():
            show_advanced = True
            advanced_options.show()
        else:
            show_advanced = False
            #vbox.remove(advanced_options)
            advanced_options.hide()
        install_dialog.resize(400,5)
        print(name, "is now", show_advanced)
    show_advanced_check_button.connect("toggled", show_advanced_button_toggled, "show_advanced")

    vbox.show()
    install_dialog.show()
    #advanced_options.hide()
    #install_dialog.resize(400,5)

    response = install_dialog.run()
    base_path = base_path_entry.get_text()
    game_folder = game_folder_entry.get_text()
    max_shm = max_shm_entry.get_text()
    max_workers = max_workers_entry.get_text()
    override_manifest = override_manifest_entry.get_text()
    override_old_manifest = override_old_manifest_entry.get_text()
    override_delta_manifest = override_delta_manifest_entry.get_text()
    override_base_url = override_base_url_entry.get_text()
    platform_override = platform_override_entry.get_text()
    file_prefix_filter = file_prefix_filter_entry.get_text()
    file_exclude_filter = file_exclude_filter_entry.get_text()
    file_install_tag = file_install_tag_entry.get_text()
    dl_timeout = dl_timeout_entry.get_text()
    save_path = save_path_entry.get_text()
    install_dialog.destroy()
    print(base_path)
    return 1


    # TODO:
    if response != Gtk.ResponseType.OK:
        return 1

    if core.is_installed(app_name):
        igame = core.get_installed_game(app_name)
        if igame.needs_verification:
            repair_mode = True
    repair_file = None
    if repair_mode:
        args.no_install = args.repair_and_update is False
        repair_file = os.path.join(self.core.lgd.get_tmp_path(), f'{args.app_name}.repair')

    if not self.core.login():
        logger.error('Login failed! Cannot continue with download process.')
        exit(1)

    if args.file_prefix or args.file_exclude_prefix or args.install_tag:
        args.no_install = True

    if args.update_only:
        if not self.core.is_installed(args.app_name):
            logger.error(f'Update requested for "{args.app_name}", but app not installed!')
            exit(1)

    if args.platform_override:
        args.no_install = True

    game = self.core.get_game(args.app_name, update_meta=True)

    if not game:
        logger.error(f'Could not find "{args.app_name}" in list of available games,'
                     f'did you type the name correctly?')
        exit(1)

    if game.is_dlc:
        logger.info('Install candidate is DLC')
        app_name = game.metadata['mainGameItem']['releaseInfo'][0]['appId']
        base_game = self.core.get_game(app_name)
        # check if base_game is actually installed
        if not self.core.is_installed(app_name):
            # download mode doesn't care about whether or not something's installed
            if not args.no_install:
                logger.fatal(f'Base game "{app_name}" is not installed!')
                exit(1)
    else:
        base_game = None

    if args.repair_mode:
        if not self.core.is_installed(game.app_name):
            logger.error(f'Game "{game.app_title}" ({game.app_name}) is not installed!')
            exit(0)

        if not os.path.exists(repair_file):
            logger.info('Game has not been verified yet.')
            if not args.yes:
                if not get_boolean_choice(f'Verify "{game.app_name}" now ("no" will abort repair)?'):
                    print('Aborting...')
                    exit(0)

            self.verify_game(args, print_command=False)
        else:
            logger.info(f'Using existing repair file: {repair_file}')

    # Workaround for Cyberpunk 2077 preload
    if not args.install_tag and not game.is_dlc and ((sdl_name := get_sdl_appname(game.app_name)) is not None):
        config_tags = self.core.lgd.config.get(game.app_name, 'install_tags', fallback=None)
        if not self.core.is_installed(game.app_name) or config_tags is None or args.reset_sdl:
            args.install_tag = sdl_prompt(sdl_name, game.app_title)
            if game.app_name not in self.core.lgd.config:
                self.core.lgd.config[game.app_name] = dict()
            self.core.lgd.config.set(game.app_name, 'install_tags', ','.join(args.install_tag))
        else:
            args.install_tag = config_tags.split(',')

    logger.info('Preparing download...')
    # todo use status queue to print progress from CLI
    # This has become a little ridiculous hasn't it?
    dlm, analysis, igame = self.core.prepare_download(game=game, base_game=base_game, base_path=args.base_path,
                                                      force=args.force, max_shm=args.shared_memory,
                                                      max_workers=args.max_workers, game_folder=args.game_folder,
                                                      disable_patching=args.disable_patching,
                                                      override_manifest=args.override_manifest,
                                                      override_old_manifest=args.override_old_manifest,
                                                      override_base_url=args.override_base_url,
                                                      platform_override=args.platform_override,
                                                      file_prefix_filter=args.file_prefix,
                                                      file_exclude_filter=args.file_exclude_prefix,
                                                      file_install_tag=args.install_tag,
                                                      dl_optimizations=args.order_opt,
                                                      dl_timeout=args.dl_timeout,
                                                      repair=args.repair_mode,
                                                      repair_use_latest=args.repair_and_update,
                                                      disable_delta=args.disable_delta,
                                                      override_delta_manifest=args.override_delta_manifest)

    # game is either up to date or hasn't changed, so we have nothing to do
    if not analysis.dl_size:
        old_igame = self.core.get_installed_game(game.app_name)
        logger.info('Download size is 0, the game is either already up to date or has not changed. Exiting...')
        if old_igame and args.repair_mode and os.path.exists(repair_file):
            if old_igame.needs_verification:
                old_igame.needs_verification = False
                self.core.install_game(old_igame)

            logger.debug('Removing repair file.')
            os.remove(repair_file)

        # check if install tags have changed, if they did; try deleting files that are no longer required.
        if old_igame and old_igame.install_tags != igame.install_tags:
            old_igame.install_tags = igame.install_tags
            self.logger.info('Deleting now untagged files.')
            self.core.uninstall_tag(old_igame)
            self.core.install_game(old_igame)

        exit(0)

    logger.info(f'Install size: {analysis.install_size / 1024 / 1024:.02f} MiB')
    compression = (1 - (analysis.dl_size / analysis.uncompressed_dl_size)) * 100
    logger.info(f'Download size: {analysis.dl_size / 1024 / 1024:.02f} MiB '
                f'(Compression savings: {compression:.01f}%)')
    logger.info(f'Reusable size: {analysis.reuse_size / 1024 / 1024:.02f} MiB (chunks) / '
                f'{analysis.unchanged / 1024 / 1024:.02f} MiB (unchanged / skipped)')

    res = self.core.check_installation_conditions(analysis=analysis, install=igame, game=game,
                                                  updating=self.core.is_installed(args.app_name),
                                                  ignore_space_req=args.ignore_space)

    if res.warnings or res.failures:
        logger.info('Installation requirements check returned the following results:')

    if res.warnings:
        for warn in sorted(res.warnings):
            logger.warning(warn)

    if res.failures:
        for msg in sorted(res.failures):
            logger.fatal(msg)
        logger.error('Installation cannot proceed, exiting.')
        exit(1)

    logger.info('Downloads are resumable, you can interrupt the download with '
                'CTRL-C and resume it using the same command later on.')

    if not args.yes:
        if not get_boolean_choice(f'Do you wish to install "{igame.title}"?'):
            print('Aborting...')
            exit(0)

    start_t = time.time()

    try:
        # set up logging stuff (should be moved somewhere else later)
        dlm.logging_queue = self.logging_queue
        dlm.proc_debug = args.dlm_debug

        dlm.start()
        dlm.join()
    except Exception as e:
        end_t = time.time()
        logger.info(f'Installation failed after {end_t - start_t:.02f} seconds.')
        logger.warning(f'The following exception occurred while waiting for the downloader to finish: {e!r}. '
                       f'Try restarting the process, the resume file will be used to start where it failed. '
                       f'If it continues to fail please open an issue on GitHub.')
    else:
        end_t = time.time()
        if not args.no_install:
            # Allow setting savegame directory at install time so sync-saves will work immediately
            if game.supports_cloud_saves and args.save_path:
                igame.save_path = args.save_path

            postinstall = self.core.install_game(igame)
            if postinstall:
                self._handle_postinstall(postinstall, igame, yes=args.yes)

            dlcs = self.core.get_dlc_for_game(game.app_name)
            if dlcs:
                print('The following DLCs are available for this game:')
                for dlc in dlcs:
                    print(f' - {dlc.app_title} (App name: {dlc.app_name}, version: {dlc.app_version})')
                print('Manually installing DLCs works the same; just use the DLC app name instead.')

                install_dlcs = True
                if not args.yes:
                    if not get_boolean_choice(f'Do you wish to automatically install DLCs?'):
                        install_dlcs = False

                if install_dlcs:
                    _yes, _app_name = args.yes, args.app_name
                    args.yes = True
                    for dlc in dlcs:
                        args.app_name = dlc.app_name
                        self.install_game(args)
                    args.yes, args.app_name = _yes, _app_name

            if game.supports_cloud_saves and not game.is_dlc:
                # todo option to automatically download saves after the installation
                #  args does not have the required attributes for sync_saves in here,
                #  not sure how to solve that elegantly.
                logger.info('This game supports cloud saves, syncing is handled by the "sync-saves" command.')
                logger.info(f'To download saves for this game run "legendary sync-saves {args.app_name}"')

        old_igame = self.core.get_installed_game(game.app_name)
        if old_igame and args.repair_mode and os.path.exists(repair_file):
            if old_igame.needs_verification:
                old_igame.needs_verification = False
                self.core.install_game(old_igame)

            logger.debug('Removing repair file.')
            os.remove(repair_file)

        # check if install tags have changed, if they did; try deleting files that are no longer required.
        if old_igame and old_igame.install_tags != igame.install_tags:
            old_igame.install_tags = igame.install_tags
            self.logger.info('Deleting now untagged files.')
            self.core.uninstall_tag(old_igame)
            self.core.install_game(old_igame)

        logger.info(f'Finished installation process in {end_t - start_t:.02f} seconds.')

class main_window(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self,title="Legendary")
        #self.grid = Gtk.Grid(column_spacing=30, row_spacing=30)
        self.set_default_size(800, 600)
        self.box = Gtk.Box()
        self.add(self.box)

        logged = False
        try:
            if core.login():
                logged = True
        except ValueError: pass
        except InvalidCredentialsError:
            print("Found invalid stored credentials")

        # 'Legendary' label
        self.legendary_label = Gtk.Label(label="Legendary")
        self.login_vbox = Gtk.VBox()
        self.login_vbox.pack_start(self.legendary_label, False, False, 10)

        # Login button
        if not logged:
            self.button_login = Gtk.Button(label="Login")
            self.button_login.connect("clicked", self.onclick_login)
            self.login_vbox.pack_start(self.button_login, False, False, 10)
        else:
            self.username_label = Gtk.Label(label=core.lgd.userdata["displayName"])
            self.button_logout = Gtk.Button(label="Logout")
            self.button_logout.connect("clicked", self.onclick_logout)
            self.login_vbox.pack_end(self.button_logout, False, False, 10)
            self.login_vbox.pack_end(self.username_label, False, False, 0)

        self.box.pack_start(self.login_vbox, False, False, 20)

        # Games
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_border_width(10)
        self.scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
        self.box.pack_end(self.scroll, True, True, 0)
        self.scroll.games = Gtk.ListStore(str, str, str, str, str)
        gcols = ["appname","Title","Installed","Size","Update Avaiable"]

        if logged:
            # get games
            games, dlc_list = core.get_game_and_dlc_list()
            games = sorted(games, key=lambda x: x.app_title.lower())
            for citem_id in dlc_list.keys():
                dlc_list[citem_id] = sorted(dlc_list[citem_id], key=lambda d: d.app_title.lower())
            # add games to liststore for treeview
            for game in games:
                ls = (  game.app_name,
                        game.app_title,
                        is_installed(game.app_name),
                        installed_size(game.app_name),
                        update_avail(game.app_name),
                     )
                self.scroll.games.append(list(ls))
                #print(f' * {game.app_title} (App name: {game.app_name} | Version: {game.app_version})')
                for dlc in dlc_list[game.asset_info.catalog_item_id]:
                    ls = (  dlc.app_name,
                            dlc.app_title+f" (DLC of {game.app_title})",
                            is_installed(dlc.app_name),
                            installed_size(dlc.app_name),
                            update_avail(dlc.app_name),
                         )
                    self.scroll.games.append(list(ls))
                    #print(f'  + {dlc.app_title} (App name: {dlc.app_name} | Version: {dlc.app_version})')

            # add games to treeview
            #self.scroll.gview = Gtk.TreeView(Gtk.TreeModelSort(model=self.scroll.games))
            self.scroll.gview = Gtk.TreeView(model=self.scroll.games)
            for i, c in enumerate(gcols):
                cell = Gtk.CellRendererText()
                col = Gtk.TreeViewColumn(c, cell, text=i)
                col.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
                col.set_resizable(True)
                col.set_reorderable(True)
                col.set_sort_column_id(i)
                if c == "appname":
                    col.set_visible(False)
                self.scroll.gview.append_column(col)

            self.scroll.gview.connect("row-activated", self.on_tree_selection_changed)

            l = Gtk.Label()
            l.set_text("")
            g = Gtk.Grid()
            g.attach(self.scroll.gview, 0, 0, 1, 1)
            g.attach(l, 0, 1, 1, 1)
            self.scroll.add(g)

        
    def onclick_login(self, widget):
        webbrowser.open('https://www.epicgames.com/id/login?redirectUrl=https%3A%2F%2Fwww.epicgames.com%2Fid%2Fapi%2Fredirect')
        exchange_token = ''
        sid = ask_sid(self)
        exchange_token = core.auth_sid(sid)
        if not exchange_token:
            log_gtk('No exchange token, cannot login.')
            return
        if core.auth_code(exchange_token):
            log_gtk(f'Successfully logged in as "{core.lgd.userdata["displayName"]}"')
        else:
            log_gtk('Login attempt failed, please see log for details.')
        self.destroy()
        main()

    def onclick_logout(self, widget):
        core.lgd.invalidate_userdata()
        log_gtk("Successfully logged out")
        self.destroy()
        main()

    def on_tree_selection_changed(self, selection,b,c):
        #print(selection,b,c)
        model, treeiter = selection.get_selection().get_selected()
        if treeiter is not None:
            install_gtk(model[treeiter][0], model[treeiter][1], self)
            #print(model[treeiter][0], model[treeiter][1])

def ask_sid(parent):
    dialog = Gtk.MessageDialog(parent=parent, destroy_with_parent=True, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.OK_CANCEL)
    dialog.set_title("Enter Sid")
    #dialog.set_default_size(200, 200)

    label = Gtk.Label()
    label.set_markup("Please login via the epic web login, if web page did not open automatically, please manually open the following URL:\n<a href=\"https://www.epicgames.com/id/login?redirectUrl=https://www.epicgames.com/id/api/redirect\">https://www.epicgames.com/id/login?redirectUrl=https://www.epicgames.com/id/api/redirect</a>")
    entry = Gtk.Entry()
    box = dialog.get_content_area()
    box.pack_start(label, False, False, 0)
    box.add(entry)

    dialog.show_all()
    response = dialog.run()
    sid = entry.get_text()
    dialog.destroy()
    if response == Gtk.ResponseType.OK:
        return sid
    else:
        return 1

def main():
    win = main_window()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()

if __name__ == '__main__':
    main()
