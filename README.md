# Legendary
## A free and open-source Epic Games Launcher alternative
![Logo](https://repository-images.githubusercontent.com/249938026/80b18f80-96c7-11ea-9183-0a8c96e7cada)

[![Discord](https://discordapp.com/api/guilds/695233346627698689/widget.png?style=shield)](https://legendary.gl/discord) [![Twitter Follow](https://img.shields.io/twitter/follow/legendary_gl?label=Follow%20us%20for%20updates%21&style=social)](https://twitter.com/legendary_gl)

Legendary is an open-source game launcher that can download and install games from the Epic Games platform on Linux, macOS, and Windows.
Its name as a tongue-in-cheek play on tiers of [item rarity in many MMORPGs](https://wow.gamepedia.com/Quality).

Please read the the [config file](#config-file) and [cli usage](#usage) sections before creating an issue to avoid invalid reports.

If you run into any issues [ask for help on our Discord](https://legendary.gl/discord) or [create an issue on GitHub](https://github.com/derrod/legendary/issues/new/choose) so we can fix it!

Finally, if you wish to support the project, please consider [buying me a coffee on Ko-Fi](https://ko-fi.com/derrod).
Alternatively, if you've been considering picking up a copy of CrossOver you can use my [affiliate link](https://www.codeweavers.com/?ad=892) and discount code `LEGENDARY15` in their store.

**Note:** Legendary is currently a CLI (command-line interface) application without a graphical user interface,
it has to be run from a terminal (e.g. PowerShell)

**Features:**
 - Authenticating with Epic's service
 - Downloading and installing your games and their DLC
 - Delta patching/updating of installed games
 - Launching games with online authentication (for multiplayer/DRM)
 - Syncing cloud saves (compatible with EGL)
 - Running games with WINE on Linux/macOS
 - Importing/Exporting installed games from/to the Epic Games Launcher (unsupported for macOS version of EGL)

**Planned:**
 - Simple GUI for managing/launching games
 - Lots and lots of bug fixes, optimizations, and refactoring...

## Requirements

- Linux, Windows (8.1+), or macOS (12.0+)
  + 32-bit operating systems are not supported
- python 3.9+ (64-bit)
  + (Windows) `pythonnet` is not yet compatible with 3.10+, use 3.9 if you plan to install `pywebview` 
- PyPI packages:
  + `requests`
  + (optional) `pywebview` for webview-based login
  + (optional) `setuptools` and `wheel` for setup/building

**Note:** Running Windows applications on Linux or macOS requires [Wine](https://www.winehq.org/).

## How to run/install

### Package Manager (Linux)

Several distros already have packages available, check out the [Available Linux Packages](https://github.com/derrod/legendary/wiki/Available-Linux-Packages) wiki page for details.

Currently this includes
[Arch](https://github.com/derrod/legendary/wiki/Available-Linux-Packages#arch-aur),
[Fedora](https://github.com/derrod/legendary/wiki/Available-Linux-Packages#fedora),
[openSUSE](https://github.com/derrod/legendary/wiki/Available-Linux-Packages#opensuse), and
[Gentoo](https://github.com/derrod/legendary/wiki/Available-Linux-Packages#gentoo)
but more will be available in the future.

Note that since packages are maintained by third parties it may take a bit for them to be updated to the latest version.
If you always want to have the latest features and fixes available then using the PyPI distribution is recommended.

### Prebuilt Standalone Binary (Windows, macOS, and Linux)

Download the `legendary` or `legendary.exe` binary from [the latest release](https://github.com/derrod/legendary/releases/latest)
and move it to somewhere in your `$PATH`/`%PATH%`. Don't forget to `chmod +x` it on Linux/macOS.

The Windows .exe and Linux/macOS executable were created with PyInstaller and will run standalone even without python being installed.
Note that on Linux glibc >= 2.25 is required, so older distributions such as Ubuntu 16.04 or Debian stretch will not work.

### Python Package (any)

#### Prerequisites

To prevent problems with permissions during installation, please upgrade your `pip` by running `python -m pip install -U pip --user`. 

> **Tip:** You may need to replace `python` in the above command with `python3` on Linux/macOS, or `py -3` on Windows.

#### Installation from PyPI (recommended)

Legendary is available on [PyPI](https://pypi.org/project/legendary-gl/), to install simply run:

```bash
pip install legendary-gl
```

Optionally if logging in via an embedded web view is desired also run
```bash
pip install legendary-gl[webview]
```
On Linux this may also require installing a supported web engine and its python bindings.  
Ubunutu example:
```bash
sudo apt install python3-gi-cairo
pip install legendary-gl[webview]
```

Alternatively `pip install legendary-gl[webview_gtk]` or `pip install pywebview[gtk]` will work
but may require manually installing dependencies needed to build `PyGObject`.

**Note:** Using pywebview's Qt engine may not work correctly. Using pywebview is currently unsupported on macOS.

#### Manually from the repo

- Install python3.9, setuptools, wheel, and requests
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

- Install python3.9 and requests (optionally in a venv)
- cd into the repository
- Run `pip install -e .`

This installs `legendary` in "editable" mode - any changes to the source code will take effect next time the `legendary` executable runs.

## Quickstart

**Tip:** When using PowerShell with the standalone executable, you may need to replace `legendary` with `.\legendary` in the commands below.

To log in:
````
legendary auth
````
When using the prebuilt Windows executables of version 0.20.14 or higher this should open a new window with the Epic Login.

Otherwise, authentication is a little finicky since we have to go through the Epic website and manually copy a code.
The login page should open in your browser and after logging in you should be presented with a JSON response that contains a code ("authorizationCode"), just copy the code into the terminal and hit enter.

Alternatively you can use the `--import` flag to import the authentication from the Epic Games Launcher (manually specifying the used WINE prefix may be required on Linux).
Note that this will log you out of the Epic Launcher.

Listing your games
````
legendary list
````
This will fetch a list of games available on your account, the first time may take a while depending on how many games you have.

Installing a game
````
legendary install Anemone
````
**Note:** the name used here is generally the game's "app name" as seen in the games list rather than its title, but as of 0.20.12 legendary will try to match game names or abbreviations thereof as well. In this case `legendary install world of goo` or `legendary install wog` would also work!

List installed games and check for updates
````
legendary list-installed --check-updates
````

Launch (run) a game with online authentication
````
legendary launch "world of goo"
````
**Tip:** most games will run fine offline (`--offline`), and thus won't require launching through legendary for online authentication.
You can run `legendary launch <App Name> --offline --dry-run` to get a command line that will launch the game with all parameters that would be used by the Epic Launcher.
These can then be entered into any other game launcher (e.g. Lutris/Steam) if the game requires them.

Importing a previously installed game
````
legendary import Anemone /mnt/games/Epic/WorldOfGoo
````
**Note:** Importing will require a full verification so Legendary can correctly update the game later.  
**Note 2:** In order to use an alias here you may have to put it into quotes if if contains more than one word, e.g. `legendary import-game "world of goo" /mnt/games/Epic/WorldOfGoo`.

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
usage: legendary [-h] [-H] [-v] [-y] [-V] [-J] [-A <seconds>] <command> ...

Legendary v0.X.X - "Codename"

optional arguments:
  -h, --help            show this help message and exit
  -H, --full-help       Show full help (including individual command help)
  -v, --debug           Set loglevel to debug
  -y, --yes             Default to yes for all prompts
  -V, --version         Print version and exit
  -J, --pretty-json     Pretty-print JSON
  -A <seconds>, --api-timeout <seconds>
                        API HTTP request timeout (default: 10 seconds)

Commands:
  <command>
    activate            Activate games on third party launchers
    alias               Manage aliases
    auth                Authenticate with the Epic Games Store
    clean-saves         Clean cloud saves
    cleanup             Remove old temporary, metadata, and manifest files
    crossover           Setup CrossOver for launching games (macOS only)
    download-saves      Download all cloud saves
    egl-sync            Setup or run Epic Games Launcher sync
    eos-overlay         Manage EOS Overlay install
    import              Import an already installed game
    info                Prints info about specified app name or manifest
    install (download, update, repair)
                        Install/download/update/repair a game
    launch              Launch a game
    list                List available (installable) games
    list-files          List files in manifest
    list-installed      List installed games
    list-saves          List available cloud saves
    move                Move specified app name to a new location
    status              Show legendary status information
    sync-saves          Sync cloud saves
    uninstall           Uninstall (delete) a game
    verify              Verify a game's local files

Individual command help:

Command: activate
usage: legendary activate [-h] (-U | -O)

optional arguments:
  -h, --help    show this help message and exit
  -U, --uplay   Activate Uplay/Ubisoft Connect titles on your Ubisoft account
                (Uplay install not required)
  -O, --origin  Activate Origin/EA App managed titles on your EA account
                (requires Origin to be installed)


Command: alias
usage: legendary alias [-h]
                       <add|rename|remove|list> [<App name/Old alias>]
                       [<New alias>]

positional arguments:
  <add|rename|remove|list>
                        Action: Add, rename, remove, or list alias(es)
  <App name/Old alias>  App name when using "add" or "list" action, existing
                        alias when using "rename" or "remove" action
  <New alias>           New alias when using "add" action

optional arguments:
  -h, --help            show this help message and exit


Command: auth
usage: legendary auth [-h] [--import] [--code <exchange code>]
                      [--sid <session id>] [--delete] [--disable-webview]

optional arguments:
  -h, --help            show this help message and exit
  --import              Import Epic Games Launcher authentication data (logs
                        out of EGL)
  --code <authorization code>
                        Use specified authorization code instead of interactive authentication
  --token <exchange token>
                        Use specified exchange token instead of interactive authentication
  --sid <session id>    Use specified session id instead of interactive
                        authentication
  --delete              Remove existing authentication (log out)
  --disable-webview     Do not use embedded browser for login


Command: clean-saves
usage: legendary clean-saves [-h] [--delete-incomplete] [<App Name>]

positional arguments:
  <App Name>           Name of the app (optional)

optional arguments:
  -h, --help           show this help message and exit
  --delete-incomplete  Delete incomplete save files


Command: cleanup
usage: legendary cleanup [-h] [--keep-manifests]

optional arguments:
  -h, --help        show this help message and exit
  --keep-manifests  Do not delete old manifests


Command: crossover
usage: legendary crossover [-h] [--reset] [--download] [--ignore-version]
                           [--crossover-app <path to .app>]
                           [--crossover-bottle <bottle name>]
                           [<App Name>]

positional arguments:
  <App Name>            App name to configure, will configure defaults if
                        ommited

optional arguments:
  -h, --help            show this help message and exit
  --reset               Reset default/app-specific crossover configuration
  --download            Automatically download and set up a preconfigured
                        bottle (experimental)
  --ignore-version      Disable version check for available bottles when using
                        --download
  --crossover-app <path to .app>
                        Specify app to skip interactive selection
  --crossover-bottle <bottle name>
                        Specify bottle to skip interactive selection


Command: download-saves
usage: legendary download-saves [-h] [<App Name>]

positional arguments:
  <App Name>  Name of the app (optional)

optional arguments:
  -h, --help  show this help message and exit


Command: egl-sync
usage: legendary egl-sync [-h] [--egl-manifest-path EGL_MANIFEST_PATH]
                          [--egl-wine-prefix EGL_WINE_PREFIX] [--enable-sync]
                          [--disable-sync] [--one-shot] [--import-only]
                          [--export-only] [--migrate] [--unlink]

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
  --migrate             Import games into legendary, then remove them from EGL
                        (implies --import-only --one-shot --unlink)
  --unlink              Disable sync and remove EGL metadata from installed
                        games


Command: eos-overlay
usage: legendary eos-overlay [-h] [--path PATH] [--prefix PREFIX] [--app APP]
                             [--bottle BOTTLE]
                             <install|update|remove|enable|disable|info>

positional arguments:
  <install|update|remove|enable|disable|info>
                        Action: install, remove, enable, disable, or print
                        info about the overlay

optional arguments:
  -h, --help            show this help message and exit
  --path PATH           Path to the EOS overlay folder to be enabled/installed
                        to.
  --prefix PREFIX       WINE prefix to install the overlay in
  --app APP             Use this app's wine prefix (if configured in config)
  --bottle BOTTLE       WINE prefix to install the overlay in


Command: import
usage: legendary import [-h] [--disable-check] [--with-dlcs] [--skip-dlcs]
                        [--platform <Platform>]
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
  --with-dlcs           Automatically attempt to import all DLCs with the base
                        game
  --skip-dlcs           Do not ask about importing DLCs.
  --platform <Platform>
                        Platform for import (default: Mac on macOS, otherwise
                        Windows)


Command: info
usage: legendary info [-h] [--offline] [--json] [--platform <Platform>]
                      <App Name/Manifest URI>

positional arguments:
  <App Name/Manifest URI>
                        App name or manifest path/URI

optional arguments:
  -h, --help            show this help message and exit
  --offline             Only print info available offline
  --json                Output information in JSON format
  --platform <Platform>
                        Platform to fetch info for (default: installed or Mac
                        on macOS, Windows otherwise)


Command: install
usage: legendary install <App Name> [options]

Aliases: download, update

positional arguments:
  <App Name>            Name of the app

optional arguments:
  -h, --help            show this help message and exit
  --base-path <path>    Path for game installations (defaults to ~/Games)
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
                        Do not install app and do not run prerequisite
                        installers after download
  --update-only         Only update, do not do anything if specified app is
                        not installed
  --dlm-debug           Set download manager and worker processes' loglevel to
                        debug
  --platform <Platform>
                        Platform for install (default: installed or Windows)
  --prefix <prefix>     Only fetch files whose path starts with <prefix> (case
                        insensitive)
  --exclude <prefix>    Exclude files starting with <prefix> (case
                        insensitive)
  --install-tag <tag>   Only download files with the specified install tag
  --read-files          Read duplicated parts from already saved files, do not
                        keep them in RAM
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
  --skip-sdl            Skip SDL prompt and continue with defaults (only
                        required game data)
  --disable-sdl         Disable selective downloading for title, reset
                        existing configuration (if any)
  --preferred-cdn <hostname>
                        Set the hostname of the preferred CDN to use when
                        available
  --no-https            Download games via plaintext HTTP (like EGS), e.g. for
                        use with a lan cache
  --with-dlcs           Automatically install all DLCs with the base game
  --skip-dlcs           Do not ask about installing DLCs.


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
  --override-exe <exe path>
                        Override executable to launch (relative path)
  --origin              Launch Origin to activate or run the game.
  --json                Print launch information as JSON and exit
  --wine <wine binary>  Set WINE binary to use to launch the app
  --wine-prefix <wine pfx path>
                        Set WINE prefix to use
  --no-wine             Do not run game with WINE (e.g. if a wrapper is used)
  --crossover           Interactively configure CrossOver for this
                        application.
  --crossover-app <path to .app>
                        Specify which App to use for CrossOver (e.g.
                        "/Applications/CrossOver.app")
  --crossover-bottle <bottle name>
                        Specify which bottle to use for CrossOver


Command: list
usage: legendary list [-h] [--platform <Platform>] [--include-ue] [-T] [--csv]
                      [--tsv] [--json] [--force-refresh]

optional arguments:
  -h, --help            show this help message and exit
  --platform <Platform>
                        Platform to fetch game list for (default: Mac on
                        macOS, otherwise Windows)
  --include-ue          Also include Unreal Engine content
                        (Engine/Marketplace) in list
  -T, --third-party, --include-non-installable
                        Include apps that are not installable (e.g. that have
                        to be activated on Origin)
  --csv                 List games in CSV format
  --tsv                 List games in TSV format
  --json                List games in JSON format
  --force-refresh       Force a refresh of all game metadata


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
                        Platform (default: Mac on macOS, otherwise Windows)
  --manifest <uri>      Manifest URL or path to use instead of the CDN one
  --csv                 Output in CSV format
  --tsv                 Output in TSV format
  --json                Output in JSON format
  --hashlist            Output file hash list in hashcheck/sha1sum -c
                        compatible format
  --install-tag <tag>   Show only files with specified install tag


Command: list-installed
usage: legendary list-installed [-h] [--check-updates] [--csv] [--tsv]
                                [--json] [--show-dirs]

optional arguments:
  -h, --help       show this help message and exit
  --check-updates  Check for updates for installed games
  --csv            List games in CSV format
  --tsv            List games in TSV format
  --json           List games in JSON format
  --show-dirs      Print installation directory in output


Command: list-saves
usage: legendary list-saves [-h] [<App Name>]

positional arguments:
  <App Name>  Name of the app (optional)

optional arguments:
  -h, --help  show this help message and exit


Command: move
usage: legendary move [-h] [--skip-move] <App Name> <New Base Path>

positional arguments:
  <App Name>       Name of the app
  <New Base Path>  Directory to move game folder to

optional arguments:
  -h, --help       show this help message and exit
  --skip-move      Only change legendary database, do not move files (e.g. if
                   already moved)


Command: status
usage: legendary status [-h] [--offline] [--json]

optional arguments:
  -h, --help  show this help message and exit
  --offline   Only print offline status information, do not login
  --json      Show status in JSON format


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


Command: uninstall
usage: legendary uninstall [-h] [--keep-files] <App Name>

positional arguments:
  <App Name>    Name of the app

optional arguments:
  -h, --help    show this help message and exit
  --keep-files  Keep files but remove game from Legendary database


Command: verify
usage: legendary verify [-h] <App Name>

positional arguments:
  <App Name>  Name of the app

optional arguments:
  -h, --help  show this help message and exit
````


## Config file

Legendary supports some options as well as game specific configuration in `~/.config/legendary/config.ini`:
````ini
[Legendary]
log_level = debug
; maximum shared memory (in MiB) to use for installation
max_memory = 2048
; maximum number of worker processes when downloading (fewer workers will be slower, but also use less system resources)
max_workers = 8
; Enables reading duplicated data from files during download (decreases RAM usage but increases disk I/O)
read_files = false
; default install directory
install_dir = /mnt/tank/games
; locale override, must be in RFC 1766 format (e.g. "en-US")
locale = en-US
; whether or not syncing with egl is enabled
egl_sync = false
; path to the "Manifests" folder in the EGL ProgramData directory
egl_programdata = /home/user/Games/epic-games-store/drive_c/... 
; Set preferred CDN host (e.g. to improve download speed)
preferred_cdn = epicgames-download1.akamaized.net
; disable HTTPS for downloads (e.g. to use a LanCache)
disable_https = false
; Disables the automatic update check
disable_update_check = false
; Disables the notice about an available update on exit
disable_update_notice = false
; Disable automatically-generated aliases
disable_auto_aliasing = false

; macOS specific settings
; Default application platform to use (default: Mac on macOS, Windows elsewhere)
default_platform = Windows
; Fallback to "Windows" platform if native version unavailable
install_platform_fallback = true
; (macOS) Disable automatic CrossOver use
disable_auto_crossover = false
; Default directory for native Mac applications (.app packages)
mac_install_dir = /User/legendary/Applications

[Legendary.aliases]
; List of aliases for simpler CLI use, in the format `<alias> = <app name>`
HITMAN 3 = Eider
gtav = 9d2d0eb64d5c44529cece33fe2a46482

; default settings to use for all apps (unless overridden in the app's config section)
; Note that only the settings listed below are supported.
[default]
; (all) wrapper to run the game with (e.g. "gamemode")
wrapper = gamemode
; (linux/macOS) Wine executable and prefix
wine_executable = wine
wine_prefix = /home/user/.wine
; (macOS) CrossOver options
crossover_app = /Applications/CrossOver.app
crossover_bottle = Legendary

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
; override language with two-letter language code
language = fr
; Override Wine version for this app
wine_executable = /path/to/wine64

[AppName.env]
; environment variables to set for this game (mostly useful on linux)
WINEPREFIX = /mnt/tank/games/Game/.wine
DXVK_CONFIG_FILE = /mnt/tank/games/Game/dxvk.conf

[AppName2]
; Use a wrapper to run this script
; Note that the path might have to be quoted if it contains spaces
wrapper = "/path/with spaces/gamemoderun"
; Do not run this executable with WINE (e.g. when the wrapper handles that)
no_wine = true
; Override the executable launched for this game, for example to bypass a launcher (e.g. Borderlands)
override_exe = relative/path/to/file.exe
; Disable selective downloading for this title
disable_sdl = true

[AppName3]
; Command to run before launching the gmae
pre_launch_command = /path/to/script.sh
; Whether or not to wait for command to finish running
pre_launch_wait = false
; (macOS) override crossover settings
crossover_app = /Applications/CrossOver Nightly.app
crossover_bottle = SomethingElse
````
