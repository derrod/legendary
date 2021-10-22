import configparser
import logging
import os

logger = logging.getLogger('WineHelpers')


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


def case_insensitive_path_search(path):
    """
    Attempts to find a path case-insensitively
    """
    # Legendary's save path resolver always returns absolute paths, so this is not as horrible as it looks
    path_parts = path.replace('\\', '/').split('/')
    path_parts[0] = '/'
    # filter out empty parts
    path_parts = [i for i in path_parts if i]

    # attempt to find lowest level directory that exists case-sensitively
    longest_path = ''
    remaining_parts = []
    for i in range(len(path_parts), 0, -1):
        if os.path.exists(os.path.join(*path_parts[:i])):
            longest_path = path_parts[:i]
            remaining_parts = path_parts[i:]
            break
    logger.debug(f'Longest valid path: {longest_path}')
    logger.debug(f'Remaining parts: {remaining_parts}')

    # Iterate over remaining parts, find matching directories case-insensitively
    still_remaining = []
    for idx, part in enumerate(remaining_parts):
        for item in os.listdir(os.path.join(*longest_path)):
            if not os.path.isdir(os.path.join(*longest_path, item)):
                continue
            if item.lower() == part.lower():
                longest_path.append(item)
                break
        else:
            # once we stop finding parts break
            still_remaining = remaining_parts[idx-1:]
            break

    logger.debug(f'New longest path: {longest_path}')
    logger.debug(f'Still unresolved: {still_remaining}')
    final_path = os.path.join(*longest_path, *still_remaining)
    logger.debug('Final path:', final_path)
    return os.path.realpath(final_path)
