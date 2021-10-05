# coding: utf-8

import configparser
import json
import os

from typing import List

from legendary.models.egl import EGLManifest


class EPCLFS:
    # Known encryption key(s) for JSON user data
    # Data is encrypted using AES-256-ECB mode
    data_keys = []

    def __init__(self):
        if os.name == 'nt':
            self.appdata_path = os.path.expandvars(
                r'%LOCALAPPDATA%\EpicGamesLauncher\Saved\Config\Windows'
            )
            self.programdata_path = os.path.expandvars(
                r'%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests'
            )
        else:
            self.appdata_path = self.programdata_path = None

        self.config = configparser.ConfigParser(strict=False)
        self.config.optionxform = lambda option: option

        self.manifests = dict()

    def read_config(self):
        if not self.appdata_path:
            raise ValueError('EGS AppData path is not set')

        self.config.read(os.path.join(self.appdata_path, 'GameUserSettings.ini'))

    def save_config(self):
        if not self.appdata_path:
            raise ValueError('EGS AppData path is not set')

        with open(os.path.join(self.appdata_path, 'GameUserSettings.ini'), 'w') as f:
            self.config.write(f, space_around_delimiters=False)

    def read_manifests(self):
        if not self.programdata_path:
            raise ValueError('EGS ProgramData path is not set')

        for f in os.listdir(self.programdata_path):
            if f.endswith('.item'):
                data = json.load(open(os.path.join(self.programdata_path, f)))
                self.manifests[data['AppName']] = data

    def get_manifests(self) -> List[EGLManifest]:
        if not self.manifests:
            self.read_manifests()

        return [EGLManifest.from_json(m) for m in self.manifests.values()]

    def get_manifest(self, app_name) -> EGLManifest:
        if not self.manifests:
            self.read_manifests()

        if app_name in self.manifests:
            return EGLManifest.from_json(self.manifests[app_name])
        else:
            raise ValueError('Cannot find manifest')

    def set_manifest(self, manifest: EGLManifest):
        if not self.programdata_path:
            raise ValueError('EGS ProgramData path is not set')

        manifest_data = manifest.to_json()
        self.manifests[manifest.app_name] = manifest_data
        with open(os.path.join(self.programdata_path, f'{manifest.installation_guid}.item'), 'w') as f:
            json.dump(manifest_data, f, indent=4, sort_keys=True)

    def delete_manifest(self, app_name):
        if not self.manifests:
            self.read_manifests()
        if app_name not in self.manifests:
            raise ValueError('AppName is not in manifests!')

        manifest = EGLManifest.from_json(self.manifests.pop(app_name))
        os.remove(os.path.join(self.programdata_path, f'{manifest.installation_guid}.item'))
