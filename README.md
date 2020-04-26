# Legendary Game Launcher
### A free and open-source Epic Games Launcher replacement
[![Discord](https://discordapp.com/api/guilds/695233346627698689/widget.png?style=shield)](https://discord.gg/UJKBwPw) [![Twitter Follow](https://img.shields.io/twitter/follow/legendary_gl?label=Follow%20us%20for%20updates%21&style=social)](https://twitter.com/legendary_gl)

Legendary (named after the next highest tier [in item rarity](https://wow.gamepedia.com/Quality)) is an open-source game launcher that can download and install games from the Epic Games Store on Linux and Windows.

Right now it is in an early public pre-release stage and still needs a lot of work to work. But it does work!

**What works:**
 - Authenticate with Epic
 - Download and install games
 - Update installed games and their DLC
 - Launch games with online authentication

**Planned:**
 - Better Linux and WINE support
 - Importing installed games from the EGS launcher
 - PyPI distribution
 - Miscellaneous optimizations
 - Simple GUI for managing/launching games
 - Lots and lots of bug fixes and refactoring...

## Requirements

- python 3.8+
- requests

## How to install

- Windows (standalone): Download the latest EXE from [GitHub](https://github.com/derrod/legendary/releases/latest)
- Linux/Windows (requires setuptools to be installed): `python3.8 setup.py install`

A PyPI package will follow once it has gotten more testing.

The Windows .exe was created with PyInstaller and will run standalone without python being installed.

## Quickstart

To log in:
````
$ legendary auth
````
Authentication is a little finicky since we have to go through the Epic website. The login page should open in your browser and after logging in you should be presented with a JSON response that contains a code, just copy and paste the code into your terminal to log in.

Listing your games
````
$ legendary list-games
````
This will fetch a list of games available on your account, the first time may take a while depending on how many games you have.

Installing a game
````
$ legendary download Anemone
````
**Important:** the name used for these commands is the app name, *not* the game's name! The app name is in the parentheses after the game title in the games list.

List installed games and check for updates
````
$ legendary list-installed --check-updates
````

Launch (run) a game with online authentication
````
$ legendary launch Anemone
````
**Tip:** most games will run fine offline (`--offline`), and thus won't require launching through legendary for online authentication. You can run `legendary launch <App Name> --offline --dry-run` to get a command line that will launch the game with all parameters that would be used by the Epic Launcher. These can then be entered into any other game launcher (e.g. Lutris/Steam) if the game requires them.

## Usage

````
usage: legendary [-h] [-v] [-y] {auth,download,uninstall,launch,list-games,list-installed} ...

Legendary Game Launcher

optional arguments:
  -h, --help            show this help message and exit
  -v                    Set loglevel to debug
  -y                    Default to yes for all prompts

Commands:
  {auth,download,uninstall,launch,list-games,list-installed}
    auth                Authenticate with EPIC
    download            Download a game
    uninstall           Uninstall (delete) a game
    launch              Launch a game
    list-games          List available (installable) games
    list-installed      List installed games

Individual command help:

Command: auth
usage: legendary.exe auth [-h] [--import]

optional arguments:
  -h, --help  show this help message and exit
  --import    Import EGS authentication data


Command: download
usage: legendary.exe download <App Name> [options]

positional arguments:
  <App Name>            Name of the app

optional arguments:
  -h, --help            show this help message and exit
  --base-path <path>    Path for game installations (defaults to ~/legendary)
  --game-folder <path>  Folder for game installation (defaults to folder in metadata)
  --max-shared-memory <size>
                        Maximum amount of shared memory to use (in MiB), default: 1 GiB
  --max-workers <num>   Maximum amount of download workers, default: 2 * logical CPU
  --manifest <uri>      Manifest URL or path to use instead of the CDN one (e.g. for downgrading)
  --old-manifest <uri>  Manifest URL or path to use as the old one (e.g. for testing patching)
  --base-url <url>      Base URL to download from (e.g. to test or switch to a different CDNs)
  --force               Ignore existing files (overwrite)
  --disable-patching    Do not attempt to patch existing installations (download entire changed file)
  --download-only       Do not mark game as intalled and do not run prereq installers after download
  --update-only         Abort if game is not already installed (for automation)
  --dlm-debug           Set download manager and worker processes' loglevel to debug


Command: uninstall
usage: legendary.exe uninstall [-h] <App Name>

positional arguments:
  <App Name>  Name of the app

optional arguments:
  -h, --help  show this help message and exit


Command: launch
usage: legendary.exe launch <App Name> [options]

Note: additional arguments are passed to the game

positional arguments:
  <App Name>            Name of the app

optional arguments:
  -h, --help            show this help message and exit
  --offline             Skip login and launch game without online authentication
  --skip-version-check  Skip version check when launching game in online mode
  --override-username <username>
                        Override username used when launching the game (only works with some titles)
  --dry-run             Print the command line that would have been used to launch the game and exit


Command: list-games
usage: legendary.exe list-games [-h]

optional arguments:
  -h, --help  show this help message and exit


Command: list-installed
usage: legendary.exe list-installed [-h] [--check-updates]

optional arguments:
  -h, --help       show this help message and exit
  --check-updates  Check for updates when listing installed games
````


## Config file

Legendary supports some options as well as game specific configuration in `~/.config/legendary/config.ini`:
````ini
[Legendary]
log_level = debug
; maximum shared memory (in MiB) to use for installation
max_memory = 1024
; default install directory
install_dir = /mnt/tank/games

; default settings to use (currently limited to WINE executable)
[default]
; (linux) specify wine executable to use
wine_executable = wine

; default environment variables to set (overriden by game specific ones)
[default.env]
WINEPREFIX = /home/user/legendary/.wine

; Settings to only use for "AppName"
[AppName]
; launch game without online authentication by default
offline = true
; Skip checking for updates when launching this game
skip_update_check = true
; start parameters to use (in addition to the required ones)
start_params = -windowed
wine_executable = proton

[AppName.env]
; environment variables to set for this game (mostly useful on linux)
WINEPREFIX = /mnt/tank/games/Game/.wine
DXVK_CONFIG_FILE = /mnt/tank/games/Game/dxvk.conf
````

