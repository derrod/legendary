#!/usr/bin/env python3
# coding: utf-8

import argparse
import csv
import json
import logging
import os
import shlex
import subprocess
import time
import webbrowser

from collections import defaultdict, namedtuple
from logging.handlers import QueueListener
from multiprocessing import freeze_support, Queue as MPQueue
from platform import platform
from sys import exit, stdout, platform as sys_platform

from legendary import __version__, __codename__
from legendary.core import LegendaryCore
from legendary.models.exceptions import InvalidCredentialsError
from legendary.models.game import SaveGameStatus, VerifyResult, Game
from legendary.utils.cli import get_boolean_choice, get_int_choice, sdl_prompt, strtobool
from legendary.lfs.crossover import *
from legendary.utils.custom_parser import HiddenAliasSubparsersAction
from legendary.utils.env import is_windows_mac_or_pyi
from legendary.lfs.eos import add_registry_entries, query_registry_entries, remove_registry_entries
from legendary.lfs.utils import validate_files, clean_filename
from legendary.utils.selective_dl import get_sdl_appname
from legendary.lfs.wine_helpers import read_registry, get_shell_folders, case_insensitive_file_search

# todo custom formatter for cli logger (clean info, highlighted error/warning)
logging.basicConfig(
    format='[%(name)s] %(levelname)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('cli')


class LegendaryCLI:
    def __init__(self, override_config=None, api_timeout=None):
        self.core = LegendaryCore(override_config, timeout=api_timeout)
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

    def _resolve_aliases(self, name):
        # make sure aliases exist if not yet created
        self.core.update_aliases(force=False)
        name = name.strip()
        # resolve alias (if any) to real app name
        return self.core.lgd.config.get(
            section='Legendary.aliases', option=name,
            fallback=self.core.lgd.aliases.get(name.lower(), name)
        )

    @staticmethod
    def _print_json(data, pretty=False):
        if pretty:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(json.dumps(data))

    def auth(self, args):
        if args.auth_delete:
            self.core.lgd.invalidate_userdata()
            logger.info('User data deleted.')
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

        # Force an update check and notice in case there are API changes
        self.core.check_for_updates(force=True)
        self.core.force_show_update = True

        if args.import_egs_auth:
            # get appdata path on Linux
            if not self.core.egl.appdata_path:
                egl_wine_pfx = None
                lutris_wine_pfx = os.path.expanduser('~/Games/epic-games-store')
                if os.path.exists(lutris_wine_pfx):
                    logger.info(f'Found Lutris EGL WINE prefix at "{lutris_wine_pfx}"')
                    if args.yes or get_boolean_choice('Do you want to use the Lutris install?'):
                        egl_wine_pfx = lutris_wine_pfx

                if not egl_wine_pfx:
                    logger.info('Please enter the path to the Wine prefix that has EGL installed')
                    egl_wine_pfx = input('Path [empty input to quit]: ').strip()
                    if not egl_wine_pfx:
                        print('Empty input, quitting...')
                        exit(0)
                    if not os.path.exists(egl_wine_pfx) and os.path.isdir(egl_wine_pfx):
                        print('Path is invalid (does not exist)!')
                        exit(1)

                try:
                    wine_folders = get_shell_folders(read_registry(egl_wine_pfx), egl_wine_pfx)
                    egl_appdata = os.path.realpath(os.path.join(wine_folders['Local AppData'],
                                                                'EpicGamesLauncher', 'Saved',
                                                                'Config', 'Windows'))
                except Exception as e:
                    logger.error(f'Got exception when trying to read WINE registry: {e!r}')
                    logger.error('Make sure you are specifying a valid wine prefix.')
                    exit(1)

                if not os.path.exists(egl_appdata):
                    logger.error(f'Wine prefix does not have EGL appdata path at "{egl_appdata}"')
                    exit(0)
                else:
                    logger.info(f'Using EGL appdata path at "{egl_appdata}"')
                    self.core.egl.appdata_path = egl_appdata

            logger.info('Importing login session from the Epic Launcher...')
            try:
                if self.core.auth_import():
                    logger.info('Successfully imported login session from EGS!')
                    logger.info(f'Now logged in as user "{self.core.lgd.userdata["displayName"]}"')
                    return
                else:
                    logger.warning('Login session from EGS seems to no longer be valid.')
                    exit(1)
            except Exception as e:
                logger.error(f'No EGS login session found, please login manually. (Exception: {e!r})')
                exit(1)

        exchange_token = ''
        auth_code = ''
        if not args.auth_code and not args.session_id and not args.ex_token:
            # only import here since pywebview import is slow
            from legendary.utils.webview_login import webview_available, do_webview_login

            if not webview_available or args.no_webview or self.core.webview_killswitch:
                # unfortunately the captcha stuff makes a complete CLI login flow kinda impossible right now...
                print('Please login via the epic web login!')
                url = 'https://legendary.gl/epiclogin'
                webbrowser.open(url)
                print(f'If the web page did not open automatically, please manually open the following URL: {url}')
                auth_code = input('Please enter the "authorizationCode" value from the JSON response: ')
                auth_code = auth_code.strip()
                if auth_code[0] == '{':
                    tmp = json.loads(auth_code)
                    auth_code = tmp['authorizationCode']
                else:
                    auth_code = auth_code.strip('"')
            else:
                if do_webview_login(callback_code=self.core.auth_ex_token,
                                    user_agent=f'EpicGamesLauncher/{self.core.get_egl_version()}'):
                    logger.info(f'Successfully logged in as "{self.core.lgd.userdata["displayName"]}" via WebView')
                else:
                    logger.error('WebView login attempt failed, please see log for details.')
                return
        elif args.session_id:
            exchange_token = self.core.auth_sid(args.session_id)
        elif args.auth_code:
            auth_code = args.auth_code
        elif args.ex_token:
            exchange_token = args.ex_token

        if not exchange_token and not auth_code:
            logger.fatal('No exchange token/authorization code, cannot login.')
            return

        if exchange_token and self.core.auth_ex_token(exchange_token):
            logger.info(f'Successfully logged in as "{self.core.lgd.userdata["displayName"]}"')
        elif auth_code and self.core.auth_code(auth_code):
            logger.info(f'Successfully logged in as "{self.core.lgd.userdata["displayName"]}"')
        else:
            logger.error('Login attempt failed, please see log for details.')

    def list_games(self, args):
        logger.info('Logging in...')
        if not self.core.login():
            logger.error('Login failed, cannot continue!')
            exit(1)

        if args.force_refresh:
            logger.info('Refreshing game list, this may take a while...')
        else:
            logger.info('Getting game list... (this may take a while)')

        games, dlc_list = self.core.get_game_and_dlc_list(
            platform=args.platform, skip_ue=not args.include_ue,
            force_refresh=args.force_refresh
        )
        # Get information for games that cannot be installed through legendary (yet), such
        # as games that have to be activated on and launched through Origin.
        if args.include_noasset:
            na_games, na_dlcs = self.core.get_non_asset_library_items(skip_ue=not args.include_ue)
            games.extend(na_games)
        else:
            na_dlcs = []

        # sort games and dlc by name
        games = sorted(games, key=lambda x: x.app_title.lower())
        for citem_id in dlc_list.keys():
            if citem_id in na_dlcs:
                dlc_list[citem_id].extend(na_dlcs[citem_id])
            dlc_list[citem_id] = sorted(dlc_list[citem_id], key=lambda d: d.app_title.lower())

        if args.csv or args.tsv:
            writer = csv.writer(stdout, dialect='excel-tab' if args.tsv else 'excel', lineterminator='\n')
            writer.writerow(['App name', 'App title', 'Version', 'Is DLC'])
            for game in games:
                writer.writerow((game.app_name, game.app_title, game.app_version(args.platform), False))
                for dlc in dlc_list[game.catalog_item_id]:
                    writer.writerow((dlc.app_name, dlc.app_title, dlc.app_version(args.platform), True))
            return

        if args.json:
            _out = []
            for game in games:
                _j = vars(game)
                _j['dlcs'] = [vars(dlc) for dlc in dlc_list[game.catalog_item_id]]
                _out.append(_j)

            return self._print_json(_out, args.pretty_json)

        print('\nAvailable games:')
        for game in games:
            version = game.app_version(args.platform)
            print(f' * {game.app_title.strip()} (App name: {game.app_name} | Version: {version})')
            # Games that "require" launching through EGL/Legendary, but have to be installed and managed through
            # a third-party application (such as Origin).
            if not version:
                _store = game.third_party_store
                if game.is_origin_game:
                    print(f'  - This game has to be activated, installed, and launched via Origin, use '
                          f'"legendary launch --origin {game.app_name}" to activate and/or run the game.')
                elif _store:
                    print(f'  ! This game has to be installed through a third-party store ({_store}, not supported)')
                else:
                    print('  ! No version information (unknown cause)')
            # Games that have assets, but only require a one-time activation before they can be independently installed
            # via a third-party platform (e.g. Uplay)
            if game.partner_link_type:
                _type = game.partner_link_type
                if _type == 'ubisoft':
                    print('  - This game can be activated directly on your Ubisoft account and does not require '
                          'legendary to install/run. This game requires Ubisoft Connect to be installed. '
                          'Use "legendary activate --uplay" and follow the instructions.')
                else:
                    print(f'  ! This app requires linking to a third-party account (name: "{_type}", not supported)')

            for dlc in dlc_list[game.catalog_item_id]:
                print(f'  + {dlc.app_title} (App name: {dlc.app_name} | Version: {dlc.app_version(args.platform)})')
                if not dlc.app_version(args.platform):
                    print(f'   ! This DLC is either included in the base game, or not available for {args.platform}')

        print(f'\nTotal: {len(games)}')

    def list_installed(self, args):
        if args.check_updates:
            logger.info('Logging in to check for updates...')
            if not self.core.login():
                logger.error('Login failed! Not checking for updates.')
            else:
                # Update assets for all platforms currently installed
                for app_platform in self.core.get_installed_platforms():
                    self.core.get_assets(True, platform=app_platform)

        games = sorted(self.core.get_installed_list(include_dlc=True),
                       key=lambda x: x.title.lower())

        versions = dict()
        for game in games:
            try:
                versions[game.app_name] = self.core.get_asset(game.app_name, platform=game.platform).build_version
            except ValueError:
                logger.warning(f'Metadata for "{game.app_name}" is missing, the game may have been removed from '
                               f'your account or not be in legendary\'s database yet, try rerunning the command '
                               f'with "--check-updates".')

        if args.csv or args.tsv:
            writer = csv.writer(stdout, dialect='excel-tab' if args.tsv else 'excel', lineterminator='\n')
            writer.writerow(['App name', 'App title', 'Installed version', 'Available version',
                             'Update available', 'Install size', 'Install path', 'Platform'])
            writer.writerows((game.app_name, game.title, game.version, versions[game.app_name],
                              versions[game.app_name] != game.version, game.install_size, game.install_path,
                              game.platform)
                             for game in games if game.app_name in versions)
            return

        if args.json:
            return self._print_json([vars(g) for g in games], args.pretty_json)

        installed_dlcs = defaultdict(list)
        for game in games.copy():
            if not game.is_dlc:
                continue
            games.remove(game)
            dlc = self.core.get_game(game.app_name)
            if not dlc or not dlc.metadata:
                logger.warning(f'DLC "{game.app_name}" is missing metadata for some reason. '
                               f'Running "legendary list-games" may fix this.')
                continue
            main_app_name = dlc.metadata['mainGameItem']['releaseInfo'][0]['appId']
            installed_dlcs[main_app_name].append(game)

        print('\nInstalled games:')
        for game in games:
            if game.install_size == 0 and self.core.lgd.lock_installed():
                logger.debug(f'Updating missing size for {game.app_name}')
                m = self.core.load_manifest(self.core.get_installed_manifest(game.app_name)[0])
                game.install_size = sum(fm.file_size for fm in m.file_manifest_list.elements)
                self.core.install_game(game)

            print(f' * {game.title} (App name: {game.app_name} | Version: {game.version} | '
                  f'Platform: {game.platform} | {game.install_size / (1024 * 1024 * 1024):.02f} GiB)')
            if args.include_dir:
                print(f'  + Location: {game.install_path}')
            if not os.path.exists(game.install_path):
                print(f'  ! Game does no longer appear to be installed (directory "{game.install_path}" missing)!')
            elif game.app_name in versions and versions[game.app_name] != game.version:
                print(f'  -> Update available! Installed: {game.version}, Latest: {versions[game.app_name]}')
            for dlc in installed_dlcs[game.app_name]:
                print(f'  + {dlc.title} (App name: {dlc.app_name} | Version: {dlc.version}) | '
                      f'{dlc.install_size / (1024 * 1024 * 1024):.02f} GiB)')
                if dlc.app_name in versions and versions[dlc.app_name] != dlc.version:
                    print(f'   -> Update available! Installed: {dlc.version}, Latest: {versions[dlc.app_name]}')

        print(f'\nTotal: {len(games)}')

    def list_files(self, args):
        if args.platform:
            args.force_download = True

        if not args.override_manifest and not args.app_name:
            print('You must provide either a manifest url/path or app name!')
            return
        elif args.app_name:
            args.app_name = self._resolve_aliases(args.app_name)

        # check if we even need to log in
        if args.override_manifest:
            logger.info(f'Loading manifest from "{args.override_manifest}"')
            manifest_data, _ = self.core.get_uri_manifest(args.override_manifest)
        elif self.core.is_installed(args.app_name) and not args.force_download:
            logger.info(f'Loading installed manifest for "{args.app_name}"')
            manifest_data, _ = self.core.get_installed_manifest(args.app_name)
        else:
            logger.info(f'Logging in and downloading manifest for {args.app_name}')
            if not self.core.login():
                logger.error('Login failed! Cannot continue with download process.')
                exit(1)
            game = self.core.get_game(args.app_name, update_meta=True)
            if not game:
                logger.fatal(f'Could not fetch metadata for "{args.app_name}" (check spelling/account ownership)')
                exit(1)
            manifest_data, _ = self.core.get_cdn_manifest(game, platform=args.platform)

        manifest = self.core.load_manifest(manifest_data)
        files = sorted(manifest.file_manifest_list.elements,
                       key=lambda a: a.filename.lower())

        if args.install_tag:
            files = [fm for fm in files if args.install_tag in fm.install_tags]
        elif args.install_tag is not None:
            files = [fm for fm in files if not fm.install_tags]

        if args.hashlist:
            for fm in files:
                print(f'{fm.hash.hex()} *{fm.filename}')
        elif args.csv or args.tsv:
            writer = csv.writer(stdout, dialect='excel-tab' if args.tsv else 'excel', lineterminator='\n')
            writer.writerow(['path', 'hash', 'size', 'install_tags'])
            writer.writerows((fm.filename, fm.hash.hex(), fm.file_size, '|'.join(fm.install_tags)) for fm in files)
        elif args.json:
            _files = [
                dict(
                    filename=fm.filename,
                    sha_hash=fm.hash.hex(),
                    install_tags=fm.install_tags,
                    file_size=fm.file_size,
                    flags=fm.flags
                )
                for fm in files
            ]
            return self._print_json(_files, args.pretty_json)
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
        saves = self.core.get_save_games(self._resolve_aliases(args.app_name))
        last_app = ''
        print('Save games:')
        for save in sorted(saves, key=lambda a: a.app_name + a.manifest_name):
            if save.app_name != last_app:
                if game := self.core.get_game(save.app_name):
                    game_title = game.app_title
                else:
                    game_title = 'Unknown'

                last_app = save.app_name
                print(f'- {game_title} ("{save.app_name}")')
            print(' +', save.manifest_name)

    def download_saves(self, args):
        if not self.core.login():
            logger.error('Login failed! Cannot continue with download process.')
            exit(1)
        logger.info(f'Downloading saves to "{self.core.get_default_install_dir()}"')
        self.core.download_saves(self._resolve_aliases(args.app_name))

    def clean_saves(self, args):
        if not self.core.login():
            logger.error('Login failed! Cannot continue with download process.')
            exit(1)
        logger.info('Cleaning saves...')
        self.core.clean_saves(self._resolve_aliases(args.app_name), args.delete_incomplete)

    def sync_saves(self, args):
        if not self.core.login():
            logger.error('Login failed! Cannot continue with download process.')
            exit(1)

        igames = self.core.get_installed_list()
        if args.app_name:
            args.app_name = self._resolve_aliases(args.app_name)
            igame = self.core.get_installed_game(args.app_name)
            if not igame:
                logger.fatal(f'Game not installed: {args.app_name}')
                exit(1)
            igames = [igame]

        # check available saves
        saves = self.core.get_save_games(args.app_name if args.app_name else '')
        latest_save = {
            save.app_name: save for save in sorted(saves, key=lambda a: a.datetime)
        }

        logger.info(f'Got {len(latest_save)} remote save game(s)')

        # evaluate current save state for each game.
        for igame in igames:
            game = self.core.get_game(igame.app_name)
            if not game or not (game.supports_cloud_saves or game.supports_mac_cloud_saves):
                if igame.app_name in latest_save:
                    # this should never happen unless cloud save support was removed from a game
                    logger.warning(f'{igame.app_name} has remote save(s) but does not support cloud saves?!')
                continue

            logger.info(f'Checking "{igame.title}" ({igame.app_name})')
            # override save path only if app name is specified
            if args.app_name and args.save_path:
                if not self.core.lgd.lock_installed():
                    logger.error('Unable to lock install data, cannot modify save path.')
                    break
                logger.info(f'Overriding save path with "{args.save_path}"...')
                igame.save_path = args.save_path
                self.core.lgd.set_installed_game(igame.app_name, igame)

            # if there is no saved save path, try to get one, skip if we cannot get a install data lock
            if not igame.save_path and self.core.lgd.lock_installed():
                if args.yes and not args.accept_path:
                    logger.info('Save path for this title has not been set, skipping due to --yes')
                    continue

                save_path = self.core.get_save_path(igame.app_name, platform=igame.platform)

                # ask user if path is correct if computing for the first time
                logger.info(f'Computed save path: "{save_path}"')

                if '%' in save_path or '{' in save_path:
                    logger.warning('Path contains unprocessed variables, please enter the correct path manually.')
                    yn = False
                    # When accept_path is set we don't want to fall back to interactive mode
                    if args.accept_path:
                        continue
                elif args.accept_path:
                    yn = True
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
        app_name = self._resolve_aliases(args.app_name)
        addon_app_name = None

        # Interactive CrossOver setup
        if args.crossover and sys_platform == 'darwin':
            args.reset = args.download = args.disable_version_check = False
            self.crossover_setup(args)

        if args.origin:
            return self._launch_origin(args)

        igame = self.core.get_installed_game(app_name)
        if (not igame or not igame.executable) and (game := self.core.get_game(app_name)) is not None:
            # override installed game with base title
            if game.is_launchable_addon:
                addon_app_name = app_name
                app_name = game.metadata['mainGameItem']['releaseInfo'][0]['appId']
                igame = self.core.get_installed_game(app_name)

        if not igame:
            logger.error(f'Game {app_name} is not currently installed!')
            exit(1)

        if igame.is_dlc and not igame.executable:
            logger.error(f'{app_name} is DLC without an executable; please launch the base game instead!')
            exit(1)

        if not os.path.exists(igame.install_path):
            logger.fatal(f'Install directory "{igame.install_path}" appears to be deleted, cannot launch {app_name}!')
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
                try:
                    latest = self.core.get_asset(app_name, update=True, platform=igame.platform)
                except ValueError:
                    logger.fatal(f'Metadata for "{app_name}" does not exist, cannot launch!')
                    exit(1)

                if latest.build_version != igame.version:
                    logger.error('Game is out of date, please update or launch with update check skipping!')
                    exit(1)

        params = self.core.get_launch_parameters(app_name=app_name, offline=args.offline,
                                                 extra_args=extra, user=args.user_name_override,
                                                 wine_bin=args.wine_bin, wine_pfx=args.wine_pfx,
                                                 language=args.language, wrapper=args.wrapper,
                                                 disable_wine=args.no_wine,
                                                 executable_override=args.executable_override,
                                                 crossover_app=args.crossover_app,
                                                 crossover_bottle=args.crossover_bottle,
                                                 addon_app_name=addon_app_name)

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
            if sys_platform == 'darwin':
                if args.crossover_app:
                    self.core.lgd.config[app_name]['crossover_app'] = args.crossover_app
                if args.crossover_bottle:
                    self.core.lgd.config[app_name]['crossover_bottle'] = args.crossover_bottle

        if args.json:
            return self._print_json(vars(params), args.pretty_json)

        full_params = list()
        full_params.extend(params.launch_command)
        full_params.append(os.path.join(params.game_directory, params.game_executable))
        full_params.extend(params.game_parameters)
        full_params.extend(params.user_parameters)
        full_params.extend(params.egl_parameters)
        # Copying existing env vars is required on Windows, probably a good idea on Linux
        full_env = os.environ.copy()
        full_env.update(params.environment)

        if 'CX_BOTTLE' in full_env and any('SharedSupport/CrossOver' in p for p in params.launch_command):
            # if using crossover, unset WINEPREFIX
            full_env.pop('WINEPREFIX', None)
            # check that bottle is valid, show error otherwise
            bottle_name = full_env["CX_BOTTLE"].strip()
            if not mac_is_valid_bottle(bottle_name):
                if bottle_name == 'Legendary':
                    logger.error('Attempted to use default CrossOver bottle ("Legendary"), but it does not exist, '
                                 'see https://legendary.gl/crossover-setup for setup instructions.')
                else:
                    logger.error(f'Specified CrossOver bottle {bottle_name} does not exist, cannot launch.')
                exit(1)
            else:
                logger.info(f'Using CrossOver Bottle "{bottle_name}"')

        if args.dry_run:
            logger.info(f'Not Launching {app_name} (dry run)')
            if params.pre_launch_command:
                logger.info(f'Pre-Launch Command: {params.pre_launch_command}')
            logger.info(f'Launch parameters: {shlex.join(full_params)}')
            logger.info(f'Working directory: {params.working_directory}')
            if params.environment:
                logger.info('Environment overrides: {}'.format(', '.join(
                    f'{k}={v}' for k, v in params.environment.items())))
        else:
            logger.info(f'Launching {app_name}...')
            if params.pre_launch_command:
                try:
                    logger.debug(f'Running pre-launch command: {params.pre_launch_command}')
                    p = subprocess.Popen(shlex.split(params.pre_launch_command), env=full_env)
                    if params.pre_launch_wait:
                        logger.debug('Waiting for pre-launch command to finish...')
                        p.wait()
                except Exception as e:
                    logger.warning(f'Pre-launch command failed: {e!r}')

            logger.debug(f'Launch parameters: {shlex.join(full_params)}')
            logger.debug(f'Working directory: {params.working_directory}')
            if params.environment:
                logger.debug('Environment overrides: {}'.format(', '.join(
                    f'{k}={v}' for k, v in params.environment.items())))
            subprocess.Popen(full_params, cwd=params.working_directory, env=full_env)

    def _launch_origin(self, args):
        game = self.core.get_game(app_name=args.app_name)
        if not game:
            logger.error(f'Unknown game "{args.app_name}", run "legendary list-games --third-party" '
                         f'to fetch data for Origin titles before using this command.')
            return

        if not game.is_origin_game:
            logger.error(f'The specified game is not an Origin title.')
            return

        # login is not required to launch the game, but linking does require it.
        if not args.offline:
            logger.info('Logging in...')
            if not self.core.login():
                logger.error('Login failed, cannot continue!')
                exit(1)

        origin_uri = self.core.get_origin_uri(args.app_name, args.offline)
        if args.json:
            return self._print_json(dict(uri=origin_uri), args.pretty_json)

        if os.name == 'nt':
            cmd, wait_for_exit = self.core.get_pre_launch_command(args.app_name)

            if args.dry_run:
                if cmd:
                    logger.info(f'Pre-launch command: {cmd}')
                logger.info(f'Origin URI: {origin_uri}')
            else:
                if cmd:
                    try:
                        logger.debug(f'Running pre-launch command: {cmd}')
                        p = subprocess.Popen(shlex.split(cmd))
                        if wait_for_exit:
                            logger.debug('Waiting for pre-launch command to finish...')
                            p.wait()
                    except Exception as e:
                        logger.warning(f'Pre-launch command failed: {e!r}')

                logger.debug(f'Opening Origin URI: {origin_uri}')
                webbrowser.open(origin_uri)
            return

        # on linux, require users to specify at least the wine binary and prefix in config or command line
        command = self.core.get_app_launch_command(args.app_name, wrapper=args.wrapper,
                                                   wine_binary=args.wine_bin,
                                                   disable_wine=args.no_wine,
                                                   crossover_app=args.crossover_app)
        env = self.core.get_app_environment(args.app_name, wine_pfx=args.wine_pfx,
                                            cx_bottle=args.crossover_bottle)
        cmd, wait_for_exit = self.core.get_pre_launch_command(args.app_name)

        full_env = os.environ.copy()
        full_env.update(env)

        if 'CX_BOTTLE' in full_env and any('SharedSupport/CrossOver' in p for p in command):
            # if using crossover, unset WINEPREFIX
            full_env.pop('WINEPREFIX', None)
            # check that bottle is valid, show error otherwise
            bottle_name = full_env["CX_BOTTLE"].strip()
            if not mac_is_valid_bottle(bottle_name):
                if bottle_name == 'Legendary':
                    logger.error('Attempted to use default CrossOver bottle ("Legendary"), but it does not exist, '
                                 'see https://legendary.gl/crossover-setup for setup instructions.')
                else:
                    logger.error(f'Specified CrossOver bottle {bottle_name} does not exist, cannot launch.')
                exit(1)
            else:
                logger.info(f'Using CrossOver Bottle "{bottle_name}"')

        if not command:
            logger.error(f'In order to launch Origin correctly you must specify a prefix and wine binary or '
                         f'wrapper in the configuration file or command line. See the README for details.')
            return

        # You cannot launch a URI without start.exe
        command.append('start')
        command.append(origin_uri)
        if args.dry_run:
            if cmd:
                logger.info(f'Pre-launch command: {cmd}')
            logger.info(f'Origin launch command: {shlex.join(command)}')
        else:
            if cmd:
                try:
                    logger.debug(f'Running pre-launch command: {cmd}')
                    p = subprocess.Popen(shlex.split(cmd), env=full_env)
                    if wait_for_exit:
                        logger.debug('Waiting for pre-launch command to finish...')
                        p.wait()
                except Exception as e:
                    logger.warning(f'Pre-launch command failed: {e!r}')

            logger.debug(f'Opening Origin URI with command: {shlex.join(command)}')
            subprocess.Popen(command, env=full_env)

    def install_game(self, args):
        if not self.core.lgd.lock_installed():
            logger.fatal('Failed to acquire installed data lock, only one instance of Legendary may '
                         'install/import/move applications at a time.')
            return

        args.app_name = self._resolve_aliases(args.app_name)
        if self.core.is_installed(args.app_name):
            igame = self.core.get_installed_game(args.app_name)
            args.platform = igame.platform
            if igame.needs_verification and not args.repair_mode:
                logger.info('Game needs to be verified before updating, switching to repair mode...')
                args.repair_mode = True

        repair_file = None
        if args.subparser_name == 'download':
            logger.info('Setting --no-install flag since "download" command was used')
            args.no_install = True
        elif args.subparser_name == 'repair' or args.repair_mode:
            args.repair_mode = True
            args.no_install = args.repair_and_update is False
            repair_file = os.path.join(self.core.lgd.get_tmp_path(), f'{args.app_name}.repair')

        if not self.core.login():
            logger.error('Login failed! Cannot continue with download process.')
            exit(1)

        if args.file_prefix or args.file_exclude_prefix:
            args.no_install = True

        if args.update_only:
            if not self.core.is_installed(args.app_name):
                logger.error(f'Update requested for "{args.app_name}", but app not installed!')
                exit(1)

        game = self.core.get_game(args.app_name, update_meta=True, platform=args.platform)

        if not game:
            logger.error(f'Could not find "{args.app_name}" in list of available games, '
                         f'did you type the name correctly?')
            exit(1)

        if store := game.third_party_store:
            logger.error(f'The selected title has to be installed via a third-party store: {store}')
            if game.is_origin_game:
                logger.info(f'For Origin games use "legendary launch --origin {args.app_name}" to '
                            f'activate and/or run the game.')
            exit(0)

        if args.platform not in game.asset_infos:
            if not args.no_install:
                if self.core.lgd.config.getboolean('Legendary', 'install_platform_fallback', fallback=True):
                    logger.warning(f'App has no asset for platform "{args.platform}", falling back to "Windows".')
                    args.platform = 'Windows'
                else:
                    logger.error(f'No app asset found for platform "{args.platform}", run '
                                 f'"legendary info --platform {args.platform}" and make '
                                 f'sure the app is available for the specified platform.')
                    exit(1)
            else:
                logger.warning(f'No asset found for platform "{args.platform}", '
                               f'trying anyway since --no-install is set.')

        if game.is_dlc:
            logger.info('Install candidate is DLC')
            app_name = game.metadata['mainGameItem']['releaseInfo'][0]['appId']
            base_game = self.core.get_game(app_name)
            # check if base_game is actually installed
            if not self.core.is_installed(app_name):
                # download mode doesn't care about whether something's installed
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

                try:
                    self.verify_game(args, print_command=False, repair_mode=True, repair_online=args.repair_and_update)
                except ValueError:
                    logger.error('To repair a game with a missing manifest you must run the command with '
                                 '"--repair-and-update". However this will redownload any file that does '
                                 'not match the current hash in its entirety.')
                    return
            else:
                logger.info(f'Using existing repair file: {repair_file}')

        # check if SDL should be disabled
        sdl_enabled = not args.install_tag and not game.is_dlc
        config_tags = self.core.lgd.config.get(game.app_name, 'install_tags', fallback=None)
        config_disable_sdl = self.core.lgd.config.getboolean(game.app_name, 'disable_sdl', fallback=False)
        # remove config flag if SDL is reset
        if config_disable_sdl and args.reset_sdl and not args.disable_sdl:
            self.core.lgd.config.remove_option(game.app_name, 'disable_sdl')
        # if config flag is not yet set, set it and remove previous install tags
        elif not config_disable_sdl and args.disable_sdl:
            logger.info('Clearing install tags from config and disabling SDL for title.')
            if config_tags:
                self.core.lgd.config.remove_option(game.app_name, 'install_tags')
                config_tags = None
            self.core.lgd.config.set(game.app_name, 'disable_sdl', 'true')
            sdl_enabled = False
        # just disable SDL, but keep config tags that have been manually specified
        elif config_disable_sdl or args.disable_sdl:
            sdl_enabled = False

        if sdl_enabled and ((sdl_name := get_sdl_appname(game.app_name)) is not None):
            if not self.core.is_installed(game.app_name) or config_tags is None or args.reset_sdl:
                sdl_data = self.core.get_sdl_data(sdl_name, platform=args.platform)
                if sdl_data:
                    if args.skip_sdl:
                        args.install_tag = ['']
                        if '__required' in sdl_data:
                            args.install_tag.extend(sdl_data['__required']['tags'])
                    else:
                        args.install_tag = sdl_prompt(sdl_data, game.app_title)
                    self.core.lgd.config.set(game.app_name, 'install_tags', ','.join(args.install_tag))
                else:
                    logger.error(f'Unable to get SDL data for {sdl_name}')
            else:
                args.install_tag = config_tags.split(',')
        elif args.install_tag and not game.is_dlc and not args.no_install:
            config_tags = ','.join(args.install_tag)
            logger.info(f'Saving install tags for "{game.app_name}" to config: {config_tags}')
            self.core.lgd.config.set(game.app_name, 'install_tags', config_tags)
        elif not game.is_dlc:
            if config_tags and args.reset_sdl:
                logger.info('Clearing install tags from config.')
                self.core.lgd.config.remove_option(game.app_name, 'install_tags')
            elif config_tags:
                logger.info(f'Using install tags from config: {config_tags}')
                args.install_tag = config_tags.split(',')

        logger.info(f'Preparing download for "{game.app_title}" ({game.app_name})...')
        # todo use status queue to print progress from CLI
        # This has become a little ridiculous hasn't it?
        dlm, analysis, igame = self.core.prepare_download(game=game, base_game=base_game, base_path=args.base_path,
                                                          force=args.force, max_shm=args.shared_memory,
                                                          max_workers=args.max_workers, game_folder=args.game_folder,
                                                          disable_patching=args.disable_patching,
                                                          override_manifest=args.override_manifest,
                                                          override_old_manifest=args.override_old_manifest,
                                                          override_base_url=args.override_base_url,
                                                          platform=args.platform,
                                                          file_prefix_filter=args.file_prefix,
                                                          file_exclude_filter=args.file_exclude_prefix,
                                                          file_install_tag=args.install_tag,
                                                          dl_optimizations=args.order_opt,
                                                          dl_timeout=args.dl_timeout,
                                                          repair=args.repair_mode,
                                                          repair_use_latest=args.repair_and_update,
                                                          disable_delta=args.disable_delta,
                                                          override_delta_manifest=args.override_delta_manifest,
                                                          preferred_cdn=args.preferred_cdn,
                                                          disable_https=args.disable_https,
                                                          bind_ip=args.bind_ip)

        # game is either up-to-date or hasn't changed, so we have nothing to do
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

            if old_igame.install_tags:
                self.core.lgd.config.set(game.app_name, 'install_tags', ','.join(old_igame.install_tags))
                self.core.lgd.save_config()

            # check if the version changed, this can happen for DLC that gets a version bump with no actual file changes
            if old_igame and old_igame.version != igame.version:
                old_igame.version = igame.version
                self.core.install_game(old_igame)

            exit(0)

        logger.info(f'Install size: {analysis.install_size / 1024 / 1024:.02f} MiB')
        compression = (1 - (analysis.dl_size / analysis.uncompressed_dl_size)) * 100
        logger.info(f'Download size: {analysis.dl_size / 1024 / 1024:.02f} MiB '
                    f'(Compression savings: {compression:.01f}%)')
        logger.info(f'Reusable size: {analysis.reuse_size / 1024 / 1024:.02f} MiB (chunks) / '
                    f'{analysis.unchanged / 1024 / 1024:.02f} MiB (unchanged / skipped)')
        logger.info('Downloads are resumable, you can interrupt the download with '
                    'CTRL-C and resume it using the same command later on.')

        res = self.core.check_installation_conditions(analysis=analysis, install=igame, game=game,
                                                      updating=self.core.is_installed(args.app_name),
                                                      ignore_space_req=args.ignore_space)

        if res.warnings or res.failures:
            print('\nInstallation requirements check returned the following results:')

        if res.warnings:
            for warn in sorted(res.warnings):
                print(' - Warning:', warn)
            if not res.failures:
                print()

        if res.failures:
            for msg in sorted(res.failures):
                print(' ! Failure:', msg)
            print()
            logger.fatal('Installation cannot proceed, exiting.')
            exit(1)

        if tip_url := self.core.get_game_tip(igame.app_name):
            print(f'\nThis game may have compatibility issues or require additional setup, see: {tip_url}\n')

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
                if (game.supports_cloud_saves or game.supports_mac_cloud_saves) and args.save_path:
                    igame.save_path = args.save_path

                postinstall = self.core.install_game(igame)
                if postinstall:
                    self._handle_postinstall(postinstall, igame, skip_prereqs=args.yes)

                dlcs = self.core.get_dlc_for_game(game.app_name)
                if dlcs and not args.skip_dlcs:
                    print('\nThe following DLCs are available for this game:')
                    for dlc in dlcs:
                        print(f' - {dlc.app_title} (App name: {dlc.app_name}, version: '
                              f'{dlc.app_version(args.platform)})')
                    print('\nYou can manually install these later by running this command with the DLC\'s app name.')

                    install_dlcs = not args.skip_dlcs
                    if not args.yes and not args.with_dlcs and not args.skip_dlcs:
                        if not get_boolean_choice(f'Do you wish to automatically install DLCs?'):
                            install_dlcs = False

                    if install_dlcs:
                        _yes, _app_name = args.yes, args.app_name
                        args.yes = True
                        for dlc in dlcs:
                            args.app_name = dlc.app_name
                            self.install_game(args)
                        args.yes, args.app_name = _yes, _app_name
                    else:
                        print('')

                if (game.supports_cloud_saves or game.supports_mac_cloud_saves) and not game.is_dlc:
                    # todo option to automatically download saves after the installation
                    #  args does not have the required attributes for sync_saves in here,
                    #  not sure how to solve that elegantly.
                    logger.info(f'This game supports cloud saves, syncing is handled by the "sync-saves" command. '
                                f'To download saves for this game run "legendary sync-saves {args.app_name}"')

                # show tip again after installation finishes so users hopefully actually see it
                if tip_url := self.core.get_game_tip(igame.app_name):
                    print(f'\nThis game may require additional setup, see: {tip_url}\n')

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

    def _handle_postinstall(self, postinstall, igame, skip_prereqs=False):
        print('\nThis game lists the following prerequisites to be installed:')
        print(f'- {postinstall["name"]}: {" ".join((postinstall["path"], postinstall["args"]))}')
        print('')

        if os.name == 'nt':
            if skip_prereqs:
                c = 'n'  # we don't want to launch anything, just silent install.
            else:
                choice = input('Do you wish to install the prerequisites? ([y]es, [n]o, [i]gnore): ')
                c = choice.lower()[0]
                print('')

            if c == 'i':  # just set it to installed
                logger.info('Marking prerequisites as installed...')
                self.core.prereq_installed(igame.app_name)
            elif c == 'y':  # set to installed and launch installation
                logger.info('Launching prerequisite executable..')
                self.core.prereq_installed(igame.app_name)
                req_path, req_exec = os.path.split(postinstall['path'])
                work_dir = os.path.join(igame.install_path, req_path)
                fullpath = os.path.join(work_dir, req_exec)
                try:
                    p = subprocess.Popen([fullpath, postinstall['args']], cwd=work_dir, shell=True)
                    p.wait()
                except Exception as e:
                    logger.error(f'Failed to run prereq executable with: {e!r}')
        else:
            logger.info('Automatic installation not available on Linux.')

    def uninstall_game(self, args):
        if not self.core.lgd.lock_installed():
            logger.fatal('Failed to acquire installed data lock, only one instance of Legendary may '
                         'install/import/move applications at a time.')
            return

        args.app_name = self._resolve_aliases(args.app_name)
        igame = self.core.get_installed_game(args.app_name)
        if not igame:
            logger.error(f'Game {args.app_name} not installed, cannot uninstall!')
            exit(0)

        if not args.yes:
            if not get_boolean_choice(f'Do you wish to uninstall "{igame.title}"?', default=False):
                print('Aborting...')
                exit(0)

        if os.name == 'nt' and igame.uninstaller and not args.skip_uninstaller:
            self._handle_uninstaller(igame, args.yes)

        try:
            if not igame.is_dlc:
                # Remove DLC first so directory is empty when game uninstall runs
                dlcs = self.core.get_dlc_for_game(igame.app_name)
                for dlc in dlcs:
                    if (idlc := self.core.get_installed_game(dlc.app_name)) is not None:
                        logger.info(f'Uninstalling DLC "{dlc.app_name}"...')
                        self.core.uninstall_game(idlc, delete_files=not args.keep_files)

            logger.info(f'Removing "{igame.title}" from "{igame.install_path}"...')
            self.core.uninstall_game(igame, delete_files=not args.keep_files,
                                     delete_root_directory=not igame.is_dlc)
            logger.info('Game has been uninstalled.')
        except Exception as e:
            logger.warning(f'Removing game failed: {e!r}, please remove {igame.install_path} manually.')

    def _handle_uninstaller(self, igame, yes=False):
        uninstaller = igame.uninstaller

        print('\nThis game provides the following uninstaller:')
        print(f'- {uninstaller["path"]} {uninstaller["args"]}\n')
        
        if yes or get_boolean_choice('Do you wish to run the uninstaller?', default=True):
            logger.info('Running uninstaller...')
            req_path, req_exec = os.path.split(uninstaller['path'])
            work_dir = os.path.join(igame.install_path, req_path)
            fullpath = os.path.join(work_dir, req_exec)
            try:
                p = subprocess.Popen([fullpath, uninstaller['args']], cwd=work_dir, shell=True)
                p.wait()
            except Exception as e:
                logger.error(f'Failed to run uninstaller: {e!r}')

    def verify_game(self, args, print_command=True, repair_mode=False, repair_online=False):
        args.app_name = self._resolve_aliases(args.app_name)
        if not self.core.is_installed(args.app_name):
            logger.error(f'Game "{args.app_name}" is not installed')
            return

        logger.info(f'Loading installed manifest for "{args.app_name}"')
        igame = self.core.get_installed_game(args.app_name)
        if not os.path.exists(igame.install_path):
            logger.error(f'Install path "{igame.install_path}" does not exist, make sure all necessary mounts '
                         f'are available. If you previously deleted the game folder without uninstalling, run '
                         f'"legendary uninstall -y {igame.app_name}" and reinstall from scratch.')
            return

        manifest_data, _ = self.core.get_installed_manifest(args.app_name)
        if manifest_data is None:
            if repair_mode:
                if not repair_online:
                    logger.critical('No manifest could be loaded, the manifest file may be missing!')
                    raise ValueError('Local manifest is missing')

                logger.warning('No manifest could be loaded, the file may be missing. Downloading the latest manifest.')
                game = self.core.get_game(args.app_name, platform=igame.platform)
                manifest_data, _ = self.core.get_cdn_manifest(game, igame.platform)
            else:
                logger.critical(f'Manifest appears to be missing! To repair, run "legendary repair '
                                f'{args.app_name} --repair-and-update", this will however redownload all files '
                                f'that do not match the latest manifest in their entirety.')
                return

        manifest = self.core.load_manifest(manifest_data)

        files = sorted(manifest.file_manifest_list.elements,
                       key=lambda a: a.filename.lower())

        # build list of hashes
        if (config_tags := self.core.lgd.config.get(args.app_name, 'install_tags', fallback=None)) is not None:
            install_tags = set(i.strip() for i in config_tags.split(','))
            file_list = [
                (f.filename, f.sha_hash.hex())
                for f in files
                if any(it in install_tags for it in f.install_tags) or not f.install_tags
            ]
        else:
            file_list = [(f.filename, f.sha_hash.hex()) for f in files]

        total = len(file_list)
        total_size = sum(manifest.file_manifest_list.get_file_by_path(fm[0]).file_size
                         for fm in file_list)
        num = processed = last_processed = 0
        speed = 0.0
        percentage = 0.0
        failed = []
        missing = []

        last_update = time.time()

        logger.info(f'Verifying "{igame.title}" version "{manifest.meta.build_version}"')
        repair_file = []
        for result, path, result_hash, bytes_read in validate_files(igame.install_path, file_list):
            processed += bytes_read
            percentage = (processed / total_size) * 100.0
            num += 1

            if (delta := ((current_time := time.time()) - last_update)) > 1:
                last_update = current_time
                speed = (processed - last_processed) / 1024 / 1024 / delta
                last_processed = processed

            stdout.write(f'Verification progress: {num}/{total} ({percentage:.01f}%) [{speed:.1f} MiB/s]\t\r')
            stdout.flush()

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

        stdout.write(f'Verification progress: {num}/{total} ({percentage:.01f}%) [{speed:.1f} MiB/s]\t\n')

        # always write repair file, even if all match
        if repair_file:
            repair_filename = os.path.join(self.core.lgd.get_tmp_path(), f'{args.app_name}.repair')
            with open(repair_filename, 'w', encoding='utf-8') as f:
                f.write('\n'.join(repair_file))
            logger.debug(f'Written repair file to "{repair_filename}"')

        if not missing and not failed:
            logger.info('Verification finished successfully.')
        else:
            logger.error(f'Verification failed, {len(failed)} file(s) corrupted, {len(missing)} file(s) are missing.')
            if print_command:
                logger.info(f'Run "legendary repair {args.app_name}" to repair your game installation.')

    def import_game(self, args):
        if not self.core.lgd.lock_installed():
            logger.fatal('Failed to acquire installed data lock, only one instance of Legendary may '
                         'install/import/move applications at a time.')
            return

        # make sure path is absolute
        args.app_path = os.path.abspath(args.app_path)
        args.app_name = self._resolve_aliases(args.app_name)

        if not os.path.exists(args.app_path):
            logger.error(f'Specified path "{args.app_path}" does not exist!')
            return

        if self.core.is_installed(args.app_name):
            logger.error('Game is already installed!')
            return

        if not self.core.login():
            logger.error('Log in failed!')
            return

        # do some basic checks
        game = self.core.get_game(args.app_name, update_meta=True, platform=args.platform)
        if not game:
            logger.fatal(f'Did not find game "{args.app_name}" on account.')
            return

        if game.is_dlc:
            release_info = game.metadata.get('mainGameItem', {}).get('releaseInfo')
            if release_info:
                main_game_appname = release_info[0]['appId']
                main_game_title = game.metadata['mainGameItem']['title']
                if not self.core.is_installed(main_game_appname):
                    logger.error(f'Import candidate is DLC but base game "{main_game_title}" '
                                 f'(App name: "{main_game_appname}") is not installed!')
                    return
            else:
                logger.fatal(f'Unable to get base game information for DLC, cannot continue.')
                return

        # get everything needed for import from core, then run additional checks.
        manifest, igame = self.core.import_game(game, args.app_path, platform=args.platform)
        exe_path = os.path.join(args.app_path, manifest.meta.launch_exe.lstrip('/'))
        if os.name != 'nt':
            exe_path = case_insensitive_file_search(exe_path)
        # check if most files at least exist or if user might have specified the wrong directory
        total = len(manifest.file_manifest_list.elements)
        found = sum(os.path.exists(os.path.join(args.app_path, f.filename))
                    for f in manifest.file_manifest_list.elements)
        ratio = found / total

        if not found:
            logger.error(f'No files belonging to {"DLC" if game.is_dlc else "Game"} "{game.app_title}" '
                         f'({game.app_name}) found in the specified location, please verify that the path is correct.')
            if not game.is_dlc:
                # check if game folder is in path, suggest alternative
                folder = game.metadata.get('customAttributes', {}).get('FolderName', {}).get('value', game.app_name)
                if folder and folder not in args.app_path:
                    new_path = os.path.join(args.app_path, folder)
                    logger.info(f'Did you mean "{new_path}"?')
            return

        if not game.is_dlc and not os.path.exists(exe_path) and not args.disable_check:
            logger.error(f'Game executable could not be found at "{exe_path}", '
                         f'please verify that the specified path is correct.')
            return

        if ratio < 0.95:
            logger.warning('Some files are missing from the game installation, install may not '
                           'match latest Epic Games Store version or might be corrupted.')
        else:
            logger.info(f'{"DLC" if game.is_dlc else "Game"} install appears to be complete.')

        self.core.install_game(igame)
        if igame.needs_verification:
            logger.info(f'NOTE: The {"DLC" if game.is_dlc else "Game"} installation will have to be '
                        f'verified before it can be updated with legendary.')
            logger.info(f'Run "legendary repair {args.app_name}" to do so.')
        else:
            logger.info(f'Installation had Epic Games Launcher metadata for version "{igame.version}", '
                        f'verification will not be required.')

        # check for importable DLC
        if not args.skip_dlcs:
            dlcs = self.core.get_dlc_for_game(game.app_name)
            if dlcs:
                logger.info(f'Found {len(dlcs)} items of DLC that could be imported.')
                import_dlc = True
                if not args.yes and not args.with_dlcs:
                    if not get_boolean_choice(f'Do you wish to automatically attempt to import all DLCs?'):
                        import_dlc = False

                if import_dlc:
                    for dlc in dlcs:
                        args.app_name = dlc.app_name
                        self.import_game(args)

        logger.info(f'{"DLC" if game.is_dlc else "Game"} "{game.app_title}" has been imported.')

    def egs_sync(self, args):
        if not self.core.lgd.lock_installed():
            logger.fatal('Failed to acquire installed data lock, only one instance of Legendary may '
                         'install/import/move applications at a time.')
            return

        if args.unlink:
            logger.info('Unlinking and resetting EGS and LGD sync...')
            self.core.lgd.config.remove_option('Legendary', 'egl_programdata')
            self.core.lgd.config.remove_option('Legendary', 'egl_sync')
            # remove EGL GUIDs from all games, DO NOT remove .egstore folders because that would fuck things up.
            for igame in self.core.get_installed_list():
                if not igame.egl_guid:
                    continue
                igame.egl_guid = ''
                self.core.install_game(igame)
            # todo track which games were imported, remove those from LGD and exported ones from EGL
            logger.info('NOTE: All games are still available in Legendary and EGL, but future changes '
                        'will not be synced. This may cause issues when trying to update/uninstall games.')
            return
        elif args.disable_sync:
            logger.info('Disabling EGS/LGD sync...')
            self.core.lgd.config.remove_option('Legendary', 'egl_sync')
            return

        if not self.core.lgd.assets:
            logger.error('Legendary is missing game metadata, please login (if not already) and use the '
                         '"status" command to fetch necessary information to set-up syncing.')
            return

        if args.migrate:
            logger.info('Migration enabled, this will remove the games from EGL, but not uninstall them.')
            args.import_only = args.one_shot = True

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

                print('\nNote: Only games that are also in Legendary\'s database are listed, '
                      'if anything is missing run "list-games" first to update it.')

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
        if not self.core.egl_sync_enabled and not args.one_shot and not args.migrate:
            if not args.enable_sync:
                args.enable_sync = args.yes or get_boolean_choice('Enable automatic synchronization?')
                if not args.enable_sync:  # if user chooses no, still run the sync once
                    self.core.egl_sync()
            self.core.lgd.config.set('Legendary', 'egl_sync', str(args.enable_sync))
        elif args.migrate:
            # migration also disables sync
            logger.info('Disabling automatic sync (if enabled) and removing EGL link to finish migration...')
            self.core.lgd.config.remove_option('Legendary', 'egl_programdata')
            self.core.lgd.config.remove_option('Legendary', 'egl_sync')

            for igame in self.core.get_installed_list():
                if not igame.egl_guid:
                    continue
                self.core.egl_uninstall(igame)
                igame.egl_guid = ''
                self.core.install_game(igame)

            logger.info('Migration complete. Your games will now be exclusively managed by Legendary.')
        else:
            self.core.egl_sync()

    def status(self, args):
        if not args.offline:
            try:
                if not self.core.login():
                    logger.error('Log in failed!')
                    exit(1)
            except ValueError:
                pass
            # if automatic checks are off force an update here
            self.core.check_for_updates(force=True)

        if not self.core.lgd.userdata:
            user_name = '<not logged in>'
            args.offline = True
        else:
            user_name = self.core.lgd.userdata['displayName']

        games_available = len(self.core.get_game_list(update_assets=not args.offline))
        games_installed = len(self.core.get_installed_list())
        if args.json:
            return self._print_json(dict(
                account=user_name,
                games_available=games_available,
                games_installed=games_installed,
                egl_sync_enabled=self.core.egl_sync_enabled,
                config_directory=self.core.lgd.path
            ), args.pretty_json)

        print(f'Epic account: {user_name}')
        print(f'Games available: {games_available}')
        print(f'Games installed: {games_installed}')
        print(f'EGL Sync enabled: {self.core.egl_sync_enabled}')
        print(f'Config directory: {self.core.lgd.path}')
        print(f'Platform (System): {platform()} ({os.name})')
        print(f'\nLegendary version: {__version__} - "{__codename__}"')
        print(f'Update available: {"yes" if self.core.update_available else "no"}')
        if self.core.update_available:
            if update_info := self.core.get_update_info():
                print(f'- New version: {update_info["version"]} - "{update_info["name"]}"')
                print(f'- Release summary:\n{update_info["summary"]}\n- Release URL: {update_info["gh_url"]}')
                if update_info['critical']:
                    print('! This update is recommended as it fixes major issues.')
            # prevent update message on close
            self.core.update_available = False

    def info(self, args):
        name_or_path = args.app_name_or_manifest
        app_name = manifest_uri = None
        if os.path.exists(name_or_path) or name_or_path.startswith('http'):
            manifest_uri = name_or_path
        else:
            app_name = self._resolve_aliases(name_or_path)

        if not args.offline and not manifest_uri:
            try:
                if not self.core.login():
                    logger.error('Log in failed!')
                    exit(1)
            except ValueError:
                pass

        # lists that will be printed or turned into JSON data
        info_items = dict(game=list(), manifest=list(), install=list())
        InfoItem = namedtuple('InfoItem', ['name', 'json_name', 'value', 'json_value'])

        if self.core.is_installed(app_name):
            installed_platform = self.core.get_installed_game(app_name).platform
            if installed_platform != args.platform:
                logger.warning(f'Game is installed for platform "{installed_platform}", '
                               f'but requested metadata is for "{args.platform}", this may '
                               f'lead to unexpected results.')

        game = self.core.get_game(app_name, update_meta=not args.offline, platform=args.platform)
        if game and not self.core.asset_available(game, platform=args.platform):
            logger.warning(f'Asset information for "{game.app_name}" is missing, this may be due to the game '
                           f'not being available on the selected platform or currently logged-in account.')
            args.offline = True

        manifest_data = None
        entitlements = None
        # load installed manifest or URI
        if args.offline or manifest_uri:
            if app_name and self.core.is_installed(app_name):
                manifest_data, _ = self.core.get_installed_manifest(app_name)
            elif manifest_uri and manifest_uri.startswith('http'):
                r = self.core.egs.unauth_session.get(manifest_uri)
                r.raise_for_status()
                manifest_data = r.content
            elif manifest_uri and os.path.exists(manifest_uri):
                with open(manifest_uri, 'rb') as f:
                    manifest_data = f.read()
            else:
                logger.info('Game not installed and offline mode enabled, cannot load manifest.')
        elif game:
            entitlements = self.core.egs.get_user_entitlements_full()
            egl_meta = self.core.egs.get_game_info(game.namespace, game.catalog_item_id)
            game.metadata = egl_meta
            # Get manifest if asset exists for current platform
            if args.platform in game.asset_infos:
                manifest_data, _ = self.core.get_cdn_manifest(game, args.platform)

        if game:
            game_infos = info_items['game']
            game_infos.append(InfoItem('App name', 'app_name', game.app_name, game.app_name))
            game_infos.append(InfoItem('Title', 'title', game.app_title, game.app_title))
            game_infos.append(InfoItem('Latest version', 'version', game.app_version(args.platform),
                                       game.app_version(args.platform)))
            all_versions = {k: v.build_version for k, v in game.asset_infos.items()}
            game_infos.append(InfoItem('All versions', 'platform_versions', all_versions, all_versions))
            # Cloud save support for Mac and Windows
            game_infos.append(InfoItem('Cloud saves supported', 'cloud_saves_supported',
                                       game.supports_cloud_saves or game.supports_mac_cloud_saves,
                                       game.supports_cloud_saves or game.supports_mac_cloud_saves))
            cs_dir = None
            if game.supports_cloud_saves:
                cs_dir = game.metadata['customAttributes']['CloudSaveFolder']['value']
            game_infos.append(InfoItem('Cloud save folder (Windows)', 'cloud_save_folder', cs_dir, cs_dir))

            cs_dir = None
            if game.supports_mac_cloud_saves:
                cs_dir = game.metadata['customAttributes']['CloudSaveFolder_MAC']['value']
            game_infos.append(InfoItem('Cloud save folder (Mac)', 'cloud_save_folder_mac', cs_dir, cs_dir))

            game_infos.append(InfoItem('Is DLC', 'is_dlc', game.is_dlc, game.is_dlc))

            external_activation = game.third_party_store or game.partner_link_type
            game_infos.append(InfoItem('Activates on external platform', 'external_activation',
                                       external_activation or 'No', external_activation))

            # Find custom launch options, if available
            launch_options = []
            i = 1
            while f'extraLaunchOption_{i:03d}_Name' in game.metadata.get('customAttributes', {}):
                launch_options.append((
                    game.metadata['customAttributes'][f'extraLaunchOption_{i:03d}_Name']['value'],
                    game.metadata['customAttributes'][f'extraLaunchOption_{i:03d}_Args']['value']
                ))
                i += 1

            if launch_options:
                human_list = []
                json_list = []
                for opt_name, opt_cmd in sorted(launch_options):
                    human_list.append(f'Name: "{opt_name}", Parameters: {opt_cmd}')
                    json_list.append(dict(name=opt_name, parameters=opt_cmd))
                game_infos.append(InfoItem('Extra launch options', 'launch_options',
                                           human_list, json_list))
            else:
                game_infos.append(InfoItem('Extra launch options', 'launch_options', None, []))

            game_infos.append(InfoItem('Command Line', 'command_line', game.additional_command_line,
                                       game.additional_command_line))

            # list all owned DLC based on entitlements
            if entitlements and not game.is_dlc:
                owned_entitlements = {i['entitlementName'] for i in entitlements}
                owned_app_names = {g.app_name for g in self.core.get_assets(args.platform)}
                owned_dlc = []
                for dlc in game.metadata.get('dlcItemList', []):
                    installable = dlc.get('releaseInfo', None)
                    if dlc['entitlementName'] in owned_entitlements:
                        owned_dlc.append((installable, None, dlc['title'], dlc['id']))
                    elif installable:
                        dlc_app_name = dlc['releaseInfo'][0]['appId']
                        if dlc_app_name in owned_app_names:
                            owned_dlc.append((installable, dlc_app_name, dlc['title'], dlc['id']))

                if owned_dlc:
                    human_list = []
                    json_list = []
                    for installable, dlc_app_name, title, dlc_id in owned_dlc:
                        json_list.append(dict(app_name=dlc_app_name, title=title,
                                              installable=installable, id=dlc_id))
                        if installable:
                            human_list.append(f'App name: {dlc_app_name}, Title: "{title}"')
                        else:
                            human_list.append(f'Title: "{title}" (no installation required)')
                    game_infos.append(InfoItem('Owned DLC', 'owned_dlc', human_list, json_list))
                else:
                    game_infos.append(InfoItem('Owned DLC', 'owned_dlc', None, []))
            else:
                game_infos.append(InfoItem('Owned DLC', 'owned_dlc', None, []))

            igame = self.core.get_installed_game(app_name)
            if igame:
                installation_info = info_items['install']
                installation_info.append(InfoItem('Platform', 'platform', igame.platform, igame.platform))
                installation_info.append(InfoItem('Version', 'version', igame.version, igame.version))
                disk_size_human = f'{igame.install_size / 1024 / 1024 / 1024:.02f} GiB'
                installation_info.append(InfoItem('Install size', 'disk_size', disk_size_human,
                                                  igame.install_size))
                installation_info.append(InfoItem('Install path', 'install_path', igame.install_path,
                                                  igame.install_path))
                installation_info.append(InfoItem('Save data path', 'save_path', igame.save_path,
                                                  igame.save_path))
                installation_info.append(InfoItem('EGL sync GUID', 'synced_egl_guid', igame.egl_guid,
                                                  igame.egl_guid))
                if igame.install_tags:
                    tags = ', '.join(igame.install_tags)
                else:
                    tags = '(None, all game data selected for install)'
                installation_info.append(InfoItem('Install tags', 'install_tags', tags, igame.install_tags))
                installation_info.append(InfoItem('Requires ownership verification token (DRM)', 'requires_ovt',
                                                  igame.requires_ot, igame.requires_ot))

                installed_dlc_human = []
                installed_dlc_json = []
                for dlc in game.metadata.get('dlcItemList', []):
                    if not dlc.get('releaseInfo', None):
                        continue
                    app_name = dlc['releaseInfo'][0]['appId']
                    if igame := self.core.get_installed_game(app_name):
                        installed_dlc_json.append(dict(app_name=igame.app_name, title=igame.title,
                                                       install_size=igame.install_size))
                        installed_dlc_human.append('App name: {}, Title: "{}", Size: {:.02f} GiB'.format(
                            igame.app_name, igame.title, igame.install_size / 1024 / 1024 / 1024
                        ))
                installation_info.append(InfoItem('Installed DLC', 'installed_dlc',
                                                  installed_dlc_human or None,
                                                  installed_dlc_json))

        if manifest_data:
            manifest_info = info_items['manifest']
            manifest = self.core.load_manifest(manifest_data)
            manifest_size = len(manifest_data)
            manifest_size_human = f'{manifest_size / 1024:.01f} KiB'
            manifest_info.append(InfoItem('Manifest size', 'size', manifest_size_human, manifest_size))
            manifest_type = 'JSON' if hasattr(manifest, 'json_data') else 'Binary'
            manifest_info.append(InfoItem('Manifest type', 'type', manifest_type, manifest_type.lower()))
            manifest_info.append(InfoItem('Manifest version', 'version', manifest.version, manifest.version))
            manifest_info.append(InfoItem('Manifest feature level', 'feature_level',
                                          manifest.meta.feature_level, manifest.meta.feature_level))
            manifest_info.append(InfoItem('Manifest app name', 'app_name', manifest.meta.app_name,
                                          manifest.meta.app_name))
            manifest_info.append(InfoItem('Launch EXE', 'launch_exe',
                                          manifest.meta.launch_exe or 'N/A',
                                          manifest.meta.launch_exe))
            manifest_info.append(InfoItem('Launch Command', 'launch_command',
                                          manifest.meta.launch_command or '(None)',
                                          manifest.meta.launch_command))
            manifest_info.append(InfoItem('Build version', 'build_version', manifest.meta.build_version,
                                          manifest.meta.build_version))
            manifest_info.append(InfoItem('Build ID', 'build_id', manifest.meta.build_id,
                                          manifest.meta.build_id))
            if manifest.meta.prereq_ids:
                human_list = [
                    f'Prerequisite IDs: {", ".join(manifest.meta.prereq_ids)}',
                    f'Prerequisite name: {manifest.meta.prereq_name}',
                    f'Prerequisite path: {manifest.meta.prereq_path}',
                    f'Prerequisite args: {manifest.meta.prereq_args or "(None)"}',
                ]
                manifest_info.append(InfoItem('Prerequisites', 'prerequisites', human_list,
                                              dict(ids=manifest.meta.prereq_ids,
                                                   name=manifest.meta.prereq_name,
                                                   path=manifest.meta.prereq_path,
                                                   args=manifest.meta.prereq_args)))
            else:
                manifest_info.append(InfoItem('Prerequisites', 'prerequisites', None, None))

            if manifest.meta.uninstall_action_path:
                human_list = [
                    f'Uninstaller path: {manifest.meta.uninstall_action_path}',
                    f'Uninstaller args: {manifest.meta.uninstall_action_args or "(None)"}',
                ]
                manifest_info.append(InfoItem('Uninstaller', 'uninstaller', human_list,
                                              dict(path=manifest.meta.uninstall_action_path,
                                                   args=manifest.meta.uninstall_action_args)))
            else:
                manifest_info.append(InfoItem('Uninstaller', 'uninstaller', None, None))

            install_tags = {''}
            for fm in manifest.file_manifest_list.elements:
                for tag in fm.install_tags:
                    install_tags.add(tag)

            install_tags = sorted(install_tags)
            install_tags_human = ', '.join(i if i else '(empty)' for i in install_tags)
            manifest_info.append(InfoItem('Install tags', 'install_tags', install_tags_human, install_tags))
            # file and chunk count
            manifest_info.append(InfoItem('Files', 'num_files', manifest.file_manifest_list.count,
                                          manifest.file_manifest_list.count))
            manifest_info.append(InfoItem('Chunks', 'num_chunks', manifest.chunk_data_list.count,
                                          manifest.chunk_data_list.count))
            # total file size
            total_size = sum(fm.file_size for fm in manifest.file_manifest_list.elements)
            file_size = '{:.02f} GiB'.format(total_size / 1024 / 1024 / 1024)
            manifest_info.append(InfoItem('Disk size (uncompressed)', 'disk_size', file_size, total_size))
            # total chunk size
            total_size = sum(c.file_size for c in manifest.chunk_data_list.elements)
            chunk_size = '{:.02f} GiB'.format(total_size / 1024 / 1024 / 1024)
            manifest_info.append(InfoItem('Download size (compressed)', 'download_size',
                                          chunk_size, total_size))

            # if there are install tags break down size by tag
            tag_disk_size = []
            tag_disk_size_human = []
            tag_download_size = []
            tag_download_size_human = []
            if len(install_tags) > 1:
                longest_tag = max(max(len(t) for t in install_tags), len('(empty)'))
                for tag in install_tags:
                    # sum up all file sizes for the tag
                    human_tag = tag or '(empty)'
                    tag_files = [fm for fm in manifest.file_manifest_list.elements if
                                 (tag in fm.install_tags) or (not tag and not fm.install_tags)]
                    tag_file_size = sum(fm.file_size for fm in tag_files)
                    tag_disk_size.append(dict(tag=tag, size=tag_file_size, count=len(tag_files)))
                    tag_file_size_human = '{:.02f} GiB'.format(tag_file_size / 1024 / 1024 / 1024)
                    tag_disk_size_human.append(f'{human_tag.ljust(longest_tag)} - {tag_file_size_human} '
                                               f'(Files: {len(tag_files)})')
                    # tag_disk_size_human.append(f'Size: {tag_file_size_human}, Files: {len(tag_files)}, Tag: "{tag}"')
                    # accumulate chunk guids used for this tag and count their size too
                    tag_chunk_guids = set()
                    for fm in tag_files:
                        for cp in fm.chunk_parts:
                            tag_chunk_guids.add(cp.guid_num)

                    tag_chunk_size = sum(c.file_size for c in manifest.chunk_data_list.elements
                                         if c.guid_num in tag_chunk_guids)
                    tag_download_size.append(dict(tag=tag, size=tag_chunk_size, count=len(tag_chunk_guids)))
                    tag_chunk_size_human = '{:.02f} GiB'.format(tag_chunk_size / 1024 / 1024 / 1024)
                    tag_download_size_human.append(f'{human_tag.ljust(longest_tag)} - {tag_chunk_size_human} '
                                                   f'(Chunks: {len(tag_chunk_guids)})')

            manifest_info.append(InfoItem('Disk size by install tag', 'tag_disk_size',
                                          tag_disk_size_human or 'N/A', tag_disk_size))
            manifest_info.append(InfoItem('Download size by install tag', 'tag_download_size',
                                          tag_download_size_human or 'N/A', tag_download_size))

        if not args.json:
            def print_info_item(item: InfoItem):
                if item.value is None:
                    print(f'- {item.name}: (None)')
                elif isinstance(item.value, list):
                    print(f'- {item.name}:')
                    for list_item in item.value:
                        print(' + ', list_item)
                elif isinstance(item.value, dict):
                    print(f'- {item.name}:')
                    for k, v in item.value.items():
                        print(' + ', k, ':', v)
                else:
                    print(f'- {item.name}: {item.value}')

            if info_items['game']:
                print('\nGame Information:')
                for info_item in info_items['game']:
                    print_info_item(info_item)
            if info_items['install']:
                print('\nInstallation information:')
                for info_item in info_items['install']:
                    print_info_item(info_item)
            if info_items['manifest']:
                print('\nManifest information:')
                for info_item in info_items['manifest']:
                    print_info_item(info_item)

            if not any(info_items.values()):
                print('No game information available.')
        else:
            json_out = dict(game=dict(), install=dict(), manifest=dict())
            for info_item in info_items['game']:
                json_out['game'][info_item.json_name] = info_item.json_value
            for info_item in info_items['install']:
                json_out['install'][info_item.json_name] = info_item.json_value
            for info_item in info_items['manifest']:
                json_out['manifest'][info_item.json_name] = info_item.json_value
            # set empty items to null
            for key, value in json_out.items():
                if not value:
                    json_out[key] = None
            return self._print_json(json_out, args.pretty_json)

    def alias(self, args):
        if args.action == 'add':
            alias = args.alias
            app_name = self._resolve_aliases(args.app_or_alias)
            game = self.core.get_game(app_name)
            if not game:
                logger.error(f'Invalid app name: "{app_name}"')
                return
            self.core.lgd.config.set('Legendary.aliases', alias, app_name)
            logger.info(f'Added alias "{alias}" to "{app_name}" (Title: "{game.app_title}")')
        elif args.action == 'rename':
            old_alias = args.app_or_alias
            new_alias = args.alias
            app_name = self.core.lgd.config.get('Legendary.aliases', old_alias, fallback=None)
            if not app_name:
                logger.error(f'Invalid old alias: "{app_name}"')
                return
            self.core.lgd.config.set('Legendary.aliases', new_alias, app_name)
            self.core.lgd.config.remove_option('Legendary.aliases', old_alias)
            logger.info(f'Renamed alias "{old_alias}" to "{new_alias}"')
        elif args.action == 'remove':
            alias = args.app_or_alias
            if not self.core.lgd.config.has_option('Legendary.aliases', alias):
                logger.error(f'Alias does not exist: "{args.alias}"')
                return
            self.core.lgd.config.remove_option('Legendary.aliases', alias)
            logger.info(f'Removed alias "{alias}"')
        elif args.action == 'list':
            if args.app_or_alias:
                self.core.update_aliases(force=True)
                app_name = self._resolve_aliases(args.app_or_alias)
                game = self.core.get_game(app_name)
                if not game:
                    logger.error(f'Invalid app name: "{app_name}"')
                    return
                print(f'\nAliases for "{game.app_title}" ({app_name}):')
                # Use-defined
                if self.core.lgd.config.has_section('Legendary.aliases'):
                    aliases = [alias for (alias, app_name) in self.core.lgd.config['Legendary.aliases'].items()
                               if app_name == game.app_name]
                    if aliases:
                        print('- User-defined aliases:')
                        for alias in sorted(aliases):
                            print(f'  + {alias}')
                    else:
                        print('- User-defined aliases: (None)')
                # Automatically generated
                aliases = [alias for (alias, app_name) in self.core.lgd.aliases.items()
                           if app_name == game.app_name]
                if aliases:
                    print('- Automatic aliases:')
                    for alias in sorted(aliases):
                        print(f'  + {alias}')
                else:
                    print('- Automatic aliases: (None)')
            else:
                if not self.core.lgd.config.has_section('Legendary.aliases'):
                    logger.error('No aliases in config!')
                    return

                print('User-defined aliases:')
                for alias, app_name in self.core.lgd.config['Legendary.aliases'].items():
                    print(f' - {alias} => {app_name}')

    def cleanup(self, args):
        before = self.core.lgd.get_dir_size()
        # delete metadata
        logger.debug('Removing app metadata...')
        app_names = set()
        for _platform in self.core.get_installed_platforms():
            app_names |= set(g.app_name for g in self.core.get_assets(update_assets=False, platform=_platform))
        self.core.lgd.clean_metadata(app_names)

        if not args.keep_manifests:
            logger.debug('Removing manifests...')
            installed = [(ig.app_name, ig.version, ig.platform) for ig in self.core.get_installed_list()]
            installed.extend((ig.app_name, ig.version, ig.platform) for ig in self.core.get_installed_dlc_list())
            self.core.lgd.clean_manifests(installed)

        logger.debug('Removing tmp data')
        self.core.lgd.clean_tmp_data()

        after = self.core.lgd.get_dir_size()
        logger.info(f'Cleanup complete! Removed {(before - after) / 1024 / 1024:.02f} MiB.')

    def activate(self, args):
        if not self.core.login():
            logger.error('Login failed!')
            return

        if args.uplay:
            ubi_account_id = ''
            ext_auths = self.core.egs.get_external_auths()
            for ext_auth in ext_auths:
                if ext_auth['type'] != 'ubisoft':
                    continue
                ubi_account_id = ext_auth['externalAuthId']
                break
            else:
                logger.error('No linked ubisoft account found! Link your accounts via your browser and try again.')
                webbrowser.open('https://www.epicgames.com/id/link/ubisoft')
                print('If the web page did not open automatically, please manually open the following URL: '
                      'https://www.epicgames.com/id/link/ubisoft')
                return

            uplay_keys = self.core.egs.store_get_uplay_codes()
            key_list = uplay_keys['data']['PartnerIntegration']['accountUplayCodes']
            redeemed = {k['gameId'] for k in key_list if k['redeemedOnUplay']}

            games = self.core.get_game_list()
            entitlements = self.core.egs.get_user_entitlements_full()
            owned_entitlements = {i['entitlementName'] for i in entitlements}

            uplay_games = []
            activated = 0
            for game in games:
                for dlc_data in game.metadata.get('dlcItemList', []):
                    if dlc_data['entitlementName'] not in owned_entitlements:
                        continue

                    try:
                        app_name = dlc_data['releaseInfo'][0]['appId']
                    except (IndexError, KeyError):
                        app_name = 'unknown'

                    dlc_game = Game(app_name=app_name, app_title=dlc_data['title'], metadata=dlc_data)
                    if dlc_game.partner_link_type != 'ubisoft':
                        continue
                    if dlc_game.partner_link_id in redeemed:
                        continue
                    uplay_games.append(dlc_game)

                if game.partner_link_type != 'ubisoft':
                    continue
                if game.partner_link_id in redeemed:
                    activated += 1
                    continue
                uplay_games.append(game)

            if not uplay_games:
                logger.info(f'All of your {activated} titles have already been activated on your Ubisoft account.')
                return

            logger.info(f'Found {len(uplay_games)} game(s) to redeem:')
            for game in sorted(uplay_games, key=lambda g: g.app_title.lower()):
                logger.info(f' - {game.app_title}')

            if not args.yes:
                y_n = get_boolean_choice('Do you want to redeem these games?')
                if not y_n:
                    logger.info('Aborting.')
                    return

            def read_service_response(response):
                # try to get specific error, otherwise just fall back to generic message
                error_msgs = []

                for error in response['errors']:
                    try:
                        srv_resp = json.loads(error['serviceResponse'])
                        error_msgs.append(srv_resp["errorMessage"])
                    except Exception as _e:
                        logger.debug(f'Reading upstream error message failed with {_e!r}')
                        error_msgs.append(error['message'])

                if len(error_msgs) > 1:
                    return error_msgs
                elif error_msgs:
                    return error_msgs[0]
                else:
                    return 'Unknown error (API error message missing)'

            try:
                for game in uplay_games:
                    result = self.core.egs.store_claim_uplay_code(ubi_account_id, game.partner_link_id)
                    if 'errors' in result:
                        logger.error(f'Claiming "{game.app_title}" failed with: {read_service_response(result)}')
                    else:
                        logger.debug(f'Successfully claimed code for "{game.partner_link_id}"')

                result = self.core.egs.store_redeem_uplay_codes(ubi_account_id)
                if 'errors' in result:
                    logger.error(f'Redeeming codes (partially) failed with: {read_service_response(result)}')
            except Exception as e:
                logger.error(f'Failed to redeem Uplay codes: {e!r}')
            else:
                logger.info('Redeemed all outstanding Uplay codes.')
        elif args.origin:
            na_games, _ = self.core.get_non_asset_library_items(skip_ue=True)
            origin_games = [game for game in na_games if game.is_origin_game]

            if not origin_games:
                logger.info('No redeemable games found.')
                return

            logger.info(f'Found {len(origin_games)} game(s) to redeem:')
            for game in origin_games:
                logger.info(f' - {game.app_title}')

            logger.info('Note: Legendary does not know which of these have already been activated. '
                        'Proceeding will result in it attempting to activate all of them.')
            logger.info('If Origin asks you to install the title rather than to activate, '
                        'it has already been activated, and the dialog can be dismissed.')

            if os.name != 'nt':
                logger.info('On non-Windows systems the automatic portion of this process does not work yet, '
                            'please use the launch commands listed below together with --wine/--wine-prefix to '
                            'specify the wine binary to use and the prefix where Origin is installed.')
                for idx, game in enumerate(origin_games, start=1):
                    logger.info(f'{idx}. legendary launch --origin {game.app_name}')
                return

            logger.info('After one title has been processed, hit enter to proceed with the next one.')

            y_n = get_boolean_choice('Do you want to redeem these games?')
            if not y_n:
                logger.info('Aborting...')
                return

            last_game = origin_games[-1]
            for game in origin_games:
                origin_uri = self.core.get_origin_uri(game.app_name)
                logger.info(f'Opening Origin to activate "{game.app_title}"')
                logger.debug(f'Opening Origin URI: {origin_uri}')
                webbrowser.open(origin_uri)

                if game == last_game:
                    break

                y_n = get_boolean_choice('Do you want to proceed with the next title?')
                if not y_n:
                    logger.info('User requested abort.')
                    return

            logger.info('Origin activation process completed.')

    def get_token(self, args):
        if not self.core.login(force_refresh=args.bearer):
            logger.error('Login failed!')
            return

        if args.bearer:
            args.json = True
            token = dict(token_type='bearer',
                         access_token=self.core.egs.user['access_token'],
                         expires_in=self.core.egs.user['expires_in'],
                         expires_at=self.core.egs.user['expires_at'],
                         account_id=self.core.egs.user['account_id'])
        else:
            token = self.core.egs.get_game_token()

        if args.json:
            if args.pretty_json:
                print(json.dumps(token, indent=2, sort_keys=True))
            else:
                print(json.dumps(token))
            return
        logger.info(f'Exchange code: {token["code"]}')

    def manage_eos_overlay(self, args):
        prefix = None
        if os.name != 'nt':
            if args.app:
                app_name = self._resolve_aliases(args.app)
                # try getting bottle/prefix from config
                if sys_platform == 'darwin':
                    args.bottle = self.core.lgd.config.get(app_name, 'crossover_bottle', fallback=None)

                args.prefix = self.core.lgd.config.get(f'{app_name}.env', 'WINEPREFIX', fallback=None)
                args.prefix = self.core.lgd.config.get(app_name, 'wine_prefix', fallback=args.prefix)

            if sys_platform == 'darwin' and args.bottle:
                if not mac_is_valid_bottle(args.bottle):
                    logger.error('Invalid bottle specified.')
                    return
                prefix = mac_get_bottle_path(args.bottle)
            elif args.prefix:
                if not os.path.exists(args.prefix):
                    logger.error(f'Prefix "{args.prefix}" does not exist.')
                    return
                prefix = args.prefix
            elif args.action not in {'info', 'install', 'remove', 'update'}:
                logger.error('Need either --prefix, --bottle, or --app for this command.')
                return

            if prefix:
                if not os.path.exists(prefix):
                    logger.error(f'Prefix "{prefix}" does not exist.')
                    return
                else:
                    logger.info(f'Using prefix "{prefix}"')

        if args.action == 'info':
            igame = self.core.lgd.get_overlay_install_info()
            if not igame:
                logger.info('No Legendary-managed installation found.')
            else:
                logger.info(f'Installed version: {igame.version}')
                logger.info(f'Installed path: {igame.install_path}')

            if os.name != 'nt' and not prefix:
                return

            reg_paths = query_registry_entries(prefix)
            available_installs = self.core.search_overlay_installs(prefix)
            logger.info('Found available Overlay installations in:')
            for install in available_installs:
                logger.info(f' - {install}')

            # check if overlay path is in registry, and if it is valid
            overlay_enabled = False
            if reg_paths['overlay_path'] and self.core.is_overlay_install(reg_paths['overlay_path']):
                overlay_enabled = True

            logger.info(f'Overlay enabled: {"Yes" if overlay_enabled else "No"}')
            logger.info(f'Enabled Overlay path: {reg_paths["overlay_path"]}')

            # Also log Vulkan overlays
            vulkan_overlays = set(reg_paths['vulkan_hkcu']) | set(reg_paths['vulkan_hklm'])
            if vulkan_overlays:
                logger.info('Enabled Vulkan layers:')
                for vk_overlay in sorted(vulkan_overlays):
                    logger.info(f' - {vk_overlay}')
            else:
                logger.info('No enabled Vulkan layers.')

        elif args.action == 'enable':
            if not args.path:
                igame = self.core.lgd.get_overlay_install_info()
                if igame:
                    args.path = igame.install_path
                else:
                    available_installs = self.core.search_overlay_installs(prefix)
                    if not available_installs:
                        logger.error('No EOS overlay installs found!')
                        return
                    args.path = available_installs[0]

            if not self.core.is_overlay_install(args.path):
                logger.error(f'Not a valid Overlay installation: {args.path}')
                return

            args.path = os.path.normpath(args.path)
            # Check for existing entries
            reg_paths = query_registry_entries(prefix)
            if old_path := reg_paths["overlay_path"]:
                if os.path.normpath(old_path) == args.path:
                    logger.info(f'Overlay already enabled, nothing to do.')
                    return
                else:
                    logger.info(f'Updating overlay registry entries from "{old_path}" to "{args.path}"')
                remove_registry_entries(prefix)
            add_registry_entries(args.path, prefix)
            logger.info(f'Enabled overlay at: {args.path}')

        elif args.action == 'disable':
            logger.info('Disabling overlay (removing registry keys)..')
            reg_paths = query_registry_entries(prefix)
            old_path = reg_paths["overlay_path"]
            remove_registry_entries(prefix)
            # if the install is not managed by legendary, specify the command including the path
            if self.core.is_overlay_installed():
                logger.info(f'To re-enable the overlay, run: legendary eos-overlay enable')
            else:
                logger.info(f'To re-enable the overlay, run: legendary eos-overlay enable --path "{old_path}"')

        elif args.action == 'remove':
            if not self.core.is_overlay_installed():
                logger.error('No legendary-managed overlay installation found.')
                return

            if not args.yes:
                if not get_boolean_choice('Do you want to uninstall the overlay?', default=False):
                    print('Aborting...')
                    return

            logger.info('Deleting overlay installation...')
            self.core.remove_overlay_install()

            if os.name != 'nt' and not prefix:
                logger.info('Registry entries in prefixes (if any) have not been removed. '
                            f'This shouldn\'t cause any issues as the overlay will simply fail to load.')
            else:
                logger.info('Removing registry entries...')
                remove_registry_entries(prefix)

                if os.name != 'nt':
                    logger.info(f'Registry entries in prefixes other than "{prefix}" were not removed. '
                                f'This shouldn\'t cause any issues as the overlay will simply fail to load.')
            logger.info('Done.')

        elif args.action in {'install', 'update'}:
            if args.action == 'update' and not self.core.is_overlay_installed():
                logger.error(f'Overlay not installed, nothing to update.')
                return
            logger.info('Preparing to start overlay install...')
            dlm, ares, igame = self.core.prepare_overlay_install(args.path)

            if old_install := self.core.lgd.get_overlay_install_info():
                if old_install.version == igame.version:
                    logger.info('Installed version is up to date, nothing to do.')
                    return

            logger.info(f'Install directory: {igame.install_path}')
            logger.info(f'Install size: {ares.install_size / 1024 / 1024:.2f} MiB')
            logger.info(f'Download size: {ares.dl_size / 1024 / 1024:.2f} MiB')

            if not args.yes:
                if not get_boolean_choice('Do you want to install the overlay?'):
                    print('Aborting...')
                    return

            try:
                # set up logging stuff (should be moved somewhere else later)
                dlm.logging_queue = self.logging_queue
                dlm.start()
                dlm.join()
            except Exception as e:
                logger.error(f'The following exception occurred while waiting for the downloader to finish: {e!r}. '
                             f'Try restarting the process, if it continues to fail please open an issue on GitHub.')
            else:
                self.core.finish_overlay_install(igame)

                if os.name == 'nt' or prefix:
                    logger.info('Finished downloading, setting up overlay...')
                    # Check for existing registry entries, and remove them if necessary
                    install_path = os.path.normpath(igame.install_path)
                    reg_paths = query_registry_entries(prefix)
                    if old_path := reg_paths["overlay_path"]:
                        if os.path.normpath(old_path) != install_path:
                            logger.info(f'Updating overlay registry entries from "{old_path}" to "{install_path}"')
                            remove_registry_entries(prefix)
                        else:
                            logger.info(f'Registry entries already exist. Done.')
                            return
                    add_registry_entries(install_path, prefix)
                    logger.info('Done.')
                else:
                    logger.info('Overlay has been downloaded. Run "legendary eos-overlay enable -h" to see '
                                'available options for enabling the overlay by specifying a prefix, app, or bottle.')

    def crossover_setup(self, args):
        if sys_platform != 'darwin':
            logger.fatal('This command is only supported on macOS.')
            return

        if not args.app_name:
            app_name = 'default'
            game = None
        else:
            app_name = self._resolve_aliases(args.app_name)
            game = self.core.get_game(app_name)

        if args.reset:
            if not game:
                prompt = 'Reset default crossover configuration?'
            else:
                prompt = f'Reset "{game.app_title}" crossover configuration?'

            y_n = args.yes or get_boolean_choice(prompt, default=False)
            if y_n:
                self.core.lgd.config.remove_option(app_name, 'crossover_app')
                self.core.lgd.config.remove_option(app_name, 'crossover_bottle')
            return

        if args.crossover_app:
            cx_version = mac_get_crossover_version(args.crossover_app)
            if not cx_version:
                logger.error(f'No valid CrossOver install specified!')
                return
            logger.info(f'Using CrossOver {cx_version} at {args.crossover_app}')
        else:
            logger.info('Looking for CrossOver installs...')
            apps = mac_find_crossover_apps()
            if len(apps) > 1:
                print('\nFound multiple CrossOver installs, please select one:')
                for i, (ver, path) in enumerate(apps, start=1):
                    print(f'  {i:2d}. {ver} ({path})')
                print('')
                choice = get_int_choice(f'Select a CrossOver install', 1, 1, len(apps))
                if choice is None:
                    logger.error(f'No valid choice made, aborting.')
                    exit(1)
                # empty line just to make the output look a little less crammed
                print('')
                cx_version, args.crossover_app = apps[choice - 1]
            elif len(apps) == 1:
                cx_version, args.crossover_app = apps[0]
                logger.info(f'Found CrossOver {cx_version} at {args.crossover_app}')
            else:
                logger.error(f'No CrossOver installs found, see https://legendary.gl/crossover-setup '
                             f'for setup instructions')
                return

        forced_selection = None
        bottles = mac_get_crossover_bottles()

        if args.crossover_bottle:
            if args.crossover_bottle not in bottles:
                logger.error(f'No valid CrossOver bottle specified!')
                return
            logger.info(f'Using Bottle "{args.crossover_bottle}"')
            forced_selection = args.crossover_bottle
        elif not any(b.startswith('Legendary') for b in bottles) and not args.download:
            logger.info('It is recommended to set up a bottle specifically for Legendary, see '
                        'https://legendary.gl/crossover-setup for setup instructions.')
        elif args.download:
            logger.warning('This feature is experimental, and may not work properly. This is not supported by '
                           'CodeWeavers/CrossOver, please report issues only on the Legendary GitHub or Discord!')
            if mac_is_crossover_running():
                logger.error('CrossOver is still running, please quit it before proceeding.')
                return

            logger.info('Checking available bottles...')
            available_bottles = self.core.get_available_bottles()
            if args.disable_version_check:
                logger.warning('All available bottles are shown, including possibly incompatible ones.')
                usable_bottles = available_bottles
            else:
                usable_bottles = [b for b in available_bottles if cx_version in b['cx_versions']]
            logger.info(f'Found {len(usable_bottles)} bottle(s) usable with the selected CrossOver version. '
                        f'(Total: {len(available_bottles)})')

            if not usable_bottles:
                logger.info(f'No usable bottles found, see https://legendary.gl/crossover-setup for '
                            f'manual setup instructions.')
                install_candidate = None
            else:
                print('\nFound available bottle(s), please select one:')

                default_choice = None
                for i, bottle in enumerate(usable_bottles, start=1):
                    extra = []
                    
                    if cx_version in bottle['cx_versions']:
                        if app_name in bottle['compatible_apps']:
                            extra.append('recommended')
                        if not default_choice and bottle['is_default']:
                            default_choice = i
                            extra.append('default')

                    if bottle['name'] in bottles:
                        extra.append('installed')

                    if extra:
                        print(f'  {i:2d}. {bottle["name"]} ({bottle["description"]}) [{", ".join(extra)}]')
                    else:
                        print(f'  {i:2d}. {bottle["name"]} ({bottle["description"]})')

                print('')
                choice = get_int_choice(f'Select a bottle (CTRL+C to abort)',
                                        default_choice, 1, len(usable_bottles),
                                        return_on_invalid=True)
                if choice is None:
                    logger.error(f'No valid choice made, aborting.')
                    return
                # empty line just to make the output look a little less crammed
                print('')
                install_candidate = usable_bottles[choice - 1]

            if install_candidate:
                bottle_name = install_candidate["name"]
                logger.info(f'Preparing to download "{bottle_name}" ({install_candidate["description"]})...')

                if bottle_name in bottles:
                    logger.warning(f'Bottle with the same name already exists!')
                    new_name = input('Please provide a new name for the bottle [CTRL-C or empty to abort]: ')
                    if not new_name:
                        logger.error('No new name provided, aborting.')
                        return
                    bottle_name = clean_filename(new_name).strip()

                dlm, ares, path = self.core.prepare_bottle_download(bottle_name, install_candidate['manifest'],
                                                                    base_url=install_candidate.get('base_url'))

                logger.info(f'Bottle install directory: {path}')
                logger.info(f'Bottle size: {ares.install_size / 1024 / 1024:.2f} MiB')
                logger.info(f'Download size: {ares.dl_size / 1024 / 1024:.2f} MiB')

                if not args.yes:
                    if not get_boolean_choice('Do you want to download the selected bottle?'):
                        print('Aborting...')
                        return

                try:
                    # set up logging stuff (should be moved somewhere else later)
                    dlm.logging_queue = self.logging_queue
                    dlm.start()
                    dlm.join()
                except Exception as e:
                    logger.error(f'The following exception occurred while waiting for the downloader: {e!r}. '
                                 f'Try restarting the process, if it continues to fail please open an issue on GitHub.')
                    # delete the unfinished bottle
                    self.core.remove_bottle(bottle_name)
                    return
                else:
                    logger.info('Finished downloading, finalising bottle setup...')
                    self.core.finish_bottle_setup(bottle_name)
                    forced_selection = bottle_name

        if len(bottles) > 1 and not forced_selection:
            print('\nFound multiple CrossOver bottles, please select one:')

            if 'Legendary' in bottles:
                default_choice = bottles.index('Legendary') + 1
            elif 'Heroic' in bottles:
                default_choice = bottles.index('Heroic') + 1
            else:
                default_choice = None

            for i, bottle in enumerate(bottles, start=1):
                if i == default_choice:
                    print(f'  {i:2d}. {bottle} (default)')
                else:
                    print(f'  {i:2d}. {bottle}')
            print('')

            choice = get_int_choice(f'Select a bottle', default_choice, 1, len(bottles))
            if choice is None:
                logger.error(f'No valid choice made, aborting.')
                exit(1)
            # empty line just to make the output look a little less crammed
            print('')
            args.crossover_bottle = bottles[choice - 1]
        elif len(bottles) == 1 and not forced_selection:
            logger.info(f'Found only one bottle: {bottles[0]}')
            args.crossover_bottle = bottles[0]
        elif forced_selection:
            args.crossover_bottle = forced_selection
        else:
            logger.error('No Bottles found, see https://legendary.gl/crossover-setup for setup instructions.')
            return

        logger.info(f'Current configuration: '
                    f'--crossover-bottle "{args.crossover_bottle}" '
                    f'--crossover-app "{args.crossover_app}" ')

        if not game:
            prompt = 'Would you like to save these choices as the default?'
        else:
            prompt = f'Would you like to save these choices for "{game.app_title}"?'

        y_n = args.yes or get_boolean_choice(prompt)
        if y_n:
            self.core.lgd.config.set(app_name, 'crossover_app', args.crossover_app)
            self.core.lgd.config.set(app_name, 'crossover_bottle', args.crossover_bottle)
            logger.info('Saved choices to configuration.')

    def move(self, args):
        if not self.core.lgd.lock_installed():
            logger.fatal('Failed to acquire installed data lock, only one instance of Legendary may '
                         'install/import/move applications at a time.')
            return

        app_name = self._resolve_aliases(args.app_name)
        igame = self.core.get_installed_game(app_name, skip_sync=True)
        if not igame:
            logger.error(f'No installed game found for "{app_name}"')
            return

        old_base, game_folder = os.path.split(igame.install_path.replace('\\', '/'))
        new_path = os.path.join(args.new_path, game_folder)
        logger.info(f'Moving "{game_folder}" from "{old_base}" to "{args.new_path}"')

        if not args.skip_move:
            try:
                if not os.path.exists(args.new_path):
                    os.makedirs(args.new_path)

                os.rename(igame.install_path, new_path)
            except Exception as e:
                if isinstance(e, OSError) and e.errno == 18:
                    logger.error(f'Moving to a different drive is not supported. Move the folder manually to '
                                 f'"{new_path}" and run "legendary move {app_name} "{args.new_path}" --skip-move"')
                elif isinstance(e, FileExistsError):
                    logger.error(f'The target path already contains a folder called "{game_folder}", '
                                 f'please remove or rename it first.')
                else:
                    logger.error(f'Moving failed with unknown error {e!r}.')
                    logger.info(f'Try moving the folder manually to "{new_path}" and running '
                                f'"legendary move {app_name} "{args.new_path}" --skip-move"')
                return
        else:
            logger.info(f'Not moving, just rewriting legendary metadata...')

        igame.install_path = new_path
        self.core.install_game(igame)
        logger.info('Finished.')


def main():
    # Set output encoding to UTF-8 if not outputting to a terminal
    if not stdout.isatty():
        stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description=f'Legendary v{__version__} - "{__codename__}"')
    parser.register('action', 'parsers', HiddenAliasSubparsersAction)

    # general arguments
    parser.add_argument('-H', '--full-help', dest='full_help', action='store_true',
                        help='Show full help (including individual command help)')
    parser.add_argument('-v', '--debug', dest='debug', action='store_true', help='Set loglevel to debug')
    parser.add_argument('-y', '--yes', dest='yes', action='store_true', help='Default to yes for all prompts')
    parser.add_argument('-V', '--version', dest='version', action='store_true', help='Print version and exit')
    parser.add_argument('-c', '--config-file', dest='config_file', action='store', metavar='<path/name>',
                        help=argparse.SUPPRESS)
    parser.add_argument('-J', '--pretty-json', dest='pretty_json', action='store_true',
                        help='Pretty-print JSON')
    parser.add_argument('-A', '--api-timeout', dest='api_timeout', action='store',
                        type=float, default=10, metavar='<seconds>',
                        help='API HTTP request timeout (default: 10 seconds)')

    # all the commands
    subparsers = parser.add_subparsers(title='Commands', dest='subparser_name', metavar='<command>')
    activate_parser = subparsers.add_parser('activate', help='Activate games on third party launchers')
    alias_parser = subparsers.add_parser('alias', help='Manage aliases')
    auth_parser = subparsers.add_parser('auth', help='Authenticate with the Epic Games Store')
    clean_saves_parser = subparsers.add_parser('clean-saves', help='Clean cloud saves')
    clean_parser = subparsers.add_parser('cleanup', help='Remove old temporary, metadata, and manifest files')
    cx_parser = subparsers.add_parser('crossover', help='Setup CrossOver for launching games (macOS only)')
    download_saves_parser = subparsers.add_parser('download-saves', help='Download all cloud saves')
    egl_sync_parser = subparsers.add_parser('egl-sync', help='Setup or run Epic Games Launcher sync')
    eos_overlay_parser = subparsers.add_parser('eos-overlay', help='Manage EOS Overlay install')
    import_parser = subparsers.add_parser('import', help='Import an already installed game',
                                          aliases=('import-game',), hide_aliases=True)
    info_parser = subparsers.add_parser('info', help='Prints info about specified app name or manifest')
    install_parser = subparsers.add_parser('install', help='Install/download/update/repair a game',
                                           aliases=('download', 'update', 'repair'),
                                           usage='%(prog)s <App Name> [options]',
                                           description='Aliases: download, update')
    launch_parser = subparsers.add_parser('launch', help='Launch a game', usage='%(prog)s <App Name> [options]',
                                          description='Note: additional arguments are passed to the game')
    list_parser = subparsers.add_parser('list', aliases=('list-games',), hide_aliases=True,
                                        help='List available (installable) games')
    list_files_parser = subparsers.add_parser('list-files', help='List files in manifest')
    list_installed_parser = subparsers.add_parser('list-installed', help='List installed games')
    list_saves_parser = subparsers.add_parser('list-saves', help='List available cloud saves')
    move_parser = subparsers.add_parser('move', help='Move specified app name to a new location')
    status_parser = subparsers.add_parser('status', help='Show legendary status information')
    sync_saves_parser = subparsers.add_parser('sync-saves', help='Sync cloud saves')
    uninstall_parser = subparsers.add_parser('uninstall', help='Uninstall (delete) a game')
    verify_parser = subparsers.add_parser('verify', help='Verify a game\'s local files',
                                          aliases=('verify-game',), hide_aliases=True)

    # hidden commands have no help text
    get_token_parser = subparsers.add_parser('get-token')

    # Positional arguments
    install_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    uninstall_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    launch_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    list_files_parser.add_argument('app_name', nargs='?', metavar='<App Name>',
                                   help='Name of the app (optional)')
    list_saves_parser.add_argument('app_name', nargs='?', metavar='<App Name>', default='',
                                   help='Name of the app (optional)')
    download_saves_parser.add_argument('app_name', nargs='?', metavar='<App Name>', default='',
                                       help='Name of the app (optional)')
    clean_saves_parser.add_argument('app_name', nargs='?', metavar='<App Name>', default='',
                                    help='Name of the app (optional)')
    sync_saves_parser.add_argument('app_name', nargs='?', metavar='<App Name>', default='',
                                   help='Name of the app (optional)')
    verify_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    import_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    import_parser.add_argument('app_path', help='Path where the game is installed',
                               metavar='<Installation directory>')
    info_parser.add_argument('app_name_or_manifest', help='App name or manifest path/URI',
                             metavar='<App Name/Manifest URI>')

    alias_parser.add_argument('action', help='Action: Add, rename, remove, or list alias(es)',
                              choices=['add', 'rename', 'remove', 'list'],
                              metavar='<add|rename|remove|list>')
    alias_parser.add_argument('app_or_alias', help='App name when using "add" or "list" action, '
                                                   'existing alias when using "rename" or "remove" action',
                              metavar='<App name/Old alias>', nargs='?')
    alias_parser.add_argument('alias', help='New alias when using "add" action',
                              metavar='<New alias>', nargs='?')

    cx_parser.add_argument('app_name', metavar='<App Name>', nargs='?',
                           help='App name to configure, will configure defaults if ommited')

    move_parser.add_argument('app_name', metavar='<App Name>', help='Name of the app')
    move_parser.add_argument('new_path', metavar='<New Base Path>', help='Directory to move game folder to')

    # Flags
    auth_parser.add_argument('--import', dest='import_egs_auth', action='store_true',
                             help='Import Epic Games Launcher authentication data (logs out of EGL)')
    auth_parser.add_argument('--code', dest='auth_code', action='store', metavar='<authorization code>',
                             help='Use specified authorization code instead of interactive authentication')
    auth_parser.add_argument('--token', dest='ex_token', action='store', metavar='<exchange token>',
                             help='Use specified exchange token instead of interactive authentication')
    auth_parser.add_argument('--sid', dest='session_id', action='store', metavar='<session id>',
                             help='Use specified session id instead of interactive authentication')
    auth_parser.add_argument('--delete', dest='auth_delete', action='store_true',
                             help='Remove existing authentication (log out)')
    auth_parser.add_argument('--disable-webview', dest='no_webview', action='store_true',
                             help='Do not use embedded browser for login')

    install_parser.add_argument('--base-path', dest='base_path', action='store', metavar='<path>',
                                help='Path for game installations (defaults to ~/Games)')
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
    install_parser.add_argument('--delta-manifest', dest='override_delta_manifest', action='store', metavar='<uri>',
                                help='Manifest URL or path to use as the delta one (e.g. for testing)')
    install_parser.add_argument('--base-url', dest='override_base_url', action='store', metavar='<url>',
                                help='Base URL to download from (e.g. to test or switch to a different CDNs)')
    install_parser.add_argument('--force', dest='force', action='store_true',
                                help='Download all files / ignore existing (overwrite)')
    install_parser.add_argument('--disable-patching', dest='disable_patching', action='store_true',
                                help='Do not attempt to patch existing installation (download entire changed files)')
    install_parser.add_argument('--download-only', '--no-install', dest='no_install', action='store_true',
                                help='Do not install app and do not run prerequisite installers after download')
    install_parser.add_argument('--update-only', dest='update_only', action='store_true',
                                help='Only update, do not do anything if specified app is not installed')
    install_parser.add_argument('--dlm-debug', dest='dlm_debug', action='store_true',
                                help='Set download manager and worker processes\' loglevel to debug')
    install_parser.add_argument('--platform', dest='platform', action='store', metavar='<Platform>', type=str,
                                help='Platform for install (default: installed or Windows)')
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
    install_parser.add_argument('--repair-and-update', dest='repair_and_update', action='store_true',
                                help='Update game to the latest version when repairing')
    install_parser.add_argument('--ignore-free-space', dest='ignore_space', action='store_true',
                                help='Do not abort if not enough free space is available')
    install_parser.add_argument('--disable-delta-manifests', dest='disable_delta', action='store_true',
                                help='Do not use delta manifests when updating (may increase download size)')
    install_parser.add_argument('--reset-sdl', dest='reset_sdl', action='store_true',
                                help='Reset selective downloading choices (requires repair to download new components)')
    install_parser.add_argument('--skip-sdl', dest='skip_sdl', action='store_true',
                                help='Skip SDL prompt and continue with defaults (only required game data)')
    install_parser.add_argument('--disable-sdl', dest='disable_sdl', action='store_true',
                                help='Disable selective downloading for title, reset existing configuration (if any)')
    install_parser.add_argument('--preferred-cdn', dest='preferred_cdn', action='store', metavar='<hostname>',
                                help='Set the hostname of the preferred CDN to use when available')
    install_parser.add_argument('--no-https', dest='disable_https', action='store_true',
                                help='Download games via plaintext HTTP (like EGS), e.g. for use with a lan cache')
    install_parser.add_argument('--with-dlcs', dest='with_dlcs', action='store_true',
                                help='Automatically install all DLCs with the base game')
    install_parser.add_argument('--skip-dlcs', dest='skip_dlcs', action='store_true',
                                help='Do not ask about installing DLCs.')
    install_parser.add_argument('--bind', dest='bind_ip', action='store', metavar='<IPs>', type=str,
                                help='Comma-separated list of IPs to bind to for downloading')

    uninstall_parser.add_argument('--keep-files', dest='keep_files', action='store_true',
                                  help='Keep files but remove game from Legendary database')
    uninstall_parser.add_argument('--skip-uninstaller', dest='skip_uninstaller', action='store_true',
                                  help='Skip running the uninstaller')

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
    launch_parser.add_argument('--override-exe', dest='executable_override', action='store', metavar='<exe path>',
                               help='Override executable to launch (relative path)')
    launch_parser.add_argument('--origin', dest='origin', action='store_true',
                               help='Launch Origin to activate or run the game.')
    launch_parser.add_argument('--json', dest='json', action='store_true',
                               help='Print launch information as JSON and exit')

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

    if sys_platform == 'darwin':
        launch_parser.add_argument('--crossover', dest='crossover', action='store_true',
                                   help='Interactively configure CrossOver for this application.')
        launch_parser.add_argument('--crossover-app', dest='crossover_app', action='store', metavar='<path to .app>',
                                   help='Specify which App to use for CrossOver (e.g. "/Applications/CrossOver.app")')
        launch_parser.add_argument('--crossover-bottle', dest='crossover_bottle', action='store',
                                   help='Specify which bottle to use for CrossOver', metavar='<bottle name>')
    else:
        launch_parser.add_argument('--crossover', dest='crossover', action='store_true',
                                   help=argparse.SUPPRESS)
        launch_parser.add_argument('--crossover-app', dest='crossover_app', action='store',
                                   help=argparse.SUPPRESS)
        launch_parser.add_argument('--crossover-bottle', dest='crossover_bottle', action='store',
                                   help=argparse.SUPPRESS)

    list_parser.add_argument('--platform', dest='platform', action='store', metavar='<Platform>', type=str,
                             help='Platform to fetch game list for (default: Mac on macOS, otherwise Windows)')
    list_parser.add_argument('--include-ue', dest='include_ue', action='store_true',
                             help='Also include Unreal Engine content (Engine/Marketplace) in list')
    list_parser.add_argument('-T', '--third-party', '--include-non-installable',
                             dest='include_noasset', action='store_true', default=False,
                             help='Include apps that are not installable (e.g. that have to be activated on Origin)')
    list_parser.add_argument('--csv', dest='csv', action='store_true', help='List games in CSV format')
    list_parser.add_argument('--tsv', dest='tsv', action='store_true', help='List games in TSV format')
    list_parser.add_argument('--json', dest='json', action='store_true', help='List games in JSON format')
    list_parser.add_argument('--force-refresh', dest='force_refresh', action='store_true',
                             help='Force a refresh of all game metadata')

    list_installed_parser.add_argument('--check-updates', dest='check_updates', action='store_true',
                                       help='Check for updates for installed games')
    list_installed_parser.add_argument('--csv', dest='csv', action='store_true',
                                       help='List games in CSV format')
    list_installed_parser.add_argument('--tsv', dest='tsv', action='store_true',
                                       help='List games in TSV format')
    list_installed_parser.add_argument('--json', dest='json', action='store_true',
                                       help='List games in JSON format')
    list_installed_parser.add_argument('--show-dirs', dest='include_dir', action='store_true',
                                       help='Print installation directory in output')

    list_files_parser.add_argument('--force-download', dest='force_download', action='store_true',
                                   help='Always download instead of using on-disk manifest')
    list_files_parser.add_argument('--platform', dest='platform', action='store', metavar='<Platform>',
                                   type=str, help='Platform (default: Mac on macOS, otherwise Windows)')
    list_files_parser.add_argument('--manifest', dest='override_manifest', action='store', metavar='<uri>',
                                   help='Manifest URL or path to use instead of the CDN one')
    list_files_parser.add_argument('--csv', dest='csv', action='store_true', help='Output in CSV format')
    list_files_parser.add_argument('--tsv', dest='tsv', action='store_true', help='Output in TSV format')
    list_files_parser.add_argument('--json', dest='json', action='store_true', help='Output in JSON format')
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
    sync_saves_parser.add_argument('--accept-path', dest='accept_path', action='store_true',
                                   help=argparse.SUPPRESS)

    clean_saves_parser.add_argument('--delete-incomplete', dest='delete_incomplete', action='store_true',
                                    help='Delete incomplete save files')

    import_parser.add_argument('--disable-check', dest='disable_check', action='store_true',
                               help='Disables completeness check of the to-be-imported game installation '
                                    '(useful if the imported game is a much older version or missing files)')
    import_parser.add_argument('--with-dlcs', dest='with_dlcs', action='store_true',
                               help='Automatically attempt to import all DLCs with the base game')
    import_parser.add_argument('--skip-dlcs', dest='skip_dlcs', action='store_true',
                               help='Do not ask about importing DLCs.')
    import_parser.add_argument('--platform', dest='platform', action='store', metavar='<Platform>', type=str,
                               help='Platform for import (default: Mac on macOS, otherwise Windows)')

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
    egl_sync_parser.add_argument('--migrate', dest='migrate', action='store_true',
                                 help='Import games into legendary, then remove them from EGL '
                                      '(implies --import-only --one-shot --unlink)')
    egl_sync_parser.add_argument('--unlink', dest='unlink', action='store_true',
                                 help='Disable sync and remove EGL metadata from installed games')

    status_parser.add_argument('--offline', dest='offline', action='store_true',
                               help='Only print offline status information, do not login')
    status_parser.add_argument('--json', dest='json', action='store_true',
                               help='Show status in JSON format')

    clean_parser.add_argument('--keep-manifests', dest='keep_manifests', action='store_true',
                              help='Do not delete old manifests')

    info_parser.add_argument('--offline', dest='offline', action='store_true',
                             help='Only print info available offline')
    info_parser.add_argument('--json', dest='json', action='store_true',
                             help='Output information in JSON format')
    info_parser.add_argument('--platform', dest='platform', action='store', metavar='<Platform>', type=str,
                             help='Platform to fetch info for (default: installed or Mac on macOS, Windows otherwise)')

    store_group = activate_parser.add_mutually_exclusive_group(required=True)
    store_group.add_argument('-U', '--uplay', dest='uplay', action='store_true',
                             help='Activate Uplay/Ubisoft Connect titles on your Ubisoft account '
                                  '(Uplay install not required)')
    store_group.add_argument('-O', '--origin', dest='origin', action='store_true',
                             help='Activate Origin/EA App managed titles on your EA account '
                                  '(requires Origin to be installed)')

    get_token_parser.add_argument('--json', dest='json', action='store_true',
                                  help='Output information in JSON format')
    get_token_parser.add_argument('--bearer', dest='bearer', action='store_true',
                                  help='Return fresh bearer token rather than an exchange code')

    eos_overlay_parser.add_argument('action', help='Action: install, remove, enable, disable, '
                                                   'or print info about the overlay',
                                    choices=['install', 'update', 'remove', 'enable', 'disable', 'info'],
                                    metavar='<install|update|remove|enable|disable|info>')
    eos_overlay_parser.add_argument('--path', dest='path', action='store',
                                    help='Path to the EOS overlay folder to be enabled/installed to.')

    if os.name != 'nt':
        eos_overlay_parser.add_argument('--prefix', dest='prefix', action='store',
                                        help='WINE prefix to install the overlay in')
        eos_overlay_parser.add_argument('--app', dest='app', action='store',
                                        help='Use this app\'s wine prefix (if configured in config)')

        if sys_platform == 'darwin':
            eos_overlay_parser.add_argument('--bottle', dest='bottle', action='store',
                                            help='WINE prefix to install the overlay in')
        else:
            eos_overlay_parser.add_argument('--bottle', dest='bottle', action='store', help=argparse.SUPPRESS)
    else:
        eos_overlay_parser.add_argument('--prefix', dest='prefix', action='store', help=argparse.SUPPRESS)
        eos_overlay_parser.add_argument('--bottle', dest='bottle', action='store', help=argparse.SUPPRESS)
        eos_overlay_parser.add_argument('--app', dest='app', action='store', help=argparse.SUPPRESS)

    cx_parser.add_argument('--reset', dest='reset', action='store_true',
                           help='Reset default/app-specific crossover configuration')
    cx_parser.add_argument('--download', dest='download', action='store_true',
                           help='Automatically download and set up a preconfigured bottle (experimental)')
    cx_parser.add_argument('--ignore-version', dest='disable_version_check', action='store_true',
                           help='Disable version check for available bottles when using --download')
    cx_parser.add_argument('--crossover-app', dest='crossover_app', action='store', metavar='<path to .app>',
                           help='Specify app to skip interactive selection')
    cx_parser.add_argument('--crossover-bottle', dest='crossover_bottle', action='store', metavar='<bottle name>',
                           help='Specify bottle to skip interactive selection')

    move_parser.add_argument('--skip-move', dest='skip_move', action='store_true',
                             help='Only change legendary database, do not move files (e.g. if already moved)')

    args, extra = parser.parse_known_args()

    if args.version:
        print(f'legendary version "{__version__}", codename "{__codename__}"')
        exit(0)

    if not args.subparser_name or args.full_help:
        print(parser.format_help())

        if args.full_help:
            # Commands that should not be shown in full help/list of commands (e.g. aliases)
            _hidden_commands = {'download', 'update', 'repair', 'get-token',
                                'import-game', 'verify-game', 'list-games'}
            # Print the help for all of the subparsers. Thanks stackoverflow!
            print('Individual command help:')
            subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
            for choice, subparser in subparsers.choices.items():
                if choice in _hidden_commands:
                    continue
                print(f'\nCommand: {choice}')
                print(subparser.format_help())
        elif os.name == 'nt':
            from legendary.lfs.windows_helpers import double_clicked
            if double_clicked():
                print('Please note that this is not the intended way to run Legendary.')
                print('Follow https://github.com/derrod/legendary/wiki/Setup-Instructions to set it up properly')
                subprocess.Popen(['cmd', '/K', 'echo>nul'])
        return

    cli = LegendaryCLI(override_config=args.config_file, api_timeout=args.api_timeout)
    ql = cli.setup_threaded_logging()

    config_ll = cli.core.lgd.config.get('Legendary', 'log_level', fallback='info')
    if config_ll == 'debug' or args.debug:
        logging.getLogger().setLevel(level=logging.DEBUG)
        # keep requests quiet
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

    if hasattr(args, 'platform'):
        if not args.platform:
            os_default = 'Mac' if sys_platform == 'darwin' else 'Windows'
            args.platform = cli.core.lgd.config.get('Legendary', 'default_platform', fallback=os_default)
        elif args.platform not in ('Win32', 'Windows', 'Mac'):
            logger.warning(f'Platform "{args.platform}" may be invalid. Valid ones are: Windows, Win32, Mac.')

    # if --yes is used as part of the subparsers arguments manually set the flag in the main parser.
    if '-y' in extra or '--yes' in extra:
        args.yes = True
        extra = [i for i in extra if i not in ('--yes', '-y')]

    # technically args.func() with setdefaults could work (see docs on subparsers)
    # but that would require all funcs to accept args and extra...
    try:
        if args.subparser_name == 'auth':
            cli.auth(args)
        elif args.subparser_name in {'list', 'list-games'}:
            cli.list_games(args)
        elif args.subparser_name == 'list-installed':
            cli.list_installed(args)
        elif args.subparser_name == 'launch':
            cli.launch_game(args, extra)
        elif args.subparser_name in {'download', 'install', 'update', 'repair'}:
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
        elif args.subparser_name == 'clean-saves':
            cli.clean_saves(args)
        elif args.subparser_name in {'verify', 'verify-game'}:
            cli.verify_game(args)
        elif args.subparser_name in {'import', 'import-game'}:
            cli.import_game(args)
        elif args.subparser_name == 'egl-sync':
            cli.egs_sync(args)
        elif args.subparser_name == 'status':
            cli.status(args)
        elif args.subparser_name == 'info':
            cli.info(args)
        elif args.subparser_name == 'alias':
            cli.alias(args)
        elif args.subparser_name == 'cleanup':
            cli.cleanup(args)
        elif args.subparser_name == 'activate':
            cli.activate(args)
        elif args.subparser_name == 'get-token':
            cli.get_token(args)
        elif args.subparser_name == 'eos-overlay':
            cli.manage_eos_overlay(args)
        elif args.subparser_name == 'crossover':
            cli.crossover_setup(args)
        elif args.subparser_name == 'move':
            cli.move(args)
    except KeyboardInterrupt:
        logger.info('Command was aborted via KeyboardInterrupt, cleaning up...')

    # Disable the update message if JSON/TSV/CSV outputs are used
    disable_update_message = False
    if hasattr(args, 'json'):
        disable_update_message = args.json
    if not disable_update_message and hasattr(args, 'tsv'):
        disable_update_message = args.tsv
    if not disable_update_message and hasattr(args, 'csv'):
        disable_update_message = args.csv

    # show note if update is available
    if not disable_update_message and cli.core.update_available and cli.core.update_notice_enabled():
        if update_info := cli.core.get_update_info():
            print(f'\nLegendary update available!')
            print(f'- New version: {update_info["version"]} - "{update_info["name"]}"')
            print(f'- Release summary:\n{update_info["summary"]}\n- Release URL: {update_info["gh_url"]}')
            if update_info['critical']:
                print('! This update is recommended as it fixes major issues.')
            if not is_windows_mac_or_pyi():
                print('If you installed legendary via a package manager it may '
                      'take some time for the update to become available.')
            elif 'downloads' in update_info:
                dl_platform = 'windows'
                if sys_platform == 'darwin':
                    dl_platform = 'macos'
                elif sys_platform == 'linux':
                    dl_platform = 'linux'

                print(f'\n- Download URL: {update_info["downloads"][dl_platform]}')

    if not disable_update_message and cli.core.overlay_update_available:
        old_version = cli.core.lgd.get_overlay_install_info().version
        new_version = cli.core.lgd.get_cached_overlay_version()["data"]["buildVersion"]
        print(f'\nEOS Overlay update available: {new_version} (Current: {old_version}).')
        print('Run "legendary eos-overlay update" to update to the latest version.')

    cli.core.exit()
    ql.stop()
    exit(0)


if __name__ == '__main__':
    # required for pyinstaller on Windows, does nothing on other platforms.
    freeze_support()
    main()
