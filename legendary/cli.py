#!/usr/bin/env python
# coding: utf-8

import argparse
import logging
import multiprocessing
import os
import shlex
import subprocess
import time
import webbrowser

from sys import exit

from legendary.core import LegendaryCore
from legendary.models.exceptions import InvalidCredentialsError

logging.basicConfig(
    format='[%(asctime)s] [%(name)s] %(levelname)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('cli')


# todo refactor this

def main():
    parser = argparse.ArgumentParser(description='Legendary (Game Launcher)')

    group = parser.add_mutually_exclusive_group()
    group.required = True
    group.title = 'Commands'
    group.add_argument('--auth', dest='auth', action='store_true',
                       help='Authenticate Legendary with your account')
    group.add_argument('--download', dest='download', action='store',
                       help='Download a game\'s files', metavar='<name>')
    group.add_argument('--install', dest='install', action='store',
                       help='Download and install a game', metavar='<name>')
    group.add_argument('--update', dest='update', action='store',
                       help='Update a game (alias for --install)', metavar='<name>')
    group.add_argument('--uninstall', dest='uninstall', action='store',
                       help='Remove a game', metavar='<name>')
    group.add_argument('--launch', dest='launch', action='store',
                       help='Launch game', metavar='<name>')
    group.add_argument('--list-games', dest='list_games', action='store_true',
                       help='List available games')
    group.add_argument('--list-installed', dest='list_installed', action='store_true',
                       help='List installed games')

    # general arguments
    parser.add_argument('-v', dest='debug', action='store_true', help='Set loglevel to debug')

    # arguments for the different commands
    if os.name == 'nt':
        auth_group = parser.add_argument_group('Authentication options')
        # auth options
        auth_group.add_argument('--import', dest='import_egs_auth', action='store_true',
                                help='Import EGS authentication data')

    download_group = parser.add_argument_group('Downloading options')
    download_group.add_argument('--base-path', dest='base_path', action='store', metavar='<path>',
                                help='Path for game installations (defaults to ~/legendary)')
    download_group.add_argument('--max-shared-memory', dest='shared_memory', action='store', metavar='<size>',
                                type=int, help='Maximum amount of shared memory to use (in MiB), default: 1 GiB')
    download_group.add_argument('--max-workers', dest='max_workers', action='store', metavar='<num>',
                                type=int, help='Maximum amount of download workers, default: 2 * logical CPU')
    download_group.add_argument('--manifest', dest='override_manifest', action='store', metavar='<uri>',
                                help='Manifest URL or path to use instead of the CDN one (e.g. for downgrading)')
    download_group.add_argument('--base-url', dest='override_base_url', action='store', metavar='<url>',
                                help='Base URL to download from (e.g. to test or switch to a different CDNs)')
    download_group.add_argument('--force', dest='force', action='store_true',
                                help='Ignore existing files (overwrite)')

    install_group = parser.add_argument_group('Installation options')
    install_group.add_argument('--disable-patching', dest='disable_patching', action='store_true',
                               help='Do not attempt to patch existing installations (download full game)')

    launch_group = parser.add_argument_group('Game launch options',
                                             description='Note: any additional arguments will be passed to the game.')
    launch_group.add_argument('--offline', dest='offline', action='store_true',
                              default=False, help='Skip login and launch game without online authentication')
    launch_group.add_argument('--skip-version-check', dest='skip_version_check', action='store_true',
                              default=False, help='Skip version check when launching game in online mode')
    launch_group.add_argument('--override-username', dest='user_name_override', action='store', metavar='<username>',
                              help='Override username used when launching the game (only works with some titles)')
    launch_group.add_argument('--dry-run', dest='dry_run', action='store_true',
                              help='Print the command line that would have been used to launch the game and exit')

    list_group = parser.add_argument_group('Listing options')
    list_group.add_argument('--check-updates', dest='check_updates', action='store_true',
                            help='Check for updates when listing installed games')

    args, extra = parser.parse_known_args()
    core = LegendaryCore()

    config_ll = core.lgd.config.get('Legendary', 'log_level', fallback='info')
    if config_ll == 'debug' or args.debug:
        logging.getLogger().setLevel(level=logging.DEBUG)
        # keep requests quiet
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

    if args.auth:
        try:
            logger.info('Testing existing login data if present...')
            if core.login():
                logger.info('Stored credentials are still valid, if you wish to switch to a different'
                            'account, delete ~/.config/legendary/user.json and try again.')
                exit(0)
        except ValueError:
            pass
        except InvalidCredentialsError:
            logger.error('Stored credentials were found but were no longer valid. Continuing with login...')
            core.lgd.invalidate_userdata()

        if os.name == 'nt' and args.import_egs_auth:
            logger.info('Importing login session from the Epic Launcher...')
            try:
                if core.auth_import():
                    logger.info('Successfully imported login session from EGS!')
                    logger.info(f'Now logged in as user "{core.lgd.userdata["displayName"]}"')
                    exit(0)
                else:
                    logger.warning('Login session from EGS seems to no longer be valid.')
                    exit(1)
            except ValueError:
                logger.error('No EGS login session found, please login normally.')
                exit(1)

        # unfortunately the captcha stuff makes a complete CLI login flow kinda impossible right now...
        print('Please login via the epic web login!')
        webbrowser.open('https://www.epicgames.com/id/login')
        print('If web page did not open automatically, please navigate '
              'to https://www.epicgames.com/id/login in your web browser')
        _ = input('Once you\'re logged in press [Enter] to continue.')

        # after logging in we need the user to copy a code from a JSON response, less than ideal :/
        webbrowser.open('https://www.epicgames.com/id/api/exchange')
        print('If second web page did not open automatically, please navigate '
              'to https://www.epicgames.com/id/api/exchange in your web browser')
        exchange_code = input('Please enter code from response: ')
        exchange_token = exchange_code.strip().strip('"')

        if core.auth_code(exchange_token):
            logger.info(f'Successfully logged in as "{core.lgd.userdata["displayName"]}"')
        else:
            logger.error('Login attempt failed, please see log for details.')

    elif args.list_games:
        logger.info('Logging in...')
        if not core.login():
            logger.error('Login failed, cannot continue!')
            exit(1)
        logger.info('Getting game list...')
        games = core.get_game_list()

        print('\nAvailable games:')
        for game in sorted(games, key=lambda x: x.app_title):
            print(f'  * {game.app_title} (App name: {game.app_name}, version: {game.app_version})')

        print(f'\nTotal: {len(games)}')

    elif args.list_installed:
        games = core.get_installed_list()

        if args.check_updates:
            logger.info('Logging in to check for updates...')
            if not core.login():
                logger.error('Login failed! Not checking for updates.')
            else:
                core.get_assets(True)

        print('\nInstalled games:')
        for game in sorted(games, key=lambda x: x.title):
            print(f'  * {game.title} (App name: {game.app_name}, version: {game.version})')
            game_asset = core.get_asset(game.app_name)
            if game_asset.build_version != game.version:
                print(f'    -> Update available! Installed: {game.version}, Latest: {game_asset.build_version}')

        print(f'\nTotal: {len(games)}')

    elif args.launch:
        app_name = args.launch.strip()
        if not core.is_installed(app_name):
            logger.error(f'Game {app_name} is not currently installed!')
            exit(1)

        if not args.offline and not core.is_offline_game(app_name):
            logger.info('Logging in...')
            if not core.login():
                logger.error('Login failed, cannot continue!')
                exit(1)

            if not args.skip_version_check and not core.is_noupdate_game(app_name):
                logger.info('Checking for updates...')
                installed = core.lgd.get_installed_game(app_name)
                latest = core.get_asset(app_name, update=True)
                if latest.build_version != installed.version:
                    logger.error('Game is out of date, please update or launch with update check skipping!')
                    exit(1)

        params, cwd, env = core.get_launch_parameters(app_name=app_name, offline=args.offline,
                                                      extra_args=extra, user=args.user_name_override)

        logger.info(f'Launching {app_name}...')
        if args.dry_run:
            logger.info(f'Launch parameters: {shlex.join(params)}')
            logger.info(f'Working directory: {cwd}')
            if env:
                logger.info('Environment overrides:', env)
        else:
            logger.debug(f'Launch parameters: {shlex.join(params)}')
            logger.debug(f'Working directory: {cwd}')
            if env:
                logger.debug('Environment overrides:', env)

            subprocess.Popen(params, cwd=cwd, env=env)

    elif args.download or args.install or args.update:
        if not core.login():
            logger.error('Login failed! Cannot continue with download process.')
            exit(1)

        target_app = next(i for i in (args.install, args.update, args.download) if i)
        if args.update:
            if not core.get_installed_game(target_app):
                logger.error(f'Update requested for "{target_app}", but app not installed!')
                exit(1)

        game = core.get_game(target_app, update_meta=True)

        if not game:
            logger.fatal(f'Could not find "{target_app}" in list of available games, did you type the name correctly?')
            exit(1)

        # todo use status queue to print progress from CLI
        dlm, analysis, igame = core.prepare_download(game=game, base_path=args.base_path, force=args.force,
                                                     max_shm=args.shared_memory, max_workers=args.max_workers,
                                                     disable_patching=args.disable_patching,
                                                     override_manifest=args.override_manifest,
                                                     override_base_url=args.override_base_url)

        # game is either up to date or hasn't changed, so we have nothing to do
        if not analysis.dl_size:
            logger.info('Download size is 0, the game is either already up to date or has not changed. Exiting...')
            # if game is downloaded but not "installed", "install" it now (todo handle postinstall as well)
            if args.install:
                core.install_game(igame)
            exit(0)

        logger.info(f'Install size: {analysis.install_size / 1024 / 1024:.02f} MiB')
        compression = (1 - (analysis.dl_size / analysis.uncompressed_dl_size)) * 100
        logger.info(f'Download size: {analysis.dl_size / 1024 / 1024:.02f} MiB '
                    f'(Compression savings: {compression:.01f}%)')
        logger.info(f'Reusable size: {analysis.reuse_size / 1024 / 1024:.02f} MiB (chunks) / '
                    f'{analysis.unchanged / 1024 / 1024:.02f} MiB (unchanged)')

        res = core.check_installation_conditions(analysis=analysis, install=igame)

        if res.failures:
            logger.fatal('Download cannot proceed, the following errors occured:')
            for msg in sorted(res.failures):
                logger.fatal(msg)
            exit(1)

        if res.warnings:
            logger.warning('Installation requirements check returned the following warnings:')
            for warn in sorted(res.warnings):
                logger.warning(warn)

        _ = input('Do you wish to proceed? [Press Enter]')
        start_t = time.time()

        try:
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
            if args.install or args.update:
                postinstall = core.install_game(igame)
                if postinstall:
                    logger.info('This game lists the following prequisites to be installed:')
                    logger.info(f'{postinstall["name"]}: {" ".join((postinstall["path"], postinstall["args"]))}')
                    if os.name == 'nt':
                        choice = input('Do you wish to install the prerequisites? ([y]es, [n]o, [i]gnore): ')
                        c = choice.lower()[0]
                        if c == 'i':
                            core.prereq_installed(igame.app_name)
                        elif c == 'y':
                            req_path, req_exec = os.path.split(postinstall['path'])
                            work_dir = os.path.join(igame.install_path, req_path)
                            fullpath = os.path.join(work_dir, req_exec)
                            subprocess.Popen([fullpath, postinstall['args']], cwd=work_dir)
                    else:
                        logger.info('Automatic installation not available on Linux.')

            logger.info(f'Finished installation process in {end_t - start_t:.02f} seconds.')

    elif args.uninstall:
        target_app = args.uninstall
        igame = core.get_installed_game(target_app)
        if not igame:
            logger.error(f'Game {target_app} not installed, cannot uninstall!')

        try:
            logger.info(f'Removing "{igame.title}" from "{igame.install_path}"...')
            core.uninstall_game(igame)
            logger.info('Game has been uninstalled.')
        except Exception as e:
            logger.warning(f'Removing game failed: {e!r}, please remove {igame.install_path} manually.')

    core.exit()
    exit(0)


if __name__ == '__main__':
    multiprocessing.freeze_support()  # required for pyinstaller
    main()
