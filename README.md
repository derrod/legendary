# Legendary (Game Launcher)
### A free and open-source Epic Games Launcher replacement
[![Discord](https://discordapp.com/api/guilds/695233346627698689/widget.png?style=shield)](https://discord.gg/UJKBwPw) [![Twitter Follow](https://img.shields.io/twitter/follow/legendary_gl?label=Follow%20us%20for%20updates%21&style=social)](https://twitter.com/legendary_gl)

Legendary (named after the next highest tier [in item rarity](https://wow.gamepedia.com/Quality)) is an open-source game launcher that can download and install games from the Epic Games Store on Linux and Windows.

Right now it is in an early public pre-release stage and still needs a lot of work to work. But it does work!

**Currently implemented:**
 - Authenticate with Epic (can import authentication from EGS installation [Windows only])
 - Download and install games
 - Update installed games (not well tested/potentially buggy)
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
$ legendary --auth
````
Authentication is a little finicky since we have to go through the Epic website. In the first step you will log in and in the second one you are required to copy an exchange code from a JSON site into the command line.
On Windows you can add `--import` to attempt to import the session from the Epic Games Launcher, if it is installed and you're logged in.

Listing your games
````
$ legendary --list-games
````
This will fetch a list of games available on your account, the first time may take a while depending on how many games you have.

Installing a game
````
$ legendary --install Anemone
````
**Important:** the name used for these commands is the app name, *not* the game's name! The app name is included in the games list after the title.

List installed games and check for updates
````
$ legendary --list-installed --check-updates
````

Launch (run) a game with online authentication
````
$ legendary --launch Anemone
````

## Usage

````
usage: legendary [-h] (--auth | --download <name> | --install <name> | --update <name> | --uninstall <name> | --launch <name> | --list-games | --list-installed) [-v] [--import] [--base-path <path>] [--max-shared-memory <size>] [--max-workers <num>] [--manifest <uri>] [--base-url <url>] [--force]
                 [--disable-patching] [--offline] [--skip-version-check] [--override-username <username>] [--dry-run] [--check-updates]

Legendary (Game Launcher)

optional arguments:
  -h, --help            show this help message and exit
  --auth                Authenticate Legendary with your account
  --download <name>     Download a game's files
  --install <name>      Download and install a game
  --update <name>       Update a game (alias for --install)
  --uninstall <name>    Remove a game
  --launch <name>       Launch game
  --list-games          List available games
  --list-installed      List installed games
  -v                    Set loglevel to debug

Authentication options:
  --import              Import EGS authentication data

Downloading options:
  --base-path <path>    Path for game installations (defaults to ~/legendary)
  --max-shared-memory <size>
                        Maximum amount of shared memory to use (in MiB), default: 1 GiB
  --max-workers <num>   Maximum amount of download workers, default: 2 * logical CPU
  --manifest <uri>      Manifest URL or path to use instead of the CDN one (e.g. for downgrading)
  --base-url <url>      Base URL to download from (e.g. to test or switch to a different CDNs)
  --force               Ignore existing files (overwrite)

Installation options:
  --disable-patching    Do not attempt to patch existing installations (download full game)

Game launch options:
  Note: any additional arguments will be passed to the game.

  --offline             Skip login and launch game without online authentication
  --skip-version-check  Skip version check when launching game in online mode
  --override-username <username>
                        Override username used when launching the game (only works with some titles)
  --dry-run             Print the command line that would have been used to launch the game and exit

Listing options:
  --check-updates       Check for updates when listing installed games
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

[AppName]
; launch game without online authentication by default
offline = true
; Skip checking for updates when launching this game
skip_update_check = true
; start parameters to use (in addition to the required ones)
start_params = -windowed
; (linux) specify wine executable to use
wine_executable = wine

[AppName.env]
; environment variables to set for this game (mostly useful on linux)
WINEPREFIX = /home/user/legendary/Game/.wine
DXVK_CONFIG_FILE = /home/user/legendary/Game/dxvk.conf
````

