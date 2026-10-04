"""Cached summaries of the GPX files in a directory, so the file list doesn't re-parse every file."""

import json
import logging
import os
from pathlib import Path

import gpx_utils

logger = logging.getLogger(__name__)

# Bump when the summary fields change so stale caches are rebuilt.
CACHE_VERSION = 1
CACHE_FILENAME = ".index_cache.json"


def _fingerprint(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_mtime_ns, stat.st_size]


def _load_cache(cache_path: Path) -> dict:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("GPX index cache %s is unreadable; rebuilding it", cache_path)
        return {}
    if data.get("version") != CACHE_VERSION:
        return {}
    return data.get("files", {})


def _save_cache(cache_path: Path, entries: dict) -> None:
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"version": CACHE_VERSION, "files": entries}), encoding="utf-8"
    )
    os.replace(tmp, cache_path)


def _summarise(path: Path) -> dict:
    try:
        return gpx_utils.summarise_gpx(path)
    except Exception:
        logger.exception("Could not parse %s", path.name)
        return {
            "filename": path.name,
            "name": path.stem,
            "description": "",
            "author": "",
            "track_count": 0,
            "point_count": 0,
            "distance_km": 0,
            "date": "",
        }


def list_gpx_files(directory: Path, cache_path: Path | None = None) -> list[dict]:
    """Summaries of every .gpx file in the directory, sorted by filename.

    Only files that are new or whose modification time or size changed since the last call are parsed.
    """
    cache_path = cache_path or directory / CACHE_FILENAME
    cached = _load_cache(cache_path)
    entries = {}
    for path in sorted(directory.glob("*.gpx")):
        fingerprint = _fingerprint(path)
        entry = cached.get(path.name)
        if entry is None or entry["fingerprint"] != fingerprint:
            entry = {"fingerprint": fingerprint, "summary": _summarise(path)}
        entries[path.name] = entry

    if entries != cached:
        try:
            _save_cache(cache_path, entries)
        except OSError:
            logger.exception("Could not write GPX index cache %s", cache_path)

    return [entry["summary"] for entry in entries.values()]
