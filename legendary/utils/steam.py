import logging
import json
import os
import plistlib

from io import BytesIO
from random import randint
from sys import platform as sys_platform, argv as sys_argv
from zlib import crc32

from requests.models import CaseInsensitiveDict

from legendary.models.game import InstalledGame

if sys_platform == 'win32':
    from legendary.lfs.windows_helpers import query_registry_value, HKEY_CURRENT_USER
else:
    query_registry_value = HKEY_CURRENT_USER = None

try:
    import vdf
except ImportError:
    vdf = None

_script = '''#!/bin/bash
EPIC_PARAMS=$("{executable}" launch $1 --steam)
ret=$?
if [ $ret -ne 0 ]; then
     echo "Legendary failed with $ret"
     # hack to open URL in Deck UI browser (doesn't work from within legendary)
     if [ -n "${EPIC_PARAMS}" ]; then
         python3 -m webbrowser "${EPIC_PARAMS}"
         # This is just here so the browser opens before we get thrown back to the deck UI.
         read -s -t 5 -p "Waiting 5 seconds..."
     fi
     exit $ret
fi
eval "$2" $EPIC_PARAMS
'''


class SteamHelper:
    def __init__(self, steam_path=None, legendary_binary=None, legendary_config=None):
        if not vdf:
            raise RuntimeError('Steam support requires the vdf module to be installed.')

        if not steam_path:
            if sys_platform == 'win32':
                search_paths = [os.path.expandvars(f'%programfiles(x86)%\\steam'),
                                'C:\\Program Files (x86)\\Steam']
            elif sys_platform == 'darwin':
                search_paths = [os.path.expanduser('~/Library/Application Support/Steam')]
            elif sys_platform == 'linux':
                search_paths = [os.path.expanduser('~/.steam/Steam'),
                                os.path.expanduser('~/.steam/steam'),
                                os.path.expanduser('~/.local/share/Steam')]
            else:
                raise NotImplementedError('Steam support is not implemented for this platform.')

            for _path in search_paths:
                if os.path.exists(_path) and os.path.isdir(_path):
                    if os.path.isdir(os.path.join(_path, 'userdata')):
                        steam_path = _path
                        break

            if not steam_path:
                raise FileNotFoundError('Unable to find Steam installation.')

        # Legendary will be used as the executable in the shortcuts to run the games, in order for that to work,
        # it must be either run from a PyInstaller binary or the wrapper script that setuptools creates.
        if not legendary_binary or not os.path.exists(legendary_binary):
            legendary_binary = os.path.join(os.getcwd(), sys_argv[0])
            if legendary_binary.endswith('.py'):
                raise RuntimeError('Legendary must not be run from a .py file for Steam shortcuts to work.')

            if not os.path.exists(legendary_binary):
                # on windows, try again with '.exe':
                if sys_platform == 'win32':
                    legendary_binary += '.exe'
                    if not os.path.exists(legendary_binary):
                        raise RuntimeError('Could not automatically find a usable legendary binary!')
                else:
                    raise RuntimeError('Could not automatically find a usable legendary binary!')

        self.log = logging.getLogger('SteamHelper')

        self.steam_path = steam_path
        self.lgd_binary = os.path.abspath(legendary_binary)
        self.lgd_config_dir = legendary_config
        self.launch_script = None
        self.user_id = None
        self.user_dir = None
        self.grid_path = None
        self.shortcuts = dict()
        self.steam_config = dict()

    def is_steam_running(self):
        if sys_platform == 'win32':
            pid = query_registry_value(HKEY_CURRENT_USER, 'Software\\Valve\\Steam\\ActiveProcess', 'pid')
            self.log.debug(f'Steam PID: {pid}')
            return pid is not None and pid != 0
        elif sys_platform == 'darwin' or sys_platform == 'linux':
            if sys_platform == 'linux':
                registry_path = os.path.abspath(os.path.join(self.steam_path, '..', 'registry.vdf'))
            else:
                registry_path = os.path.join(self.steam_path, 'registry.vdf')
            registry = vdf.load(open(registry_path), mapper=CaseInsensitiveDict)
            pid = int(registry.get('Registry', {}).get('HKLM', {}).get('Software', {})
                      .get('Valve', {}).get('Steam', {}).get('SteamPID', '0'))
            return pid is not None and pid != 0
        else:
            raise NotImplementedError('Steam support is not implemented for this platform.')

    @staticmethod
    def _userid_from_steam64(sid):
        return sid & 0xFFFFFFFF

    def get_user_dir(self, username=None):
        if not username:
            # attempt to get primary username from registry
            if sys_platform == 'win32':
                username = query_registry_value(HKEY_CURRENT_USER, 'Software\\Valve\\Steam', 'AutoLoginUser')
            elif sys_platform == 'darwin' or sys_platform == 'linux':
                if sys_platform == 'linux':
                    registry_path = os.path.abspath(os.path.join(self.steam_path, '..', 'registry.vdf'))
                else:
                    registry_path = os.path.join(self.steam_path, 'registry.vdf')
                registry = vdf.load(open(registry_path), mapper=CaseInsensitiveDict)
                username = registry.get('Registry', {}).get('HKCU', {}).get('Software', {})\
                    .get('Valve', {}).get('Steam', {}).get('AutoLoginUser', '')
            else:
                raise NotImplementedError('Getting username from Steam registry is not implemented on Linux.')

        if not username:
            raise ValueError('Unable to find username.')

        self.log.info(f'Using Steam username: {username}')
        # read config from steam path

        login_users = vdf.load(open(os.path.join(self.steam_path, 'config', 'loginusers.vdf')),
                               mapper=CaseInsensitiveDict)
        for _steam_id, user_info in login_users.get('users', {}).items():
            if user_info['AccountName'] == username:
                steam_id = int(_steam_id)
                break
        else:
            raise ValueError('Unable to find user in Steam configuration.')

        self.user_id = self._userid_from_steam64(steam_id)
        self.user_dir = os.path.realpath(os.path.join(self.steam_path, 'userdata', str(self.user_id)))

        self.grid_path = os.path.join(self.user_dir, 'config', 'grid')
        if not os.path.exists(self.grid_path):
            os.makedirs(self.grid_path)

        return self.user_dir

    def read_shortcuts(self):
        if not self.user_dir:
            raise ValueError('Steam user directory not set.')

        # todo figure out case-insensitive dict
        shortcuts_file = os.path.join(self.user_dir, 'config', 'shortcuts.vdf')
        if os.path.exists(shortcuts_file):
            self.shortcuts = vdf.binary_load(open(shortcuts_file, 'rb'), mapper=CaseInsensitiveDict)
        else:
            self.shortcuts = dict(shortcuts=dict())

        return self.shortcuts

    def write_shortcuts(self, shortcuts):
        if not self.user_dir:
            raise ValueError('Steam user directory not set.')

        vdf.binary_dump(shortcuts, open(os.path.join(self.user_dir, 'config', 'shortcuts.vdf'), 'wb'))

    def read_config(self):
        if not self.steam_path:
            raise ValueError('Steam directory not set.')

        config_file = os.path.join(self.steam_path, 'config', 'config.vdf')
        if os.path.exists(config_file):
            self.steam_config = vdf.load(open(config_file), mapper=CaseInsensitiveDict)
        else:
            self.steam_config = dict(shortcuts=dict())

        return self.steam_config

    def write_config(self, config=None):
        if not self.steam_path:
            raise ValueError('Steam directory not set.')
        if not config:
            config = self.steam_config

        vdf.dump(config, open(os.path.join(self.steam_path, 'config', 'config.vdf'), 'w'), pretty=True)

    def create_shortcut_entry(self, igame: InstalledGame, app_id: int = 0):
        if not app_id:
            # check against existing and keep generating until unique
            existing_ids = set(entry['appid'] + 2**32 for entry in self.shortcuts.get('shortcuts', {}).values())
            while not app_id or app_id in existing_ids:
                app_id = randint(2 ** 31, 2 ** 32 - 1)

        if sys_platform == 'linux':
            launch_options = f'{self.launch_script} {igame.app_name} "%command%"'
            launch_dir = f'{igame.install_path}'
            exe = os.path.join(igame.install_path, igame.executable)
            launch_exe = f'\'{exe}\''
        else:
            launch_options = f'launch {igame.app_name} --steam'
            launch_dir = f'"{os.path.dirname(self.lgd_binary)}"'
            launch_exe = f'"{self.lgd_binary}"'

        entry = {
            'AllowDesktopConfig': 1,
            'AllowOverlay': 1,
            'Devkit': 0,
            'DevkitGameID': '',
            'DevkitOverrideAppID': 0,
            'IsHidden': 0,
            'LastPlayTime': 0,
            'LaunchOptions': launch_options,
            'ShortcutPath': '',
            'StartDir': launch_dir,
            'appid': app_id - 2 ** 32,  # appid is unsigned, but stored as signed, so hack it to be right
            'appname': igame.title,
            'exe': launch_exe,
            'icon': os.path.realpath(os.path.join(self.grid_path, f'{app_id}_icon.png')),
            'openvr': 0,
            'tags': {'0': 'Installed', '1': 'Unplayed', '2': 'Legendary'},
        }

        return entry

    def set_compat_tool(self, app_id: int, compat_tool: str):
        # todo ensure this section exists
        self.steam_config['InstallConfigStore']['Software']['Valve']['Steam']['CompatToolMapping'].update({
            str(app_id): {
                'name': compat_tool,
                'config': '',
                'Priority': '250'
            }
        })

    @staticmethod
    def make_header_image(banner, logo=None):
        # Big Picture banner
        try:
            from PIL import Image
            from PIL import ImageOps
        except ImportError:
            return banner

        bfp = BytesIO(banner)
        banner_img = Image.open(bfp).convert(mode='RGBA')
        banner_fit = ImageOps.fit(banner_img, (460, 215), Image.BILINEAR)

        if logo:
            lfp = BytesIO(logo)
            logo_img = Image.open(lfp).convert(mode='RGBA')
            logo_width = round(banner_fit.width * 0.50)
            # use sharper algorithm for upscaling
            method = Image.NEAREST if logo_img.width < logo_width else Image.BILINEAR
            logo_fit = ImageOps.pad(logo_img, (logo_width, banner_fit.height), method)
            x_pos = round(banner_fit.width * 0.25)

            banner_fit.alpha_composite(logo_fit, (x_pos, 0))

        outfp = BytesIO()
        banner_fit.convert(mode='RGB').save(outfp, format='JPEG', quality=95)
        return outfp.getvalue()

    @staticmethod
    def make_banner_image(banner, logo=None):
        # Steam Deck UI banners just use the game ID and PNG format and have a slightly different size
        try:
            from PIL import Image
            from PIL import ImageOps
        except ImportError:
            return banner

        bfp = BytesIO(banner)
        banner_img = Image.open(bfp).convert(mode='RGBA')
        banner_fit = ImageOps.fit(banner_img, (616, 353), Image.BILINEAR)

        if logo:
            lfp = BytesIO(logo)
            logo_img = Image.open(lfp).convert(mode='RGBA')
            logo_width = round(banner_fit.width * 0.50)
            # use sharper algorithm for upscaling
            method = Image.NEAREST if logo_img.width < logo_width else Image.BILINEAR
            logo_fit = ImageOps.pad(logo_img, (logo_width, banner_fit.height), method)
            x_pos = round(banner_fit.width * 0.25)

            banner_fit.alpha_composite(logo_fit, (x_pos, 0))

        outfp = BytesIO()
        banner_fit.convert(mode='RGB').save(outfp, format='PNG')
        return outfp.getvalue()

    @staticmethod
    def make_tall_box(tall, logo):
        try:
            from PIL import Image
            from PIL import ImageOps
        except ImportError:
            return tall

        bfp = BytesIO(tall)
        banner_img = Image.open(bfp).convert(mode='RGBA')
        banner_fit = ImageOps.fit(banner_img, (600, 900), Image.BILINEAR)

        lfp = BytesIO(logo)
        logo_img = Image.open(lfp).convert(mode='RGBA')
        logo_width = round(banner_fit.width * 0.8)
        # use sharper algorithm for upscaling
        method = Image.NEAREST if logo_img.width < logo_width else Image.BILINEAR
        logo_fit = ImageOps.pad(logo_img, (logo_width, banner_fit.height), method)
        x_pos = round(banner_fit.width * 0.1)

        banner_fit.alpha_composite(logo_fit, (x_pos, 0))

        outfp = BytesIO()
        banner_fit.convert(mode='RGB').save(outfp, format='PNG')
        return outfp.getvalue()

    @staticmethod
    def make_icon(igame):
        if igame.platform in ('Windows', 'Win32'):
            try:
                from legendary.utils.pe import PEUtils
            except ImportError:
                raise RuntimeError('Could not import PEUtils.')

            game_exe = os.path.join(igame.install_path, igame.executable)
            p = PEUtils(game_exe)
            icon = p.get_icon()
            p.close()
            return icon
        elif igame.platform == 'Mac':
            try:
                from PIL import Image
            except ImportError:
                raise RuntimeError('Could not import PIL.')

            # Install path for app bundles points to ~/Applications (or similar), the easiest way to
            # get to the info plist is to go to the executable first, and then check from there.
            # If it's not an app bundle (e.g. Unreal Engine) then this will fail.
            info_plist = os.path.realpath(os.path.join(igame.install_path, igame.executable, '..', 'Info.plist'))
            if not os.path.exists(info_plist):
                raise FileNotFoundError(f'Could not find Info.plist for {igame.title}.')

            plist = plistlib.load(open(info_plist, 'rb'))
            icon_file = plist.get('CFBundleIconFile', None)
            if not icon_file:
                return None
            icon_path = os.path.join(igame.install_path, 'Contents', 'Resources', icon_file)
            icon_img = Image.open(icon_path).convert(mode='RGBA')

            out = BytesIO()
            icon_img.save(out, format='PNG')
            return out.getvalue()
        else:
            raise NotImplementedError(f'Icon generation for {igame.platform} not implemented.')

    def get_header_id(self, igame):
        # taken from chimera
        if sys_platform == 'linux':
            exe = os.path.join(igame.install_path, igame.executable)
        else:
            exe = self.lgd_binary

        crc_input = ''.join([f'"{exe}"', igame.title])
        high_32 = crc32(crc_input.encode('utf-8')) | 0x80000000
        full_64 = (high_32 << 32) | 0x02000000
        return full_64

    def create_grid_json(self, app_id):
        filename = os.path.join(self.grid_path, f'{app_id}.json')

        if os.path.exists(filename):
            return

        # Always just center the logo
        grid_json = {
            "nVersion": 1,
            "logoPosition": {
                "pinnedPosition": "CenterCenter", "nWidthPct": 75, "nHeightPct": 75
            }
        }
        json.dump(grid_json, open(filename, 'w'))

    def ensure_launch_script(self):
        if self.lgd_binary is None or self.lgd_config_dir is None:
            raise RuntimeError('No LGD binary or config fir specified.')

        self.launch_script = os.path.join(self.lgd_config_dir, 'steam_launch')
        if os.path.exists(self.launch_script):
            # todo make sure the launch script still points at the right binary
            return

        with open(self.launch_script, 'w') as fp:
            fp.write(_script.replace('{executable}', self.lgd_binary))

        st = os.stat(self.launch_script)
        os.chmod(self.launch_script, st.st_mode | 0o0100)

