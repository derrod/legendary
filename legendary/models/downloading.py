# coding: utf-8


class DownloaderTask:
    def __init__(self, url=None, chunk_guid=None, shm=None, kill=False):
        self.url = url
        self.guid = chunk_guid
        self.shm = shm
        self.kill = kill


class DownloaderTaskResult:
    def __init__(self, success, chunk_guid, shm, url, size=None,
                 compressed_size=None, time_delta=None):
        self.success = success
        self.shm = shm
        self.size = size
        self.compressed_size = compressed_size
        self.guid = chunk_guid
        self.time_delta = time_delta
        self.url = url


class WriterTask:
    """
    Writing task for FileWorker, including some metadata that is required.
    """

    def __init__(self, filename, chunk_offset=0, chunk_size=0, chunk_guid=None, close=False,
                 shared_memory=None, cache_file='', old_file='', release_memory=False, rename=False,
                 empty=False, kill=False, delete=False, old_filename='', fopen=False):
        self.filename = filename
        self.empty = empty
        self.shm = shared_memory
        self.chunk_offset = chunk_offset
        self.chunk_size = chunk_size
        self.chunk_guid = chunk_guid
        self.release_memory = release_memory

        # reading from a cached chunk instead of memory
        self.cache_file = cache_file
        self.old_file = old_file
        self.open = fopen
        self.close = close
        self.delete = delete
        self.rename = rename
        self.old_filename = old_filename

        self.kill = kill  # final task for worker (quit)


class WriterTaskResult:
    def __init__(self, success, filename='', chunk_guid='',
                 release_memory=False, shm=None, size=0,
                 kill=False, closed=False, time_delta=None):
        self.success = success
        self.filename = filename
        self.chunk_guid = chunk_guid
        self.release_memory = release_memory
        self.shm = shm
        self.size = size
        self.kill = kill
        self.closed = closed
        self.time_delta = time_delta


class UIUpdate:
    """
    Status update object sent from the manager to the CLI/GUI to update status indicators
    """

    def __init__(self, progress, download_speed, write_speed, read_speed,
                 memory_usage, current_filename=''):
        self.progress = progress
        self.download_speed = download_speed
        self.write_speed = write_speed
        self.read_speed = read_speed
        self.current_filename = current_filename
        self.memory_usage = memory_usage


class SharedMemorySegment:
    """
    Segment of the shared memory used for one Chunk
    """

    def __init__(self, offset=0, end=1024 * 1024):
        self.offset = offset
        self.end = end

    @property
    def size(self):
        return self.end - self.offset


class ChunkTask:
    def __init__(self, chunk_guid, chunk_offset=0, chunk_size=0, cleanup=False, chunk_file=None):
        """
        Download amanger chunk task

        :param chunk_guid: GUID of chunk
        :param cleanup: whether or not this chunk can be removed from disk/memory after it has been written
        :param chunk_offset: Offset into file or shared memory
        :param chunk_size: Size to read from file or shared memory
        :param chunk_file: Either cache or existing game file this chunk is read from if not using shared memory
        """
        self.chunk_guid = chunk_guid
        self.cleanup = cleanup
        self.chunk_offset = chunk_offset
        self.chunk_size = chunk_size
        self.chunk_file = chunk_file


class FileTask:
    def __init__(self, filename, delete=False, empty=False, fopen=False, close=False,
                 rename=False, temporary_filename=None):
        """
        Download manager Task for a file

        :param filename: name of the file
        :param delete: if this is a file to be deleted, if rename is true, delete filename before renaming
        :param empty: if this is an empty file that just needs to be "touch"-ed (may not have chunk tasks)

        :param temporary_filename: If rename is true: Filename to rename from.
        """
        self.filename = filename
        self.delete = delete
        self.empty = empty
        self.open = fopen
        self.close = close
        self.rename = rename
        self.temporary_filename = temporary_filename

    @property
    def is_reusing(self):
        return self.temporary_filename is not None


class AnalysisResult:
    def __init__(self):
        self.dl_size = 0
        self.uncompressed_dl_size = 0
        self.install_size = 0
        self.reuse_size = 0
        self.biggest_file_size = 0
        self.unchanged_size = 0
        self.biggest_chunk = 0
        self.min_memory = 0
        self.num_chunks = 0
        self.num_chunks_cache = 0
        self.num_files = 0
        self.removed = 0
        self.added = 0
        self.changed = 0
        self.unchanged = 0
        self.manifest_comparison = None


class ConditionCheckResult:
    """Result object used in Core to identify problems that would prevent an installation from succeeding"""
    def __init__(self, failures=None, warnings=None):
        self.failures = failures
        self.warnings = warnings
