# coding: utf-8

import json
import logging
import os
import shlex
import shutil

from base64 import b64decode
from collections import defaultdict
from datetime import datetime, timezone
from locale import getdefaultlocale
from multiprocessing import Queue
from random import choice as randchoice
from requests import Request, session
from requests.exceptions import HTTPError
from typing import List, Dict
from uuid import uuid4

from legendary.api.egs import EPCAPI
from legendary.downloader.manager import DLManager
from legendary.lfs.egl import EPCLFS
from legendary.lfs.lgndry import LGDLFS
from legendary.utils.lfs import clean_filename, delete_folder
from legendary.models.downloading import AnalysisResult, ConditionCheckResult
from legendary.models.egl import EGLManifest
from legendary.models.exceptions import *
from legendary.models.game import *
from legendary.models.json_manifest import JSONManifest
from legendary.models.manifest import Manifest, ManifestMeta
from legendary.models.chunk import Chunk
from legendary.utils.game_workarounds import is_opt_enabled
from legendary.utils.savegame_helper import SaveGameHelper


# ToDo: instead of true/false return values for success/failure actually raise an exception that the CLI/GUI
#  can handle to give the user more details. (Not required yet since there's no GUI so log output is fine)


class LegendaryCore:
    """
    LegendaryCore handles most of the lower level interaction with
    the downloader, lfs, and api components to make writing CLI/GUI
    code easier and cleaner and avoid duplication.
    """

    def __init__(self):
        self.log = logging.getLogger('Core')
        self.egs = EPCAPI()
        self.lgd = LGDLFS()
        self.egl = EPCLFS()

        # on non-Windows load the programdata path from config
        if os.name != 'nt':
            self.egl.programdata_path = self.lgd.config.get('Legendary', 'egl_programdata', fallback=None)
            if self.egl.programdata_path and not os.path.exists(self.egl.programdata_path):
                self.log.error(f'Config EGL ProgramData path ("{self.egl.programdata_path}") is invalid! Please fix.')
                self.egl.programdata_path = None
                self.lgd.config.remove_option('Legendary', 'egl_programdata', fallback=None)
                self.lgd.save_config()

        self.local_timezone = datetime.now().astimezone().tzinfo
        self.language_code, self.country_code = ('en', 'US')

    def get_locale(self):
        locale = self.lgd.config.get('Legendary', 'locale', fallback=getdefaultlocale()[0])

        if locale:
            try:
                self.language_code, self.country_code = locale.split('-' if '-' in locale else '_')
                self.log.debug(f'Set locale to {self.language_code}-{self.country_code}')

                # if egs is loaded make sure to override its language setting as well
                if self.egs:
                    self.egs.language_code, self.egs.country_code = self.language_code, self.country_code
            except Exception as e:
                self.log.warning(f'Getting locale failed: {e!r}, falling back to using en-US.')
        else:
            self.log.warning(f'Could not determine locale, falling back to en-US')

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
                          'EpicGamesLauncher/10.16.1-13343695+++Portal+Release-Live '
                          'UnrealEngine/4.23.0-13343695+++Portal+Release-Live '
                          'Chrome/59.0.3071.15 Safari/537.36'
        })

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
        re_data = json.loads(b64decode(remember_me_data))[0]
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

        if self.lgd.userdata['expires_at']:
            dt_exp = datetime.fromisoformat(self.lgd.userdata['expires_at'][:-1])
            dt_now = datetime.utcnow()
            td = dt_now - dt_exp

            # if session still has at least 10 minutes left we can re-use it.
            if dt_exp > dt_now and abs(td.total_seconds()) > 600:
                self.log.info('Trying to re-use existing login session...')
                try:
                    self.egs.resume_session(self.lgd.userdata)
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
        return True

    def get_assets(self, update_assets=False, platform_override=None) -> List[GameAsset]:
        # do not save and always fetch list when platform is overriden
        if platform_override:
            return [GameAsset.from_egs_json(a) for a in
                    self.egs.get_game_assets(platform=platform_override)]

        if not self.lgd.assets or update_assets:
            self.lgd.assets = [GameAsset.from_egs_json(a) for a in self.egs.get_game_assets()]

        return self.lgd.assets

    def get_asset(self, app_name, update=False) -> GameAsset:
        if update:
            self.get_assets(update_assets=True)

        return next(i for i in self.lgd.assets if i.app_name == app_name)

    def get_game(self, app_name, update_meta=False) -> Game:
        if update_meta:
            self.get_game_list(True)
        return self.lgd.get_game_meta(app_name)

    def get_game_list(self, update_assets=True) -> List[Game]:
        return self.get_game_and_dlc_list(update_assets=update_assets)[0]

    def get_game_and_dlc_list(self, update_assets=True,
                              platform_override=None,
                              skip_ue=True) -> (List[Game], Dict[str, Game]):
        # resolve locale
        self.get_locale()
        _ret = []
        _dlc = defaultdict(list)

        for ga in self.get_assets(update_assets=update_assets,
                                  platform_override=platform_override):
            if ga.namespace == 'ue' and skip_ue:
                continue

            game = self.lgd.get_game_meta(ga.app_name)
            if update_assets and (not game or
                                  (game and game.app_version != ga.build_version and not platform_override)):
                if game and game.app_version != ga.build_version and not platform_override:
                    self.log.info(f'Updating meta for {game.app_name} due to build version mismatch')

                eg_meta = self.egs.get_game_info(ga.namespace, ga.catalog_item_id)
                game = Game(app_name=ga.app_name, app_version=ga.build_version,
                            app_title=eg_meta['title'], asset_info=ga, metadata=eg_meta)

                if not platform_override:
                    self.lgd.set_game_meta(game.app_name, game)

            # replace asset info with the platform specific one if override is used
            if platform_override:
                game.app_version = ga.build_version
                game.asset_info = ga

            if game.is_dlc:
                _dlc[game.metadata['mainGameItem']['id']].append(game)
            else:
                _ret.append(game)

        return _ret, _dlc

    def get_dlc_for_game(self, app_name):
        game = self.get_game(app_name)
        if game.is_dlc:  # dlc shouldn't have DLC
            return []

        _, dlcs = self.get_game_and_dlc_list(update_assets=False)
        return dlcs[game.asset_info.catalog_item_id]

    def get_installed_list(self) -> List[InstalledGame]:
        if self.egl_sync_enabled:
            self.log.debug('Running EGL sync...')
            self.egl_sync()

        return self._get_installed_list()

    def _get_installed_list(self) -> List[InstalledGame]:
        return [g for g in self.lgd.get_installed_list() if not g.is_dlc]

    def get_installed_dlc_list(self) -> List[InstalledGame]:
        return [g for g in self.lgd.get_installed_list() if g.is_dlc]

    def get_installed_game(self, app_name) -> InstalledGame:
        igame = self._get_installed_game(app_name)
        if igame and self.egl_sync_enabled and igame.egl_guid:
            self.egl_sync(app_name)
            return self._get_installed_game(app_name)
        else:
            return igame

    def _get_installed_game(self, app_name) -> InstalledGame:
        return self.lgd.get_installed_game(app_name)

    def get_launch_parameters(self, app_name: str, offline: bool = False,
                              user: str = None, extra_args: list = None,
                              wine_bin: str = None, wine_pfx: str = None,
                              language: str = None, wrapper: str = None,
                              disable_wine: bool = False) -> (list, str, dict):
        install = self.lgd.get_installed_game(app_name)
        game = self.lgd.get_game_meta(app_name)

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

        game_exe = os.path.join(install.install_path,
                                install.executable.replace('\\', '/').lstrip('/'))
        working_dir = os.path.split(game_exe)[0]

        params = []

        if wrapper or (wrapper := self.lgd.config.get(app_name, 'wrapper', fallback=None)):
            params.extend(shlex.split(wrapper))

        if os.name != 'nt' and not disable_wine:
            if not wine_bin:
                # check if there's a default override
                wine_bin = self.lgd.config.get('default', 'wine_executable', fallback='wine')
                # check if there's a game specific override
                wine_bin = self.lgd.config.get(app_name, 'wine_executable', fallback=wine_bin)

            if not self.lgd.config.getboolean(app_name, 'no_wine', fallback=False):
                params.append(wine_bin)

        params.append(game_exe)

        if install.launch_parameters:
            params.extend(shlex.split(install.launch_parameters))

        params.extend([
              '-AUTH_LOGIN=unused',
              f'-AUTH_PASSWORD={game_token}',
              '-AUTH_TYPE=exchangecode',
              f'-epicapp={app_name}',
              '-epicenv=Prod'])

        if install.requires_ot and not offline:
            self.log.info('Getting ownership token.')
            ovt = self.egs.get_ownership_token(game.asset_info.namespace,
                                               game.asset_info.catalog_item_id)
            ovt_path = os.path.join(self.lgd.get_tmp_path(),
                                    f'{game.asset_info.namespace}{game.asset_info.catalog_item_id}.ovt')
            with open(ovt_path, 'wb') as f:
                f.write(ovt)
            params.append(f'-epicovt={ovt_path}')

        language_code = self.lgd.config.get(app_name, 'language', fallback=language)
        if not language_code:  # fall back to system or config language
            self.get_locale()
            language_code = self.language_code

        params.extend([
              '-EpicPortal',
              f'-epicusername={user_name}',
              f'-epicuserid={account_id}',
              f'-epiclocale={language_code}'
        ])

        if extra_args:
            params.extend(extra_args)

        if config_args := self.lgd.config.get(app_name, 'start_params', fallback=None):
            params.extend(shlex.split(config_args.strip()))

        # get environment overrides from config
        env = os.environ.copy()
        if f'{app_name}.env' in self.lgd.config:
            env.update(dict(self.lgd.config[f'{app_name}.env']))
        elif 'default.env' in self.lgd.config:
            env.update(dict(self.lgd.config['default.env']))

        if wine_pfx:
            env['WINEPREFIX'] = wine_pfx
        elif 'WINEPREFIX' not in env:
            # only use config variable if not already set in environment
            if wine_pfx := self.lgd.config.get(app_name, 'wine_prefix', fallback=None):
                env['WINEPREFIX'] = wine_pfx

        return params, working_dir, env

    def get_save_games(self, app_name: str = ''):
        savegames = self.egs.get_user_cloud_saves(app_name, manifests=not not app_name)
        _saves = []
        for fname, f in savegames['files'].items():
            if '.manifest' not in fname:
                continue
            f_parts = fname.split('/')
            _saves.append(SaveGameFile(app_name=f_parts[2], filename=fname, manifest=f_parts[4],
                                       datetime=datetime.fromisoformat(f['lastModified'][:-1])))

        return _saves

    def get_save_path(self, app_name):
        game = self.lgd.get_game_meta(app_name)
        save_path = game.metadata['customAttributes'].get('CloudSaveFolder', {}).get('value')
        if not save_path:
            raise ValueError('Game does not support cloud saves')

        igame = self.lgd.get_installed_game(app_name)
        if not igame:
            raise ValueError('Game is not installed!')

        # the following variables are known:
        path_vars = {
            '{appdata}': os.path.expandvars('%APPDATA%'),
            '{installdir}': igame.install_path,
            '{userdir}': os.path.expandvars('%userprofile%/documents'),
            '{epicid}': self.lgd.userdata['account_id']
        }
        # the following variables are in the EGL binary but are not used by any of
        # my games and I'm not sure where they actually point at:
        # {UserProfile} (Probably %USERPROFILE%)
        # {UserSavedGames}

        # these paths should always use a forward slash
        new_save_path = [path_vars.get(p.lower(), p) for p in save_path.split('/')]
        return os.path.join(*new_save_path)

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

        include_f = exclude_f = None
        if not disable_filtering:
            # get file inclusion and exclusion filters if they exist
            if (_include := custom_attr.get('CloudIncludeList', {}).get('value', None)) is not None:
                include_f = _include.split(',')
            if (_exclude := custom_attr.get('CloudExcludeList', {}).get('value', None)) is not None:
                exclude_f = _exclude.split(',')

        if not save_path:
            raise ValueError('Game does not support cloud saves')

        sgh = SaveGameHelper()
        files = sgh.package_savegame(save_dir, app_name, self.egs.user.get('account_id'),
                                     save_path, include_f, exclude_f, local_dt)

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

        savegames = self.egs.get_user_cloud_saves(app_name=app_name)
        files = savegames['files']
        for fname, f in files.items():
            if '.manifest' not in fname:
                continue
            f_parts = fname.split('/')

            if manifest_name and f_parts[4] != manifest_name:
                continue
            if not save_dir:
                save_dir = os.path.join(save_path, f'{f_parts[2]}/{f_parts[4].rpartition(".")[0]}')
                if not os.path.exists(save_dir):
                    os.makedirs(save_dir)

            if clean_dir:
                self.log.info('Deleting old save files...')
                delete_folder(save_dir)

            self.log.info(f'Downloading "{fname.split("/", 2)[2]}"...')
            # download manifest
            r = self.egs.unauth_session.get(f['readLink'])
            if r.status_code != 200:
                self.log.error(f'Download failed, status code: {r.status_code}')
                continue
            m = self.load_manfiest(r.content)

            # download chunks required for extraction
            chunks = dict()
            for chunk in m.chunk_data_list.elements:
                cpath_p = fname.split('/', 3)[:3]
                cpath_p.append(chunk.path)
                cpath = '/'.join(cpath_p)
                self.log.debug(f'Downloading chunk "{cpath}"')
                r = self.egs.unauth_session.get(files[cpath]['readLink'])
                if r.status_code != 200:
                    self.log.error(f'Download failed, status code: {r.status_code}')
                    break
                c = Chunk.read_buffer(r.content)
                chunks[c.guid_num] = c.data

            for fm in m.file_manifest_list.elements:
                dirs, fname = os.path.split(fm.filename)
                fdir = os.path.join(save_dir, dirs)
                fpath = os.path.join(fdir, fname)
                if not os.path.exists(fdir):
                    os.makedirs(fdir)

                self.log.debug(f'Writing "{fpath}"...')
                with open(fpath, 'wb') as fh:
                    for cp in fm.chunk_parts:
                        fh.write(chunks[cp.guid_num][cp.offset:cp.offset+cp.size])

                # set modified time to savegame creation timestamp
                m_date = datetime.strptime(f_parts[4], '%Y.%m.%d-%H.%M.%S.manifest')
                m_date = m_date.replace(tzinfo=timezone.utc).astimezone(self.local_timezone)
                os.utime(fpath, (m_date.timestamp(), m_date.timestamp()))

        self.log.info('Successfully completed savegame download.')

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
    def load_manfiest(data: bytes) -> Manifest:
        if data[0:1] == b'{':
            return JSONManifest.read_all(data)
        else:
            return Manifest.read_all(data)

    def get_installed_manifest(self, app_name):
        igame = self._get_installed_game(app_name)
        old_bytes = self.lgd.load_manifest(app_name, igame.version)
        return old_bytes, igame.base_urls

    def get_cdn_urls(self, game, platform_override=''):
        platform = 'Windows' if not platform_override else platform_override
        m_api_r = self.egs.get_game_manifest(game.asset_info.namespace,
                                             game.asset_info.catalog_item_id,
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

            params = None
            if 'queryParams' in manifest:
                params = {p['name']: p['value'] for p in manifest['queryParams']}

            # build url with a prepared request
            manifest_urls.append(Request('GET', manifest['uri'], params=params).prepare().url)

        return manifest_urls, base_urls

    def get_cdn_manifest(self, game, platform_override=''):
        manifest_urls, base_urls = self.get_cdn_urls(game, platform_override)
        self.log.debug(f'Downloading manifest from {manifest_urls[0]} ...')
        r = self.egs.unauth_session.get(manifest_urls[0])
        r.raise_for_status()
        return r.content, base_urls

    def get_uri_manfiest(self, uri):
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

    def prepare_download(self, game: Game, base_game: Game = None, base_path: str = '',
                         status_q: Queue = None, max_shm: int = 0, max_workers: int = 0,
                         force: bool = False, disable_patching: bool = False,
                         game_folder: str = '', override_manifest: str = '',
                         override_old_manifest: str = '', override_base_url: str = '',
                         platform_override: str = '', file_prefix_filter: list = None,
                         file_exclude_filter: list = None, file_install_tag: list = None,
                         dl_optimizations: bool = False, dl_timeout: int = 10,
                         repair: bool = False, egl_guid: str = ''
                         ) -> (DLManager, AnalysisResult, ManifestMeta):
        # load old manifest
        old_manifest = None

        # load old manifest if we have one
        if override_old_manifest:
            self.log.info(f'Overriding old manifest with "{override_old_manifest}"')
            old_bytes, _ = self.get_uri_manfiest(override_old_manifest)
            old_manifest = self.load_manfiest(old_bytes)
        elif not disable_patching and not force and self.is_installed(game.app_name):
            old_bytes, _base_urls = self.get_installed_manifest(game.app_name)
            if _base_urls and not game.base_urls:
                game.base_urls = _base_urls

            if not old_bytes:
                self.log.error(f'Could not load old manifest, patching will not work!')
            else:
                old_manifest = self.load_manfiest(old_bytes)

        base_urls = list(game.base_urls)  # copy list for manipulation

        if override_manifest:
            self.log.info(f'Overriding manifest with "{override_manifest}"')
            new_manifest_data, _base_urls = self.get_uri_manfiest(override_manifest)
            # if override manifest has a base URL use that instead
            if _base_urls:
                base_urls = _base_urls
        else:
            new_manifest_data, _base_urls = self.get_cdn_manifest(game, platform_override)
            base_urls.extend(i for i in _base_urls if i not in base_urls)
            game.base_urls = base_urls
            # save base urls to game metadata
            self.lgd.set_game_meta(game.app_name, game)

        self.log.info('Parsing game manifest...')
        new_manifest = self.load_manfiest(new_manifest_data)
        self.log.debug(f'Base urls: {base_urls}')
        self.lgd.save_manifest(game.app_name, new_manifest_data)
        # save manifest with version name as well for testing/downgrading/etc.
        self.lgd.save_manifest(game.app_name, new_manifest_data,
                               version=new_manifest.meta.build_version)

        # reuse existing installation's directory
        if igame := self.get_installed_game(base_game.app_name if base_game else game.app_name):
            install_path = igame.install_path
            # make sure to re-use the epic guid we assigned on first install
            if not game.is_dlc and igame.egl_guid:
                egl_guid = igame.egl_guid
        else:
            if not game_folder:
                if game.is_dlc:
                    game_folder = base_game.metadata.get('customAttributes', {}).\
                        get('FolderName', {}).get('value', base_game.app_name)
                else:
                    game_folder = game.metadata.get('customAttributes', {}).\
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
            # use installed manifest for repairs, do not update to latest version (for now)
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

        if override_base_url:
            self.log.info(f'Overriding base URL with "{override_base_url}"')
            base_url = override_base_url
        else:
            # randomly select one CDN
            base_url = randchoice(base_urls)

        self.log.debug(f'Using base URL: {base_url}')

        if not max_shm:
            max_shm = self.lgd.config.getint('Legendary', 'max_memory', fallback=1024)

        if dl_optimizations or is_opt_enabled(game.app_name):
            self.log.info('Download order optimizations are enabled.')
            process_opt = True
        else:
            process_opt = False

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

        igame = InstalledGame(app_name=game.app_name, title=game.app_title,
                              version=new_manifest.meta.build_version, prereq_info=prereq,
                              manifest_path=override_manifest, base_urls=base_urls,
                              install_path=install_path, executable=new_manifest.meta.launch_exe,
                              launch_parameters=new_manifest.meta.launch_command,
                              can_run_offline=offline == 'true', requires_ot=ot == 'true',
                              is_dlc=base_game is not None, install_size=anlres.install_size,
                              egl_guid=egl_guid)

        return dlm, anlres, igame

    @staticmethod
    def check_installation_conditions(analysis: AnalysisResult, install: InstalledGame) -> ConditionCheckResult:
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

        # check if enough disk space is free (dl size is the approximate amount the installation will grow)
        min_disk_space = analysis.uncompressed_dl_size + analysis.biggest_file_size
        _, _, free = shutil.disk_usage(os.path.split(install.install_path)[0])
        if free < min_disk_space:
            free_mib = free / 1024 / 1024
            required_mib = min_disk_space / 1024 / 1024
            results.failures.add(f'Not enough available disk space! {free_mib:.02f} MiB < {required_mib:.02f} MiB')

        return results

    def get_default_install_dir(self):
        return os.path.expanduser(self.lgd.config.get('Legendary', 'install_dir', fallback='~/legendary'))

    def install_game(self, installed_game: InstalledGame) -> dict:
        if self.egl_sync_enabled:
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

    def uninstall_game(self, installed_game: InstalledGame, delete_files=True):
        self.lgd.remove_installed_game(installed_game.app_name)
        if installed_game.egl_guid:
            self.egl_uninstall(installed_game, delete_files=delete_files)

        if delete_files:
            if not delete_folder(installed_game.install_path, recursive=True):
                self.log.error(f'Unable to delete "{installed_game.install_path}" from disk, please remove manually.')

    def prereq_installed(self, app_name):
        igame = self.lgd.get_installed_game(app_name)
        igame.prereq_info['installed'] = True
        self.lgd.set_installed_game(app_name, igame)

    def import_game(self, game: Game, app_path: str, egl_guid='') -> (Manifest, InstalledGame):
        needs_verify = True
        manifest_data = None

        # check if the game is from an EGL installation, load manifest if possible
        if os.path.exists(os.path.join(app_path, '.egstore')):
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
                self.log.warning('.egstore folder exists but manifest file is missing, contiuing as regular import...')

            # If there's no in-progress installation assume the game doesn't need to be verified
            if mf and not os.path.exists(os.path.join(app_path, '.egstore', 'bps')):
                needs_verify = False
                if os.path.exists(os.path.join(app_path, '.egstore',  'Pending')):
                    if os.listdir(os.path.join(app_path, '.egstore',  'Pending')):
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
        new_manifest = self.load_manfiest(manifest_data)
        self.lgd.save_manifest(game.app_name, manifest_data)
        self.lgd.save_manifest(game.app_name, manifest_data,
                               version=new_manifest.meta.build_version)
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
                              needs_verification=needs_verify, install_size=install_size, egl_guid=egl_guid)

        return new_manifest, igame

    def egl_get_importable(self):
        return [g for g in self.egl.get_manifests()
                if not self.is_installed(g.app_name) and g.main_game_appname == g.app_name]

    def egl_get_exportable(self):
        if not self.egl.manifests:
            self.egl.read_manifests()
        return [g for g in self.get_installed_list() if g.app_name not in self.egl.manifests]

    def egl_import(self, app_name):
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
        new_manifest = self.load_manfiest(manifest_data)
        self.lgd.save_manifest(lgd_igame.app_name, manifest_data)
        self.lgd.save_manifest(lgd_igame.app_name, manifest_data,
                               version=new_manifest.meta.build_version)
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
        with open(os.path.join(egstore_folder, f'{egl_game.installation_guid}.manifest',), 'wb') as mf:
            mf.write(manifest_data)

        mancpn = dict(FormatVersion=0, AppName=app_name,
                      CatalogItemId=lgd_game.asset_info.catalog_item_id,
                      CatalogNamespace=lgd_game.asset_info.namespace)
        with open(os.path.join(egstore_folder, f'{egl_game.installation_guid}.mancpn',), 'w') as mcpnf:
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
                if egl_igame.app_version_string != lgd_igame.version:
                    self.log.info(f'App "{egl_igame.app_name}" has been updated from EGL, syncing...')
                    return self.egl_import(egl_igame.app_name)
        else:
            # check EGL -> Legendary sync
            for egl_igame in self.egl.get_manifests():
                if egl_igame.main_game_appname != egl_igame.app_name:  # skip DLC
                    continue

                if not self._is_installed(egl_igame.app_name):
                    self.egl_import(egl_igame.app_name)
                else:
                    lgd_igame = self._get_installed_game(egl_igame.app_name)
                    if lgd_igame.version != egl_igame.app_version_string:
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

