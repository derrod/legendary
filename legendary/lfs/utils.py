# coding: utf-8

import os
import shutil
import hashlib
import json
import logging

from pathlib import Path
from sys import stdout
from time import perf_counter
from typing import List, Iterator

from filelock import FileLock

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


def delete_filelist(path: str, filenames: List[str],
                    delete_root_directory: bool = False,
                    silent: bool = False) -> bool:
    dirs = set()
    no_error = True

    # delete all files that were installed
    for filename in filenames:
        _dir, _fn = os.path.split(filename)
        if _dir:
            dirs.add(_dir)

        try:
            os.remove(os.path.join(path, _dir, _fn))
        except Exception as e:
            if not silent:
                logger.error(f'Failed deleting file {filename} with {e!r}')
            no_error = False

    # add intermediate directories that would have been missed otherwise
    for _dir in sorted(dirs):
        head, _ = os.path.split(_dir)
        while head:
            dirs.add(head)
            head, _ = os.path.split(head)

    # remove all directories
    for _dir in sorted(dirs, key=len, reverse=True):
        try:
            os.rmdir(os.path.join(path, _dir))
        except FileNotFoundError:
            # directory has already been deleted, ignore that
            continue
        except Exception as e:
            if not silent:
                logger.error(f'Failed removing directory "{_dir}" with {e!r}')
            no_error = False

    if delete_root_directory:
        try:
            os.rmdir(path)
        except Exception as e:
            if not silent:
                logger.error(f'Removing game directory failed with {e!r}')

    return no_error


def validate_files(base_path: str, filelist: List[tuple], hash_type='sha1',
                   large_file_threshold=1024 * 1024 * 512) -> Iterator[tuple]:
    """
    Validates the files in filelist in path against the provided hashes

    :param base_path: path in which the files are located
    :param filelist: list of tuples in format (path, hash [hex])
    :param hash_type: (optional) type of hash, default is sha1
    :param large_file_threshold: (optional) threshold for large files, default is 512 MiB
    :return: yields tuples in format (VerifyResult, path, hash [hex], bytes read)
    """

    if not filelist:
        raise ValueError('No files to validate!')

    if not os.path.exists(base_path):
        raise OSError('Path does not exist')

    for file_path, file_hash in filelist:
        full_path = os.path.join(base_path, file_path)
        # logger.debug(f'Checking "{file_path}"...')

        if not os.path.exists(full_path):
            yield VerifyResult.FILE_MISSING, file_path, '', 0
            continue

        show_progress = False
        interval = 0
        speed = 0.0
        start_time = 0.0

        try:
            _size = os.path.getsize(full_path)
            if _size > large_file_threshold:
                # enable progress indicator and go to new line
                stdout.write('\n')
                show_progress = True
                interval = (_size / (1024 * 1024)) // 100
                start_time = perf_counter()

            with open(full_path, 'rb') as f:
                real_file_hash = hashlib.new(hash_type)
                i = 0
                while chunk := f.read(1024*1024):
                    real_file_hash.update(chunk)
                    if show_progress and i % interval == 0:
                        pos = f.tell()
                        perc = (pos / _size) * 100
                        speed = pos / 1024 / 1024 / (perf_counter() - start_time)
                        stdout.write(f'\r=> Verifying large file "{file_path}": {perc:.0f}% '
                                     f'({pos / 1024 / 1024:.1f}/{_size / 1024 / 1024:.1f} MiB) '
                                     f'[{speed:.1f} MiB/s]\t')
                        stdout.flush()
                    i += 1

                if show_progress:
                    stdout.write(f'\r=> Verifying large file "{file_path}": 100% '
                                 f'({_size / 1024 / 1024:.1f}/{_size / 1024 / 1024:.1f} MiB) '
                                 f'[{speed:.1f} MiB/s]\t\n')

                result_hash = real_file_hash.hexdigest()
                if file_hash != result_hash:
                    yield VerifyResult.HASH_MISMATCH, file_path, result_hash, f.tell()
                else:
                    yield VerifyResult.HASH_MATCH, file_path, result_hash, f.tell()
        except Exception as e:
            logger.fatal(f'Could not verify "{file_path}"; opening failed with: {e!r}')
            yield VerifyResult.OTHER_ERROR, file_path, '', 0


def clean_filename(filename):
    return ''.join(i for i in filename if i not in '<>:"/\\|?*')


def get_dir_size(path):
    return sum(f.stat().st_size for f in Path(path).glob('**/*') if f.is_file())


class LockedJSONData(FileLock):
    def __init__(self, lock_file: str):
        super().__init__(lock_file + '.lock')

        self._file_path = lock_file
        self._data = None
        self._initial_data = None

    def __enter__(self):
        super().__enter__()

        if os.path.exists(self._file_path):
            with open(self._file_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
                self._initial_data = self._data
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)

        if self._data != self._initial_data:
            if self._data is not None:
                with open(self._file_path, 'w', encoding='utf-8') as f:
                    json.dump(self._data, f, indent=2, sort_keys=True)
            else:
                if os.path.exists(self._file_path):
                    os.remove(self._file_path)

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, new_data):
        if new_data is None:
            raise ValueError('Invalid new data, use clear() explicitly to reset file data')
        self._data = new_data

    def clear(self):
        self._data = None
