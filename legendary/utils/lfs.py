# coding: utf-8

import os
import shutil
import hashlib
import logging

from typing import List, Iterator

from legendary.models.game import VerifyResult

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


def validate_files(base_path: str, filelist: List[tuple], hash_type='sha1') -> Iterator[tuple]:
    """
    Validates the files in filelist in path against the provided hashes

    :param base_path: path in which the files are located
    :param filelist: list of tuples in format (path, hash [hex])
    :param hash_type: (optional) type of hash, default is sha1
    :return: list of files that failed hash check
    """

    if not filelist:
        raise ValueError('No files to validate!')

    if not os.path.exists(base_path):
        raise OSError('Path does not exist')

    for file_path, file_hash in filelist:
        full_path = os.path.join(base_path, file_path)
        # logger.debug(f'Checking "{file_path}"...')

        if not os.path.exists(full_path):
            yield VerifyResult.FILE_MISSING, file_path, ''
            continue

        try:
            with open(full_path, 'rb') as f:
                real_file_hash = hashlib.new(hash_type)
                while chunk := f.read(1024*1024):
                    real_file_hash.update(chunk)

                result_hash = real_file_hash.hexdigest()
                if file_hash != result_hash:
                    yield VerifyResult.HASH_MISMATCH, file_path, result_hash
                else:
                    yield VerifyResult.HASH_MATCH, file_path, result_hash
        except Exception as e:
            logger.fatal(f'Could not verify "{file_path}"; opening failed with: {e!r}')
            yield VerifyResult.OTHER_ERROR, file_path, ''


def clean_filename(filename):
    return ''.join(i for i in filename if i not in '<>:"/\\|?*')
