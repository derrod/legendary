#!/usr/bin/env python
# coding: utf-8

import json
import logging
import os
import shlex
import shutil

from base64 import b64decode
from collections import defaultdict
from datetime import datetime
from multiprocessing import Queue
from random import choice as randchoice
from requests.exceptions import HTTPError
from typing import List, Dict

from legendary.api.egs import EPCAPI
from legendary.downloader.manager import DLManager
from legendary.lfs.egl import EPCLFS
from legendary.lfs.lgndry import LGDLFS
from legendary.lfs.utils import clean_filename, delete_folder
from legendary.models.downloading import AnalysisResult, ConditionCheckResult
from legendary.models.exceptions import *
from legendary.models.game import *
from legendary.models.json_manifest import JSONManifest
from legendary.models.manifest import Manifest, ManifestMeta


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

        # epic lfs only works on Windows right now
        if os.name == 'nt':
            self.egl = EPCLFS()
        else:
            self.egl = None

    def auth(self, username, password):
        """
        Attempts direct non-web login, raises CaptchaError if manual login is required

        :param username:
        :param password:
        :return:
        """
        raise NotImplementedError

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

    def get_assets(self, update_assets=False) -> List[GameAsset]:
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

    def get_game_and_dlc_list(self, update_assets=True) -> (List[Game], Dict[str, Game]):
        _ret = []
        _dlc = defaultdict(list)

        for ga in self.get_assets(update_assets=update_assets):
            if ga.namespace == 'ue':  # skip UE demo content
                continue

            game = self.lgd.get_game_meta(ga.app_name)
            if not game or (game and game.app_version != ga.build_version):
                if game and game.app_version != ga.build_version:
                    self.log.info(f'Updating meta for {game.app_name} due to build version mismatch')

                eg_meta = self.egs.get_game_info(ga.namespace, ga.catalog_item_id)
                game = Game(app_name=ga.app_name, app_version=ga.build_version,
                            app_title=eg_meta['title'], asset_info=ga, metadata=eg_meta)
                self.lgd.set_game_meta(game.app_name, game)

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
        return [g for g in self.lgd.get_installed_list() if not g.is_dlc]

    def get_installed_dlc_list(self) -> List[InstalledGame]:
        return [g for g in self.lgd.get_installed_list() if g.is_dlc]

    def get_installed_game(self, app_name) -> InstalledGame:
        return self.lgd.get_installed_game(app_name)

    def get_launch_parameters(self, app_name: str, offline: bool = False,
                              user: str = None, extra_args: list = None) -> (list, str, dict):
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

        game_exe = os.path.join(install.install_path, install.executable)
        working_dir = os.path.split(game_exe)[0]

        params = []

        if os.name != 'nt':
            # check if there's a default override
            wine_binary = self.lgd.config.get('default', 'wine_executable', fallback='wine')
            # check if there's a game specific override
            wine_binary = self.lgd.config.get(app_name, 'wine_executable', fallback=wine_binary)
            params.append(wine_binary)

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

        params.extend([
              '-EpicPortal',
              f'-epicusername={user_name}',
              f'-epicuserid={account_id}',
              '-epiclocale=en'
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

        return params, working_dir, env

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
        return self.lgd.get_installed_game(app_name) is not None

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

    def prepare_download(self, game: Game, base_game: Game = None, base_path: str = '',
                         status_q: Queue = None, max_shm: int = 0, max_workers: int = 0,
                         force: bool = False, disable_patching: bool = False, game_folder: str = '',
                         override_manifest: str = '', override_old_manifest: str = '',
                         override_base_url: str = '') -> (DLManager, AnalysisResult, ManifestMeta):

        # load old manifest
        old_manifest = None
        new_manifest_data = b''

        # load old manifest if we have one
        if override_old_manifest:
            if override_old_manifest.startswith('http'):
                r = self.egs.unauth_session.get(override_old_manifest)
                r.raise_for_status()
                old_manifest_data = r.content
            else:
                with open(override_old_manifest, 'rb') as f:
                    old_manifest_data = f.read()
            old_manifest = self.load_manfiest(old_manifest_data)
        elif not disable_patching and not force and self.is_installed(game.app_name):
            igame = self.get_installed_game(game.app_name)
            if old_bytes := self.lgd.load_manifest(game.app_name, igame.version):
                old_manifest = self.load_manfiest(old_bytes)

        base_urls = list(game.base_urls)  # copy list for manipulation

        if override_manifest:
            if override_manifest.startswith('http'):
                r = self.egs.unauth_session.get(override_manifest)
                r.raise_for_status()
                new_manifest_data = r.content
                base_urls = [r.url.rpartition('/')[0]]
            else:
                with open(override_manifest, 'rb') as f:
                    new_manifest_data = f.read()
        else:
            # get latest manifest from API
            m_api_r = self.egs.get_game_manifest(game.asset_info.namespace,
                                                 game.asset_info.catalog_item_id,
                                                 game.app_name)

            # never seen this outside the launcher itself, but if it happens: PANIC!
            if len(m_api_r['elements']) > 1:
                raise ValueError('Manifest response has more than one element!')

            manifest_info = m_api_r['elements'][0]
            for manifest in manifest_info['manifests']:
                base_url = manifest['uri'].rpartition('/')[0]
                if base_url not in base_urls:
                    base_urls.append(base_url)

                if 'queryParams' in manifest:
                    continue

                self.log.debug(f'Downloading manifest from {manifest["uri"]} ...')
                r = self.egs.unauth_session.get(manifest['uri'])
                r.raise_for_status()
                new_manifest_data = r.content

        if override_base_url:
            base_urls = [override_base_url]

        self.log.debug(f'Base urls: {base_urls}')
        new_manifest = self.load_manfiest(new_manifest_data)
        self.lgd.save_manifest(game.app_name, new_manifest_data)
        # save manifest with version name as well for testing/downgrading/etc.
        self.lgd.save_manifest(game.app_name, new_manifest_data,
                               version=new_manifest.meta.build_version)

        if not game_folder:
            if game.is_dlc:
                game_folder = base_game.metadata.get('customAttributes', {}).\
                    get('FolderName', {}).get('value', base_game.app_name)
            else:
                game_folder = game.metadata.get('customAttributes', {}).\
                    get('FolderName', {}).get('value', game.app_name)

        if not base_path:
            base_path = self.get_default_install_dir()

        install_path = os.path.join(base_path, game_folder)

        # todo move this somewhere else so the directory only gets created once the download is started
        if not os.path.exists(install_path):
            os.makedirs(install_path)

        self.log.info(f'Install path: {install_path}')

        if not force:
            filename = clean_filename(f'{game.app_name}_{new_manifest.meta.build_version}.resume')
            resume_file = os.path.join(self.lgd.get_tmp_path(), filename)
        else:
            resume_file = None

        # randomly select one CDN
        base_url = randchoice(base_urls)
        self.log.debug(f'Using base URL: {base_url}')

        if not max_shm:
            max_shm = self.lgd.config.getint('Legendary', 'max_memory', fallback=1024)

        dlm = DLManager(install_path, base_url, resume_file=resume_file, status_q=status_q,
                        max_shared_memory=max_shm * 1024 * 1024, max_workers=max_workers)
        anlres = dlm.run_analysis(manifest=new_manifest, old_manifest=old_manifest,
                                  patch=not disable_patching, resume=not force)

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
                              is_dlc=base_game is not None)

        return dlm, anlres, igame

    @staticmethod
    def check_installation_conditions(analysis: AnalysisResult, install: InstalledGame) -> ConditionCheckResult:
        # ToDo add more checks in the future
        results = ConditionCheckResult(failures=list(), warnings=list())

        # if on linux, check for eac in the files
        if os.name != 'nt':
            for f in analysis.manifest_comparison.added:
                if 'easyanticheat' in f.lower():
                    results.warnings.append('(Linux) The game uses EasyAntiCheat and may not run on linux')
                    break

        if install.requires_ot:
            results.warnings.append('This game requires an ownership verification token and likely uses Denuvo DRM.')
        if not install.can_run_offline:
            results.warnings.append('This game is not marked for offline use (may still work).')

        # check if enough disk space is free (dl size is the approximate amount the installation will grow)
        min_disk_space = analysis.uncompressed_dl_size + analysis.biggest_file_size
        _, _, free = shutil.disk_usage(install.install_path)
        if free < min_disk_space:
            free_mib = free / 1024 / 1024
            required_mib = min_disk_space / 1024 / 1024
            results.failures.append(f'Not enough available disk space! {free_mib:.02f} MiB < {required_mib:.02f} MiB')

        return results

    def get_default_install_dir(self):
        return self.lgd.config.get('Legendary', 'install_dir', fallback=os.path.expanduser('~/legendary'))

    def install_game(self, installed_game: InstalledGame) -> dict:  # todo class for result?
        """Save game metadata and info to mark it "installed" and also show the user the prerequisites"""
        self.lgd.set_installed_game(installed_game.app_name, installed_game)
        if installed_game.prereq_info:
            if not installed_game.prereq_info.get('installed', False):
                return installed_game.prereq_info

        return dict()

    def uninstall_game(self, installed_game: InstalledGame, delete_files=True):
        self.lgd.remove_installed_game(installed_game.app_name)
        if delete_files:
            delete_folder(installed_game.install_path, recursive=True)

    def prereq_installed(self, app_name):
        igame = self.lgd.get_installed_game(app_name)
        igame.prereq_info['installed'] = True
        self.lgd.set_installed_game(app_name, igame)

    def exit(self):
        """
        Do cleanup, config saving, and exit.
        """
        # self.lgd.clean_tmp_data()
        self.lgd.save_config()

