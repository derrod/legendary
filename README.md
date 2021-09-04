# Legendary
## A free and open-source Epic Games Launcher alternative
![Logo](https://repository-images.githubusercontent.com/249938026/80b18f80-96c7-11ea-9183-0a8c96e7cada)

[![Discord](https://discordapp.com/api/guilds/695233346627698689/widget.png?style=shield)](https://discord.gg/UJKBwPw) [![Twitter Follow](https://img.shields.io/twitter/follow/legendary_gl?label=Follow%20us%20for%20updates%21&style=social)](https://twitter.com/legendary_gl)

Legendary is an open-source game launcher that can download and install games from the Epic Games platform on Linux and Windows.
Its name as a tongue-in-cheek play on tiers of [item rarity in many MMORPGs](https://wow.gamepedia.com/Quality).

Right now Legendary is in beta and not feature-complete. You might run into some bugs or issues.
If you do please [create an issue on GitHub](https://github.com/derrod/legendary/issues/new) so we can fix it.

**Note:** Legendary is currently a CLI (command-line interface) application without a graphical user interface,
it has to be run from a terminal (e.g. PowerShell)

**What works:**
 - Authenticating with Epic's service
 - Downloading and installing your games and their DLC
 - Delta patching/updating of installed games
 - Launching games with online authentication (for multiplayer/DRM)
 - Syncing cloud saves (compatible with EGL)
 - Running games with WINE on Linux
 - Importing/Exporting installed games from/to the Epic Games Launcher

**Planned:**
 - Simple GUI for managing/launching games
 - Better interfaces for other developers to use Legendary in their projects
 - Lots and lots of bug fixes, optimizations, and refactoring...

## Requirements

- Linux or Windows (64-bit)
- python 3.8+ (64-bit on Windows)
- PyPI packages: `requests`, optionally `setuptools` and `wheel` for setup/building

## How to run/install

### Package Manager

Several distros already have packages available, check out the [Available Linux Packages](https://github.com/derrod/legendary/wiki/Available-Linux-Packages) wiki page for details.

Currently this includes
[Arch](https://github.com/derrod/legendary/wiki/Available-Linux-Packages#arch-aur),
[Fedora](https://github.com/derrod/legendary/wiki/Available-Linux-Packages#fedora),
[openSUSE](https://github.com/derrod/legendary/wiki/Available-Linux-Packages#opensuse), and
[Gentoo](https://github.com/derrod/legendary/wiki/Available-Linux-Packages#gentoo)
but more will be available in the future.

Note that since packages are maintained by third parties it may take a bit for them to be updated to the latest version.
If you always want to have the latest features and fixes available then using the PyPI distribution is recommended.

### Standalone

Download the `legendary` or `legendary.exe` binary from [the latest release](https://github.com/derrod/legendary/releases/latest)
and move it to somewhere in your `$PATH`/`%PATH%`. Don't forget to `chmod +x` it on Linux.

The Windows .exe and Linux executable were created with PyInstaller and will run standalone even without python being installed.
Note that on Linux glibc >= 2.25 is required, so older distributions such as Ubuntu 16.04 or Debian stretch will not work.

### Python package

#### Prerequisites

To prevent problems with permissions during installation, please upgrade your `pip` by running `python -m pip install -U pip --user`. 

> **Tip:** You may need to replace `python` in the above command with `python3.8` on Linux, or `py -3.8` on Windows.

#### Installation from PyPI (recommended)

Legendary is available on [PyPI](https://pypi.org/project/legendary-gl/), to install simply run:

```bash
pip install legendary-gl
```

#### Manually from the repo

- Install python3.8, setuptools, wheel, and requests
- Clone the git repository and cd into it
- Run `pip install .`

#### Ubuntu 20.04 example

Ubuntu 20.04's standard repositories include everything needed to install legendary:
````bash
sudo apt install python3 python3-requests python3-setuptools-git
git clone https://github.com/derrod/legendary.git
cd legendary
pip install .
````

If the `legendary` executable is not available after installation, you may need to configure your `PATH` correctly. You can do this by running the command: 

```bash
echo 'export PATH=$PATH:~/.local/bin' >> ~/.profile && source ~/.profile
```

### Directly from the repo (for dev/testing)

- Install python3.8 and requests (optionally in a venv)
- cd into the repository
- Run `pip install -e .`

This installs `legendary` in "editable" mode - any changes to the source code will take effect next time the `legendary` executable runs.

## Quickstart

**Tip:** When using PowerShell with the standalone executable, you may need to replace `legendary` with `.\legendary` in the commands below.

To log in:
````
legendary auth
````
Authentication is a little finicky since we have to go through the Epic website. The login page should open in your browser and after logging in you should be presented with a JSON response that contains a code, just copy and paste the code into your terminal to log in.
On Windows you can use the `--import` flag to import the authentication from the Epic Games Launcher. Note that this will log you out of the Epic Launcher.

Listing your games
````
legendary list-games
````
This will fetch a list of games available on your account, the first time may take a while depending on how many games you have.

Installing a game
````
legendary install Anemone
````
**Important:** the name used for these commands is the app name, *not* the game's name! The app name is in the parentheses after the game title in the games list.

List installed games and check for updates
````
legendary list-installed --check-updates
````

Launch (run) a game with online authentication
````
legendary launch Anemone
````
**Tip:** most games will run fine offline (`--offline`), and thus won't require launching through legendary for online authentication. You can run `legendary launch <App Name> --offline --dry-run` to get a command line that will launch the game with all parameters that would be used by the Epic Launcher. These can then be entered into any other game launcher (e.g. Lutris/Steam) if the game requires them.

Importing a previously installed game
````
legendary import-game Anemone /mnt/games/Epic/WorldOfGoo
````
**Note:** Importing will require a full verification so Legendary can correctly update the game later.

Sync savegames with the Epic Cloud
````
legendary sync-saves
````
**Note:** When this command is run the first time after a supported game has been installed it will ask you to confirm or provide the path to where the savegame is located.

Automatically sync all games with the Epic Games Launcher
````
legendary -y egl-sync
````

## Usage

````
usage: legendary [-h] [-v] [-y] [-V]
                 {auth,install,download,update,repair,uninstall,launch,list-games,list-installed,list-files,list-saves,download-saves,sync-saves,verify-game,import-game,egl-sync,status,cleanup}
                 ...

Legendary v0.X.X - "Codename"

optional arguments:
  -h, --help            show this help message and exit
  -v, --debug           Set loglevel to debug
  -y, --yes             Default to yes for all prompts
  -V, --version         Print version and exit

Commands:
  {auth,install,download,update,repair,uninstall,launch,list-games,list-installed,list-files,list-saves,download-saves,sync-saves,verify-game,import-game,egl-sync,status,cleanup}
    auth                Authenticate with EPIC
    install (download,update,repair)
                        Download a game
    uninstall           Uninstall (delete) a game
    launch              Launch a game
    list-games          List available (installable) games
    list-installed      List installed games
    list-files          List files in manifest
    list-saves          List available cloud saves
    download-saves      Download all cloud saves
    sync-saves          Sync cloud saves
    verify-game         Verify a game's local files
    import-game         Import an already installed game
    egl-sync            Setup or run Epic Games Launcher sync
    status              Show legendary status information
    cleanup             Remove old temporary, metadata, and manifest files

Individual command help:

Command: auth
usage: legendary auth [-h] [--import] [--code <exchange code>]
                      [--sid <session id>] [--delete]

optional arguments:
  -h, --help            show this help message and exit
  --import              Import Epic Games Launcher authentication data (logs
                        out of EGL)
  --code <exchange code>
                        Use specified exchange code instead of interactive
                        authentication
  --sid <session id>    Use specified session id instead of interactive
                        authentication
  --delete              Remove existing authentication (log out)


Command: install
usage: legendary install <App Name> [options]

Aliases: download, update

positional arguments:
  <App Name>            Name of the app

optional arguments:
  -h, --help            show this help message and exit
  --base-path <path>    Path for game installations (defaults to ~/legendary)
  --game-folder <path>  Folder for game installation (defaults to folder
                        specified in metadata)
  --max-shared-memory <size>
                        Maximum amount of shared memory to use (in MiB),
                        default: 1 GiB
  --max-workers <num>   Maximum amount of download workers, default: min(2 *
                        CPUs, 16)
  --manifest <uri>      Manifest URL or path to use instead of the CDN one
                        (e.g. for downgrading)
  --old-manifest <uri>  Manifest URL or path to use as the old one (e.g. for
                        testing patching)
  --delta-manifest <uri>
                        Manifest URL or path to use as the delta one (e.g. for
                        testing)
  --base-url <url>      Base URL to download from (e.g. to test or switch to a
                        different CDNs)
  --force               Download all files / ignore existing (overwrite)
  --disable-patching    Do not attempt to patch existing installation
                        (download entire changed files)
  --download-only, --no-install
                        Do not intall app and do not run prerequisite
                        installers after download
  --update-only         Only update, do not do anything if specified app is
                        not installed
  --dlm-debug           Set download manager and worker processes' loglevel to
                        debug
  --platform <Platform>
                        Platform override for download (also sets --no-
                        install)
  --prefix <prefix>     Only fetch files whose path starts with <prefix> (case
                        insensitive)
  --exclude <prefix>    Exclude files starting with <prefix> (case
                        insensitive)
  --install-tag <tag>   Only download files with the specified install tag
  --enable-reordering   Enable reordering optimization to reduce RAM
                        requirements during download (may have adverse results
                        for some titles)
  --dl-timeout <sec>    Connection timeout for downloader (default: 10
                        seconds)
  --save-path <path>    Set save game path to be used for sync-saves
  --repair              Repair installed game by checking and redownloading
                        corrupted/missing files
  --repair-and-update   Update game to the latest version when repairing
  --ignore-free-space   Do not abort if not enough free space is available
  --disable-delta-manifests
                        Do not use delta manifests when updating (may increase
                        download size)
  --reset-sdl           Reset selective downloading choices (requires repair
                        to download new components)


Command: uninstall
usage: legendary uninstall [-h] [--keep-files] <App Name>

positional arguments:
  <App Name>    Name of the app

optional arguments:
  -h, --help    show this help message and exit
  --keep-files  Keep files but remove game from Legendary database


Command: launch
usage: legendary launch <App Name> [options]

Note: additional arguments are passed to the game

positional arguments:
  <App Name>            Name of the app

optional arguments:
  -h, --help            show this help message and exit
  --offline             Skip login and launch game without online
                        authentication
  --skip-version-check  Skip version check when launching game in online mode
  --override-username <username>
                        Override username used when launching the game (only
                        works with some titles)
  --dry-run             Print the command line that would have been used to
                        launch the game and exit
  --language <two letter language code>
                        Override language for game launch (defaults to system
                        locale)
  --wrapper <wrapper command>
                        Wrapper command to launch game with
  --set-defaults        Save parameters used to launch to config (does not
                        include env vars)
  --reset-defaults      Reset config settings for app and exit
  --wine <wine binary>  Set WINE binary to use to launch the app
  --wine-prefix <wine pfx path>
                        Set WINE prefix to use
  --no-wine             Do not run game with WINE (e.g. if a wrapper is used)


Command: list-games
usage: legendary list-games [-h] [--platform <Platform>] [--include-ue] [--csv]
                            [--tsv] [--json]

optional arguments:
  -h, --help            show this help message and exit
  --platform <Platform>
                        Override platform that games are shown for (e.g.
                        Win32/Mac)
  --include-ue          Also include Unreal Engine content
                        (Engine/Marketplace) in list
  --csv                 List games in CSV format
  --tsv                 List games in TSV format
  --json                List games in JSON format


Command: list-installed
usage: legendary list-installed [-h] [--check-updates] [--csv] [--tsv] [--json]
                                [--show-dirs]

optional arguments:
  -h, --help       show this help message and exit
  --check-updates  Check for updates for installed games
  --csv            List games in CSV format
  --tsv            List games in TSV format
  --json           List games in JSON format
  --show-dirs      Print installation directory in output


Command: list-files
usage: legendary list-files [-h] [--force-download] [--platform <Platform>]
                            [--manifest <uri>] [--csv] [--tsv] [--json]
                            [--hashlist] [--install-tag <tag>]
                            [<App Name>]

positional arguments:
  <App Name>            Name of the app (optional)

optional arguments:
  -h, --help            show this help message and exit
  --force-download      Always download instead of using on-disk manifest
  --platform <Platform>
                        Platform override for download (disables install)
  --manifest <uri>      Manifest URL or path to use instead of the CDN one
  --csv                 Output in CSV format
  --tsv                 Output in TSV format
  --json                Output in JSON format
  --hashlist            Output file hash list in hashcheck/sha1sum -c
                        compatible format
  --install-tag <tag>   Show only files with specified install tag


Command: list-saves
usage: legendary list-saves [-h] [<App Name>]

positional arguments:
  <App Name>  Name of the app (optional)

optional arguments:
  -h, --help  show this help message and exit


Command: download-saves
usage: legendary download-saves [-h] [<App Name>]

positional arguments:
  <App Name>  Name of the app (optional)

optional arguments:
  -h, --help  show this help message and exit


Command: sync-saves
usage: legendary sync-saves [-h] [--skip-upload] [--skip-download]
                            [--force-upload] [--force-download]
                            [--save-path <path>] [--disable-filters]
                            [<App Name>]

positional arguments:
  <App Name>          Name of the app (optional)

optional arguments:
  -h, --help          show this help message and exit
  --skip-upload       Only download new saves from cloud, don't upload
  --skip-download     Only upload new saves from cloud, don't download
  --force-upload      Force upload even if local saves are older
  --force-download    Force download even if local saves are newer
  --save-path <path>  Override savegame path (requires single app name to be
                      specified)
  --disable-filters   Disable save game file filtering


Command: verify-game
usage: legendary verify-game [-h] <App Name>

positional arguments:
  <App Name>  Name of the app

optional arguments:
  -h, --help  show this help message and exit


Command: import-game
usage: legendary import-game [-h] [--disable-check]
                             <App Name> <Installation directory>

positional arguments:
  <App Name>            Name of the app
  <Installation directory>
                        Path where the game is installed

optional arguments:
  -h, --help            show this help message and exit
  --disable-check       Disables completeness check of the to-be-imported game
                        installation (useful if the imported game is a much
                        older version or missing files)


Command: egl-sync
usage: legendary egl-sync [-h] [--egl-manifest-path EGL_MANIFEST_PATH]
                          [--egl-wine-prefix EGL_WINE_PREFIX] [--enable-sync]
                          [--disable-sync] [--one-shot] [--import-only]
                          [--export-only] [--unlink]

optional arguments:
  -h, --help            show this help message and exit
  --egl-manifest-path EGL_MANIFEST_PATH
                        Path to the Epic Games Launcher's Manifests folder,
                        should point to
                        /ProgramData/Epic/EpicGamesLauncher/Data/Manifests
  --egl-wine-prefix EGL_WINE_PREFIX
                        Path to the WINE prefix the Epic Games Launcher is
                        installed in
  --enable-sync         Enable automatic EGL <-> Legendary sync
  --disable-sync        Disable automatic sync and exit
  --one-shot            Sync once, do not ask to setup automatic sync
  --import-only         Only import games from EGL (no export)
  --export-only         Only export games to EGL (no import)
  --unlink              Disable sync and remove EGL metadata from installed
                        games


Command: status
usage: legendary status [-h] [--offline] [--json]

optional arguments:
  -h, --help  show this help message and exit
  --offline   Only print offline status information, do not login
  --json      Show status in JSON format


Command: cleanup
usage: legendary cleanup [-h] [--keep-manifests]

optional arguments:
  -h, --help        show this help message and exit
  --keep-manifests  Do not delete old manifests
````


## Environment variables

Legendary supports overriding certain things via environment variables,
it also passes through any environment variables set before it is called.

Legendary specific environment variables:
+ `LGDRY_WINE_BINARY` - specifies wine binary
+ `LGDRY_WINE_PREFIX` - specified wine prefix
+ `LGDRY_NO_WINE` - disables wine
+ `LGDRY_WRAPPER` - specifies wrapper binary/command line

Note that the priority for settings that occur multiple times is:
command line > environment variables > config variables.

## Config file

Legendary supports some options as well as game specific configuration in `~/.config/legendary/config.ini`:
````ini
[Legendary]
log_level = debug
; maximum shared memory (in MiB) to use for installation
max_memory = 1024
; maximum number of worker processes when downloading (fewer workers will be slower, but also use fewer system resources)
max_workers = 8
; default install directory
install_dir = /mnt/tank/games
; locale override, must be in RFC 1766 format (e.g. "en-US")
locale = en-US
; whether or not syncing with egl is enabled
egl_sync = false
; path to the "Manifests" folder in the EGL ProgramData directory
egl_programdata = /home/user/Games/epic-games-store/drive_c/... 

; default settings to use (currently limited to WINE executable)
[default]
; (linux) specify wine executable to use
wine_executable = wine
; wine prefix (alternative to using environment variable)
wine_prefix = /home/user/.wine

; default environment variables to set (overridden by game specific ones)
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
wine_executable = /path/to/proton/wine64
; override language with two-letter language code
language = fr

[AppName.env]
; environment variables to set for this game (mostly useful on linux)
WINEPREFIX = /mnt/tank/games/Game/.wine
DXVK_CONFIG_FILE = /mnt/tank/games/Game/dxvk.conf

[AppName2]
; Use a wrapper to run this script
; Note that the path might have to be quoted if it contains spaces
wrapper = "/path/to/Proton 5.0/proton" run
; Do not run this executable with WINE (e.g. when the wrapper handles that)
no_wine = true
````
