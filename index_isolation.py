"""Consistent, write-denied Windows snapshots. Never opens Chroma on the source.

Close index users before running. On unsupported platforms or a sharing conflict,
fail closed; an unchecked directory copy is never used as a fallback.
"""

from contextlib import contextmanager, ExitStack
import ctypes
import hashlib
import os
from pathlib import Path
import shutil

from index_paths import disjoint

_guarded_path = None


def require_isolated_index():
    """Evaluation entry points must run in an SDK-guarded snapshot worker."""
    from index_paths import resolve_index_path
    if _guarded_path is None or resolve_index_path() != _guarded_path:
        from rag_errors import RAGError
        raise RAGError('index_isolation', 'retrieval')


def inventory(root):
    root = Path(root).absolute()
    files, directories = [], []
    for parent in (root, *root.parents):
        if parent.exists() and getattr(parent.lstat(), "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Snapshot paths must not contain reparse points or links")
    for parent, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(parent) / name
            if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
                raise RuntimeError("Snapshot contains a link/reparse point")
            (directories if name in dirs else files).append(path.relative_to(root).as_posix())
    return sorted(files), sorted(directories)


def open_write_denied(path):
    """Read handle denying WRITE and DELETE sharing, including existing writers."""
    if os.name != "nt":
        raise RuntimeError("Consistent snapshot locking is implemented for Windows only")
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # GENERIC_READ, FILE_SHARE_READ only, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL.
    handle = create(str(Path(path).resolve()), 0x80000000, 0x1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise RuntimeError(
            "Cannot establish a quiescent snapshot. Close all index users and retry "
            f"(Windows error {ctypes.get_last_error()})."
        )
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        close(handle)
        raise
    return os.fdopen(descriptor, "rb")


def tree_hashes(root):
    files, _ = inventory(root)
    result = {}
    for name in files:
        with (Path(root) / name).open("rb") as file:
            result[name] = hashlib.file_digest(file, "sha256").hexdigest()
    return result


class LockedSnapshot:
    def __init__(self, root, files, directories, handles):
        self.root, self.files, self.directories, self.handles = root, files, directories, handles

    def hashes(self):
        if inventory(self.root) != (self.files, self.directories):
            raise RuntimeError("Source inventory changed during snapshot; refusing to continue")
        result = {}
        for name, file in self.handles.items():
            file.seek(0)
            result[name] = hashlib.file_digest(file, "sha256").hexdigest()
        return result

    def copy_to(self, destination):
        destination = Path(destination).absolute()
        if not disjoint(destination, self.root):
            raise ValueError("Snapshot destination overlaps the source")
        # Also reject links in destination ancestors before creating anything.
        for parent in destination.parents:
            if parent.exists() and getattr(parent.lstat(), "st_file_attributes", 0) & 0x400:
                raise ValueError("Snapshot destination contains a reparse point")
        destination.mkdir(parents=True, exist_ok=False)
        for name in self.directories:
            (destination / name).mkdir(parents=True, exist_ok=False)
        for name, source in self.handles.items():
            source.seek(0)
            with (destination / name).open("xb") as target:
                shutil.copyfileobj(source, target)
        if tree_hashes(destination) != self.hashes():
            raise RuntimeError("Snapshot byte verification failed")


@contextmanager
def locked_snapshot(root):
    if os.name != "nt":
        raise RuntimeError("This snapshot command requires Windows write-denying locks")
    root = Path(root).absolute()
    files, directories = inventory(root)
    if "chroma.sqlite3" not in files:
        raise RuntimeError("Source index is missing chroma.sqlite3")
    with ExitStack() as stack:
        # Lock SQLite first; a live SQLite writer prevents copying altogether.
        order = ["chroma.sqlite3"] + [name for name in files if name != "chroma.sqlite3"]
        handles = {name: stack.enter_context(open_write_denied(root / name)) for name in order}
        snapshot = LockedSnapshot(root, files, directories, handles)
        snapshot.hashes()  # Reject additions/removals during lock acquisition.
        yield snapshot


def install_chroma_guard(allowed):
    """Guard the shared storage initializer, even for pre-imported client aliases.

    Only for fresh test-worker processes. No existing Chroma systems are allowed.
    """
    global _guarded_path
    from chromadb.api.shared_system_client import SharedSystemClient
    allowed = Path(allowed).resolve()
    if not disjoint(allowed) or SharedSystemClient._identifier_to_system:
        raise RuntimeError("Isolation requires a fresh process and a separate copied index")
    original = SharedSystemClient._create_system_if_not_exists.__func__
    opened = []

    def guarded(cls, identifier, settings):
        if not settings.is_persistent or Path(settings.persist_directory).resolve() != allowed:
            raise RuntimeError("Isolated worker refused an unexpected Chroma storage path")
        opened.append(str(allowed))
        return original(cls, identifier, settings)

    SharedSystemClient._create_system_if_not_exists = classmethod(guarded)
    _guarded_path = allowed
    return opened
