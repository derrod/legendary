# coding: utf-8

from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict


@dataclass
class GameAsset:
    """
    App asset data
    """
    app_name: str = ''
    asset_id: str = ''
    build_version: str = ''
    catalog_item_id: str = ''
    label_name: str = ''
    namespace: str = ''
    metadata: Dict = field(default_factory=dict)

    @classmethod
    def from_egs_json(cls, json):
        tmp = cls()
        tmp.app_name = json.get('appName', '')
        tmp.asset_id = json.get('assetId', '')
        tmp.build_version = json.get('buildVersion', '')
        tmp.catalog_item_id = json.get('catalogItemId', '')
        tmp.label_name = json.get('labelName', '')
        tmp.namespace = json.get('namespace', '')
        tmp.metadata = json.get('metadata', {})
        return tmp

    @classmethod
    def from_json(cls, json):
        tmp = cls()
        tmp.app_name = json.get('app_name', '')
        tmp.asset_id = json.get('asset_id', '')
        tmp.build_version = json.get('build_version', '')
        tmp.catalog_item_id = json.get('catalog_item_id', '')
        tmp.label_name = json.get('label_name', '')
        tmp.namespace = json.get('namespace', '')
        tmp.metadata = json.get('metadata', {})
        return tmp


@dataclass
class Game:
    """
    Combination of app asset and app metadata as stored on disk
    """
    app_name: str
    app_title: str

    asset_infos: Dict[str, GameAsset] = field(default_factory=dict)
    base_urls: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def app_version(self, platform='Windows'):
        if platform not in self.asset_infos:
            return None
        return self.asset_infos[platform].build_version

    @property
    def is_dlc(self):
        return self.metadata and 'mainGameItem' in self.metadata

    @property
    def third_party_store(self):
        if not self.metadata:
            return None
        return self.metadata.get('customAttributes', {}).get('ThirdPartyManagedApp', {}).get('value', None)

    @property
    def partner_link_type(self):
        if not self.metadata:
            return None
        return self.metadata.get('customAttributes', {}).get('partnerLinkType', {}).get('value', None)

    @property
    def partner_link_id(self):
        if not self.metadata:
            return None
        return self.metadata.get('customAttributes', {}).get('partnerLinkId', {}).get('value', None)

    @property
    def supports_cloud_saves(self):
        return self.metadata and (self.metadata.get('customAttributes', {}).get('CloudSaveFolder') is not None)

    @property
    def supports_mac_cloud_saves(self):
        return self.metadata and (self.metadata.get('customAttributes', {}).get('CloudSaveFolder_MAC') is not None)

    @property
    def catalog_item_id(self):
        if not self.metadata:
            return None
        return self.metadata['id']

    @property
    def namespace(self):
        if not self.metadata:
            return None
        return self.metadata['namespace']

    @classmethod
    def from_json(cls, json):
        tmp = cls(
            app_name=json.get('app_name', ''),
            app_title=json.get('app_title', ''),
        )
        tmp.metadata = json.get('metadata', dict())
        if 'asset_infos' in json:
            tmp.asset_infos = {k: GameAsset.from_json(v) for k, v in json['asset_infos'].items()}
        else:
            # Migrate old asset_info to new asset_infos
            tmp.asset_infos['Windows'] = GameAsset.from_json(json.get('asset_info', dict()))

        tmp.base_urls = json.get('base_urls', list())
        return tmp

    @property
    def __dict__(self):
        """This is just here so asset_infos gets turned into a dict as well"""
        assets_dictified = {k: v.__dict__ for k, v in self.asset_infos.items()}
        return dict(metadata=self.metadata, asset_infos=assets_dictified, app_name=self.app_name,
                    app_title=self.app_title, base_urls=self.base_urls)


@dataclass
class InstalledGame:
    """
    Local metadata for an installed app
    """
    app_name: str
    install_path: str
    title: str
    version: str

    base_urls: List[str] = field(default_factory=list)
    can_run_offline: bool = False
    egl_guid: str = ''
    executable: str = ''
    install_size: int = 0
    install_tags: List[str] = field(default_factory=list)
    is_dlc: bool = False
    launch_parameters: str = ''
    manifest_path: str = ''
    needs_verification: bool = False
    platform: str = 'Windows'
    prereq_info: Optional[Dict] = None
    requires_ot: bool = False
    save_path: Optional[str] = None

    @classmethod
    def from_json(cls, json):
        tmp = cls(
            app_name=json.get('app_name', ''),
            install_path=json.get('install_path', ''),
            title=json.get('title', ''),
            version=json.get('version', ''),
        )

        tmp.base_urls = json.get('base_urls', list())
        tmp.executable = json.get('executable', '')
        tmp.launch_parameters = json.get('launch_parameters', '')
        tmp.prereq_info = json.get('prereq_info', None)

        tmp.can_run_offline = json.get('can_run_offline', False)
        tmp.requires_ot = json.get('requires_ot', False)
        tmp.is_dlc = json.get('is_dlc', False)
        tmp.save_path = json.get('save_path', None)
        tmp.manifest_path = json.get('manifest_path', '')
        tmp.needs_verification = json.get('needs_verification', False) is True
        tmp.platform = json.get('platform', 'Windows')
        tmp.install_size = json.get('install_size', 0)
        tmp.egl_guid = json.get('egl_guid', '')
        tmp.install_tags = json.get('install_tags', [])
        return tmp


@dataclass
class SaveGameFile:
    """
    Metadata for a cloud save manifest
    """
    app_name: str
    filename: str
    manifest_name: str
    datetime: Optional[datetime] = None


class SaveGameStatus(Enum):
    LOCAL_NEWER = 0
    REMOTE_NEWER = 1
    SAME_AGE = 2
    NO_SAVE = 3


class VerifyResult(Enum):
    HASH_MATCH = 0
    HASH_MISMATCH = 1
    FILE_MISSING = 2
    OTHER_ERROR = 3


@dataclass
class LaunchParameters:
    """
    Parameters for launching a game
    """
    # game-supplied parameters
    game_parameters: list = field(default_factory=list)
    game_executable: str = ''
    game_directory: str = ''
    # EGL parameters (auth, ovt, etc.)
    egl_parameters: list = field(default_factory=list)
    # command line before executable (WINE, gamemode, etc.)
    launch_command: list = field(default_factory=list)
    # working directory for launched process
    working_directory: str = ''
    # user and environment supplied options
    user_parameters: list = field(default_factory=list)
    environment: dict = field(default_factory=dict)
