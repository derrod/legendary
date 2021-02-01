import os
import configparser


def read_registry(wine_pfx):
    reg = configparser.ConfigParser(comment_prefixes=(';', '#', '/', 'WINE'), allow_no_value=True)
    reg.optionxform = str
    reg.read(os.path.join(wine_pfx, 'user.reg'))
    return reg


def get_shell_folders(registry, wine_pfx):
    folders = dict()
    for k, v in registry['Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Explorer\\\\Shell Folders'].items():
        path_cleaned = v.strip('"').strip().replace('\\\\', '/').replace('C:/', '')
        folders[k.strip('"').strip()] = os.path.join(wine_pfx, 'drive_c', path_cleaned)
    return folders
