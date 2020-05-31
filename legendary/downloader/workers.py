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
from legendary.models.downloading import DownloaderTaskResult, WriterTaskResult


class DLWorker(Process):
    def __init__(self, name, queue, out_queue, shm, max_retries=5,
                 logging_queue=None, dl_timeout=10):
        super().__init__(name=name)
        self.q = queue
        self.o_q = out_queue
        self.session = requests.session()
        self.session.headers.update({
            'User-Agent': 'EpicGamesLauncher/10.16.1-13343695+++Portal+Release-Live Windows/10.0.18363.1.256.64bit'
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
                job = self.q.get(timeout=10.0)
                empty = False
            except Empty:
                if not empty:
                    logger.debug(f'Queue Empty, waiting for more...')
                empty = True
                continue

            if job.kill:  # let worker die
                logger.debug(f'Worker received kill signal, shutting down...')
                break

            tries = 0
            dl_start = dl_end = 0
            compressed = 0
            chunk = None

            try:
                while tries < self.max_retries:
                    # print('Downloading', job.url)
                    logger.debug(f'Downloading {job.url}')
                    dl_start = time.time()

                    try:
                        r = self.session.get(job.url, timeout=self.dl_timeout)
                        r.raise_for_status()
                    except Exception as e:
                        logger.warning(f'Chunk download for {job.guid} failed: ({e!r}), retrying...')
                        continue

                    dl_end = time.time()
                    if r.status_code != 200:
                        logger.warning(f'Chunk download for {job.guid} failed: status {r.status_code}, retrying...')
                        continue
                    else:
                        compressed = len(r.content)
                        chunk = Chunk.read_buffer(r.content)
                        break
                else:
                    raise TimeoutError('Max retries reached')
            except Exception as e:
                logger.error(f'Job for {job.guid} failed with: {e!r}, fetching next one...')
                # add failed job to result queue to be requeued
                self.o_q.put(DownloaderTaskResult(success=False, chunk_guid=job.guid, shm=job.shm, url=job.url))
            except KeyboardInterrupt:
                logger.warning('Immediate exit requested, quitting...')
                break

            if not chunk:
                logger.warning(f'Chunk somehow None?')
                self.o_q.put(DownloaderTaskResult(success=False, chunk_guid=job.guid, shm=job.shm, url=job.url))
                continue

            # decompress stuff
            try:
                size = len(chunk.data)
                if size > job.shm.size:
                    logger.fatal(f'Downloaded chunk is longer than SharedMemorySegment!')

                self.shm.buf[job.shm.offset:job.shm.offset + size] = bytes(chunk.data)
                del chunk
                self.o_q.put(DownloaderTaskResult(success=True, chunk_guid=job.guid, shm=job.shm,
                                                  url=job.url, size=size, compressed_size=compressed,
                                                  time_delta=dl_end - dl_start))
            except Exception as e:
                logger.warning(f'Job for {job.guid} failed with: {e!r}, fetching next one...')
                self.o_q.put(DownloaderTaskResult(success=False, chunk_guid=job.guid, shm=job.shm, url=job.url))
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
                    j = self.q.get(timeout=10.0)
                except Empty:
                    logger.warning('Writer queue empty!')
                    continue

                if j.kill:
                    if current_file:
                        current_file.close()
                    self.o_q.put(WriterTaskResult(success=True, kill=True))
                    break

                # make directories if required
                path = os.path.split(j.filename)[0]
                if not os.path.exists(os.path.join(self.base_path, path)):
                    os.makedirs(os.path.join(self.base_path, path))

                full_path = os.path.join(self.base_path, j.filename)

                if j.empty:  # just create an empty file
                    open(full_path, 'a').close()
                    self.o_q.put(WriterTaskResult(success=True, filename=j.filename))
                    continue
                elif j.open:
                    if current_file:
                        logger.warning(f'Opening new file {j.filename} without closing previous! {last_filename}')
                        current_file.close()

                    current_file = open(full_path, 'wb')
                    last_filename = j.filename

                    self.o_q.put(WriterTaskResult(success=True, filename=j.filename))
                    continue
                elif j.close:
                    if current_file:
                        current_file.close()
                        current_file = None
                    else:
                        logger.warning(f'Asking to close file that is not open: {j.filename}')

                    self.o_q.put(WriterTaskResult(success=True, filename=j.filename, closed=True))
                    continue
                elif j.rename:
                    if current_file:
                        logger.warning('Trying to rename file without closing first!')
                        current_file.close()
                        current_file = None
                    if j.delete:
                        try:
                            os.remove(full_path)
                        except OSError as e:
                            logger.error(f'Removing file failed: {e!r}')
                            self.o_q.put(WriterTaskResult(success=False, filename=j.filename))
                            continue

                    try:
                        os.rename(os.path.join(self.base_path, j.old_filename), full_path)
                    except OSError as e:
                        logger.error(f'Renaming file failed: {e!r}')
                        self.o_q.put(WriterTaskResult(success=False, filename=j.filename))
                        continue

                    self.o_q.put(WriterTaskResult(success=True, filename=j.filename))
                    continue
                elif j.delete:
                    if current_file:
                        logger.warning('Trying to delete file without closing first!')
                        current_file.close()
                        current_file = None

                    try:
                        os.remove(full_path)
                    except OSError as e:
                        logger.error(f'Removing file failed: {e!r}')

                    self.o_q.put(WriterTaskResult(success=True, filename=j.filename))
                    continue

                pre_write = post_write = 0

                try:
                    if j.shm:
                        pre_write = time.time()
                        shm_offset = j.shm.offset + j.chunk_offset
                        shm_end = shm_offset + j.chunk_size
                        current_file.write(self.shm.buf[shm_offset:shm_end].tobytes())
                        post_write = time.time()
                    elif j.cache_file:
                        pre_write = time.time()
                        with open(os.path.join(self.cache_path, j.cache_file), 'rb') as f:
                            if j.chunk_offset:
                                f.seek(j.chunk_offset)
                            current_file.write(f.read(j.chunk_size))
                        post_write = time.time()
                    elif j.old_file:
                        pre_write = time.time()
                        with open(os.path.join(self.base_path, j.old_file), 'rb') as f:
                            if j.chunk_offset:
                                f.seek(j.chunk_offset)
                            current_file.write(f.read(j.chunk_size))
                        post_write = time.time()
                except Exception as e:
                    logger.warning(f'Something in writing a file failed: {e!r}')
                    self.o_q.put(WriterTaskResult(success=False, filename=j.filename,
                                                  chunk_guid=j.chunk_guid,
                                                  release_memory=j.release_memory,
                                                  shm=j.shm, size=j.chunk_size,
                                                  time_delta=post_write-pre_write))
                else:
                    self.o_q.put(WriterTaskResult(success=True, filename=j.filename,
                                                  chunk_guid=j.chunk_guid,
                                                  release_memory=j.release_memory,
                                                  shm=j.shm, size=j.chunk_size,
                                                  time_delta=post_write-pre_write))
            except Exception as e:
                logger.warning(f'Job {j.filename} failed with: {e!r}, fetching next one...')
                self.o_q.put(WriterTaskResult(success=False, filename=j.filename, chunk_guid=j.chunk_guid))

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
