#!/usr/bin/env python
# coding: utf-8

import configparser
import json
import os


# ToDo make it possible to read manifests from game installs for migration.
#  Also make paths configurable for importing games from WINE roots in the future

# this is taken directly from rktlnch, needs to be updated

class EPCLFS:
    def __init__(self):
        self.appdata_path = os.path.expandvars(
            r'%LOCALAPPDATA%\EpicGamesLauncher\Saved\Config\Windows'
        )
        self.programdata_path = os.path.expandvars(
            r'%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests'
        )
        self.config = configparser.ConfigParser(strict=False)
        self.config.optionxform = lambda option: option

        self.manifests = dict()
        self.codename_map = dict()
        self.guid_map = dict()

    def read_config(self):
        self.config.read(os.path.join(self.appdata_path, 'GameUserSettings.ini'))

    def save_config(self):
        with open(os.path.join(self.appdata_path, 'GameUserSettings.ini'), 'w') as f:
            self.config.write(f, space_around_delimiters=False)

    def read_manifests(self):
        for f in os.listdir(self.programdata_path):
            if f.endswith('.item'):
                data = json.load(open(os.path.join(self.programdata_path, f)))
                self.manifests[data['CatalogItemId']] = data
                self.codename_map[data['AppName']] = data['CatalogItemId']
                self.guid_map[data['InstallationGuid'].lower()] = data['CatalogItemId']

    def get_manifest(self, *, game_name=None, install_guid=None, catalog_item_id=None):
        if not game_name and not install_guid and not catalog_item_id:
            raise ValueError('What are you doing?')

        if game_name and game_name in self.codename_map:
            return self.manifests[self.codename_map[game_name]]
        elif install_guid and install_guid in self.guid_map:
            return self.manifests[self.guid_map[install_guid]]
        elif catalog_item_id and catalog_item_id in self.manifests:
            return self.manifests[catalog_item_id]
        else:
            raise ValueError('Cannot find manifest')
