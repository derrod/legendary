# coding: utf-8

import json
import os
import configparser
import logging

from legendary.models.game import *
from legendary.utils.lfs import clean_filename


class LGDLFS:
    def __init__(self):
        self.log = logging.getLogger('LGDLFS')

        if config_path := os.environ.get('XDG_CONFIG_HOME'):
            self.path = os.path.join(config_path, 'legendary')
        else:
            self.path = os.path.expanduser('~/.config/legendary')

        # EGS user info
        self._user_data = None
        # EGS entitlements
        self._entitlements = None
        # EGS asset data
        self._assets = None
        # EGS metadata
        self._game_metadata = dict()
        # Config with game specific settings (e.g. start parameters, env variables)
        self.config = configparser.ConfigParser()
        self.config.optionxform = str

        # ensure folders exist.
        for f in ['', 'manifests', 'metadata', 'tmp', 'manifests/old']:
            if not os.path.exists(os.path.join(self.path, f)):
                os.makedirs(os.path.join(self.path, f))

        # try loading config
        self.config.read(os.path.join(self.path, 'config.ini'))
        # make sure "Legendary" section exists
        if 'Legendary' not in self.config:
            self.config['Legendary'] = dict()

        try:
            self._installed = json.load(open(os.path.join(self.path, 'installed.json')))
        except Exception as e:  # todo do not do this
            self._installed = None

        # load existing app metadata
        for gm_file in os.listdir(os.path.join(self.path, 'metadata')):
            try:
                _meta = json.load(open(os.path.join(self.path, 'metadata', gm_file)))
                self._game_metadata[_meta['app_name']] = _meta
            except Exception as e:
                self.log.debug(f'Loading game meta file "{gm_file}" failed: {e!r}')

    @property
    def userdata(self):
        if self._user_data is not None:
            return self._user_data

        try:
            self._user_data = json.load(open(os.path.join(self.path, 'user.json')))
            return self._user_data
        except Exception as e:
            self.log.debug(f'Failed to load user data: {e!r}')
            return None

    @userdata.setter
    def userdata(self, userdata):
        if userdata is None:
            raise ValueError('Userdata is none!')

        self._user_data = userdata
        json.dump(userdata, open(os.path.join(self.path, 'user.json'), 'w'),
                  indent=2, sort_keys=True)

    def invalidate_userdata(self):
        self._user_data = None
        if os.path.exists(os.path.join(self.path, 'user.json')):
            os.remove(os.path.join(self.path, 'user.json'))

    @property
    def entitlements(self):
        if self._entitlements is not None:
            return self._entitlements

        try:
            self._entitlements = json.load(open(os.path.join(self.path, 'entitlements.json')))
            return self._entitlements
        except Exception as e:
            self.log.debug(f'Failed to load entitlements data: {e!r}')
            return None

    @entitlements.setter
    def entitlements(self, entitlements):
        if entitlements is None:
            raise ValueError('Entitlements is none!')

        self._entitlements = entitlements
        json.dump(entitlements, open(os.path.join(self.path, 'entitlements.json'), 'w'),
                  indent=2, sort_keys=True)

    @property
    def assets(self):
        if self._assets is None:
            try:
                self._assets = [GameAsset.from_json(a) for a in
                                json.load(open(os.path.join(self.path, 'assets.json')))]
            except Exception as e:
                self.log.debug(f'Failed to load assets data: {e!r}')
                return None

        return self._assets

    @assets.setter
    def assets(self, assets):
        if assets is None:
            raise ValueError('Assets is none!')

        self._assets = assets
        json.dump([a.__dict__ for a in self._assets],
                  open(os.path.join(self.path, 'assets.json'), 'w'),
                  indent=2, sort_keys=True)

    def _get_manifest_filename(self, app_name, version=''):
        if not version:
            return os.path.join(self.path, 'manifests', f'{app_name}.manifest')
        else:
            # if a version is specified load it from the versioned directory
            fname = clean_filename(f'{app_name}_{version}')
            return os.path.join(self.path, 'manifests', 'old', f'{fname}.manifest')

    def load_manifest(self, app_name, version=''):
        try:
            return open(self._get_manifest_filename(app_name, version), 'rb').read()
        except FileNotFoundError:  # all other errors should propagate
            return None

    def save_manifest(self, app_name, manifest_data, version=''):
        with open(self._get_manifest_filename(app_name, version), 'wb') as f:
            f.write(manifest_data)

    def get_game_meta(self, app_name):
        _meta = self._game_metadata.get(app_name, None)
        if _meta:
            return Game.from_json(_meta)
        return None

    def set_game_meta(self, app_name, meta):
        json_meta = meta.__dict__
        self._game_metadata[app_name] = json_meta
        meta_file = os.path.join(self.path, 'metadata', f'{app_name}.json')
        json.dump(json_meta, open(meta_file, 'w'), indent=2, sort_keys=True)

    def delete_game_meta(self, app_name):
        if app_name in self._game_metadata:
            del self._game_metadata[app_name]
            meta_file = os.path.join(self.path, 'metadata', f'{app_name}.json')
            if os.path.exists(meta_file):
                os.remove(meta_file)
        else:
            raise ValueError(f'Game {app_name} does not exist in metadata DB!')

    def get_tmp_path(self):
        return os.path.join(self.path, 'tmp')

    def clean_tmp_data(self):
        for f in os.listdir(os.path.join(self.path, 'tmp')):
            try:
                os.remove(os.path.join(self.path, 'tmp', f))
            except Exception as e:
                self.log.warning(f'Failed to delete file "{f}": {e!r}')

    def get_installed_game(self, app_name):
        if self._installed is None:
            try:
                self._installed = json.load(open(os.path.join(self.path, 'installed.json')))
            except Exception as e:
                self.log.debug(f'Failed to load installed game data: {e!r}')
                return None

        game_json = self._installed.get(app_name, None)
        if game_json:
            return InstalledGame.from_json(game_json)
        return None

    def set_installed_game(self, app_name, install_info):
        if self._installed is None:
            self._installed = dict()

        if app_name in self._installed:
            self._installed[app_name].update(install_info.__dict__)
        else:
            self._installed[app_name] = install_info.__dict__

        json.dump(self._installed, open(os.path.join(self.path, 'installed.json'), 'w'),
                  indent=2, sort_keys=True)

    def remove_installed_game(self, app_name):
        if self._installed is None:
            self.log.warning('Trying to remove a game, but no installed games?!')
            return

        if app_name in self._installed:
            del self._installed[app_name]
        else:
            self.log.warning('Trying to remove non-installed game:', app_name)
            return

        json.dump(self._installed, open(os.path.join(self.path, 'installed.json'), 'w'),
                  indent=2, sort_keys=True)

    def get_installed_list(self):
        if not self._installed:
            return []

        return [InstalledGame.from_json(i) for i in self._installed.values()]

    def save_config(self):
        with open(os.path.join(self.path, 'config.ini'), 'w') as cf:
            self.config.write(cf)

