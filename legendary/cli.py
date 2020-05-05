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

from logging.handlers import QueueListener
from multiprocessing import freeze_support, Queue as MPQueue
from sys import exit, stdout

from legendary import __version__, __codename__
from legendary.core import LegendaryCore
from legendary.models.exceptions import InvalidCredentialsError
from legendary.utils.custom_parser import AliasedSubParsersAction

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
        sformatter = logging.Formatter('[%(asctime)s] [%(name)s] %(levelname)s: %(message)s')
        shandler.setFormatter(sformatter)
        ql = QueueListener(self.logging_queue, shandler)
        ql.start()
        return ql

    def auth(self, args):
        try:
            logger.info('Testing existing login data if present...')
            if self.core.login():
                logger.info('Stored credentials are still valid, if you wish to switch to a different'
                            'account, delete ~/.config/legendary/user.json and try again.')
                exit(0)
        except ValueError:
            pass
        except InvalidCredentialsError:
            logger.error('Stored credentials were found but were no longer valid. Continuing with login...')
            self.core.lgd.invalidate_userdata()

        if os.name == 'nt' and args.import_egs_auth:
            logger.info('Importing login session from the Epic Launcher...')
            try:
                if self.core.auth_import():
                    logger.info('Successfully imported login session from EGS!')
                    logger.info(f'Now logged in as user "{self.core.lgd.userdata["displayName"]}"')
                    exit(0)
                else:
                    logger.warning('Login session from EGS seems to no longer be valid.')
                    exit(1)
            except ValueError:
                logger.error('No EGS login session found, please login normally.')
                exit(1)

        # unfortunately the captcha stuff makes a complete CLI login flow kinda impossible right now...
        print('Please login via the epic web login!')
        webbrowser.open(
            'https://www.epicgames.com/id/login?redirectUrl=https%3A%2F%2Fwww.epicgames.com%2Fid%2Fapi%2Fexchange'
        )
        print('If web page did not open automatically, please navigate '
              'to https://www.epicgames.com/id/login in your web browser')
        print('- In case you opened the link manually; please open https://www.epicgames.com/id/api/exchange '
              'in your web browser after you have finished logging in.')
        exchange_code = input('Please enter code from JSON response: ')
        exchange_token = exchange_code.strip().strip('"')

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
            print(f' * {game.app_title} (App name: {game.app_name}, version: {game.app_version})')
            for dlc in dlc_list[game.asset_info.catalog_item_id]:
                print(f'  + {dlc.app_title} (App name: {dlc.app_name}, version: {dlc.app_version})')

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
            print(f' * {game.title} (App name: {game.app_name}, version: {game.version})')
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

    def launch_game(self, args, extra):
        app_name = args.app_name
        if not self.core.is_installed(app_name):
            logger.error(f'Game {app_name} is not currently installed!')
            exit(1)

        if self.core.is_dlc(app_name):
            logger.error(f'{app_name} is DLC; please launch the base game instead!')
            exit(1)

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

    def install_game(self, args):
        if args.subparser_name == 'download':
            logger.info('The "download" command will be changed to set the --no-install command by default '
                        'in the future, please adjust install scripts etc. to use "install" instead.')

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
                                                          dl_timeout=args.dl_timeout)

        # game is either up to date or hasn't changed, so we have nothing to do
        if not analysis.dl_size:
            logger.info('Download size is 0, the game is either already up to date or has not changed. Exiting...')
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

        if not args.yes:
            choice = input(f'Do you wish to install "{igame.title}"? [Y/n]: ')
            if choice and choice.lower()[0] != 'y':
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
                dlcs = self.core.get_dlc_for_game(game.app_name)
                if dlcs:
                    print('The following DLCs are available for this game:')
                    for dlc in dlcs:
                        print(f' - {dlc.app_title} (App name: {dlc.app_name}, version: {dlc.app_version})')
                    # todo recursively call install with modified args to install DLC automatically (after confirm)
                    print('Installing DLCs works the same as the main game, just use the DLC app name instead.')
                    print('(Automatic installation of DLC is currently not supported.)')

                postinstall = self.core.install_game(igame)
                if postinstall:
                    self._handle_postinstall(postinstall, igame, yes=args.yes)

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
            choice = input(f'Do you wish to uninstall "{igame.title}"? [y/N]: ')
            if not choice or choice.lower()[0] != 'y':
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


def main():
    parser = argparse.ArgumentParser(description=f'Legendary v{__version__} - "{__codename__}"')
    parser.register('action', 'parsers', AliasedSubParsersAction)

    # general arguments
    parser.add_argument('-v', dest='debug', action='store_true', help='Set loglevel to debug')
    parser.add_argument('-y', dest='yes', action='store_true', help='Default to yes for all prompts')
    parser.add_argument('-V', dest='version', action='store_true', help='Print version and exit')

    # all the commands
    subparsers = parser.add_subparsers(title='Commands', dest='subparser_name')
    auth_parser = subparsers.add_parser('auth', help='Authenticate with EPIC')
    install_parser = subparsers.add_parser('install', help='Download a game',
                                           aliases=('download', 'update'),
                                           usage='%(prog)s <App Name> [options]',
                                           description='Aliases: download, update')
    uninstall_parser = subparsers.add_parser('uninstall', help='Uninstall (delete) a game')
    launch_parser = subparsers.add_parser('launch', help='Launch a game', usage='%(prog)s <App Name> [options]',
                                          description='Note: additional arguments are passed to the game')
    list_parser = subparsers.add_parser('list-games', help='List available (installable) games')
    list_installed_parser = subparsers.add_parser('list-installed', help='List installed games')
    list_files_parser = subparsers.add_parser('list-files', help='List files in manifest')

    install_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    uninstall_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    launch_parser.add_argument('app_name', help='Name of the app', metavar='<App Name>')
    list_files_parser.add_argument('app_name', nargs='?', help='Name of the app', metavar='<App Name>')

    # importing only works on Windows right now
    if os.name == 'nt':
        auth_parser.add_argument('--import', dest='import_egs_auth', action='store_true',
                                 help='Import EGS authentication data')

    install_parser.add_argument('--base-path', dest='base_path', action='store', metavar='<path>',
                                help='Path for game installations (defaults to ~/legendary)')
    install_parser.add_argument('--game-folder', dest='game_folder', action='store', metavar='<path>',
                                help='Folder for game installation (defaults to folder in metadata)')
    install_parser.add_argument('--max-shared-memory', dest='shared_memory', action='store', metavar='<size>',
                                type=int, help='Maximum amount of shared memory to use (in MiB), default: 1 GiB')
    install_parser.add_argument('--max-workers', dest='max_workers', action='store', metavar='<num>',
                                type=int, help='Maximum amount of download workers, default: 2 * logical CPU')
    install_parser.add_argument('--manifest', dest='override_manifest', action='store', metavar='<uri>',
                                help='Manifest URL or path to use instead of the CDN one (e.g. for downgrading)')
    install_parser.add_argument('--old-manifest', dest='override_old_manifest', action='store', metavar='<uri>',
                                help='Manifest URL or path to use as the old one (e.g. for testing patching)')
    install_parser.add_argument('--base-url', dest='override_base_url', action='store', metavar='<url>',
                                help='Base URL to download from (e.g. to test or switch to a different CDNs)')
    install_parser.add_argument('--force', dest='force', action='store_true',
                                help='Ignore existing files (overwrite)')
    install_parser.add_argument('--disable-patching', dest='disable_patching', action='store_true',
                                help='Do not attempt to patch existing installations (download entire changed file)')
    install_parser.add_argument('--download-only', '--no-install', dest='no_install', action='store_true',
                                help='Do not mark game as intalled and do not run prereq installers after download')
    install_parser.add_argument('--update-only', dest='update_only', action='store_true',
                                help='Abort if game is not already installed (for automation)')
    install_parser.add_argument('--dlm-debug', dest='dlm_debug', action='store_true',
                                help='Set download manager and worker processes\' loglevel to debug')
    install_parser.add_argument('--platform', dest='platform_override', action='store', metavar='<Platform>',
                                type=str, help='Platform override for download (disables install)')
    install_parser.add_argument('--prefix', dest='file_prefix', action='store', metavar='<prefix>', type=str,
                                help='Only fetch files whose path starts with <prefix> (case insensitive)')
    install_parser.add_argument('--exclude', dest='file_exclude_prefix', action='store', metavar='<prefix>',
                                type=str, help='Exclude files starting with <prefix> (case insensitive)')
    install_parser.add_argument('--install-tag', dest='install_tag', action='store', metavar='<tag>',
                                type=str, help='Only download files with the specified install tag (testing)')
    install_parser.add_argument('--enable-reordering', dest='order_opt', action='store_true',
                                help='Enable reordering to attempt to optimize RAM usage during download')
    install_parser.add_argument('--dl-timeout', dest='dl_timeout', action='store', metavar='<sec>', type=int,
                                help='Connection timeout for downloader (default: 10 seconds)')

    launch_parser.add_argument('--offline', dest='offline', action='store_true',
                               default=False, help='Skip login and launch game without online authentication')
    launch_parser.add_argument('--skip-version-check', dest='skip_version_check', action='store_true',
                               default=False, help='Skip version check when launching game in online mode')
    launch_parser.add_argument('--override-username', dest='user_name_override', action='store', metavar='<username>',
                               help='Override username used when launching the game (only works with some titles)')
    launch_parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                               help='Print the command line that would have been used to launch the game and exit')

    list_parser.add_argument('--platform', dest='platform_override', action='store', metavar='<Platform>',
                             type=str, help='Override platform that games are shown for')
    list_parser.add_argument('--include-ue', dest='include_ue', action='store_true',
                             help='Also include Unreal Engine content in list')
    list_parser.add_argument('--csv', dest='csv', action='store_true', help='List games in CSV format')
    list_parser.add_argument('--tsv', dest='tsv', action='store_true', help='List games in TSV format')

    list_installed_parser.add_argument('--check-updates', dest='check_updates', action='store_true',
                                       help='Check for updates when listing installed games')
    list_installed_parser.add_argument('--csv', dest='csv', action='store_true',
                                       help='List games in CSV format')
    list_installed_parser.add_argument('--tsv', dest='tsv', action='store_true',
                                       help='List games in TSV format')

    list_files_parser.add_argument('--force-download', dest='force_download', action='store_true',
                                   help='Always download instead of using on-disk manifest')
    list_files_parser.add_argument('--platform', dest='platform_override', action='store', metavar='<Platform>',
                                   type=str, help='Platform override for download (disables install)')
    list_files_parser.add_argument('--manifest', dest='override_manifest', action='store', metavar='<uri>',
                                   help='Manifest URL or path to use instead of the CDN one')
    list_files_parser.add_argument('--csv', dest='csv', action='store_true', help='Output in CSV format')
    list_files_parser.add_argument('--tsv', dest='tsv', action='store_true', help='Output in TSV format')
    list_files_parser.add_argument('--hashlist', dest='hashlist', action='store_true',
                                   help='Output file hash list in hashcheck/sha1sum compatible format')
    list_files_parser.add_argument('--install-tag', dest='install_tag', action='store', metavar='<tag>',
                                   type=str, help='Show only files with specified install tag')

    args, extra = parser.parse_known_args()

    if args.version:
        print(f'legendary version "{__version__}", codename "{__codename__}"')
        exit(0)

    if args.subparser_name not in ('auth', 'list-games', 'list-installed', 'list-files',
                                   'launch', 'download', 'uninstall', 'install', 'update'):
        print(parser.format_help())

        # Print the main help *and* the help for all of the subcommands. Thanks stackoverflow!
        print('Individual command help:')
        subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        for choice, subparser in subparsers.choices.items():
            if choice in ('install', 'update'):
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
        elif args.subparser_name in ('download', 'install', 'update'):
            cli.install_game(args)
        elif args.subparser_name == 'uninstall':
            cli.uninstall_game(args)
        elif args.subparser_name == 'list-files':
            cli.list_files(args)
    except KeyboardInterrupt:
        logger.info('Command was aborted via KeyboardInterrupt, cleaning up...')

    cli.core.exit()
    ql.stop()
    exit(0)


if __name__ == '__main__':
    # required for pyinstaller on Windows, does nothing on other platforms.
    freeze_support()
    main()
