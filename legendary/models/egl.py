from copy import deepcopy
from distutils.util import strtobool

from legendary.models.game import InstalledGame, Game


_template = {
    'AppCategories': ['public', 'games', 'applications'],
    'AppName': '',
    'AppVersionString': '',
    'BaseURLs': [],
    'BuildLabel': '',
    'CatalogItemId': '',
    'CatalogNamespace': '',
    'ChunkDbs': [],
    'CompatibleApps': [],
    'DisplayName': '',
    'FormatVersion': 0,
    'FullAppName': '',
    'HostInstallationGuid': '',
    'InstallComponents': [],
    'InstallLocation': '',
    'InstallSessionId': '',
    'InstallSize': 0,
    'InstallTags': [],
    'InstallationGuid': '',
    'LaunchCommand': '',
    'LaunchExecutable': '',
    'MainGameAppName': '',
    'MainWindowProcessName': '',
    'MandatoryAppFolderName': '',
    'ManifestLocation': '',
    'OwnershipToken': '',
    'PrereqIds': [],
    'ProcessNames': [],
    'StagingLocation': '',
    'TechnicalType': '',
    'VaultThumbnailUrl': '',
    'VaultTitleText': '',
    'bCanRunOffline': True,
    'bIsApplication': True,
    'bIsExecutable': True,
    'bIsIncompleteInstall': False,
    'bIsManaged': False,
    'bNeedsValidation': False,
    'bRequiresAuth': True
}


class EGLManifest:
    def __init__(self):
        self.app_name = None
        self.app_version_string = None
        self.base_urls = None
        self.build_label = None
        self.catalog_item_id = None
        self.namespace = None
        self.display_name = None
        self.install_location = None
        self.install_size = None
        self.install_tags = None
        self.installation_guid = None
        self.launch_command = None
        self.executable = None
        self.main_game_appname = None
        self.app_folder_name = None
        self.manifest_location = None
        self.ownership_token = None
        self.staging_location = None
        self.can_run_offline = None
        self.is_incomplete_install = None
        self.needs_validation = None

        self.remainder = dict()

    @classmethod
    def from_json(cls, json: dict):
        json = deepcopy(json)
        tmp = cls()
        tmp.app_name = json.pop('AppName')
        tmp.app_version_string = json.pop('AppVersionString', None)
        tmp.base_urls = json.pop('BaseURLs', list())
        tmp.build_label = json.pop('BuildLabel', '')
        tmp.catalog_item_id = json.pop('CatalogItemId', '')
        tmp.namespace = json.pop('CatalogNamespace', '')
        tmp.display_name = json.pop('DisplayName', '')
        tmp.install_location = json.pop('InstallLocation', '')
        tmp.install_size = json.pop('InstallSize', 0)
        tmp.install_tags = json.pop('InstallTags', [])
        tmp.installation_guid = json.pop('InstallationGuid', '')
        tmp.launch_command = json.pop('LaunchCommand', '')
        tmp.executable = json.pop('LaunchExecutable', '')
        tmp.main_game_appname = json.pop('MainGameAppName', '')
        tmp.app_folder_name = json.pop('MandatoryAppFolderName', '')
        tmp.manifest_location = json.pop('ManifestLocation', '')
        tmp.ownership_token = strtobool(json.pop('OwnershipToken', 'False'))
        tmp.staging_location = json.pop('StagingLocation', '')
        tmp.can_run_offline = json.pop('bCanRunOffline', True)
        tmp.is_incomplete_install = json.pop('bIsIncompleteInstall', False)
        tmp.needs_validation = json.pop('bNeedsValidation', False)
        tmp.remainder = json.copy()
        return tmp

    def to_json(self) -> dict:
        out = _template.copy()
        out.update(self.remainder)
        out['AppName'] = self.app_name
        out['AppVersionString'] = self.app_version_string
        out['BaseURLs'] = self.base_urls
        out['BuildLabel'] = self.build_label
        out['CatalogItemId'] = self.catalog_item_id
        out['CatalogNamespace'] = self.namespace
        out['DisplayName'] = self.display_name
        out['InstallLocation'] = self.install_location
        out['InstallSize'] = self.install_size
        out['InstallTags'] = self.install_tags
        out['InstallationGuid'] = self.installation_guid
        out['LaunchCommand'] = self.launch_command
        out['LaunchExecutable'] = self.executable
        out['MainGameAppName'] = self.main_game_appname
        out['MandatoryAppFolderName'] = self.app_folder_name
        out['ManifestLocation'] = self.manifest_location
        out['OwnershipToken'] = str(self.ownership_token).lower()
        out['StagingLocation'] = self.staging_location
        out['bCanRunOffline'] = self.can_run_offline
        out['bIsIncompleteInstall'] = self.is_incomplete_install
        out['bNeedsValidation'] = self.needs_validation
        return out

    @classmethod
    def from_lgd_game(cls, game: Game, igame: InstalledGame):
        tmp = cls()
        tmp.app_name = game.app_name
        tmp.app_version_string = igame.version
        tmp.base_urls = igame.base_urls
        tmp.build_label = 'Live'
        tmp.catalog_item_id = game.catalog_item_id
        tmp.namespace = game.namespace
        tmp.display_name = igame.title
        tmp.install_location = igame.install_path
        tmp.install_size = igame.install_size
        tmp.install_tags = igame.install_tags
        tmp.installation_guid = igame.egl_guid
        tmp.launch_command = igame.launch_parameters
        tmp.executable = igame.executable
        tmp.main_game_appname = game.app_name  # todo for DLC support this needs to be the base game
        tmp.app_folder_name = game.metadata.get('customAttributes', {}).get('FolderName', {}).get('value', '')
        tmp.manifest_location = igame.install_path + '/.egstore'
        tmp.ownership_token = igame.requires_ot
        tmp.staging_location = igame.install_path + '/.egstore/bps'
        tmp.can_run_offline = igame.can_run_offline
        tmp.is_incomplete_install = False
        tmp.needs_validation = igame.needs_verification
        return tmp

    def to_lgd_igame(self) -> InstalledGame:
        return InstalledGame(app_name=self.app_name, title=self.display_name, version=self.app_version_string,
                             base_urls=self.base_urls, install_path=self.install_location, executable=self.executable,
                             launch_parameters=self.launch_command, can_run_offline=self.can_run_offline,
                             requires_ot=self.ownership_token, is_dlc=False,
                             needs_verification=self.needs_validation, install_size=self.install_size,
                             egl_guid=self.installation_guid, install_tags=self.install_tags)
