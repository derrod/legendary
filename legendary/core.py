# coding: utf-8

import json
import logging
import os
import shlex
import shutil

from base64 import b64decode
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from locale import getdefaultlocale
from multiprocessing import Queue
from platform import system
from requests import session
from requests.exceptions import HTTPError
from sys import platform as sys_platform
from uuid import uuid4
from urllib.parse import urlencode, parse_qsl

from legendary import __version__
from legendary.api.egs import EPCAPI
from legendary.api.lgd import LGDAPI
from legendary.downloader.mp.manager import DLManager
from legendary.lfs.egl import EPCLFS
from legendary.lfs.lgndry import LGDLFS
from legendary.utils.lfs import clean_filename, delete_folder, delete_filelist, get_dir_size
from legendary.models.downloading import AnalysisResult, ConditionCheckResult
from legendary.models.egl import EGLManifest
from legendary.models.exceptions import *
from legendary.models.game import *
from legendary.models.json_manifest import JSONManifest
from legendary.models.manifest import Manifest, ManifestMeta
from legendary.models.chunk import Chunk
from legendary.utils.egl_crypt import decrypt_epic_data
from legendary.utils.env import is_windows_mac_or_pyi
from legendary.utils.game_workarounds import is_opt_enabled, update_workarounds
from legendary.utils.savegame_helper import SaveGameHelper
from legendary.utils.selective_dl import games as sdl_games
from legendary.utils.manifests import combine_manifests
from legendary.utils.wine_helpers import read_registry, get_shell_folders, case_insensitive_path_search


# ToDo: instead of true/false return values for success/failure actually raise an exception that the CLI/GUI
#  can handle to give the user more details. (Not required yet since there's no GUI so log output is fine)


class LegendaryCore:
    """
    LegendaryCore handles most of the lower level interaction with
    the downloader, lfs, and api components to make writing CLI/GUI
    code easier and cleaner and avoid duplication.
    """
    _egl_version = '11.0.1-14907503+++Portal+Release-Live'

    def __init__(self, override_config=None):
        self.log = logging.getLogger('Core')
        self.egs = EPCAPI()
        self.lgd = LGDLFS(config_file=override_config)
        self.egl = EPCLFS()
        self.lgdapi = LGDAPI()

        # on non-Windows load the programdata path from config
        if os.name != 'nt':
            self.egl.programdata_path = self.lgd.config.get('Legendary', 'egl_programdata', fallback=None)
            if self.egl.programdata_path and not os.path.exists(self.egl.programdata_path):
                self.log.error(f'Config EGL path ("{self.egl.programdata_path}") is invalid! Disabling sync...')
                self.egl.programdata_path = None
                self.lgd.config.remove_option('Legendary', 'egl_programdata')
                self.lgd.config.remove_option('Legendary', 'egl_sync')
                self.lgd.save_config()

        self.local_timezone = datetime.now().astimezone().tzinfo
        self.language_code, self.country_code = ('en', 'US')

        if locale := self.lgd.config.get('Legendary', 'locale', fallback=getdefaultlocale()[0]):
            try:
                self.language_code, self.country_code = locale.split('-' if '-' in locale else '_')
                self.log.debug(f'Set locale to {self.language_code}-{self.country_code}')
                # adjust egs api language as well
                self.egs.language_code, self.egs.country_code = self.language_code, self.country_code
            except Exception as e:
                self.log.warning(f'Getting locale failed: {e!r}, falling back to using en-US.')
        elif system() != 'Darwin':  # macOS doesn't have a default locale we can query
            self.log.warning(f'Could not determine locale, falling back to en-US')

        self.update_available = False
        self.force_show_update = False
        self.webview_killswitch = False
        self.logged_in = False

    def auth(self, username, password):
        """
        Attempts direct non-web login, raises CaptchaError if manual login is required

        :param username:
        :param password:
        :return:
        """
        raise NotImplementedError

    def auth_sid(self, sid) -> str:
        """
        Handles getting an exchange code from a session id
        :param sid: session id
        :return: exchange code
        """
        s = session()
        s.headers.update({
            'X-Epic-Event-Action': 'login',
            'X-Epic-Event-Category': 'login',
            'X-Epic-Strategy-Flags': '',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          f'EpicGamesLauncher/{self._egl_version} '
                          'UnrealEngine/4.23.0-14907503+++Portal+Release-Live '
                          'Chrome/84.0.4147.38 Safari/537.36'
        })
        s.cookies['EPIC_COUNTRY'] = self.country_code.upper()

        # get first set of cookies (EPIC_BEARER_TOKEN etc.)
        _ = s.get('https://www.epicgames.com/id/api/set-sid', params=dict(sid=sid))
        # get XSRF-TOKEN and EPIC_SESSION_AP cookie
        _ = s.get('https://www.epicgames.com/id/api/csrf')
        # finally, get the exchange code
        r = s.post('https://www.epicgames.com/id/api/exchange/generate',
                   headers={'X-XSRF-TOKEN': s.cookies['XSRF-TOKEN']})

        if r.status_code == 200:
            return r.json()['code']
        else:
            self.log.error(f'Getting exchange code failed: {r.json()}')
            return ''

    def auth_code(self, code) -> bool:
        """
        Handles authentication via exchange code (either retrieved manually or automatically)
        """
        try:
            self.lgd.userdata = self.egs.start_session(exchange_token=code)
            return True
        except Exception as e:
            self.log.error(f'Logging in failed with {e!r}, please try again.')
            return False

    def auth_import(self) -> bool:
        """Import refresh token from EGL installation and use it for logging in"""
        self.egl.read_config()
        remember_me_data = self.egl.config.get('RememberMe', 'Data')
        raw_data = b64decode(remember_me_data)
        # data is encrypted
        if raw_data[0] != '{':
            for data_key in self.egl.data_keys:
                try:
                    decrypted_data = decrypt_epic_data(data_key, raw_data)
                    re_data = json.loads(decrypted_data)[0]
                    break
                except Exception as e:
                    self.log.debug(f'Decryption with key {data_key} failed with {e!r}')
            else:
                raise ValueError('Decryption of EPIC launcher user information failed.')
        else:
            re_data = json.loads(raw_data)[0]

        if 'Token' not in re_data:
            raise ValueError('No login session in config')
        refresh_token = re_data['Token']
        try:
            self.lgd.userdata = self.egs.start_session(refresh_token=refresh_token)
            return True
        except Exception as e:
            self.log.error(f'Logging in failed with {e!r}, please try again.')
            return False

    def login(self) -> bool:
        """
        Attempts logging in with existing credentials.

        raises ValueError if no existing credentials or InvalidCredentialsError if the API return an error
        """
        if not self.lgd.userdata:
            raise ValueError('No saved credentials')
        elif self.logged_in and self.lgd.userdata['expires_at']:
            dt_exp = datetime.fromisoformat(self.lgd.userdata['expires_at'][:-1])
            dt_now = datetime.utcnow()
            td = dt_now - dt_exp

            # if session still has at least 10 minutes left we can re-use it.
            if dt_exp > dt_now and abs(td.total_seconds()) > 600:
                return True
            else:
                self.logged_in = False

        # run update check
        if self.update_check_enabled():
            try:
                self.check_for_updates()
            except Exception as e:
                self.log.warning(f'Checking for Legendary updates failed: {e!r}')
        else:
            self.apply_lgd_config()

        if self.lgd.userdata['expires_at']:
            dt_exp = datetime.fromisoformat(self.lgd.userdata['expires_at'][:-1])
            dt_now = datetime.utcnow()
            td = dt_now - dt_exp

            # if session still has at least 10 minutes left we can re-use it.
            if dt_exp > dt_now and abs(td.total_seconds()) > 600:
                self.log.info('Trying to re-use existing login session...')
                try:
                    self.egs.resume_session(self.lgd.userdata)
                    self.logged_in = True
                    return True
                except InvalidCredentialsError as e:
                    self.log.warning(f'Resuming failed due to invalid credentials: {e!r}')
                except Exception as e:
                    self.log.warning(f'Resuming failed for unknown reason: {e!r}')
                # If verify fails just continue the normal authentication process
                self.log.info('Falling back to using refresh token...')

        try:
            self.log.info('Logging in...')
            userdata = self.egs.start_session(self.lgd.userdata['refresh_token'])
        except InvalidCredentialsError:
            self.log.error('Stored credentials are no longer valid! Please login again.')
            self.lgd.invalidate_userdata()
            return False
        except HTTPError as e:
            self.log.error(f'HTTP request for login failed: {e!r}, please try again later.')
            return False

        self.lgd.userdata = userdata
        self.logged_in = True
        return True

    def update_check_enabled(self):
        return not self.lgd.config.getboolean('Legendary', 'disable_update_check', fallback=False)

    def update_notice_enabled(self):
        if self.force_show_update:
            return True
        return not self.lgd.config.getboolean('Legendary', 'disable_update_notice',
                                              fallback=not is_windows_mac_or_pyi())

    def check_for_updates(self, force=False):
        def version_tuple(v):
            return tuple(map(int, (v.split('.'))))

        cached = self.lgd.get_cached_version()
        version_info = cached['data']
        if force or not version_info or (datetime.now().timestamp() - cached['last_update']) > 24*3600:
            version_info = self.lgdapi.get_version_information()
            self.lgd.set_cached_version(version_info)

        web_version = version_info['release_info']['version']
        self.update_available = version_tuple(web_version) > version_tuple(__version__)
        self.apply_lgd_config(version_info)

    def apply_lgd_config(self, version_info=None):
        """Applies configuration options returned by update API"""
        if not version_info:
            version_info = self.lgd.get_cached_version()['data']
            # if cached data is invalid
            if not version_info:
                self.log.debug('No cached legendary config to apply.')
                return

        if 'egl_config' in version_info:
            self.egs.update_egs_params(version_info['egl_config'])
            self._egl_version = version_info['egl_config'].get('version', self._egl_version)
            for data_key in version_info['egl_config'].get('data_keys', []):
                if data_key not in self.egl.data_keys:
                    self.egl.data_keys.append(data_key)
        if game_overrides := version_info.get('game_overrides'):
            update_workarounds(game_overrides)
            if sdl_config := game_overrides.get('sdl_config'):
                # add placeholder for games to fetch from API that aren't hardcoded
                for app_name in sdl_config.keys():
                    if app_name not in sdl_games:
                        sdl_games[app_name] = None
        if lgd_config := version_info.get('legendary_config'):
            self.webview_killswitch = lgd_config.get('webview_killswitch', False)

    def get_update_info(self):
        return self.lgd.get_cached_version()['data'].get('release_info')

    def get_sdl_data(self, app_name):
        if app_name not in sdl_games:
            return None
        # load hardcoded data as fallback
        sdl_data = sdl_games[app_name]
        # get cached data
        cached = self.lgd.get_cached_sdl_data(app_name)
        # check if newer version is available and/or download if necessary
        version_info = self.lgd.get_cached_version()['data']
        latest = version_info.get('game_overrides', {}).get('sdl_config', {}).get(app_name)
        if (not cached and latest) or (cached and latest and latest > cached['version']):
            try:
                sdl_data = self.lgdapi.get_sdl_config(app_name)
                self.log.debug(f'Downloaded SDL data for "{app_name}", version: {latest}')
                self.lgd.set_cached_sdl_data(app_name, latest, sdl_data)
            except Exception as e:
                self.log.warning(f'Downloading SDL data failed with {e!r}')
        elif cached:
            sdl_data = cached['data']
        # return data if available
        return sdl_data

    def update_aliases(self, force=False):
        _aliases_enabled = not self.lgd.config.getboolean('Legendary', 'disable_auto_aliasing', fallback=False)
        if _aliases_enabled and (force or not self.lgd.aliases):
            self.lgd.generate_aliases()

    def get_assets(self, update_assets=False, platform='Windows') -> List[GameAsset]:
        # do not save and always fetch list when platform is overridden
        if not self.lgd.assets or update_assets or platform not in self.lgd.assets:
            # if not logged in, return empty list
            if not self.egs.user:
                return []

            if self.lgd.assets:
                assets = self.lgd.assets
            else:
                assets = dict()

            assets.update({
                platform: [
                    GameAsset.from_egs_json(a) for a in
                    self.egs.get_game_assets(platform=platform)
                ]
            })

            self.lgd.assets = assets

        return self.lgd.assets[platform]

    def get_asset(self, app_name, platform='Windows', update=False) -> GameAsset:
        if update or platform not in self.lgd.assets:
            self.get_assets(update_assets=True, platform=platform)

        try:
            return next(i for i in self.lgd.assets[platform] if i.app_name == app_name)
        except StopIteration:
            raise ValueError

    def asset_valid(self, app_name) -> bool:
        # EGL sync is only supported for Windows titles so this is fine
        return any(i.app_name == app_name for i in self.lgd.assets['Windows'])

    def asset_available(self, game: Game, platform='Windows') -> bool:
        # Just say yes for Origin titles
        if game.third_party_store:
            return True

        try:
            asset = self.get_asset(game.app_name, platform=platform)
            return asset is not None
        except ValueError:
            return False

    def get_game(self, app_name, update_meta=False, platform='Windows') -> Game:
        if update_meta:
            self.get_game_list(True, platform=platform)
        return self.lgd.get_game_meta(app_name)

    def get_game_list(self, update_assets=True, platform='Windows') -> List[Game]:
        return self.get_game_and_dlc_list(update_assets=update_assets, platform=platform)[0]

    def get_game_and_dlc_list(self, update_assets=True, platform='Windows',
                              force_refresh=False, skip_ue=True) -> (List[Game], Dict[str, List[Game]]):
        _ret = []
        _dlc = defaultdict(list)
        meta_updated = False

        # fetch asset information for Windows, all installed platforms, and the specified one
        platforms = {'Windows'}
        platforms |= {platform}
        platforms |= self.get_installed_platforms()

        for _platform in platforms:
            self.get_assets(update_assets=update_assets, platform=_platform)

        assets = {}
        for _platform, _assets in self.lgd.assets.items():
            for _asset in _assets:
                if _asset.app_name in assets:
                    assets[_asset.app_name][_platform] = _asset
                else:
                    assets[_asset.app_name] = {_platform: _asset}

        fetch_list = []
        games = {}

        for app_name, app_assets in sorted(assets.items()):
            if skip_ue and any(v.namespace == 'ue' for v in app_assets.values()):
                continue

            game = self.lgd.get_game_meta(app_name)
            asset_updated = False
            if game:
                asset_updated = any(game.app_version(_p) != app_assets[_p].build_version for _p in app_assets.keys())
                games[app_name] = game

            if update_assets and (not game or force_refresh or (game and asset_updated)):
                self.log.debug(f'Scheduling metadata update for {app_name}')
                # namespace/catalog item are the same for all platforms, so we can just use the first one
                _ga = next(iter(app_assets.values()))
                fetch_list.append((app_name, _ga.namespace, _ga.catalog_item_id))
                meta_updated = True

        def fetch_game_meta(args):
            app_name, namespace, catalog_item_id = args
            eg_meta = self.egs.get_game_info(namespace, catalog_item_id, timeout=10.0)
            game = Game(app_name=app_name, app_title=eg_meta['title'], metadata=eg_meta, asset_infos=assets[app_name])
            self.lgd.set_game_meta(game.app_name, game)
            games[app_name] = game
            still_needs_update.remove(app_name)

        # setup and teardown of thread pool takes some time, so only do it when it makes sense.
        still_needs_update = {e[0] for e in fetch_list}
        use_threads = len(fetch_list) > 5
        if fetch_list:
            self.log.info(f'Fetching metadata for {len(fetch_list)} app(s).')
            if use_threads:
                with ThreadPoolExecutor(max_workers=16) as executor:
                    executor.map(fetch_game_meta, fetch_list, timeout=60.0)

        for app_name, app_assets in sorted(assets.items()):
            if skip_ue and any(v.namespace == 'ue' for v in app_assets.values()):
                continue

            game = games.get(app_name)
            # retry if metadata is still missing/threaded loading wasn't used
            if not game or app_name in still_needs_update:
                if use_threads:
                    self.log.warning(f'Fetching metadata for {app_name} failed, retrying')
                _ga = next(iter(app_assets.values()))
                fetch_game_meta((app_name, _ga.namespace, _ga.catalog_item_id))
                game = games[app_name]

            if game.is_dlc:
                _dlc[game.metadata['mainGameItem']['id']].append(game)
            elif not any(i['path'] == 'mods' for i in game.metadata.get('categories', [])) and platform in app_assets:
                _ret.append(game)

        self.update_aliases(force=meta_updated)
        if meta_updated:
            self._prune_metadata()

        return _ret, _dlc

    def _prune_metadata(self):
        # compile list of games without assets, then delete their metadata
        available_assets = set()
        for platform in self.get_installed_platforms() | {'Windows'}:
            available_assets |= {i.app_name for i in self.get_assets(platform=platform)}

        for app_name in self.lgd.get_game_app_names():
            if app_name in available_assets:
                continue
            # if metadata is still used by an install hold-off on deleting it
            if self.is_installed(app_name):
                continue
            game = self.get_game(app_name)
            # Origin games etc.
            if game.third_party_store:
                continue
            self.log.debug(f'Removing old/unused metadata for "{app_name}"')
            self.lgd.delete_game_meta(app_name)

    def get_non_asset_library_items(self, force_refresh=False,
                                    skip_ue=True) -> (List[Game], Dict[str, List[Game]]):
        """
        Gets a list of Games without assets for installation, for instance Games delivered via
        third-party stores that do not have assets for installation

        :param force_refresh: Force a metadata refresh
        :param skip_ue: Ingore Unreal Marketplace entries
        :return: List of Games and DLC that do not have assets
        """
        _ret = []
        _dlc = defaultdict(list)
        # get all the appnames we have to ignore
        ignore = set(i.app_name for i in self.get_assets())

        for libitem in self.egs.get_library_items():
            if libitem['namespace'] == 'ue' and skip_ue:
                continue
            if libitem['appName'] in ignore:
                continue

            game = self.lgd.get_game_meta(libitem['appName'])
            if not game or force_refresh:
                eg_meta = self.egs.get_game_info(libitem['namespace'], libitem['catalogItemId'])
                game = Game(app_name=libitem['appName'], app_title=eg_meta['title'], metadata=eg_meta)
                self.lgd.set_game_meta(game.app_name, game)

            if game.is_dlc:
                _dlc[game.metadata['mainGameItem']['id']].append(game)
            elif not any(i['path'] == 'mods' for i in game.metadata.get('categories', [])):
                _ret.append(game)

        # Force refresh to make sure these titles are included in aliasing
        self.update_aliases(force=True)
        return _ret, _dlc

    def get_dlc_for_game(self, app_name, platform='Windows'):
        game = self.get_game(app_name)
        if not game:
            self.log.warning(f'Metadata for {app_name} is missing!')
            return []

        if game.is_dlc:  # dlc shouldn't have DLC
            return []

        _, dlcs = self.get_game_and_dlc_list(update_assets=False, platform=platform)
        return dlcs[game.catalog_item_id]

    def get_installed_platforms(self):
        return {i.platform for i in self._get_installed_list(False)}

    def get_installed_list(self, include_dlc=False) -> List[InstalledGame]:
        if self.egl_sync_enabled:
            self.log.debug('Running EGL sync...')
            self.egl_sync()

        return self._get_installed_list(include_dlc)

    def _get_installed_list(self, include_dlc=False) -> List[InstalledGame]:
        if include_dlc:
            return self.lgd.get_installed_list()
        else:
            return [g for g in self.lgd.get_installed_list() if not g.is_dlc]

    def get_installed_dlc_list(self) -> List[InstalledGame]:
        return [g for g in self.lgd.get_installed_list() if g.is_dlc]

    def get_installed_game(self, app_name, skip_sync=False) -> InstalledGame:
        igame = self._get_installed_game(app_name)
        if not skip_sync and igame and self.egl_sync_enabled and igame.egl_guid and not igame.is_dlc:
            self.egl_sync(app_name)
            return self._get_installed_game(app_name)
        else:
            return igame

    def _get_installed_game(self, app_name) -> InstalledGame:
        return self.lgd.get_installed_game(app_name)

    def get_app_environment(self, app_name, wine_pfx=None) -> dict:
        # get environment overrides from config
        env = dict()
        if 'default.env' in self.lgd.config:
            env.update({k: v for k, v in self.lgd.config[f'default.env'].items() if v and not k.startswith(';')})
        if f'{app_name}.env' in self.lgd.config:
            env.update({k: v for k, v in self.lgd.config[f'{app_name}.env'].items() if v and not k.startswith(';')})

        # override wine prefix if necessary
        if wine_pfx:
            env['WINEPREFIX'] = wine_pfx
        elif 'WINEPREFIX' not in os.environ:
            # only use config variable if not already set in environment
            if wine_pfx := self.lgd.config.get(app_name, 'wine_prefix', fallback=None):
                env['WINEPREFIX'] = wine_pfx

        return env

    def get_app_launch_command(self, app_name, wrapper=None, wine_binary=None, disable_wine=False):
        _cmd = []
        if wrapper or (wrapper := self.lgd.config.get(app_name, 'wrapper',
                                                      fallback=self.lgd.config.get('default', 'wrapper',
                                                                                   fallback=None))):
            _cmd.extend(shlex.split(wrapper))

        if os.name != 'nt' and not disable_wine:
            if not wine_binary:
                # check if there's a default override
                wine_binary = self.lgd.config.get('default', 'wine_executable', fallback='wine')
                # check if there's a game specific override
                wine_binary = self.lgd.config.get(app_name, 'wine_executable', fallback=wine_binary)

            if not self.lgd.config.getboolean(app_name, 'no_wine',
                                              fallback=self.lgd.config.get('default', 'no_wine', fallback=False)):
                _cmd.append(wine_binary)

        return _cmd

    def get_launch_parameters(self, app_name: str, offline: bool = False,
                              user: str = None, extra_args: list = None,
                              wine_bin: str = None, wine_pfx: str = None,
                              language: str = None, wrapper: str = None,
                              disable_wine: bool = False,
                              executable_override: str = None) -> LaunchParameters:
        install = self.lgd.get_installed_game(app_name)
        game = self.lgd.get_game_meta(app_name)

        # Disable wine for non-Windows executables (e.g. native macOS)
        if not install.platform.startswith('Win'):
            disable_wine = True
            wine_pfx = wine_bin = None

        if executable_override or (executable_override := self.lgd.config.get(app_name, 'override_exe', fallback=None)):
            game_exe = executable_override.replace('\\', '/')
            exe_path = os.path.join(install.install_path, game_exe)
            if not os.path.exists(exe_path):
                raise ValueError(f'Executable path is invalid: {exe_path}')
        else:
            game_exe = install.executable.replace('\\', '/').lstrip('/')
            exe_path = os.path.join(install.install_path, game_exe)

        working_dir = os.path.split(exe_path)[0]

        params = LaunchParameters(
            game_executable=game_exe, game_directory=install.install_path, working_directory=working_dir,
            launch_command=self.get_app_launch_command(app_name, wrapper, wine_bin, disable_wine),
            environment=self.get_app_environment(app_name, wine_pfx=wine_pfx)
        )

        if install.launch_parameters:
            try:
                params.game_parameters.extend(shlex.split(install.launch_parameters, posix=False))
            except ValueError as e:
                self.log.warning(f'Parsing predefined launch parameters failed with: {e!r}, '
                                 f'input: {install.launch_parameters}')

        game_token = ''
        if not offline:
            self.log.info('Getting authentication token...')
            game_token = self.egs.get_game_token()['code']
        elif not install.can_run_offline:
            self.log.warning('Game is not approved for offline use and may not work correctly.')

        user_name = self.lgd.userdata['displayName']
        account_id = self.lgd.userdata['account_id']
        if user:
            user_name = user

        params.egl_parameters.extend([
            '-AUTH_LOGIN=unused',
            f'-AUTH_PASSWORD={game_token}',
            '-AUTH_TYPE=exchangecode',
            f'-epicapp={app_name}',
            '-epicenv=Prod'])

        if install.requires_ot and not offline:
            self.log.info('Getting ownership token.')
            ovt = self.egs.get_ownership_token(game.namespace, game.catalog_item_id)
            ovt_path = os.path.join(self.lgd.get_tmp_path(), f'{game.namespace}{game.catalog_item_id}.ovt')
            with open(ovt_path, 'wb') as f:
                f.write(ovt)
            params.egl_parameters.append(f'-epicovt={ovt_path}')

        language_code = self.lgd.config.get(app_name, 'language', fallback=language)
        if not language_code:  # fall back to system or config language
            language_code = self.language_code

        params.egl_parameters.extend([
            '-EpicPortal',
            f'-epicusername={user_name}',
            f'-epicuserid={account_id}',
            f'-epiclocale={language_code}'
        ])

        if extra_args:
            params.user_parameters.extend(extra_args)

        if config_args := self.lgd.config.get(app_name, 'start_params', fallback=None):
            params.user_parameters.extend(shlex.split(config_args.strip()))

        return params

    def get_origin_uri(self, app_name: str, offline: bool = False) -> str:
        if offline:
            token = '0'
        else:
            token = self.egs.get_game_token()['code']

        user_name = self.lgd.userdata['displayName']
        account_id = self.lgd.userdata['account_id']
        parameters = [
            ('AUTH_PASSWORD', token),
            ('AUTH_TYPE', 'exchangecode'),
            ('epicusername', user_name),
            ('epicuserid', account_id),
            ('epiclocale', self.language_code),
        ]

        game = self.get_game(app_name)
        extra_args = game.metadata.get('customAttributes', {}).get('AdditionalCommandline', {}).get('value')
        if extra_args:
            parameters.extend(parse_qsl(extra_args))

        return f'link2ea://launchgame/{app_name}?{urlencode(parameters)}'

    def get_save_games(self, app_name: str = ''):
        savegames = self.egs.get_user_cloud_saves(app_name, manifests=not not app_name)
        _saves = []
        for fname, f in savegames['files'].items():
            if '.manifest' not in fname:
                continue
            f_parts = fname.split('/')
            _saves.append(SaveGameFile(app_name=f_parts[2], filename=fname, manifest_name=f_parts[4],
                                       datetime=datetime.fromisoformat(f['lastModified'][:-1])))

        return _saves

    def get_save_path(self, app_name, platform='Windows'):
        game = self.lgd.get_game_meta(app_name)

        if platform == 'Mac':
            save_path = game.metadata['customAttributes'].get('CloudSaveFolder_MAC', {}).get('value')
        else:
            save_path = game.metadata['customAttributes'].get('CloudSaveFolder', {}).get('value')

        if not save_path:
            raise ValueError('Game does not support cloud saves')

        igame = self.lgd.get_installed_game(app_name)
        if not igame:
            raise ValueError('Game is not installed!')

        # the following variables are known:
        path_vars = {
            '{installdir}': igame.install_path,
            '{epicid}': self.lgd.userdata['account_id']
        }

        if sys_platform == 'win32':
            path_vars.update({
                '{appdata}': os.path.expandvars('%LOCALAPPDATA%'),
                '{userdir}': os.path.expandvars('%userprofile%/documents'),
                '{userprofile}': os.path.expandvars('%userprofile%'),
                '{usersavedgames}': os.path.expandvars('%userprofile%/Saved Games')
            })
        elif sys_platform == 'darwin' and platform == 'Mac':
            path_vars.update({
                '{appdata}': os.path.expanduser('~/Library/Application Support'),
                '{userdir}': os.path.expanduser('~/Documents'),
                '{userlibrary}': os.path.expanduser('~/Library')
            })
        else:
            # attempt to get WINE prefix from config
            wine_pfx = self.lgd.config.get(app_name, 'wine_prefix', fallback=None)
            if not wine_pfx:
                wine_pfx = self.lgd.config.get(f'{app_name}.env', 'WINEPREFIX', fallback=None)
            if not wine_pfx:
                proton_pfx = self.lgd.config.get(f'{app_name}.env', 'STEAM_COMPAT_DATA_PATH', fallback=None)
                if proton_pfx:
                    wine_pfx = f'{proton_pfx}/pfx'
            if not wine_pfx:
                wine_pfx = os.path.expanduser('~/.wine')

            # if we have a prefix, read the `user.reg` file and get the proper paths.
            if os.path.isdir(wine_pfx):
                wine_reg = read_registry(wine_pfx)
                wine_folders = get_shell_folders(wine_reg, wine_pfx)
                # path_vars['{userprofile}'] = user_path
                path_vars['{appdata}'] = wine_folders['Local AppData']
                # this maps to ~/Documents, but the name is locale-dependent so just resolve the symlink from WINE
                path_vars['{userdir}'] = os.path.realpath(wine_folders['Personal'])
                path_vars['{usersavedgames}'] = wine_folders['{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}']

        # replace backslashes
        save_path = save_path.replace('\\', '/')

        # these paths should always use a forward slash
        new_save_path = [path_vars.get(p.lower(), p) for p in save_path.split('/')]
        absolute_path = os.path.realpath(os.path.join(*new_save_path))
        # attempt to resolve as much as possible on case-sensitive file-systems
        if os.name != 'nt' and platform != 'Mac':
            absolute_path = case_insensitive_path_search(absolute_path)

        return absolute_path

    def check_savegame_state(self, path: str, save: SaveGameFile) -> (SaveGameStatus, (datetime, datetime)):
        latest = 0
        for _dir, _, _files in os.walk(path):
            for _file in _files:
                s = os.stat(os.path.join(_dir, _file))
                latest = max(latest, s.st_mtime)

        if not latest and not save:
            return SaveGameStatus.NO_SAVE, (None, None)

        # timezones are fun!
        dt_local = datetime.fromtimestamp(latest).replace(tzinfo=self.local_timezone).astimezone(timezone.utc)
        if not save:
            return SaveGameStatus.LOCAL_NEWER, (dt_local, None)

        dt_remote = datetime.strptime(save.manifest_name, '%Y.%m.%d-%H.%M.%S.manifest').replace(tzinfo=timezone.utc)
        if not latest:
            return SaveGameStatus.REMOTE_NEWER, (None, dt_remote)

        self.log.debug(f'Local save date: {str(dt_local)}, Remote save date: {str(dt_remote)}')

        # Ideally we check the files themselves based on manifest,
        # this is mostly a guess but should be accurate enough.
        if abs((dt_local - dt_remote).total_seconds()) < 60:
            return SaveGameStatus.SAME_AGE, (dt_local, dt_remote)
        elif dt_local > dt_remote:
            return SaveGameStatus.LOCAL_NEWER, (dt_local, dt_remote)
        else:
            return SaveGameStatus.REMOTE_NEWER, (dt_local, dt_remote)

    def upload_save(self, app_name, save_dir, local_dt: datetime = None,
                    disable_filtering: bool = False):
        game = self.lgd.get_game_meta(app_name)
        custom_attr = game.metadata['customAttributes']
        save_path = custom_attr.get('CloudSaveFolder', {}).get('value')
        save_path_mac = custom_attr.get('CloudSaveFolder_MAC', {}).get('value')

        include_f = exclude_f = None
        if not disable_filtering:
            # get file inclusion and exclusion filters if they exist
            if (_include := custom_attr.get('CloudIncludeList', {}).get('value', None)) is not None:
                include_f = _include.split(',')
            if (_exclude := custom_attr.get('CloudExcludeList', {}).get('value', None)) is not None:
                exclude_f = _exclude.split(',')

        if not save_path and not save_path_mac:
            raise ValueError('Game does not support cloud saves')

        sgh = SaveGameHelper()
        files = sgh.package_savegame(save_dir, app_name, self.egs.user.get('account_id'),
                                     save_path, save_path_mac, include_f, exclude_f, local_dt)

        if not files:
            self.log.info('No files to upload. If you believe this is incorrect run command with "--disable-filters"')
            return

        self.log.debug(f'Packed files: {str(files)}, creating cloud files...')
        resp = self.egs.create_game_cloud_saves(app_name, list(files.keys()))

        self.log.info('Starting upload...')
        for remote_path, file_info in resp['files'].items():
            self.log.debug(f'Uploading "{remote_path}"')
            f = files.get(remote_path)
            self.egs.unauth_session.put(file_info['writeLink'], data=f.read())

        self.log.info('Finished uploading savegame.')

    def download_saves(self, app_name='', manifest_name='', save_dir='', clean_dir=False):
        save_path = os.path.join(self.get_default_install_dir(), '.saves')
        if not os.path.exists(save_path):
            os.makedirs(save_path)

        _save_dir = save_dir
        savegames = self.egs.get_user_cloud_saves(app_name=app_name)
        files = savegames['files']
        for fname, f in files.items():
            if '.manifest' not in fname:
                continue
            f_parts = fname.split('/')

            if manifest_name and f_parts[4] != manifest_name:
                continue
            if not save_dir:
                _save_dir = os.path.join(save_path, f'{f_parts[2]}/{f_parts[4].rpartition(".")[0]}')
                if not os.path.exists(_save_dir):
                    os.makedirs(_save_dir)

            if clean_dir:
                self.log.info('Deleting old save files...')
                delete_folder(_save_dir)

            self.log.info(f'Downloading "{fname.split("/", 2)[2]}"...')
            # download manifest
            r = self.egs.unauth_session.get(f['readLink'])
            if r.status_code != 200:
                self.log.error(f'Download failed, status code: {r.status_code}')
                continue

            if not r.content:
                self.log.error('Manifest is empty! Skipping...')
                continue

            m = self.load_manifest(r.content)

            # download chunks required for extraction
            chunks = dict()
            for chunk in m.chunk_data_list.elements:
                cpath_p = fname.split('/', 3)[:3]
                cpath_p.append(chunk.path)
                cpath = '/'.join(cpath_p)
                if cpath not in files:
                    self.log.warning(f'Chunk {cpath} not in file list, save data may be incomplete!')
                    continue

                self.log.debug(f'Downloading chunk "{cpath}"')
                r = self.egs.unauth_session.get(files[cpath]['readLink'])
                if r.status_code != 200:
                    self.log.error(f'Download failed, status code: {r.status_code}')
                    break
                c = Chunk.read_buffer(r.content)
                chunks[c.guid_num] = c.data

            if not chunks:
                if manifest_name:
                    self.log.fatal(f'No chunks were available, aborting. Try running '
                                   f'"legendary clean-saves {app_name}" and try again.')
                    return
                else:
                    self.log.error(f'No chunks were available, skipping. You can run "legendary clean-saves" '
                                   f'to remove this broken save from your account.')
                    continue

            for fm in m.file_manifest_list.elements:
                dirs, fname = os.path.split(fm.filename)
                fdir = os.path.join(_save_dir, dirs)
                fpath = os.path.join(fdir, fname)
                if not os.path.exists(fdir):
                    os.makedirs(fdir)

                self.log.debug(f'Writing "{fpath}"...')
                with open(fpath, 'wb') as fh:
                    for cp in fm.chunk_parts:
                        if cp.guid_num not in chunks:
                            self.log.error(f'Chunk part for {fname} is missing, file may be corrupted!')
                        else:
                            fh.write(chunks[cp.guid_num][cp.offset:cp.offset + cp.size])

                # set modified time to savegame creation timestamp
                m_date = datetime.strptime(f_parts[4], '%Y.%m.%d-%H.%M.%S.manifest')
                m_date = m_date.replace(tzinfo=timezone.utc).astimezone(self.local_timezone)
                os.utime(fpath, (m_date.timestamp(), m_date.timestamp()))

        self.log.info('Successfully completed savegame download.')

    def clean_saves(self, app_name='', delete_incomplete=False):
        savegames = self.egs.get_user_cloud_saves(app_name=app_name)
        files = savegames['files']
        deletion_list = []
        used_chunks = set()
        do_not_delete = set()

        # check if all chunks for manifests are there
        for fname, f in files.items():
            if '.manifest' not in fname:
                continue

            app_name = fname.split('/', 3)[2]

            self.log.info(f'Checking {app_name} "{fname.split("/", 2)[2]}"...')
            # download manifest
            r = self.egs.unauth_session.get(f['readLink'])

            if r.status_code == 404:
                self.log.error('Manifest is missing! Marking for deletion.')
                deletion_list.append(fname)
                continue
            elif r.status_code != 200:
                self.log.warning(f'Download failed, status code: {r.status_code}. Skipping...')
                do_not_delete.add(app_name)
                continue

            if not r.content:
                self.log.error('Manifest is empty! Marking for deletion.')
                deletion_list.append(fname)
                continue

            m = self.load_manifest(r.content)
            # check if all required chunks are present
            chunk_fnames = set()
            missing_chunks = 0
            total_chunks = m.chunk_data_list.count
            for chunk in m.chunk_data_list.elements:
                cpath_p = fname.split('/', 3)[:3]
                cpath_p.append(chunk.path)
                cpath = '/'.join(cpath_p)
                chunk_fnames.add(cpath)
                if cpath not in files:
                    missing_chunks += 1

            if (0 < missing_chunks < total_chunks and delete_incomplete) or missing_chunks == total_chunks:
                self.log.error(f'Chunk(s) missing, marking manifest for deletion.')
                deletion_list.append(fname)
                continue
            elif 0 < missing_chunks < total_chunks:
                self.log.error(f'Some chunk(s) missing, optionally run "legendary download-saves" to obtain a backup '
                               f'of the corrupted save, then re-run this command with "--delete-incomplete" to remove '
                               f'it from the cloud save service.')

            used_chunks |= chunk_fnames

        # check for orphaned chunks (not used in any manifests)
        for fname, f in files.items():
            if fname in used_chunks or '.manifest' in fname:
                continue
            # skip chunks where orphan status could not be reliably determined
            if fname.split('/', 3)[2] in do_not_delete:
                continue
            self.log.debug(f'Marking orphaned chunk {fname} for deletion.')
            deletion_list.append(fname)

        if deletion_list:
            self.log.info('Deleting unused/broken files...')
            for fname in deletion_list:
                self.log.debug(f'Deleting {fname}')
                self.egs.delete_game_cloud_save_file(fname)
            self.log.info(f'Deleted {len(deletion_list)} files.')
        else:
            self.log.info('Nothing to delete.')

        self.log.info('Successfully completed savegame cleanup.')

    def is_offline_game(self, app_name: str) -> bool:
        return self.lgd.config.getboolean(app_name, 'offline', fallback=False)

    def is_noupdate_game(self, app_name: str) -> bool:
        return self.lgd.config.getboolean(app_name, 'skip_update_check', fallback=False)

    def is_latest(self, app_name: str) -> bool:
        installed = self.lgd.get_installed_game(app_name)

        for ass in self.get_assets(True):
            if ass.app_name == app_name:
                if ass.build_version != installed.version:
                    return False
                else:
                    return True
        # if we get here something is very wrong
        raise ValueError(f'Could not find {app_name} in asset list!')

    def is_installed(self, app_name: str) -> bool:
        return self.get_installed_game(app_name) is not None

    def _is_installed(self, app_name: str) -> bool:
        return self._get_installed_game(app_name) is not None

    def is_dlc(self, app_name: str) -> bool:
        meta = self.lgd.get_game_meta(app_name)
        if not meta:
            raise ValueError('Game unknown!')
        return meta.is_dlc

    @staticmethod
    def load_manifest(data: bytes) -> Manifest:
        if data[0:1] == b'{':
            return JSONManifest.read_all(data)
        else:
            return Manifest.read_all(data)

    def get_installed_manifest(self, app_name):
        igame = self._get_installed_game(app_name)
        old_bytes = self.lgd.load_manifest(app_name, igame.version, igame.platform)
        return old_bytes, igame.base_urls

    def get_cdn_urls(self, game, platform='Windows'):
        m_api_r = self.egs.get_game_manifest(game.namespace, game.catalog_item_id,
                                             game.app_name, platform)

        # never seen this outside the launcher itself, but if it happens: PANIC!
        if len(m_api_r['elements']) > 1:
            raise ValueError('Manifest response has more than one element!')

        base_urls = []
        manifest_urls = []
        for manifest in m_api_r['elements'][0]['manifests']:
            base_url = manifest['uri'].rpartition('/')[0]
            if base_url not in base_urls:
                base_urls.append(base_url)

            if 'queryParams' in manifest:
                params = '&'.join(f'{p["name"]}={p["value"]}' for p in manifest['queryParams'])
                manifest_urls.append(f'{manifest["uri"]}?{params}')
            else:
                manifest_urls.append(manifest['uri'])

        return manifest_urls, base_urls

    def get_cdn_manifest(self, game, platform='Windows'):
        manifest_urls, base_urls = self.get_cdn_urls(game, platform)
        self.log.debug(f'Downloading manifest from {manifest_urls[0]} ...')
        r = self.egs.unauth_session.get(manifest_urls[0])
        r.raise_for_status()
        return r.content, base_urls

    def get_uri_manifest(self, uri):
        if uri.startswith('http'):
            r = self.egs.unauth_session.get(uri)
            r.raise_for_status()
            new_manifest_data = r.content
            base_urls = [r.url.rpartition('/')[0]]
        else:
            base_urls = []
            with open(uri, 'rb') as f:
                new_manifest_data = f.read()

        return new_manifest_data, base_urls

    def get_delta_manifest(self, base_url, old_build_id, new_build_id):
        """Get optimized delta manifest (doesn't seem to exist for most games)"""
        if old_build_id == new_build_id:
            return None

        r = self.egs.unauth_session.get(f'{base_url}/Deltas/{new_build_id}/{old_build_id}.delta')
        if r.status_code == 200:
            return r.content
        else:
            return None

    def prepare_download(self, game: Game, base_game: Game = None, base_path: str = '',
                         status_q: Queue = None, max_shm: int = 0, max_workers: int = 0,
                         force: bool = False, disable_patching: bool = False,
                         game_folder: str = '', override_manifest: str = '',
                         override_old_manifest: str = '', override_base_url: str = '',
                         platform: str = 'Windows', file_prefix_filter: list = None,
                         file_exclude_filter: list = None, file_install_tag: list = None,
                         dl_optimizations: bool = False, dl_timeout: int = 10,
                         repair: bool = False, repair_use_latest: bool = False,
                         disable_delta: bool = False, override_delta_manifest: str = '',
                         egl_guid: str = '', preferred_cdn: str = None,
                         disable_https: bool = False) -> (DLManager, AnalysisResult, ManifestMeta):
        # load old manifest
        old_manifest = None

        # load old manifest if we have one
        if override_old_manifest:
            self.log.info(f'Overriding old manifest with "{override_old_manifest}"')
            old_bytes, _ = self.get_uri_manifest(override_old_manifest)
            old_manifest = self.load_manifest(old_bytes)
        elif not disable_patching and not force and self.is_installed(game.app_name):
            old_bytes, _base_urls = self.get_installed_manifest(game.app_name)
            if _base_urls and not game.base_urls:
                game.base_urls = _base_urls

            if not old_bytes:
                self.log.error(f'Could not load old manifest, patching will not work!')
            else:
                old_manifest = self.load_manifest(old_bytes)

        base_urls = game.base_urls
        if override_manifest:
            self.log.info(f'Overriding manifest with "{override_manifest}"')
            new_manifest_data, _base_urls = self.get_uri_manifest(override_manifest)
            # if override manifest has a base URL use that instead
            if _base_urls:
                base_urls = _base_urls
        else:
            new_manifest_data, base_urls = self.get_cdn_manifest(game, platform)
            # overwrite base urls in metadata with current ones to avoid using old/dead CDNs
            game.base_urls = base_urls
            # save base urls to game metadata
            self.lgd.set_game_meta(game.app_name, game)

        self.log.info('Parsing game manifest...')
        new_manifest = self.load_manifest(new_manifest_data)
        self.log.debug(f'Base urls: {base_urls}')
        # save manifest with version name as well for testing/downgrading/etc.
        self.lgd.save_manifest(game.app_name, new_manifest_data,
                               version=new_manifest.meta.build_version,
                               platform=platform)

        # check if we should use a delta manifest or not
        disable_delta = disable_delta or ((override_old_manifest or override_manifest) and not override_delta_manifest)
        if old_manifest and new_manifest:
            disable_delta = disable_delta or (old_manifest.meta.build_id == new_manifest.meta.build_id)
        if old_manifest and new_manifest and not disable_delta:
            if override_delta_manifest:
                self.log.info(f'Overriding delta manifest with "{override_delta_manifest}"')
                delta_manifest_data, _ = self.get_uri_manifest(override_delta_manifest)
            else:
                delta_manifest_data = self.get_delta_manifest(base_urls[0],
                                                              old_manifest.meta.build_id,
                                                              new_manifest.meta.build_id)
            if delta_manifest_data:
                delta_manifest = self.load_manifest(delta_manifest_data)
                self.log.info(f'Using optimized delta manifest to upgrade from build '
                              f'"{old_manifest.meta.build_id}" to '
                              f'"{new_manifest.meta.build_id}"...')
                combine_manifests(new_manifest, delta_manifest)
            else:
                self.log.debug(f'No Delta manifest received from CDN.')

        # reuse existing installation's directory
        if igame := self.get_installed_game(base_game.app_name if base_game else game.app_name):
            install_path = igame.install_path
            # make sure to re-use the epic guid we assigned on first install
            if not game.is_dlc and igame.egl_guid:
                egl_guid = igame.egl_guid
        else:
            if not game_folder:
                if game.is_dlc:
                    game_folder = base_game.metadata.get('customAttributes', {}). \
                        get('FolderName', {}).get('value', base_game.app_name)
                else:
                    game_folder = game.metadata.get('customAttributes', {}). \
                        get('FolderName', {}).get('value', game.app_name)

            if not base_path:
                base_path = self.get_default_install_dir()

            # make sure base directory actually exists (but do not create game dir)
            if not os.path.exists(base_path):
                self.log.info(f'"{base_path}" does not exist, creating...')
                os.makedirs(base_path)

            install_path = os.path.join(base_path, game_folder)

        self.log.info(f'Install path: {install_path}')

        if repair:
            if not repair_use_latest:
                # use installed manifest for repairs instead of updating
                new_manifest = old_manifest
                old_manifest = None

            filename = clean_filename(f'{game.app_name}.repair')
            resume_file = os.path.join(self.lgd.get_tmp_path(), filename)
            force = False
        elif not force:
            filename = clean_filename(f'{game.app_name}.resume')
            resume_file = os.path.join(self.lgd.get_tmp_path(), filename)
        else:
            resume_file = None

        # Use user-specified base URL or preferred CDN first, otherwise fall back to
        # EGS's behaviour of just selecting the first CDN in the list.
        base_url = None
        if override_base_url:
            self.log.info(f'Overriding base URL with "{override_base_url}"')
            base_url = override_base_url
        elif preferred_cdn or (preferred_cdn := self.lgd.config.get('Legendary', 'preferred_cdn', fallback=None)):
            for url in base_urls:
                if preferred_cdn in url:
                    base_url = url
                    break
            else:
                self.log.warning(f'Preferred CDN "{preferred_cdn}" unavailable, using default selection.')
        # Use first, fail if none known
        if not base_url:
            if not base_urls:
                raise ValueError('No base URLs found, please try again.')
            base_url = base_urls[0]

        # The EGS client uses plaintext HTTP by default for the purposes of enabling simple DNS based
        # CDN redirection to a (local) cache. In Legendary this will be a config option.
        if disable_https or self.lgd.config.getboolean('Legendary', 'disable_https', fallback=False):
            base_url = base_url.replace('https://', 'http://')

        self.log.debug(f'Using base URL: {base_url}')
        scheme, cdn_host = base_url.split('/')[0:3:2]
        self.log.info(f'Selected CDN: {cdn_host} ({scheme.strip(":")})')

        if not max_shm:
            max_shm = self.lgd.config.getint('Legendary', 'max_memory', fallback=2048)

        if dl_optimizations or is_opt_enabled(game.app_name, new_manifest.meta.build_version):
            self.log.info('Download order optimizations are enabled.')
            process_opt = True
        else:
            process_opt = False

        if not max_workers:
            max_workers = self.lgd.config.getint('Legendary', 'max_workers', fallback=0)

        dlm = DLManager(install_path, base_url, resume_file=resume_file, status_q=status_q,
                        max_shared_memory=max_shm * 1024 * 1024, max_workers=max_workers,
                        dl_timeout=dl_timeout)
        anlres = dlm.run_analysis(manifest=new_manifest, old_manifest=old_manifest,
                                  patch=not disable_patching, resume=not force,
                                  file_prefix_filter=file_prefix_filter,
                                  file_exclude_filter=file_exclude_filter,
                                  file_install_tag=file_install_tag,
                                  processing_optimization=process_opt)

        prereq = None
        if new_manifest.meta.prereq_ids:
            prereq = dict(ids=new_manifest.meta.prereq_ids, name=new_manifest.meta.prereq_name,
                          path=new_manifest.meta.prereq_path, args=new_manifest.meta.prereq_args)

        offline = game.metadata.get('customAttributes', {}).get('CanRunOffline', {}).get('value', 'true')
        ot = game.metadata.get('customAttributes', {}).get('OwnershipToken', {}).get('value', 'false')

        if file_install_tag is None:
            file_install_tag = []
        igame = InstalledGame(app_name=game.app_name, title=game.app_title,
                              version=new_manifest.meta.build_version, prereq_info=prereq,
                              manifest_path=override_manifest, base_urls=base_urls,
                              install_path=install_path, executable=new_manifest.meta.launch_exe,
                              launch_parameters=new_manifest.meta.launch_command,
                              can_run_offline=offline == 'true', requires_ot=ot == 'true',
                              is_dlc=base_game is not None, install_size=anlres.install_size,
                              egl_guid=egl_guid, install_tags=file_install_tag,
                              platform=platform)

        return dlm, anlres, igame

    @staticmethod
    def check_installation_conditions(analysis: AnalysisResult,
                                      install: InstalledGame,
                                      game: Game,
                                      updating: bool = False,
                                      ignore_space_req: bool = False) -> ConditionCheckResult:
        results = ConditionCheckResult(failures=set(), warnings=set())

        # if on linux, check for eac in the files
        if os.name != 'nt':
            for f in analysis.manifest_comparison.added:
                flower = f.lower()
                if 'easyanticheat' in flower:
                    results.warnings.add('(Linux) This game uses EasyAntiCheat and may not run on linux')
                elif 'beclient' in flower:
                    results.warnings.add('(Linux) This game uses BattlEye and may not run on linux')
                elif 'equ8.dll' in flower:
                    results.warnings.add('(Linux) This game is using EQU8 anticheat and may not run on linux')
                elif flower == 'fna.dll' or flower == 'xna.dll':
                    results.warnings.add('(Linux) This game is using XNA/FNA and may not run in WINE')

        if install.requires_ot:
            results.warnings.add('This game requires an ownership verification token and likely uses Denuvo DRM.')
        if not install.can_run_offline:
            results.warnings.add('This game is not marked for offline use (may still work).')

        base_path = os.path.split(install.install_path)[0]
        if os.path.exists(base_path):
            # check if enough disk space is free (dl size is the approximate amount the installation will grow)
            min_disk_space = analysis.install_size
            if updating:
                current_size = get_dir_size(install.install_path)
                delta = max(0, analysis.install_size - current_size)
                min_disk_space = delta + analysis.biggest_file_size
            elif analysis.reuse_size:
                min_disk_space -= analysis.reuse_size

            _, _, free = shutil.disk_usage(base_path)
            if free < min_disk_space:
                free_mib = free / 1024 / 1024
                required_mib = min_disk_space / 1024 / 1024
                if ignore_space_req:
                    results.warnings.add(f'Potentially not enough available disk space! '
                                         f'{free_mib:.02f} MiB < {required_mib:.02f} MiB')
                else:
                    results.failures.add(f'Not enough available disk space! '
                                         f'{free_mib:.02f} MiB < {required_mib:.02f} MiB')
        else:
            results.failures.add(f'Install path "{base_path}" does not exist, make sure all necessary mounts are '
                                 f'available. If you previously deleted the game folder without uninstalling, run '
                                 f'"legendary uninstall -y {game.app_name}" first.')

        # check if the game actually ships the files or just a uplay installer + packed game files
        uplay_required = False
        executables = [f for f in analysis.manifest_comparison.added if
                       f.lower().endswith('.exe') and not f.startswith('Installer/')]
        if not updating and not any('uplay' not in e.lower() for e in executables) and \
                any('uplay' in e.lower() for e in executables):
            uplay_required = True
            results.failures.add('This game requires installation via Uplay and does not ship executable game files.')

        if install.prereq_info:
            prereq_path = install.prereq_info['path'].lower()
            if 'uplay' in prereq_path or 'ubisoft' in prereq_path:
                uplay_required = True

        # check if the game launches via uplay
        if install.executable == 'UplayLaunch.exe':
            uplay_required = True

        # check if the game requires linking to an external account first
        if game.partner_link_type and game.partner_link_type != 'ubisoft':
            results.warnings.add(f'This game requires linking to "{game.partner_link_type}", '
                                 f'this is currently unsupported and the game may not work.')

        if uplay_required or game.partner_link_type == 'ubisoft':
            if os.name == 'nt':
                results.warnings.add('This game requires installation of Uplay/Ubisoft Connect, direct '
                                     'installation via Uplay is recommended. '
                                     'Use "legendary activate --uplay" and follow the instructions.')
            else:
                results.warnings.add('This game requires installation of Uplay/Ubisoft Connect, direct '
                                     'installation via Uplay running in WINE (e.g. using Lutris) is recommended. '
                                     'Use "legendary activate --uplay" and follow the instructions.')

        return results

    def get_default_install_dir(self):
        return os.path.expanduser(self.lgd.config.get('Legendary', 'install_dir', fallback='~/legendary'))

    def install_game(self, installed_game: InstalledGame) -> dict:
        if self.egl_sync_enabled and not installed_game.is_dlc and installed_game.platform.startswith('Win'):
            if not installed_game.egl_guid:
                installed_game.egl_guid = str(uuid4()).replace('-', '').upper()
            prereq = self._install_game(installed_game)
            self.egl_export(installed_game.app_name)
            return prereq
        else:
            return self._install_game(installed_game)

    def _install_game(self, installed_game: InstalledGame) -> dict:
        """Save game metadata and info to mark it "installed" and also show the user the prerequisites"""
        self.lgd.set_installed_game(installed_game.app_name, installed_game)
        if installed_game.prereq_info:
            if not installed_game.prereq_info.get('installed', False):
                return installed_game.prereq_info

        return dict()

    def uninstall_game(self, installed_game: InstalledGame, delete_files=True, delete_root_directory=False):
        if installed_game.egl_guid:
            self.egl_uninstall(installed_game, delete_files=delete_files)

        if delete_files:
            try:
                manifest = self.load_manifest(self.get_installed_manifest(installed_game.app_name)[0])
                filelist = [
                    fm.filename for fm in manifest.file_manifest_list.elements if
                    not fm.install_tags or any(t in installed_game.install_tags for t in fm.install_tags)
                ]
                if not delete_filelist(installed_game.install_path, filelist, delete_root_directory):
                    self.log.error(f'Deleting "{installed_game.install_path}" failed, please remove manually.')
            except Exception as e:
                self.log.error(f'Deleting failed with {e!r}, please remove {installed_game.install_path} manually.')

        self.lgd.remove_installed_game(installed_game.app_name)

    def uninstall_tag(self, installed_game: InstalledGame):
        manifest = self.load_manifest(self.get_installed_manifest(installed_game.app_name)[0])
        tags = installed_game.install_tags
        if '' not in tags:
            tags.append('')

        # Create list of files that are now no longer needed *and* actually exist on disk
        filelist = [
            fm.filename for fm in manifest.file_manifest_list.elements if
            not any(((fit in fm.install_tags) or (not fit and not fm.install_tags)) for fit in tags)
            and os.path.exists(os.path.join(installed_game.install_path, fm.filename))
        ]

        if not delete_filelist(installed_game.install_path, filelist):
            self.log.warning(f'Deleting some deselected files failed, please check/remove manually.')

    def prereq_installed(self, app_name):
        igame = self.lgd.get_installed_game(app_name)
        igame.prereq_info['installed'] = True
        self.lgd.set_installed_game(app_name, igame)

    def import_game(self, game: Game, app_path: str, egl_guid='', platform='Windows') -> (Manifest, InstalledGame):
        needs_verify = True
        manifest_data = None

        # check if the game is from an EGL installation, load manifest if possible
        if not game.is_dlc and os.path.exists(os.path.join(app_path, '.egstore')):
            mf = None
            if not egl_guid:
                for f in os.listdir(os.path.join(app_path, '.egstore')):
                    if not f.endswith('.mancpn'):
                        continue

                    self.log.debug(f'Checking mancpn file "{f}"...')
                    mancpn = json.load(open(os.path.join(app_path, '.egstore', f), 'rb'))
                    if mancpn['AppName'] == game.app_name:
                        self.log.info('Found EGL install metadata, verifying...')
                        mf = f.replace('.mancpn', '.manifest')
                        break
            else:
                mf = f'{egl_guid}.manifest'

            if mf and os.path.exists(os.path.join(app_path, '.egstore', mf)):
                manifest_data = open(os.path.join(app_path, '.egstore', mf), 'rb').read()
            else:
                self.log.warning('.egstore folder exists but manifest file is missing, continuing as regular import...')

            # If there's no in-progress installation assume the game doesn't need to be verified
            if mf and not os.path.exists(os.path.join(app_path, '.egstore', 'bps')):
                needs_verify = False
                if os.path.exists(os.path.join(app_path, '.egstore', 'Pending')):
                    if os.listdir(os.path.join(app_path, '.egstore', 'Pending')):
                        needs_verify = True

                if not needs_verify:
                    self.log.debug(f'No in-progress installation found, assuming complete...')

        if not manifest_data:
            self.log.info(f'Downloading latest manifest for "{game.app_name}"')
            manifest_data, base_urls = self.get_cdn_manifest(game)
            if not game.base_urls:
                game.base_urls = base_urls
                self.lgd.set_game_meta(game.app_name, game)
        else:
            # base urls being empty isn't an issue, they'll be fetched when updating/repairing the game
            base_urls = game.base_urls

        # parse and save manifest to disk for verification step of import
        new_manifest = self.load_manifest(manifest_data)
        self.lgd.save_manifest(game.app_name, manifest_data,
                               version=new_manifest.meta.build_version, platform=platform)
        install_size = sum(fm.file_size for fm in new_manifest.file_manifest_list.elements)

        prereq = None
        if new_manifest.meta.prereq_ids:
            prereq = dict(ids=new_manifest.meta.prereq_ids, name=new_manifest.meta.prereq_name,
                          path=new_manifest.meta.prereq_path, args=new_manifest.meta.prereq_args)

        offline = game.metadata.get('customAttributes', {}).get('CanRunOffline', {}).get('value', 'true')
        ot = game.metadata.get('customAttributes', {}).get('OwnershipToken', {}).get('value', 'false')
        igame = InstalledGame(app_name=game.app_name, title=game.app_title, prereq_info=prereq, base_urls=base_urls,
                              install_path=app_path, version=new_manifest.meta.build_version, is_dlc=game.is_dlc,
                              executable=new_manifest.meta.launch_exe, can_run_offline=offline == 'true',
                              launch_parameters=new_manifest.meta.launch_command, requires_ot=ot == 'true',
                              needs_verification=needs_verify, install_size=install_size, egl_guid=egl_guid,
                              platform=platform)

        return new_manifest, igame

    def egl_get_importable(self):
        return [g for g in self.egl.get_manifests()
                if not self.is_installed(g.app_name) and
                g.main_game_appname == g.app_name and
                self.asset_valid(g.app_name)]

    def egl_get_exportable(self):
        if not self.egl.manifests:
            self.egl.read_manifests()
        return [g for g in self.get_installed_list() if
                g.app_name not in self.egl.manifests and g.platform.startswith('Win')]

    def egl_import(self, app_name):
        if not self.asset_valid(app_name):
            raise ValueError(f'To-be-imported game {app_name} not in game asset database!')

        self.log.debug(f'Importing "{app_name}" from EGL')
        # load egl json file
        try:
            egl_game = self.egl.get_manifest(app_name=app_name)
        except ValueError:
            self.log.fatal(f'EGL Manifest for {app_name} could not be loaded, not importing!')
            return
        # convert egl json file
        lgd_igame = egl_game.to_lgd_igame()

        # fix path on Linux if the game is installed to a Windows drive mapping
        if os.name != 'nt' and not lgd_igame.install_path.startswith('/'):
            drive_letter = lgd_igame.install_path[:2].lower()
            drive_c_path = self.egl.programdata_path.partition('ProgramData')[0]
            wine_pfx = os.path.realpath(os.path.join(drive_c_path, '..'))
            mapped_path = os.path.realpath(os.path.join(wine_pfx, 'dosdevices', drive_letter))
            if 'dosdevices' in mapped_path:
                self.log.error(f'Unable to resolve path for mapped drive "{drive_letter}" '
                               f'for WINE prefix at "{wine_pfx}"')
                return

            game_path = lgd_igame.install_path[2:].replace('\\', '/').lstrip('/')
            new_path = os.path.realpath(os.path.join(mapped_path, game_path))
            self.log.info(f'Adjusted game install path from "{lgd_igame.install_path}" to "{new_path}"')
            lgd_igame.install_path = new_path

        # check if manifest exists
        manifest_filename = os.path.join(lgd_igame.install_path, '.egstore', f'{lgd_igame.egl_guid}.manifest')
        if not os.path.exists(manifest_filename):
            self.log.warning(f'Game Manifest "{manifest_filename}" not found, cannot import!')
            return

        # load manifest file and copy it over
        with open(manifest_filename, 'rb') as f:
            manifest_data = f.read()
        new_manifest = self.load_manifest(manifest_data)
        self.lgd.save_manifest(lgd_igame.app_name, manifest_data,
                               version=new_manifest.meta.build_version,
                               platform='Windows')

        # transfer install tag choices to config
        if lgd_igame.install_tags:
            self.lgd.config.set(app_name, 'install_tags', ','.join(lgd_igame.install_tags))

        # mark game as installed
        _ = self._install_game(lgd_igame)
        return

    def egl_export(self, app_name):
        self.log.debug(f'Exporting "{app_name}" to EGL')
        # load igame/game
        lgd_game = self.get_game(app_name)
        lgd_igame = self._get_installed_game(app_name)
        manifest_data, _ = self.get_installed_manifest(app_name)
        if not manifest_data:
            self.log.error(f'Game Manifest for "{app_name}" not found, cannot export!')
            return

        # create guid if it's not set already
        if not lgd_igame.egl_guid:
            lgd_igame.egl_guid = str(uuid4()).replace('-', '').upper()
            _ = self._install_game(lgd_igame)
        # convert to egl manifest
        egl_game = EGLManifest.from_lgd_game(lgd_game, lgd_igame)

        # make sure .egstore folder exists
        egstore_folder = os.path.join(lgd_igame.install_path, '.egstore')
        if not os.path.exists(egstore_folder):
            os.makedirs(egstore_folder)

        # copy manifest and create mancpn file in .egstore folder
        with open(os.path.join(egstore_folder, f'{egl_game.installation_guid}.manifest', ), 'wb') as mf:
            mf.write(manifest_data)

        mancpn = dict(FormatVersion=0, AppName=app_name,
                      CatalogItemId=lgd_game.catalog_item_id,
                      CatalogNamespace=lgd_game.namespace)
        with open(os.path.join(egstore_folder, f'{egl_game.installation_guid}.mancpn', ), 'w') as mcpnf:
            json.dump(mancpn, mcpnf, indent=4, sort_keys=True)

        # And finally, write the file for EGL
        self.egl.set_manifest(egl_game)

    def egl_uninstall(self, igame: InstalledGame, delete_files=True):
        try:
            self.egl.delete_manifest(igame.app_name)
        except ValueError as e:
            self.log.warning(f'Deleting EGL manifest failed: {e!r}')

        if delete_files:
            delete_folder(os.path.join(igame.install_path, '.egstore'))

    def egl_restore_or_uninstall(self, igame):
        # check if game binary is still present, if not; uninstall
        if not os.path.exists(os.path.join(igame.install_path,
                                           igame.executable.lstrip('/'))):
            self.log.warning('Synced game\'s files no longer exists, assuming it has been uninstalled.')
            igame.egl_guid = ''
            return self.uninstall_game(igame, delete_files=False)
        else:
            self.log.info('Game files exist, assuming game is still installed, re-exporting to EGL...')
            return self.egl_export(igame.app_name)

    def egl_sync(self, app_name=''):
        """
        Sync game installs between Legendary and the Epic Games Launcher
        """
        # read egl json files
        if app_name:
            lgd_igame = self._get_installed_game(app_name)
            if not self.egl.manifests:
                self.egl.read_manifests()

            if app_name not in self.egl.manifests:
                self.log.info(f'Synced app "{app_name}" is no longer in the EGL manifest list.')
                return self.egl_restore_or_uninstall(lgd_igame)
            else:
                egl_igame = self.egl.get_manifest(app_name)
                if (egl_igame.app_version_string != lgd_igame.version) or \
                        (egl_igame.install_tags != lgd_igame.install_tags):
                    self.log.info(f'App "{egl_igame.app_name}" has been updated from EGL, syncing...')
                    return self.egl_import(egl_igame.app_name)
        else:
            # check EGL -> Legendary sync
            for egl_igame in self.egl.get_manifests():
                if egl_igame.main_game_appname != egl_igame.app_name:  # skip DLC
                    continue
                if not self.asset_valid(egl_igame.app_name):  # skip non-owned games
                    continue

                if not self._is_installed(egl_igame.app_name):
                    self.egl_import(egl_igame.app_name)
                else:
                    lgd_igame = self._get_installed_game(egl_igame.app_name)
                    if (egl_igame.app_version_string != lgd_igame.version) or \
                            (egl_igame.install_tags != lgd_igame.install_tags):
                        self.log.info(f'App "{egl_igame.app_name}" has been updated from EGL, syncing...')
                        self.egl_import(egl_igame.app_name)

            # Check for games that have been uninstalled
            for lgd_igame in self._get_installed_list():
                if not lgd_igame.egl_guid:  # skip non-exported
                    continue
                if lgd_igame.app_name in self.egl.manifests:
                    continue

                self.log.info(f'Synced app "{lgd_igame.app_name}" is no longer in the EGL manifest list.')
                self.egl_restore_or_uninstall(lgd_igame)

    @property
    def egl_sync_enabled(self):
        return self.lgd.config.getboolean('Legendary', 'egl_sync', fallback=False)

    def exit(self):
        """
        Do cleanup, config saving, and exit.
        """
        self.lgd.save_config()
