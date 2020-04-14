#!/usr/bin/env python
# coding: utf-8

import os
import shutil
import hashlib
import logging

from typing import List

logger = logging.getLogger('LFS Utils')


def delete_folder(path: str, recursive=True) -> bool:
    try:
        logger.debug(f'Deleting "{path}", recursive={recursive}...')
        if not recursive:
            os.removedirs(path)
        else:
            shutil.rmtree(path)
    except Exception as e:
        logger.error(f'Failed deleting files with {e!r}')
        return False
    else:
        return True


def validate_files(base_path: str, filelist: List[tuple], hash_type='sha1') -> list:
    """
    Validates the files in filelist in path against the provided hashes

    :param base_path: path in which the files are located
    :param filelist: list of tuples in format (path, hash [hex])
    :param hash_type: (optional) type of hash, default is sha1
    :return: list of files that failed hash check
    """

    failed = list()

    if not os.path.exists(base_path):
        logger.error('Path does not exist!')
        failed.extend(i[0] for i in filelist)
        return failed

    if not filelist:
        logger.info('No files to validate')
        return failed

    for file_path, file_hash in filelist:
        full_path = os.path.join(base_path, file_path)
        logger.debug(f'Checking "{file_path}"...')

        if not os.path.exists(full_path):
            logger.warning(f'File "{full_path}" does not exist!')
            failed.append(file_path)
            continue

        with open(full_path, 'rb') as f:
            real_file_hash = hashlib.new(hash_type)
            while chunk := f.read(8192):
                real_file_hash.update(chunk)

            if file_hash != real_file_hash.hexdigest():
                logger.error(f'Hash for "{full_path}" does not match!')
                failed.append(file_path)

    return failed


def clean_filename(filename):
    return ''.join(i for i in filename if i not in '<>:"/\\|?*')
