# coding: utf-8

from dataclasses import dataclass
from typing import Union

from .manifest import ManifestComparison


@dataclass
class SharedMemorySegment:
    """
    Segment of the shared memory used for one Chunk
    """
    offset: int = 0
    end: int = 1024 * 1024

    @property
    def size(self):
        return self.end - self.offset


@dataclass
class DownloaderTask:
    """
    Task submitted to the download worker
    """
    url: Union[str, None] = None
    chunk_guid: Union[int, None] = None
    shm: Union[SharedMemorySegment, None] = None
    kill: bool = False


@dataclass
class DownloaderTaskResult:
    """
    Result of DownloaderTask provided by download workers
    """
    success: bool
    chunk_guid: int
    shm: SharedMemorySegment
    url: str
    size: Union[int, None] = None
    compressed_size: Union[int, None] = None
    time_delta: Union[int, None] = None


@dataclass
class ChunkTask:
    """
    A task describing a single read of a (partial) chunk from memory or an existing file
    """
    chunk_guid: int
    chunk_offset: int = 0
    chunk_size: int = 0
    # Whether this chunk can be removed from memory/disk after having been written
    cleanup: bool = False
    # Path to the file the chunk is read from (if not from memory)
    chunk_file: Union[str, None] = None


@dataclass
class FileTask:
    """
    A task describing some operation on the filesystem
    """
    filename: str
    # just create a 0-byte file
    empty: bool = False
    open: bool = False
    close: bool = False
    rename: bool = False
    # Deletes the file, if rename is true, this will remove an existing file with the target name
    delete: bool = False
    silent: bool = False
    # If rename is true, this is the name of the file to be renamed
    temporary_filename: Union[str, None] = None

    @property
    def is_reusing(self):
        return self.temporary_filename is not None


@dataclass
class WriterTask:
    """
    Task for FileWriter worker process, describing an operation on the filesystem
    """
    filename: str

    chunk_offset: int = 0
    chunk_size: int = 0
    chunk_guid: Union[int, None] = None

    # Just create an empty file
    empty: bool = False
    # Whether shared memory segment shall be released back to the pool on completion
    release_memory: bool = False
    shared_memory: Union[SharedMemorySegment, None] = None

    # File to read old chunk from, disk chunk cache or old game file
    old_file: Union[str, None] = None
    cache_file: Union[str, None] = None

    open: bool = False
    close: bool = False
    delete: bool = False
    # Do not log deletion failures
    silent: bool = False

    rename: bool = False
    # Filename to rename from
    old_filename: Union[str, None] = None

    # Instruct worker to terminate
    kill: bool = False


@dataclass
class WriterTaskResult:
    """
    Result from the FileWriter worker
    """
    success: bool
    filename: Union[str, None] = None
    size: int = 0
    chunk_guid: Union[int, None] = None

    shared_memory: Union[SharedMemorySegment, None] = None
    release_memory: bool = False
    closed: bool = False
    time_delta: Union[float, None] = None

    # Worker terminated, instructs results handler to also stop
    kill: bool = False


@dataclass
class UIUpdate:
    """
    Status update object sent from the manager to the CLI/GUI to update status indicators
    """
    progress: float
    download_speed: float
    write_speed: float
    read_speed: float
    memory_usage: float
    current_filename: Union[str, None] = None


@dataclass
class AnalysisResult:
    """
    Result of processing a manifest for downloading
    """
    dl_size: int = 0
    uncompressed_dl_size: int = 0
    install_size: int = 0
    reuse_size: int = 0
    biggest_file_size: int = 0
    unchanged_size: int = 0
    biggest_chunk: int = 0
    min_memory: int = 0
    num_chunks: int = 0
    num_chunks_cache: int = 0
    num_files: int = 0
    removed: int = 0
    added: int = 0
    changed: int = 0
    unchanged: int = 0
    manifest_comparison: Union[ManifestComparison, None] = None


@dataclass
class ConditionCheckResult:
    """
    Result of install condition checks
    """
    failures: Union[list, None] = None
    warnings: Union[list, None] = None
