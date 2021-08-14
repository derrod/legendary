# coding: utf-8

from enum import Flag, auto
from dataclasses import dataclass
from typing import Optional

from .manifest import ManifestComparison


@dataclass
class SharedMemorySegment:
    """
    Segment of the shared memory used for one Chunk
    """
    offset: int
    end: int

    @property
    def size(self):
        return self.end - self.offset


@dataclass
class DownloaderTask:
    """
    Task submitted to the download worker
    """
    url: str
    chunk_guid: int
    shm: SharedMemorySegment


@dataclass
class DownloaderTaskResult(DownloaderTask):
    """
    Result of DownloaderTask provided by download workers
    """
    success: bool
    size_downloaded: Optional[int] = None
    size_decompressed: Optional[int] = None


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
    chunk_file: Optional[str] = None


class TaskFlags(Flag):
    NONE = 0
    OPEN_FILE = auto()
    CLOSE_FILE = auto()
    DELETE_FILE = auto()
    CREATE_EMPTY_FILE = auto()
    RENAME_FILE = auto()
    RELEASE_MEMORY = auto()
    SILENT = auto()


@dataclass
class FileTask:
    """
    A task describing some operation on the filesystem
    """
    filename: str
    flags: TaskFlags
    # If rename is true, this is the name of the file to be renamed
    old_file: Optional[str] = None


@dataclass
class WriterTask:
    """
    Task for FileWriter worker process, describing an operation on the filesystem
    """
    filename: str
    flags: TaskFlags

    chunk_offset: int = 0
    chunk_size: int = 0
    chunk_guid: Optional[int] = None

    # Whether shared memory segment shall be released back to the pool on completion
    shared_memory: Optional[SharedMemorySegment] = None

    # File to read old chunk from, disk chunk cache or old game file
    old_file: Optional[str] = None
    cache_file: Optional[str] = None


@dataclass
class WriterTaskResult(WriterTask):
    """
    Result from the FileWriter worker
    """
    success: bool = False
    size: int = 0


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
    current_filename: Optional[str] = None


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
    manifest_comparison: Optional[ManifestComparison] = None


@dataclass
class ConditionCheckResult:
    """
    Result of install condition checks
    """
    failures: Optional[set] = None
    warnings: Optional[set] = None


class TerminateWorkerTask:
    """
    Universal task to signal a worker to exit
    """
    pass

