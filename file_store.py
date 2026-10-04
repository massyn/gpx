"""Adding and renaming GPX files in the storage directory, with validation and no silent overwrites."""

import logging
import re
from pathlib import Path

import gpxpy
from gpxpy.gpx import GPXException
from werkzeug.utils import secure_filename

import versions

logger = logging.getLogger(__name__)

# First element tag, skipping the XML declaration, comments and doctype.
ROOT_ELEMENT = re.compile(r"<(?![?!])\s*([\w:.-]+)")


class FileStoreError(ValueError):
    """A user-facing reason a file could not be stored or renamed."""


def _clean_filename(filename: str) -> str:
    """A safe .gpx filename (no path parts), adding the extension if missing."""
    name = secure_filename(filename.strip())
    if not name:
        raise FileStoreError("Please give a filename.")
    if not name.lower().endswith(".gpx"):
        name += ".gpx"
    return name


def save_upload(directory: Path, filename: str, raw: bytes) -> str:
    """Store an uploaded file after checking it is GPX. Returns the stored filename."""
    if not filename:
        raise FileStoreError("No file selected.")
    if not filename.lower().endswith(".gpx"):
        raise FileStoreError("Only .gpx files are accepted.")
    name = _clean_filename(filename)
    target = directory / name
    if target.exists():
        raise FileStoreError(
            f"A file called {name} already exists. Rename or delete it first."
        )
    try:
        text = raw.decode("utf-8-sig")
        # gpxpy accepts any well-formed XML, so check the document really is <gpx> first.
        root = ROOT_ELEMENT.search(text)
        if not root or root.group(1).split(":")[-1] != "gpx":
            raise ValueError("root element is not <gpx>")
        gpxpy.parse(text)
    except (GPXException, UnicodeDecodeError, ValueError):
        logger.warning("Rejected upload %s: not valid GPX", name)
        raise FileStoreError(
            f"{name} could not be read. Is it a valid GPX file?"
        ) from None
    target.write_bytes(raw)
    logger.info("Uploaded %s", name)
    return name


def rename(directory: Path, filename: str, new_filename: str) -> str:
    """Rename a stored file. Returns the new filename (unchanged if the name is the same)."""
    new_name = _clean_filename(new_filename)
    if new_name == filename:
        return filename
    target = directory / new_name
    # Windows filenames are case-insensitive, so a case-only rename resolves to the same file.
    if target.exists() and new_name.lower() != filename.lower():
        raise FileStoreError(f"A file called {new_name} already exists.")
    (directory / filename).rename(target)
    versions.rename(directory / filename, target)
    logger.info("Renamed %s to %s", filename, new_name)
    return new_name
