#!/usr/bin/env python
# coding: utf-8

import argparse
import csv
import logging
import os
import shlex
import subprocess
import time
import webbrowser

from distutils.util import strtobool
from getpass import getuser
from logging.handlers import QueueListener
from multiprocessing import freeze_support, Queue as MPQueue
from sys import exit, stdout

from legendary import __version__, __codename__
from legendary.core import LegendaryCore
from legendary.models.exceptions import InvalidCredentialsError
from legendary.models.game import SaveGameStatus, VerifyResult
from legendary.utils.cli import get_boolean_choice
from legendary.utils.custom_parser import AliasedSubParsersAction
from legendary.utils.lfs import validate_files

# todo custom formatter for cli logger (clean info, highlighted error/warning)
logging.basicConfig(
    format='[%(name)s] %(levelname)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('cli')


class LegendaryCLI:
    def __init__(self):
        self.core = LegendaryCore()
        self.logger = logging.getLogger('cli')
        self.logging_queue = None

    def setup_threaded_logging(self):
        self.logging_queue = MPQueue(-1)
        shandler = logging.StreamHandler()
        sformatter = logging.Formatter('[%(name)s] %(levelname)s: %(message)s')
        shandler.setFormatter(sformatter)
        ql = QueueListener(self.logging_queue, shandler)
        ql.start()
        return ql

    def auth(self, args):
        if args.auth_delete:
            self.core.lgd.invalidate_userdata()
            return

        try:
            logger.info('Testing existing login data if present...')
            if self.core.login():
                logger.info('Stored credentials are still valid, if you wish to switch to a different '
                            'account, run "legendary auth --delete" and try again.')
                return
        except ValueError:
            pass
        except InvalidCredentialsError:
            logger.error('Stored credentials were found but were no longer valid. Continuing with login...')
            self.core.lgd.invalidate_userdata()

        if args.import_egs_auth:
            # get appdata path on Linux
            if not self.core.egl.appdata_path:
                wine_pfx_users = None
                lutris_wine_users = os.path.expanduser('~/Games/epic-games-store/drive_c/users')
                if os.path.exists(lutris_wine_users):
                    logger.info(f'Found Lutris EGL WINE prefix at "{lutris_wine_users}"')
                    if args.yes or get_boolean_choice('Do you want to use the Lutris install?'):
                        wine_pfx_users = lutris_wine_users

                if not wine_pfx_users:
                    logger.info('Please enter the path to the Wine prefix that has EGL installed')
                    wine_pfx = input('Path [empty input to quit]: ').strip()
                    if not wine_pfx:
                        print('Empty input, quitting...')
                        exit(0)
                    if not os.path.exists(wine_pfx):
                        print('Path is invalid (does not exist)!')
                        exit(1)
                    wine_pfx_users = os.path.join(wine_pfx, 'drive_c/users')

                # todo instead of getuser() this should read from the user.reg in the WINE prefix
                appdata_dir = os.path.join(wine_pfx_users, getuser(),
                                           'Local Settings/Application Data/EpicGamesLauncher',
                                           'Saved/Config/Windows')
                if not os.path.exists(appdata_dir):
                    logger.error(f'Wine prefix does not have EGL appdata path at "{appdata_dir}"')
                    exit(0)
                else:
                    logger.info(f'Using EGL appdata path at "{appdata_dir}"')
                    self.core.egl.appdata_path = appdata_dir

            logger.info('Importing login session from the Epic Launcher...')
            try:
                if self.core.auth_import():
                    logger.info('Successfully imported login session from EGS!')
                    logger.info(f'Now logged in as user "{self.core.lgd.userdata["displayName"]}"')
                    return
                else:
                    logger.warning('Login session from EGS seems to no longer be valid.')
                    exit(1)
            except ValueError:
                logger.error('No EGS login session found, please login manually.')
                exit(1)

        exchange_token = ''
        if not args.auth_code and not args.session_id:
            # unfortunately the captcha stuff makes a complete CLI login flow kinda impossible right now...
            print('Please login via the epic web login!')
            webbrowser.open(
                'https://www.epicgames.com/id/login?redirectUrl=https%3A%2F%2Fwww.epicgames.com%2Fid%2Fapi%2Fredirect'
            )
            print('If web page did not open automatically, please manually open the following URL: '
                  'https://www.epicgames.com/id/login?redirectUrl=https://www.epicgames.com/id/api/redirect')
            sid = input('Please enter the "sid" value from the JSON response: ')
            sid = sid.strip().strip('"')
            exchange_token = self.core.auth_sid(sid)
        elif args.session_id:
            exchange_token = self.core.auth_sid(args.session_id)
        elif args.auth_code:
            exchange_token = args.auth_code

        if not exchange_token:
            logger.fatal('No exchange token, cannot login.')
            return

        if self.core.auth_code(exchange_token):
            logger.info(f'Successfully logged in as "{self.core.lgd.userdata["displayName"]}"')
        else:
            logger.error('Login attempt failed, please see log for details.')

    def list_games(self, args):
        logger.info('Logging in...')
        if not self.core.login():
            logger.error('Login failed, cannot continue!')
            exit(1)
        logger.info('Getting game list... (this may take a while)')
        games, dlc_list = self.core.get_game_and_dlc_list(
            platform_override=args.platform_override, skip_ue=not args.include_ue
        )
        # sort games and dlc by name
        games = sorted(games, key=lambda x: x.app_title)
        for citem_id in dlc_list.keys():
            dlc_list[citem_id] = sorted(dlc_list[citem_id], key=lambda d: d.app_title)

        if args.csv or args.tsv:
            writer = csv.writer(stdout, dialect='excel-tab' if args.tsv else 'excel')
            writer.writerow(['App name', 'App title', 'Version', 'Is DLC'])
            for game in games:
                writer.writerow((game.app_name, game.app_title, game.app_version, False))
                for dlc in dlc_list[game.asset_info.catalog_item_id]:
                    writer.writerow((dlc.app_name, dlc.app_title, dlc.app_version, True))
            return

        print('\nAvailable games:')
        for game in games:
            print(f' * {game.app_title} (App name: {game.app_name} | Version: {game.app_version})')
            for dlc in dlc_list[game.asset_info.catalog_item_id]:
                print(f'  + {dlc.app_title} (App name: {dlc.app_name} | Version: {dlc.app_version})')

        print(f'\nTotal: {len(games)}')

    def list_installed(self, args):
        if args.check_updates:
            logger.info('Logging in to check for updates...')
            if not self.core.login():
                logger.error('Login failed! Not checking for updates.')
            else:
                self.core.get_assets(True)

        games = sorted(self.core.get_installed_list(),
                       key=lambda x: x.title)

        versions = dict()
        for game in games:
            versions[game.app_name] = self.core.get_asset(game.app_name).build_version

        if args.csv or args.tsv:
            writer = csv.writer(stdout, dialect='excel-tab' if args.tsv else 'excel')
            writer.writerow(['App name', 'App title', 'Installed version', 'Available version', 'Update available'])
            writer.writerows((game.app_name, game.title, game.version, versions[game.app_name],
                              versions[game.app_name] != game.version) for game in games)
            return

        print('\nInstalled games:')
        for game in games:
            if game.install_size == 0:
                logger.debug(f'Updating missing size for {game.app_name}')
                m = self.core.load_manfiest(self.core.get_installed_manifest(game.app_name)[0])
                game.install_size = sum(fm.file_size for fm in m.file_manifest_list.elements)
                self.core.install_game(game)

            print(f' * {game.title} (App name: {game.app_name} | Version: {game.version} | '
                  f'{game.install_size / (1024*1024*1024):.02f} GiB)')
            if args.include_dir:
                print(f'  + Location: {game.install_path}')
            if versions[game.app_name] != game.version:
                print(f'  -> Update available! Installed: {game.version}, Latest: {versions[game.app_name]}')

        print(f'\nTotal: {len(games)}')

    def list_files(self, args):
        if args.platform_override:
            args.force_download = True

        if not args.override_manifest and not args.app_name:
            print('You must provide either a manifest url/path or app name!')
            return

        # check if we even need to log in
        if args.override_manifest:
            logger.info(f'Loading manifest from "{args.override_manifest}"')
            manifest_data, _ = self.core.get_uri_manfiest(args.override_manifest)
        elif self.core.is_installed(args.app_name) and not args.force_download:
            logger.info(f'Loading installed manifest for "{args.app_name}"')
            manifest_data, _ = self.core.get_installed_manifest(args.app_name)
        else:
            logger.info(f'Logging in and downloading manifest for {args.app_name}')
            if not self.core.login():
                logger.error('Login failed! Cannot continue with download process.')
                exit(1)
            game = self.core.get_game(args.app_name, update_meta=True)
            manifest_data, _ = self.core.get_cdn_manifest(game, platform_override=args.platform_override)

        manifest = self.core.load_manfiest(manifest_data)
        files = sorted(manifest.file_manifest_list.elements,
                       key=lambda a: a.filename.lower())

        if args.install_tag:
            files = [fm for fm in files if args.install_tag in fm.install_tags]

        if args.hashlist:
            for fm in files:
                print(f'{fm.hash.hex()} *{fm.filename}')
        elif args.csv or args.tsv:
            writer = csv.writer(stdout, dialect='excel-tab' if args.tsv else 'excel')
            writer.writerow(['path', 'hash', 'size', 'install_tags'])
            writer.writerows((fm.filename, fm.hash.hex(), fm.file_size, '|'.join(fm.install_tags))for fm in files)
        else:
            install_tags = set()
            for fm in files:
                print(fm.filename)
                for t in fm.install_tags:
                    install_tags.add(t)
            if install_tags:
                # use the log output so this isn't included when piping file list into file
                logger.info(f'Install tags: {", ".join(sorted(install_tags))}')

    def list_saves(self, args):
        if not self.core.login():
            logger.error('Login failed! Cannot continue with download process.')
            exit(1)
        # update game metadata
        logger.debug('Refreshing games list...')
        _ = self.core.get_game_and_dlc_list(update_assets=True)
        # then get the saves
        logger.info('Getting list of saves...')
        saves = self.core.get_save_games(args.app_name)
        last_app = ''
        print('Save games:')
        for save in sorted(saves, key=lambda a: a.app_name + a.manifest_name):
            if save.app_name != last_app:
                game_title = self.core.get_game(save.app_name).app_title
                last_app = save.app_name
                print(f'- {game_title} ("{save.app_name}")')
            print(' +', save.manifest_name)

    def download_saves(self, args):
        if not self.core.login():
            logger.error('Login failed! Cannot continue with download process.')
            exit(1)
        logger.info(f'Downloading saves to "{self.core.get_default_install_dir()}"')
        self.core.download_saves(args.app_name)

    def sync_saves(self, args):
        if not self.core.login():
            logger.error('Login failed! Cannot continue with download process.')
            exit(1)

        igames = self.core.get_installed_list()
        if args.app_name:
            igame = self.core.get_installed_game(args.app_name)
            if not igame:
                logger.fatal(f'Game not installed: {args.app_name}')
                exit(1)
            igames = [igame]

        # check available saves
        saves = self.core.get_save_games()
        latest_save = dict()

        for save in sorted(saves, key=lambda a: a.datetime):
            latest_save[save.app_name] = save

        logger.info(f'Got {len(latest_save)} remote save game(s)')

        # evaluate current save state for each game.
        for igame in igames:
            game = self.core.get_game(igame.app_name)
            if not game or not game.supports_cloud_saves:
                if igame.app_name in latest_save:
                    # this should never happen unless cloud save support was removed from a game
                    logger.warning(f'{igame.app_name} has remote save(s) but does not support cloud saves?!')
                continue

            logger.info(f'Checking "{igame.title}" ({igame.app_name})')
            # override save path only if app name is specified
            if args.app_name and args.save_path:
                logger.info(f'Overriding save path with "{args.save_path}"...')
                igame.save_path = args.save_path
                self.core.lgd.set_installed_game(igame.app_name, igame)

            # if there is no saved save path, try to get one
            if not igame.save_path:
                save_path = self.core.get_save_path(igame.app_name)

                # ask user if path is correct if computing for the first time
                logger.info(f'Computed save path: "{save_path}"')

                if '%' in save_path or '{' in save_path:
                    logger.warning('Path contains unprocessed variables, please enter the correct path manually.')
                    yn = False
                else:
                    yn = get_boolean_choice('Is this correct?')

                if not yn:
                    save_path = input('Please enter the correct path (leave empty to skip): ')
                    if not save_path:
                        logger.info('Empty input, skipping...')
                        continue

                if not os.path.exists(save_path):
                    os.makedirs(save_path)
                igame.save_path = save_path
                self.core.lgd.set_installed_game(igame.app_name, igame)

            res, (dt_l, dt_r) = self.core.check_savegame_state(igame.save_path, latest_save.get(igame.app_name))

            if res == SaveGameStatus.NO_SAVE:
                logger.info('No cloud or local savegame found.')
                continue

            if res == SaveGameStatus.SAME_AGE and not (args.force_upload or args.force_download):
                logger.info(f'Save game for "{igame.title}" is up to date, skipping...')
                continue

            if (res == SaveGameStatus.REMOTE_NEWER and not args.force_upload) or args.force_download:
                if res == SaveGameStatus.REMOTE_NEWER:  # only print this info if not forced
                    logger.info(f'Cloud save for "{igame.title}" is newer:')
                    logger.info(f'- Cloud save date: {dt_r.strftime("%Y-%m-%d %H:%M:%S")}')
                    if dt_l:
                        logger.info(f'- Local save date: {dt_l.strftime("%Y-%m-%d %H:%M:%S")}')
                    else:
                        logger.info('- Local save date: N/A')

                if args.upload_only:
                    logger.info('Save game downloading is disabled, skipping...')
                    continue

                if not args.yes and not args.force_download:
                    if not get_boolean_choice(f'Download cloud save?'):
                        logger.info('Not downloading...')
                        continue

                logger.info('Downloading remote savegame...')
                self.core.download_saves(igame.app_name, save_dir=igame.save_path, clean_dir=True,
                                         manifest_name=latest_save[igame.app_name].manifest_name)
            elif res == SaveGameStatus.LOCAL_NEWER or args.force_upload:
                if res == SaveGameStatus.LOCAL_NEWER:
                    logger.info(f'Local save for "{igame.title}" is newer')
                    if dt_r:
                        logger.info(f'- Cloud save date: {dt_r.strftime("%Y-%m-%d %H:%M:%S")}')
                    else:
                        logger.info('- Cloud save date: N/A')
                    logger.info(f'- Local save date: {dt_l.strftime("%Y-%m-%d %H:%M:%S")}')

                if args.download_only:
                    logger.info('Save game uploading is disabled, skipping...')
                    continue

                if not args.yes and not args.force_upload:
                    if not get_boolean_choice(f'Upload local save?'):
                        logger.info('Not uploading...')
                        continue
                logger.info('Uploading local savegame...')
                self.core.upload_save(igame.app_name, igame.save_path, dt_l, args.disable_filters)

    def launch_game(self, args, extra):
        app_name = args.app_name
        if not self.core.is_installed(app_name):
            logger.error(f'Game {app_name} is not currently installed!')
            exit(1)

        if self.core.is_dlc(app_name):
            logger.error(f'{app_name} is DLC; please launch the base game instead!')
            exit(1)

        if args.reset_defaults:
            logger.info(f'Removing configuration section for "{app_name}"...')
            self.core.lgd.config.remove_section(app_name)
            return

        # override with config value
        args.offline = self.core.is_offline_game(app_name) or args.offline
        if not args.offline:
            logger.info('Logging in...')
            if not self.core.login():
                logger.error('Login failed, cannot continue!')
                exit(1)

            if not args.skip_version_check and not self.core.is_noupdate_game(app_name):
                logger.info('Checking for updates...')
                installed = self.core.lgd.get_installed_game(app_name)
                latest = self.core.get_asset(app_name, update=True)
                if latest.build_version != installed.version:
                    logger.error('Game is out of date, please update or launch with update check skipping!')
                    exit(1)

        params, cwd, env = self.core.get_launch_parameters(app_name=app_name, offline=args.offline,
                                                           extra_args=extra, user=args.user_name_override,
                                                           wine_bin=args.wine_bin, wine_pfx=args.wine_pfx,
                                                           language=args.language, wrapper=args.wrapper,
                                                           disable_wine=args.no_wine)

        if args.set_defaults:
            self.core.lgd.config[app_name] = dict()
            # we have to do this if-cacophony here because an empty value is still
            # valid and could cause issues when relying on config.get()'s fallback
            if args.offline:
                self.core.lgd.config[app_name]['offline'] = 'true'
            if args.skip_version_check:
                self.core.lgd.config[app_name]['skip_update_check'] = 'true'
            if extra:
                self.core.lgd.config[app_name]['start_params'] = shlex.join(extra)
            if args.wine_bin:
                self.core.lgd.config[app_name]['wine_executable'] = args.wine_bin
            if args.wine_pfx:
                self.core.lgd.config[app_name]['wine_prefix'] = args.wine_pfx
            if args.no_wine:
                self.core.lgd.config[app_name]['no_wine'] = 'true'
            if args.language:
                self.core.lgd.config[app_name]['language'] = args.language
            if args.wrapper:
                self.core.lgd.config[app_name]['wrapper'] = args.wrapper

        if args.dry_run:
            logger.info(f'Not Launching {app_name} (dry run)')
            logger.info(f'Launch parameters: {shlex.join(params)}')
            logger.info(f'Working directory: {cwd}')
            if env:
                logger.info('Environment overrides:', env)
        else:
            logger.info(f'Launching {app_name}...')
            logger.debug(f'Launch parameters: {shlex.join(params)}')
            logger.debug(f'Working directory: {cwd}')
            if env:
                logger.debug('Environment overrides:', env)
            subprocess.Popen(params, cwd=cwd, env=env)

    def install_game(self, args):
        if self.core.is_installed(args.app_name):
            igame = self.core.get_installed_game(args.app_name)
            if igame.needs_verification and not args.repair_mode:
                logger.info('Game needs to be verified before updating, switching to repair mode...')
                args.repair_mode = True

        repair_file = None
        if args.subparser_name == 'download':
            logger.info('Setting --no-install flag since "download" command was used')
            args.no_install = True
        elif args.subparser_name == 'repair' or args.repair_mode:
            args.repair_mode = True
            args.no_install = True
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
                                                          repair=args.repair_mode)

        # game is either up to date or hasn't changed, so we have nothing to do
        if not analysis.dl_size:
            logger.info('Download size is 0, the game is either already up to date or has not changed. Exiting...')
            if args.repair_mode and os.path.exists(repair_file):
                igame = self.core.get_installed_game(game.app_name)
                if igame.needs_verification:
                    igame.needs_verification = False
                    self.core.install_game(igame)

                logger.debug('Removing repair file.')
                os.remove(repair_file)
            exit(0)

        logger.info(f'Install size: {analysis.install_size / 1024 / 1024:.02f} MiB')
        compression = (1 - (analysis.dl_size / analysis.uncompressed_dl_size)) * 100
        logger.info(f'Download size: {analysis.dl_size / 1024 / 1024:.02f} MiB '
                    f'(Compression savings: {compression:.01f}%)')
        logger.info(f'Reusable size: {analysis.reuse_size / 1024 / 1024:.02f} MiB (chunks) / '
                    f'{analysis.unchanged / 1024 / 1024:.02f} MiB (unchanged)')

        res = self.core.check_installation_conditions(analysis=analysis, install=igame)

        if res.failures:
            logger.fatal('Download cannot proceed, the following errors occured:')
            for msg in sorted(res.failures):
                logger.fatal(msg)
            exit(1)

        if res.warnings:
            logger.warning('Installation requirements check returned the following warnings:')
            for warn in sorted(res.warnings):
                logger.warning(warn)

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
            logger.warning(f'The following exception occured while waiting for the donlowader to finish: {e!r}. '
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

            if args.repair_mode and os.path.exists(repair_file):
                igame = self.core.get_installed_game(game.app_name)
                if igame.needs_verification:
                    igame.needs_verification = False
                    self.core.install_game(igame)

                logger.debug('Removing repair file.')
                os.remove(repair_file)

            logger.info(f'Finished installation process in {end_t - start_t:.02f} seconds.')

    def _handle_postinstall(self, postinstall, igame, yes=False):
        print('This game lists the following prequisites to be installed:')
        print(f'- {postinstall["name"]}: {" ".join((postinstall["path"], postinstall["args"]))}')
        if os.name == 'nt':
            if yes:
                c = 'n'  # we don't want to launch anything, just silent install.
            else:
                choice = input('Do you wish to install the prerequisites? ([y]es, [n]o, [i]gnore): ')
                c = choice.lower()[0]

            if c == 'i':  # just set it to installed
                print('Marking prerequisites as installed...')
                self.core.prereq_installed(igame.app_name)
            elif c == 'y':  # set to installed and launch installation
                print('Launching prerequisite executable..')
                self.core.prereq_installed(igame.app_name)
                req_path, req_exec = os.path.split(postinstall['path'])
                work_dir = os.path.join(igame.install_path, req_path)
                fullpath = os.path.join(work_dir, req_exec)
                subprocess.Popen([fullpath, postinstall['args']], cwd=work_dir)
        else:
            logger.info('Automatic installation not available on Linux.')

    def uninstall_game(self, args):
        igame = self.core.get_installed_game(args.app_name)
        if not igame:
            logger.error(f'Game {args.app_name} not installed, cannot uninstall!')
            exit(0)
        if igame.is_dlc:
            logger.error('Uninstalling DLC is not supported.')
            exit(1)

        if not args.yes:
            if not get_boolean_choice(f'Do you wish to uninstall "{igame.title}"?', default=False):
                print('Aborting...')
                exit(0)

        try:
            logger.info(f'Removing "{igame.title}" from "{igame.install_path}"...')
            self.core.uninstall_game(igame)

            # DLCs are already removed once we delete the main game, so this just removes them from the list
            dlcs = self.core.get_dlc_for_game(igame.app_name)
            for dlc in dlcs:
                idlc = self.core.get_installed_game(dlc.app_name)
                if self.core.is_installed(dlc.app_name):
                    logger.info(f'Uninstalling DLC "{dlc.app_name}"...')
                    self.core.uninstall_game(idlc, delete_files=False)

            logger.info('Game has been uninstalled.')
        except Exception as e:
            logger.warning(f'Removing game failed: {e!r}, please remove {igame.install_path} manually.')

    def verify_game(self, args, print_command=True):
        if not self.core.is_installed(args.app_name):
            logger.error(f'Game "{args.app_name}" is not installed')
            return

        logger.info(f'Loading installed manifest for "{args.app_name}"')
        igame = self.core.get_installed_game(args.app_name)
        manifest_data, _ = self.core.get_installed_manifest(args.app_name)
        manifest = self.core.load_manfiest(manifest_data)

        files = sorted(manifest.file_manifest_list.elements,
                       key=lambda a: a.filename.lower())

        # build list of hashes
        file_list = [(f.filename, f.sha_hash.hex()) for f in files]
        total = len(file_list)
        num = 0
        failed = []
        missing = []

        logger.info(f'Verifying "{igame.title}" version "{manifest.meta.build_version}"')
        repair_file = []
        for result, path, result_hash in validate_files(igame.install_path, file_list):
            stdout.write(f'Verification progress: {num}/{total} ({num * 100 / total:.01f}%)\t\r')
            stdout.flush()
            num += 1

            if result == VerifyResult.HASH_MATCH:
                repair_file.append(f'{result_hash}:{path}')
                continue
            elif result == VerifyResult.HASH_MISMATCH:
                logger.error(f'File does not match hash: "{path}"')
                repair_file.append(f'{result_hash}:{path}')
                failed.append(path)
            elif result == VerifyResult.FILE_MISSING:
                logger.error(f'File is missing: "{path}"')
                missing.append(path)
            else:
                logger.error(f'Other failure (see log), treating file as missing: "{path}"')
                missing.append(path)

        stdout.write(f'Verification progress: {num}/{total} ({num * 100 / total:.01f}%)\t\n')

        # always write repair file, even if all match
        if repair_file:
            repair_filename = os.path.join(self.core.lgd.get_tmp_path(), f'{args.app_name}.repair')
            with open(repair_filename, 'w') as f:
                f.write('\n'.join(repair_file))
            logger.debug(f'Written repair file to "{repair_filename}"')

        if not missing and not failed:
            logger.info('Verification finished successfully.')
        else:
            logger.error(f'Verification failed, {len(failed)} file(s) corrupted, {len(missing)} file(s) are missing.')
            if print_command:
                logger.info(f'Run "legendary repair {args.app_name}" to repair your game installation.')

    def import_game(self, args):
        if not os.path.exists(args.app_path):
            logger.error(f'Specified path "{args.app_path}" does not exist!')
            exit(1)

        if self.core.is_installed(args.app_name):
            logger.error('Game is already installed!')
            exit(0)

        if not self.core.login():
            logger.error('Log in failed!')
            exit(1)

        # do some basic checks
        game = self.core.get_game(args.app_name, update_meta=True)
        if not game:
            logger.fatal(f'Did not find game "{args.app_name}" on account.')
            exit(1)

        # get everything needed for import from core, then run additional checks.
        manifest, igame = self.core.import_game(game, args.app_path)
        exe_path = os.path.join(args.app_path, manifest.meta.launch_exe.lstrip('/'))
        # check if most files at least exist or if user might have specified the wrong directory
        total = len(manifest.file_manifest_list.elements)
        found = sum(os.path.exists(os.path.join(args.app_path, f.filename))
                    for f in manifest.file_manifest_list.elements)
        ratio = found / total

        if not os.path.exists(exe_path and not args.disable_check):
            logger.error(f'Game executable could not be found at "{exe_path}", '
                         f'please verify that the specified path is correct.')
            exit(1)

        if ratio < 0.95:
            logger.warning('Some files are missing from the game installation, install may not '
                           'match latest Epic Games Store version or might be corrupted.')
        else:
            logger.info('Game install appears to be complete.')

        self.core.install_game(igame)
        if igame.needs_verification:
            logger.info(f'NOTE: The game installation will have to be verified before it can be updated '
                        f'with legendary. Run "legendary repair {args.app_name}" to do so.')
        else:
            logger.info(f'Installation had Epic Games Launcher metadata for version "{igame.version}", '
                        f'verification will not be requried.')
        logger.info('Game has been imported.')

    def egs_sync(self, args):
        if args.unlink:
            logger.info('Unlinking and resetting EGS and LGD sync...')
            self.core.lgd.config.remove_option('Legendary', 'egl_programdata')
            self.core.lgd.config.remove_option('Legendary', 'egl_sync')
            # remove EGL GUIDs from all games, DO NOT remove .egstore folders because that would fuck things up.
            for igame in self.core.get_installed_list():
                igame.egl_guid = ''
                self.core.install_game(igame)
            # todo track which games were imported, remove those from LGD and exported ones from EGL
            logger.info('NOTE: Games have not been removed from the Epic Games Launcher or Legendary.')
            logger.info('Games will not be removed from EGL or Legendary if it was removed from the other launcher.')
            return
        elif args.disable_sync:
            logger.info('Disabling EGS/LGD sync...')
            self.core.lgd.config.remove_option('Legendary', 'egl_sync')
            return

        if not self.core.egl.programdata_path:
            if not args.egl_manifest_path and not args.egl_wine_prefix:
                # search default Lutris install path
                lutris_data_path = os.path.expanduser('~/Games/epic-games-store/drive_c/ProgramData'
                                                      '/Epic/EpicGamesLauncher/Data')
                egl_path = None
                if os.path.exists(lutris_data_path):
                    logger.info(f'Found Lutris EGL install at "{lutris_data_path}"')

                    if args.yes or get_boolean_choice('Do you want to use the Lutris install?'):
                        egl_path = os.path.join(lutris_data_path, 'Manifests')
                        if not os.path.exists(egl_path):
                            print('EGL Data path exists but Manifests directory is missing, creating...')
                            os.makedirs(egl_path)

                if not egl_path:
                    print('EGL path not found, please manually provide the path to the WINE prefix it is installed in')
                    egl_path = input('Path [empty input to quit]: ').strip()
                    if not egl_path:
                        print('Empty input, quitting...')
                        exit(0)
                    if not os.path.exists(egl_path):
                        print('Path is invalid (does not exist)!')
                        exit(1)
                    egl_data_path = os.path.join(egl_path, 'drive_c/ProgramData/Epic/EpicGamesLauncher/Data')
                    egl_path = os.path.join(egl_data_path, 'Manifests')
                    if not os.path.exists(egl_path):
                        if not os.path.exists(egl_data_path):
                            print('Invalid path (wrong directory, WINE prefix, or EGL not installed/launched)')
                            exit(1)
                        print('EGL Data path exists but Manifests directory is missing, creating...')
                        os.makedirs(egl_path)

                if not os.listdir(egl_path):
                    logger.warning('Folder is empty, this may be fine if nothing has been installed yet.')
                self.core.egl.programdata_path = egl_path
                self.core.lgd.config.set('Legendary', 'egl_programdata', egl_path)
            elif args.egl_wine_prefix:
                egl_data_path = os.path.join(args.egl_wine_prefix,
                                             'drive_c/ProgramData/Epic/EpicGamesLauncher/Data')
                egl_path = os.path.join(egl_data_path, 'Manifests')
                if not os.path.exists(egl_path):
                    if not os.path.exists(egl_data_path):
                        print('Invalid path (wrong directory, WINE prefix, or EGL not installed/launched)')
                        exit(1)
                    print('EGL Data path exists but Manifests directory is missing, creating...')
                    os.makedirs(egl_path)

                if not os.listdir(egl_path):
                    logger.warning('Folder is empty, this may be fine if nothing has been installed yet.')
                self.core.egl.programdata_path = egl_path
                self.core.lgd.config.set('Legendary', 'egl_programdata', egl_path)
            else:
                if not os.path.exists(args.egl_manifest_path):
                    logger.fatal('Path specified via --egl-manifest-path does not exist')
                    exit(1)
                self.core.egl.programdata_path = args.egl_manifest_path
                self.core.lgd.config.set('Legendary', 'egl_programdata', args.egl_manifest_path)

        logger.debug(f'Using EGL ProgramData path "{self.core.egl.programdata_path}"...')
        logger.info('Reading EGL game manifests...')

        if not args.export_only:
            print('\nChecking for importable games...')
            importable = self.core.egl_get_importable()
            if importable:
                print('The following games are importable (EGL -> Legendary):')
                for egl_game in importable:
                    print(' *', egl_game.app_name, '-', egl_game.display_name)

                if args.yes or get_boolean_choice('Do you want to import the games from EGL?'):
                    for egl_game in importable:
                        logger.info(f'Importing "{egl_game.display_name}"...')
                        self.core.egl_import(egl_game.app_name)
            else:
                print('Nothing to import.')

        if not args.import_only:
            print('\nChecking for exportable games...')
            exportable = self.core.egl_get_exportable()
            if exportable:
                print('The following games are exportable (Legendary -> EGL)')
                for lgd_game in exportable:
                    print(' *', lgd_game.app_name, '-', lgd_game.title)

                if args.yes or get_boolean_choice('Do you want to export the games to EGL?'):
                    for lgd_game in exportable:
                        logger.info(f'Exporting "{lgd_game.title}"...')
                        self.core.egl_export(lgd_game.app_name)
            else:
                print('Nothing to export.')

        print('\nChecking automatic sync...')
        if not self.core.egl_sync_enabled and not args.one_shot:
            if not args.enable_sync:
                args.enable_sync = args.yes or get_boolean_choice('Enable automatic synchronization?')
                if not args.enable_sync:  # if user chooses no, still run the sync once
                    self.core.egl_sync()
            self.core.lgd.config.set('Legendary', 'egl_sync', str(args.enable_sync))
        else:
            self.core.egl_sync()


def main():
    parser = argparse.ArgumentParser(description=f'Legendary v{__version__} - "{__codename__}"')
    parser.register('action', 'parsers', AliasedSubParsersAction)

    # general arguments
    parser.add_argument('-v', dest='debug', action='store_true', help='Set loglevel to debug')
    parser.add_argument('-y', '--yes', dest='yes', action='store_true', help='Default to yes for all prompts')
    parser.add_argument('-V', dest='version', action='store_true', help='Print version and exit')

    # all the commands
    subparsers = parser.add_subparsers(title='Commands', dest='subparser_name')
    auth_parser = subparsers.add_parser('auth', help='Authenticate with EPIC')
    install_parser = subparsers.add_parser('install', help='Download a game',
                                           aliases=('download', 'update', 'repair'),
                                           usage='%(prog)s <App Name> [options]',
                                           description='Aliases: download, update')
    uninstall_parser = subparsers.add_parser('uninstall', help='Uninstall (delete) a game')
    launch_parser = subparsers.add_parser('launch', help='Launch a game', usage='%(prog)s <App Name> [options]',
                                          description='Note: additional arguments are passed to the game')
    list_parser = subparsers.add_parser('list-games', help='List available (installable) games')
    list_installed_parser = subparsers.add_parser('list-installed', help='List installed games')
    list_files_parser = subparsers.add_parser('list-files', help='List files in manifest')
    list_saves_parser = subparsers.add_parser('list-saves', help='List available cloud saves')
    download_saves_parser = subparsers.add_parser('download-saves', help='Download all cloud saves')
    sync_saves_parser = subparsers.add_parser('sync-saves', help='Sync cloud saves')
    verify_parser = subparsers.add_parser('verify-game', help='Verify a game\'s local files')
    import_parser = subparsers.add_parser('import-game', help='Import an already installed game')
    egl_sync_parser = subparsers.add_parser('egl-sync', help='Setup or run Epic Games Launcher sync')

    install_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    uninstall_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    launch_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    list_files_parser.add_argument('app_name', nargs='?', metavar='<App Name>',
                                   help='Name of the app (optional)')
    list_saves_parser.add_argument('app_name', nargs='?', metavar='<App Name>', default='',
                                   help='Name of the app (optional)')
    download_saves_parser.add_argument('app_name', nargs='?', metavar='<App Name>', default='',
                                       help='Name of the app (optional)')
    sync_saves_parser.add_argument('app_name', nargs='?', metavar='<App Name>', default='',
                                   help='Name of the app (optional)')
    verify_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    import_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    import_parser.add_argument('app_path', help='Path where the game is installed',
                               metavar='<Installation directory>')

    auth_parser.add_argument('--import', dest='import_egs_auth', action='store_true',
                             help='Import Epic Games Launcher authentication data (logs out of EGL)')
    auth_parser.add_argument('--code', dest='auth_code', action='store', metavar='<exchange code>',
                             help='Use specified exchange code instead of interactive authentication')
    auth_parser.add_argument('--sid', dest='session_id', action='store', metavar='<session id>',
                             help='Use specified session id instead of interactive authentication')
    auth_parser.add_argument('--delete', dest='auth_delete', action='store_true',
                             help='Remove existing authentication (log out)')

    install_parser.add_argument('--base-path', dest='base_path', action='store', metavar='<path>',
                                help='Path for game installations (defaults to ~/legendary)')
    install_parser.add_argument('--game-folder', dest='game_folder', action='store', metavar='<path>',
                                help='Folder for game installation (defaults to folder specified in metadata)')
    install_parser.add_argument('--max-shared-memory', dest='shared_memory', action='store', metavar='<size>',
                                type=int, help='Maximum amount of shared memory to use (in MiB), default: 1 GiB')
    install_parser.add_argument('--max-workers', dest='max_workers', action='store', metavar='<num>',
                                type=int, help='Maximum amount of download workers, default: min(2 * CPUs, 16)')
    install_parser.add_argument('--manifest', dest='override_manifest', action='store', metavar='<uri>',
                                help='Manifest URL or path to use instead of the CDN one (e.g. for downgrading)')
    install_parser.add_argument('--old-manifest', dest='override_old_manifest', action='store', metavar='<uri>',
                                help='Manifest URL or path to use as the old one (e.g. for testing patching)')
    install_parser.add_argument('--base-url', dest='override_base_url', action='store', metavar='<url>',
                                help='Base URL to download from (e.g. to test or switch to a different CDNs)')
    install_parser.add_argument('--force', dest='force', action='store_true',
                                help='Download all files / ignore existing (overwrite)')
    install_parser.add_argument('--disable-patching', dest='disable_patching', action='store_true',
                                help='Do not attempt to patch existing installation (download entire changed files)')
    install_parser.add_argument('--download-only', '--no-install', dest='no_install', action='store_true',
                                help='Do not intall app and do not run prerequisite installers after download')
    install_parser.add_argument('--update-only', dest='update_only', action='store_true',
                                help='Only update, do not do anything if specified app is not installed')
    install_parser.add_argument('--dlm-debug', dest='dlm_debug', action='store_true',
                                help='Set download manager and worker processes\' loglevel to debug')
    install_parser.add_argument('--platform', dest='platform_override', action='store', metavar='<Platform>',
                                type=str, help='Platform override for download (also sets --no-install)')
    install_parser.add_argument('--prefix', dest='file_prefix', action='append', metavar='<prefix>',
                                help='Only fetch files whose path starts with <prefix> (case insensitive)')
    install_parser.add_argument('--exclude', dest='file_exclude_prefix', action='append', metavar='<prefix>',
                                type=str, help='Exclude files starting with <prefix> (case insensitive)')
    install_parser.add_argument('--install-tag', dest='install_tag', action='append', metavar='<tag>',
                                type=str, help='Only download files with the specified install tag')
    install_parser.add_argument('--enable-reordering', dest='order_opt', action='store_true',
                                help='Enable reordering optimization to reduce RAM requirements '
                                     'during download (may have adverse results for some titles)')
    install_parser.add_argument('--dl-timeout', dest='dl_timeout', action='store', metavar='<sec>', type=int,
                                help='Connection timeout for downloader (default: 10 seconds)')
    install_parser.add_argument('--save-path', dest='save_path', action='store', metavar='<path>',
                                help='Set save game path to be used for sync-saves')
    install_parser.add_argument('--repair', dest='repair_mode', action='store_true',
                                help='Repair installed game by checking and redownloading corrupted/missing files')

    launch_parser.add_argument('--offline', dest='offline', action='store_true',
                               default=False, help='Skip login and launch game without online authentication')
    launch_parser.add_argument('--skip-version-check', dest='skip_version_check', action='store_true',
                               default=False, help='Skip version check when launching game in online mode')
    launch_parser.add_argument('--override-username', dest='user_name_override', action='store', metavar='<username>',
                               help='Override username used when launching the game (only works with some titles)')
    launch_parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                               help='Print the command line that would have been used to launch the game and exit')
    launch_parser.add_argument('--language', dest='language', action='store', metavar='<two letter language code>',
                               help='Override language for game launch (defaults to system locale)')
    launch_parser.add_argument('--wrapper', dest='wrapper', action='store', metavar='<wrapper command>',
                               default=os.environ.get('LGDRY_WRAPPER', None),
                               help='Wrapper command to launch game with')
    launch_parser.add_argument('--set-defaults', dest='set_defaults', action='store_true',
                               help='Save parameters used to launch to config (does not include env vars)')
    launch_parser.add_argument('--reset-defaults', dest='reset_defaults', action='store_true',
                               help='Reset config settings for app and exit')

    if os.name != 'nt':
        launch_parser.add_argument('--wine', dest='wine_bin', action='store', metavar='<wine binary>',
                                   default=os.environ.get('LGDRY_WINE_BINARY', None),
                                   help='Set WINE binary to use to launch the app')
        launch_parser.add_argument('--wine-prefix', dest='wine_pfx', action='store', metavar='<wine pfx path>',
                                   default=os.environ.get('LGDRY_WINE_PREFIX', None),
                                   help='Set WINE prefix to use')
        launch_parser.add_argument('--no-wine', dest='no_wine', action='store_true',
                                   default=strtobool(os.environ.get('LGDRY_NO_WINE', 'False')),
                                   help='Do not run game with WINE (e.g. if a wrapper is used)')
    else:
        # hidden arguments to not break this on Windows
        launch_parser.add_argument('--wine', help=argparse.SUPPRESS, dest='wine_bin')
        launch_parser.add_argument('--wine-prefix', help=argparse.SUPPRESS, dest='wine_pfx')
        launch_parser.add_argument('--no-wine', dest='no_wine', help=argparse.SUPPRESS,
                                   action='store_true', default=True)

    list_parser.add_argument('--platform', dest='platform_override', action='store', metavar='<Platform>',
                             type=str, help='Override platform that games are shown for (e.g. Win32/Mac)')
    list_parser.add_argument('--include-ue', dest='include_ue', action='store_true',
                             help='Also include Unreal Engine content (Engine/Marketplace) in list')
    list_parser.add_argument('--csv', dest='csv', action='store_true', help='List games in CSV format')
    list_parser.add_argument('--tsv', dest='tsv', action='store_true', help='List games in TSV format')

    list_installed_parser.add_argument('--check-updates', dest='check_updates', action='store_true',
                                       help='Check for updates for installed games')
    list_installed_parser.add_argument('--csv', dest='csv', action='store_true',
                                       help='List games in CSV format')
    list_installed_parser.add_argument('--tsv', dest='tsv', action='store_true',
                                       help='List games in TSV format')
    list_installed_parser.add_argument('--show-dirs', dest='include_dir', action='store_true',
                                       help='Print installation directory in output')

    list_files_parser.add_argument('--force-download', dest='force_download', action='store_true',
                                   help='Always download instead of using on-disk manifest')
    list_files_parser.add_argument('--platform', dest='platform_override', action='store', metavar='<Platform>',
                                   type=str, help='Platform override for download (disables install)')
    list_files_parser.add_argument('--manifest', dest='override_manifest', action='store', metavar='<uri>',
                                   help='Manifest URL or path to use instead of the CDN one')
    list_files_parser.add_argument('--csv', dest='csv', action='store_true', help='Output in CSV format')
    list_files_parser.add_argument('--tsv', dest='tsv', action='store_true', help='Output in TSV format')
    list_files_parser.add_argument('--hashlist', dest='hashlist', action='store_true',
                                   help='Output file hash list in hashcheck/sha1sum -c compatible format')
    list_files_parser.add_argument('--install-tag', dest='install_tag', action='store', metavar='<tag>',
                                   type=str, help='Show only files with specified install tag')

    sync_saves_parser.add_argument('--skip-upload', dest='download_only', action='store_true',
                                   help='Only download new saves from cloud, don\'t upload')
    sync_saves_parser.add_argument('--skip-download', dest='upload_only', action='store_true',
                                   help='Only upload new saves from cloud, don\'t download')
    sync_saves_parser.add_argument('--force-upload', dest='force_upload', action='store_true',
                                   help='Force upload even if local saves are older')
    sync_saves_parser.add_argument('--force-download', dest='force_download', action='store_true',
                                   help='Force download even if local saves are newer')
    sync_saves_parser.add_argument('--save-path', dest='save_path', action='store', metavar='<path>',
                                   help='Override savegame path (requires single app name to be specified)')
    sync_saves_parser.add_argument('--disable-filters', dest='disable_filters', action='store_true',
                                   help='Disable save game file filtering')

    import_parser.add_argument('--disable-check', dest='disable_check', action='store_true',
                               help='Disables completeness check of the to-be-imported game installation '
                                    '(useful if the imported game is a much older version or missing files)')

    egl_sync_parser.add_argument('--egl-manifest-path', dest='egl_manifest_path', action='store',
                                 help='Path to the Epic Games Launcher\'s Manifests folder, should '
                                      'point to /ProgramData/Epic/EpicGamesLauncher/Data/Manifests')
    egl_sync_parser.add_argument('--egl-wine-prefix', dest='egl_wine_prefix', action='store',
                                 help='Path to the WINE prefix the Epic Games Launcher is installed in')
    egl_sync_parser.add_argument('--enable-sync', dest='enable_sync', action='store_true',
                                 help='Enable automatic EGL <-> Legendary sync')
    egl_sync_parser.add_argument('--disable-sync', dest='disable_sync', action='store_true',
                                 help='Disable automatic sync and exit')
    egl_sync_parser.add_argument('--one-shot', dest='one_shot', action='store_true',
                                 help='Sync once, do not ask to setup automatic sync')
    egl_sync_parser.add_argument('--import-only', dest='import_only', action='store_true',
                                 help='Only import games from EGL (no export)')
    egl_sync_parser.add_argument('--export-only', dest='export_only', action='store_true',
                                 help='Only export games to EGL (no import)')
    egl_sync_parser.add_argument('--unlink', dest='unlink', action='store_true',
                                 help='Disable sync and remove EGL metadata from installed games')

    args, extra = parser.parse_known_args()

    if args.version:
        print(f'legendary version "{__version__}", codename "{__codename__}"')
        exit(0)

    if args.subparser_name not in ('auth', 'list-games', 'list-installed', 'list-files',
                                   'launch', 'download', 'uninstall', 'install', 'update',
                                   'repair', 'list-saves', 'download-saves', 'sync-saves',
                                   'verify-game', 'import-game', 'egl-sync'):
        print(parser.format_help())

        # Print the main help *and* the help for all of the subcommands. Thanks stackoverflow!
        print('Individual command help:')
        subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        for choice, subparser in subparsers.choices.items():
            if choice in ('download', 'update', 'repair'):
                continue
            print(f'\nCommand: {choice}')
            print(subparser.format_help())
        return

    cli = LegendaryCLI()
    ql = cli.setup_threaded_logging()

    config_ll = cli.core.lgd.config.get('Legendary', 'log_level', fallback='info')
    if config_ll == 'debug' or args.debug:
        logging.getLogger().setLevel(level=logging.DEBUG)
        # keep requests quiet
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

    # -y having to be specified before the subcommand is a little counter-intuitive
    # For now show a warning if a user is misusing that flag
    if '-y' in extra or '--yes' in extra:
        logger.warning('-y/--yes flag needs to be specified *before* the command name')

    # technically args.func() with setdefaults could work (see docs on subparsers)
    # but that would require all funcs to accept args and extra...
    try:
        if args.subparser_name == 'auth':
            cli.auth(args)
        elif args.subparser_name == 'list-games':
            cli.list_games(args)
        elif args.subparser_name == 'list-installed':
            cli.list_installed(args)
        elif args.subparser_name == 'launch':
            cli.launch_game(args, extra)
        elif args.subparser_name in ('download', 'install', 'update', 'repair'):
            cli.install_game(args)
        elif args.subparser_name == 'uninstall':
            cli.uninstall_game(args)
        elif args.subparser_name == 'list-files':
            cli.list_files(args)
        elif args.subparser_name == 'list-saves':
            cli.list_saves(args)
        elif args.subparser_name == 'download-saves':
            cli.download_saves(args)
        elif args.subparser_name == 'sync-saves':
            cli.sync_saves(args)
        elif args.subparser_name == 'verify-game':
            cli.verify_game(args)
        elif args.subparser_name == 'import-game':
            cli.import_game(args)
        elif args.subparser_name == 'egl-sync':
            cli.egs_sync(args)
    except KeyboardInterrupt:
        logger.info('Command was aborted via KeyboardInterrupt, cleaning up...')

    cli.core.exit()
    ql.stop()
    exit(0)


if __name__ == '__main__':
    # required for pyinstaller on Windows, does nothing on other platforms.
    freeze_support()
    main()
