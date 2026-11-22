"""Server-owned UUID namespaces; no client filename is ever a storage key."""
import hashlib
import os
import shutil
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath

from django.conf import settings



def resolve_stored_path(relative):
    if not isinstance(relative, str):
        raise ValueError("Invalid storage key.")
    parts = relative.split("/")
    if (not relative or "\\" in relative or PureWindowsPath(relative).drive
            or PurePosixPath(relative).is_absolute() or any(p in ("", ".", "..") or ":" in p
                or any(ord(c) < 32 for c in p) for p in parts)):
        raise ValueError("Invalid storage key.")
    root = Path(settings.MEDIA_ROOT).absolute()
    candidate = root
    for component in (None, *parts):
        if component is not None:
            candidate = candidate / component
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise ValueError("Storage links are forbidden.")
    result = candidate.resolve()
    result.relative_to(root.resolve())
    return result


def key(job_id, suffix=""):
    identifier = str(uuid.UUID(str(job_id)))
    return f"inspection_summary/{identifier}" + (f"/{suffix}" if suffix else "")


def job_root(job_id):
    return resolve_stored_path(key(job_id))


def input_path(job_id, kind):
    if kind not in ("inspection_summary", "raw"):
        raise ValueError("Invalid input kind.")
    return resolve_stored_path(key(job_id, f"input/{kind}.xlsx"))


def output_path(job_id):
    return resolve_stored_path(key(job_id, "output/Result.xlsx"))


def make_directory(relative):
    # The hierarchy is service-owned. Recheck every ancestor after creation and
    # use exclusive/no-follow file opens inside it; never reuse a client path.
    root = Path(settings.MEDIA_ROOT).absolute()
    current = root
    for part in relative.split("/"):
        current = current / part
        resolve_stored_path(current.relative_to(root).as_posix())
        current.mkdir(mode=0o700, exist_ok=True)
        resolve_stored_path(current.relative_to(root).as_posix())
    return current


def save_input(job_id, kind, uploaded):
    relative = key(job_id, f"input/{kind}.xlsx")
    destination = input_path(job_id, kind)
    make_directory(key(job_id, "input"))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    digest = hashlib.sha256()
    uploaded.seek(0)
    with os.fdopen(os.open(destination, flags, 0o600), "wb") as stream:
        for chunk in uploaded.chunks():
            stream.write(chunk)
            digest.update(chunk)
    return relative, digest.hexdigest()


def remove_job(job_id):
    target = job_root(job_id)
    if target.name != str(uuid.UUID(str(job_id))):
        raise ValueError("Invalid job identity.")
    if target.exists():
        checked = job_root(job_id)
        if checked != target or not checked.is_dir():
            raise ValueError("Invalid job directory.")
        shutil.rmtree(checked)


@contextmanager
def maintenance_lock(job_id):
    """Nonblocking process lock on shared MEDIA_ROOT, outside the deletable tree.

    Persisted ownership is still required. This lock closes the lease-reclaim vs
    paused-deleter race; never unlink its inode. Local shared filesystems must
    support advisory locks (same assumption as the existing deployment volume).
    """
    make_directory("inspection_summary")
    path = resolve_stored_path(f"inspection_summary/.maintenance-{uuid.UUID(str(job_id))}.lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    acquired = False
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Invalid maintenance lock")
        if os.name == "nt":
            import msvcrt
            # Windows permits a byte-range lock beyond EOF; no initialization
            # write may race a peer that already acquired the empty lock inode.
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                acquired = True
            except OSError as exc:
                if exc.errno not in (13, 11, 36):
                    raise
        else:
            import fcntl
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                pass
        yield acquired
    finally:
        if acquired:
            if os.name == "nt":
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
