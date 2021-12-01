# coding: utf-8

import os
import requests
import time
import logging

from logging.handlers import QueueHandler
from multiprocessing import Process
from multiprocessing.shared_memory import SharedMemory
from queue import Empty

from legendary.models.chunk import Chunk
from legendary.models.downloading import (
    DownloaderTask, DownloaderTaskResult,
    WriterTask, WriterTaskResult,
    TerminateWorkerTask, TaskFlags
)


class DLWorker(Process):
    def __init__(self, name, queue, out_queue, shm, max_retries=7,
                 logging_queue=None, dl_timeout=10):
        super().__init__(name=name)
        self.q = queue
        self.o_q = out_queue
        self.session = requests.session()
        self.session.headers.update({
            'User-Agent': 'EpicGamesLauncher/11.0.1-14907503+++Portal+Release-Live Windows/10.0.19041.1.256.64bit'
        })
        self.max_retries = max_retries
        self.shm = SharedMemory(name=shm)
        self.log_level = logging.getLogger().level
        self.logging_queue = logging_queue
        self.dl_timeout = float(dl_timeout) if dl_timeout else 10.0

    def run(self):
        # we have to fix up the logger before we can start
        _root = logging.getLogger()
        _root.handlers = []
        _root.addHandler(QueueHandler(self.logging_queue))

        logger = logging.getLogger(self.name)
        logger.setLevel(self.log_level)
        logger.debug(f'Download worker reporting for duty!')

        empty = False
        while True:
            try:
                job: DownloaderTask = self.q.get(timeout=10.0)
                empty = False
            except Empty:
                if not empty:
                    logger.debug(f'Queue Empty, waiting for more...')
                empty = True
                continue

            if isinstance(job, TerminateWorkerTask):  # let worker die
                logger.debug(f'Worker received termination signal, shutting down...')
                break

            tries = 0
            compressed = 0
            chunk = None

            try:
                while tries < self.max_retries:
                    # retry once immediately, otherwise do exponential backoff
                    if tries > 1:
                        sleep_time = 2**(tries-1)
                        logger.info(f'Sleeping {sleep_time} seconds before retrying.')
                        time.sleep(sleep_time)

                    # print('Downloading', job.url)
                    logger.debug(f'Downloading {job.url}')

                    try:
                        r = self.session.get(job.url, timeout=self.dl_timeout)
                        r.raise_for_status()
                    except Exception as e:
                        logger.warning(f'Chunk download for {job.chunk_guid} failed: ({e!r}), retrying...')
                        continue

                    if r.status_code != 200:
                        logger.warning(f'Chunk download for {job.chunk_guid} failed: status {r.status_code}, retrying...')
                        continue
                    else:
                        compressed = len(r.content)
                        chunk = Chunk.read_buffer(r.content)
                        break
                else:
                    raise TimeoutError('Max retries reached')
            except Exception as e:
                logger.error(f'Job for {job.chunk_guid} failed with: {e!r}, fetching next one...')
                # add failed job to result queue to be requeued
                self.o_q.put(DownloaderTaskResult(success=False, **job.__dict__))
            except KeyboardInterrupt:
                logger.warning('Immediate exit requested, quitting...')
                break

            if not chunk:
                logger.warning(f'Chunk somehow None?')
                self.o_q.put(DownloaderTaskResult(success=False, **job.__dict__))
                continue

            # decompress stuff
            try:
                size = len(chunk.data)
                if size > job.shm.size:
                    logger.fatal(f'Downloaded chunk is longer than SharedMemorySegment!')

                self.shm.buf[job.shm.offset:job.shm.offset + size] = bytes(chunk.data)
                del chunk
                self.o_q.put(DownloaderTaskResult(success=True, size_decompressed=size,
                                                  size_downloaded=compressed, **job.__dict__))
            except Exception as e:
                logger.warning(f'Job for {job.chunk_guid} failed with: {e!r}, fetching next one...')
                self.o_q.put(DownloaderTaskResult(success=False, **job.__dict__))
                continue
            except KeyboardInterrupt:
                logger.warning('Immediate exit requested, quitting...')
                break

        self.shm.close()


class FileWorker(Process):
    def __init__(self, queue, out_queue, base_path, shm, cache_path=None, logging_queue=None):
        super().__init__(name='FileWorker')
        self.q = queue
        self.o_q = out_queue
        self.base_path = base_path
        self.cache_path = cache_path if cache_path else os.path.join(base_path, '.cache')
        self.shm = SharedMemory(name=shm)
        self.log_level = logging.getLogger().level
        self.logging_queue = logging_queue

    def run(self):
        # we have to fix up the logger before we can start
        _root = logging.getLogger()
        _root.handlers = []
        _root.addHandler(QueueHandler(self.logging_queue))

        logger = logging.getLogger(self.name)
        logger.setLevel(self.log_level)
        logger.debug(f'Download worker reporting for duty!')

        last_filename = ''
        current_file = None

        while True:
            try:
                try:
                    j: WriterTask = self.q.get(timeout=10.0)
                except Empty:
                    logger.warning('Writer queue empty!')
                    continue

                if isinstance(j, TerminateWorkerTask):
                    if current_file:
                        current_file.close()
                    logger.debug(f'Worker received termination signal, shutting down...')
                    # send termination task to results halnder as well
                    self.o_q.put(TerminateWorkerTask())
                    break

                # make directories if required
                path = os.path.split(j.filename)[0]
                if not os.path.exists(os.path.join(self.base_path, path)):
                    os.makedirs(os.path.join(self.base_path, path))

                full_path = os.path.join(self.base_path, j.filename)

                if j.flags & TaskFlags.CREATE_EMPTY_FILE:  # just create an empty file
                    open(full_path, 'a').close()
                    self.o_q.put(WriterTaskResult(success=True, **j.__dict__))
                    continue
                elif j.flags & TaskFlags.OPEN_FILE:
                    if current_file:
                        logger.warning(f'Opening new file {j.filename} without closing previous! {last_filename}')
                        current_file.close()

                    current_file = open(full_path, 'wb')
                    last_filename = j.filename

                    self.o_q.put(WriterTaskResult(success=True, **j.__dict__))
                    continue
                elif j.flags & TaskFlags.CLOSE_FILE:
                    if current_file:
                        current_file.close()
                        current_file = None
                    else:
                        logger.warning(f'Asking to close file that is not open: {j.filename}')

                    self.o_q.put(WriterTaskResult(success=True, **j.__dict__))
                    continue
                elif j.flags & TaskFlags.RENAME_FILE:
                    if current_file:
                        logger.warning('Trying to rename file without closing first!')
                        current_file.close()
                        current_file = None
                    if j.flags & TaskFlags.DELETE_FILE:
                        try:
                            os.remove(full_path)
                        except OSError as e:
                            logger.error(f'Removing file failed: {e!r}')
                            self.o_q.put(WriterTaskResult(success=False, **j.__dict__))
                            continue

                    try:
                        os.rename(os.path.join(self.base_path, j.old_file), full_path)
                    except OSError as e:
                        logger.error(f'Renaming file failed: {e!r}')
                        self.o_q.put(WriterTaskResult(success=False, **j.__dict__))
                        continue

                    self.o_q.put(WriterTaskResult(success=True, **j.__dict__))
                    continue
                elif j.flags & TaskFlags.DELETE_FILE:
                    if current_file:
                        logger.warning('Trying to delete file without closing first!')
                        current_file.close()
                        current_file = None

                    try:
                        os.remove(full_path)
                    except OSError as e:
                        if not j.flags & TaskFlags.SILENT:
                            logger.error(f'Removing file failed: {e!r}')

                    self.o_q.put(WriterTaskResult(success=True, **j.__dict__))
                    continue
                elif j.flags & TaskFlags.MAKE_EXECUTABLE:
                    if current_file:
                        logger.warning('Trying to chmod file without closing first!')
                        current_file.close()
                        current_file = None

                    try:
                        st = os.stat(full_path)
                        os.chmod(full_path, st.st_mode | 0o111)
                    except OSError as e:
                        if not j.flags & TaskFlags.SILENT:
                            logger.error(f'chmod\'ing file failed: {e!r}')

                    self.o_q.put(WriterTaskResult(success=True, **j.__dict__))
                    continue

                try:
                    if j.shared_memory:
                        shm_offset = j.shared_memory.offset + j.chunk_offset
                        shm_end = shm_offset + j.chunk_size
                        current_file.write(self.shm.buf[shm_offset:shm_end].tobytes())
                    elif j.cache_file:
                        with open(os.path.join(self.cache_path, j.cache_file), 'rb') as f:
                            if j.chunk_offset:
                                f.seek(j.chunk_offset)
                            current_file.write(f.read(j.chunk_size))
                    elif j.old_file:
                        with open(os.path.join(self.base_path, j.old_file), 'rb') as f:
                            if j.chunk_offset:
                                f.seek(j.chunk_offset)
                            current_file.write(f.read(j.chunk_size))
                except Exception as e:
                    logger.warning(f'Something in writing a file failed: {e!r}')
                    self.o_q.put(WriterTaskResult(success=False, size=j.chunk_size, **j.__dict__))
                else:
                    self.o_q.put(WriterTaskResult(success=True, size=j.chunk_size, **j.__dict__))
            except Exception as e:
                logger.warning(f'Job {j.filename} failed with: {e!r}, fetching next one...')
                self.o_q.put(WriterTaskResult(success=False, **j.__dict__))

                try:
                    if current_file:
                        current_file.close()
                        current_file = None
                except Exception as e:
                    logger.error(f'Closing file after error failed: {e!r}')
            except KeyboardInterrupt:
                logger.warning('Immediate exit requested, quitting...')
                if current_file:
                    current_file.close()
                return
