"""Path rules for the Image Processor's private upload staging directory."""
from pathlib import Path, PurePosixPath, PureWindowsPath
from contextlib import ExitStack, contextmanager
import os
import stat

from rest_framework.exceptions import ValidationError


def validate_upload_path(value: str, *, single_component: bool = False) -> str:
    """Reject unsafe components before normalization can hide traversal.

    Apply Windows rules on every host so uploads have the same interpretation
    on Windows and Linux. Folder labels otherwise retain their original text.
    """
    value = value.replace("\\", "/")
    parts = value.split("/")
    if (
        not value
        or PureWindowsPath(value).drive
        or value.startswith("/")
        or (single_component and len(parts) != 1)
        or any(
            part in ("", ".", "..")
            or part.endswith((".", " "))
            or len(part.encode("utf-8")) > 255
            or PureWindowsPath(part).is_reserved()
            or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
            for part in parts
        )
    ):
        raise ValidationError("Invalid upload path.")
    return value


def contained_upload_path(root: Path, relative_path: str) -> Path:
    """Resolve containment and reject links, including Windows junctions.

    Call again after creating parents, immediately before exclusive file open.
    The job root is freshly created with owner-only access; no client selects it.
    """
    relative_path = validate_upload_path(relative_path)
    candidate = root
    for part in (None, *relative_path.split("/")):
        if part is not None:
            candidate = candidate / part
        try:
            metadata = candidate.lstat()  # Never follow a link to inspect its type.
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ValidationError("Upload paths must not contain links.")
    try:
        resolved = candidate.resolve()
        resolved_root = root.resolve()
        if os.name == "nt":
            # Windows can return either spelling during concurrent creation.
            # Normalize only server-resolved drive/UNC namespace prefixes.
            def without_namespace(path):
                text = str(path)
                if text.startswith("\\\\?\\UNC\\"):
                    return Path("\\\\" + text[8:])
                if text.startswith("\\\\?\\") and len(PureWindowsPath(text[4:]).drive) == 2:
                    return Path(text[4:])
                return path
            resolved = without_namespace(resolved)
            resolved_root = without_namespace(resolved_root)
        resolved.relative_to(resolved_root)
    except (ValueError, OSError, RuntimeError) as exc:
        raise ValidationError("Invalid upload destination.") from exc
    return resolved


@contextmanager
def open_upload_file(root: Path, relative_path: str):
    """Exclusive, mode-0600 writes; POSIX traversal stays anchored to open dirs.

    Windows has no stdlib openat: private job ACLs and a reparse check after
    each mkdir protect its path-based fallback. Never change process umask.
    """
    destination = contained_upload_path(root, relative_path)
    parts = relative_path.replace("\\", "/").split("/")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    with ExitStack() as opened:
        if os.name == "posix":
            directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            parent_fd = os.open(root, directory_flags)
            opened.callback(os.close, parent_fd)
            for part in parts[:-1]:
                try:
                    os.mkdir(part, 0o700, dir_fd=parent_fd)
                except FileExistsError:
                    pass  # The atomic no-follow directory open below verifies it.
                parent_fd = os.open(part, directory_flags, dir_fd=parent_fd)
                opened.callback(os.close, parent_fd)
            fd = os.open(parts[-1], flags | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
        else:
            for i in range(1, len(parts)):
                parent = contained_upload_path(root, "/".join(parts[:i]))
                parent.mkdir(mode=0o700, exist_ok=True)
                contained_upload_path(root, "/".join(parts[:i]))
            destination = contained_upload_path(root, relative_path)
            fd = os.open(destination, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            yield stream


def validate_upload_destinations(paths: list[str]) -> None:
    """Reject overwrite and file/directory conflicts, also on case-folding hosts."""
    files = set()
    directories = set()
    directory_names = {}
    for path in paths:
        path = validate_upload_path(path)
        key = path.casefold()
        parts = key.split("/")
        parents = {"/".join(parts[:i]) for i in range(1, len(parts))}
        if key in files or key in directories or parents & files:
            raise ValidationError("Upload filenames collide after normalization.")
        files.add(key)
        directories.update(parents)
        original_parts = path.split("/")
        for i in range(1, len(original_parts)):
            name = "/".join(original_parts[:i])
            previous = directory_names.setdefault(name.casefold(), name)
            if previous != name:
                raise ValidationError("Upload folder names collide across platforms.")


def validate_preparation_destinations(paths: list[str]) -> None:
    """Final normalized intake paths must not alias the worker's per-folder JPEGs."""
    targets = set()
    for path in paths:
        parts = PurePosixPath(path).parts
        target = (str(PurePosixPath(path).parent).casefold(), PurePosixPath(path).stem.casefold())
        if target in targets:
            raise ValidationError("Upload names conflict during image preparation.")
        targets.add(target)
