import os
from datetime import datetime
from pathlib import Path

import pytest

import file_index
import gpx_utils

GPX = """<?xml version="1.0"?>
<gpx version="1.1" creator="test">
  <metadata><name>{name}</name></metadata>
  <trk><trkseg>
    <trkpt lat="-27.0" lon="153.0"><time>2026-09-12T23:30:00Z</time></trkpt>
    <trkpt lat="-27.0" lon="153.1"><time>2026-09-13T00:30:00Z</time></trkpt>
  </trkseg></trk>
</gpx>
"""


@pytest.fixture
def parse_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record which files are actually parsed, while still parsing them."""
    calls = []
    real = gpx_utils.summarise_gpx

    def counting(path: Path) -> dict:
        calls.append(path.name)
        return real(path)

    monkeypatch.setattr(gpx_utils, "summarise_gpx", counting)
    return calls


def write_gpx(directory: Path, filename: str, name: str) -> Path:
    path = directory / filename
    path.write_text(GPX.format(name=name), encoding="utf-8")
    return path


def test_second_listing_is_served_from_cache(
    tmp_path: Path, parse_calls: list[str]
) -> None:
    write_gpx(tmp_path, "a.gpx", "Ride A")
    write_gpx(tmp_path, "b.gpx", "Ride B")

    first = file_index.list_gpx_files(tmp_path)
    second = file_index.list_gpx_files(tmp_path)

    assert parse_calls == ["a.gpx", "b.gpx"]
    assert first == second
    assert [f["name"] for f in second] == ["Ride A", "Ride B"]


def test_only_changed_and_new_files_are_reparsed(
    tmp_path: Path, parse_calls: list[str]
) -> None:
    write_gpx(tmp_path, "a.gpx", "Ride A")
    b = write_gpx(tmp_path, "b.gpx", "Ride B")
    file_index.list_gpx_files(tmp_path)
    parse_calls.clear()

    b.write_text(GPX.format(name="Ride B renamed"), encoding="utf-8")
    stat = b.stat()
    os.utime(b, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    write_gpx(tmp_path, "c.gpx", "Ride C")

    files = file_index.list_gpx_files(tmp_path)

    assert parse_calls == ["b.gpx", "c.gpx"]
    assert [f["name"] for f in files] == ["Ride A", "Ride B renamed", "Ride C"]


def test_deleted_files_drop_out(tmp_path: Path) -> None:
    write_gpx(tmp_path, "a.gpx", "Ride A")
    b = write_gpx(tmp_path, "b.gpx", "Ride B")
    file_index.list_gpx_files(tmp_path)

    b.unlink()

    assert [f["filename"] for f in file_index.list_gpx_files(tmp_path)] == ["a.gpx"]


def test_corrupt_cache_is_rebuilt(tmp_path: Path, parse_calls: list[str]) -> None:
    write_gpx(tmp_path, "a.gpx", "Ride A")
    (tmp_path / file_index.CACHE_FILENAME).write_text("{not json", encoding="utf-8")

    files = file_index.list_gpx_files(tmp_path)

    assert parse_calls == ["a.gpx"]
    assert files[0]["name"] == "Ride A"
    assert file_index.list_gpx_files(tmp_path) == files
    assert parse_calls == ["a.gpx"]


def test_cache_version_change_forces_rebuild(
    tmp_path: Path, parse_calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    write_gpx(tmp_path, "a.gpx", "Ride A")
    file_index.list_gpx_files(tmp_path)

    monkeypatch.setattr(file_index, "CACHE_VERSION", file_index.CACHE_VERSION + 1)
    file_index.list_gpx_files(tmp_path)

    assert parse_calls == ["a.gpx", "a.gpx"]


def test_unparseable_file_gets_placeholder_summary(tmp_path: Path) -> None:
    (tmp_path / "broken.gpx").write_text("not xml", encoding="utf-8")

    [summary] = file_index.list_gpx_files(tmp_path)

    assert summary["name"] == "broken"
    assert summary["distance_km"] == 0


def test_date_uses_first_track_point_in_local_time(tmp_path: Path) -> None:
    write_gpx(tmp_path, "a.gpx", "Ride A")

    [summary] = file_index.list_gpx_files(tmp_path)

    expected = (
        datetime.fromisoformat("2026-09-12T23:30:00+00:00")
        .astimezone()
        .date()
        .isoformat()
    )
    assert summary["date"] == expected
