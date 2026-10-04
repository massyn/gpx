"""Previous versions of GPX files, kept in a .version folder beside them as {stem}.{yyyymmddhhmmss}.gpx.

A version is a copy of a file taken just before it is overwritten, so any change can be rolled back.
Undo steps back through these versions; the content each undo replaces is kept as
{stem}.{yyyymmddhhmmss}.undone.gpx, which can be restored but is never stepped back to.
"""

import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

VERSION_DIR_NAME = ".version"
STAMP_FORMAT = "%Y%m%d%H%M%S"
UNDONE_SUFFIX = ".undone"
STAMP_PATTERN = re.compile(r"^\d{14}(\.undone)?$")
# Oldest versions beyond this many per file are deleted. 0 keeps every version.
MAX_VERSIONS = int(os.environ.get("GPX_MAX_VERSIONS", "50"))


class VersionError(ValueError):
    """A requested version does not exist or its identifier is malformed."""


def _version_dir(path: Path) -> Path:
    return path.parent / VERSION_DIR_NAME


def _versions_of(path: Path) -> list[tuple[str, Path]]:
    """(stamp, version path) pairs for a file, undone copies included, newest first."""
    folder = _version_dir(path)
    if not folder.is_dir():
        return []
    pattern = re.compile(
        rf"^{re.escape(path.stem)}\.(\d{{14}}(?:{re.escape(UNDONE_SUFFIX)})?)\.gpx$"
    )
    found = [(m.group(1), p) for p in folder.iterdir() if (m := pattern.match(p.name))]
    return sorted(found, reverse=True)


def snapshot(path: Path, now: datetime | None = None) -> Path | None:
    """Copy the file's current content into the version folder before it is changed.

    Saves that land in the same second (one editor change can write the file twice) keep the
    first copy, which holds the content from before the change.
    """
    if not path.exists():
        return None
    folder = _version_dir(path)
    folder.mkdir(exist_ok=True)
    # Stamps are in local time, as they are shown to the user.
    stamp = (now or datetime.now().astimezone()).strftime(STAMP_FORMAT)
    target = folder / f"{path.stem}.{stamp}.gpx"
    if not target.exists():
        shutil.copy2(path, target)
        logger.info("Saved version %s", target.name)
        _prune(path)
    return target


def _prune(path: Path) -> None:
    if MAX_VERSIONS <= 0:
        return
    for _, old in _versions_of(path)[MAX_VERSIONS:]:
        old.unlink()
        logger.info("Pruned old version %s", old.name)


def list_versions(path: Path) -> list[dict]:
    """Versions of a file, newest first, for display."""
    return [
        {
            "stamp": stamp,
            "saved": datetime.strptime(stamp[:14], STAMP_FORMAT)
            .astimezone()
            .strftime("%a %d %b %Y, %H:%M:%S"),
            "size_kb": round(version.stat().st_size / 1024),
            "undone": stamp.endswith(UNDONE_SUFFIX),
        }
        for stamp, version in _versions_of(path)
    ]


def _undo_target(path: Path) -> tuple[str, Path] | None:
    """The newest version that undo would step back to, if any."""
    return next(
        (
            (stamp, version)
            for stamp, version in _versions_of(path)
            if not stamp.endswith(UNDONE_SUFFIX)
        ),
        None,
    )


def can_undo(path: Path) -> bool:
    return _undo_target(path) is not None


def undo(path: Path, now: datetime | None = None) -> str:
    """Step the file back to its newest version, which is used up so the next undo goes further back.

    The content being replaced is kept as an undone copy. Returns the stamp stepped back to.
    """
    target = _undo_target(path)
    if target is None:
        raise VersionError(f"{path.name} has no earlier version to undo to")
    stamp, version = target
    now_stamp = (now or datetime.now().astimezone()).strftime(STAMP_FORMAT)
    undone = _version_dir(path) / f"{path.stem}.{now_stamp}{UNDONE_SUFFIX}.gpx"
    if undone.exists():
        raise VersionError("An undo was already saved this second; try again")
    shutil.copy2(path, undone)
    os.replace(version, path)
    # It is the current file now, so it counts as modified now rather than when it was first saved.
    path.touch()
    _prune(path)
    logger.info("Undid %s back to version %s", path.name, stamp)
    return stamp


def version_path(path: Path, stamp: str) -> Path:
    """The stored copy for a version stamp. Raises VersionError if there is none."""
    if not STAMP_PATTERN.match(stamp):
        raise VersionError(f"{stamp!r} is not a version identifier")
    version = _version_dir(path) / f"{path.stem}.{stamp}.gpx"
    if not version.exists():
        raise VersionError(f"No version {stamp} of {path.name}")
    return version


def restore(path: Path, stamp: str) -> None:
    """Replace the file with an earlier version, keeping the current content as a new version."""
    version = version_path(path, stamp)
    snapshot(path)
    shutil.copyfile(version, path)
    logger.info("Restored %s to version %s", path.name, stamp)


def rename(old_path: Path, new_path: Path) -> None:
    """Move a file's versions to follow it to a new name."""
    for stamp, version in _versions_of(old_path):
        version.rename(version.with_name(f"{new_path.stem}.{stamp}.gpx"))
