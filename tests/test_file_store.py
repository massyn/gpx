from pathlib import Path

import pytest

import file_store

GPX = (
    b'<?xml version="1.0"?><gpx version="1.1" creator="t">'
    b'<trk><trkseg><trkpt lat="1" lon="2"/></trkseg></trk></gpx>'
)


def test_valid_upload_is_stored(tmp_path: Path) -> None:
    name = file_store.save_upload(tmp_path, "My Ride.gpx", GPX)

    assert name == "My_Ride.gpx"
    assert (tmp_path / name).read_bytes() == GPX


def test_upload_that_is_not_gpx_is_rejected_and_not_written(tmp_path: Path) -> None:
    with pytest.raises(file_store.FileStoreError, match="valid GPX"):
        file_store.save_upload(tmp_path, "ride.gpx", b"<html>not a track</html>")

    assert list(tmp_path.iterdir()) == []


def test_upload_never_overwrites_an_existing_file(tmp_path: Path) -> None:
    (tmp_path / "ride.gpx").write_bytes(b"original")

    with pytest.raises(file_store.FileStoreError, match="already exists"):
        file_store.save_upload(tmp_path, "ride.gpx", GPX)

    assert (tmp_path / "ride.gpx").read_bytes() == b"original"


def test_upload_requires_gpx_extension(tmp_path: Path) -> None:
    with pytest.raises(file_store.FileStoreError, match="Only .gpx"):
        file_store.save_upload(tmp_path, "ride.txt", GPX)


def test_upload_path_parts_are_stripped(tmp_path: Path) -> None:
    name = file_store.save_upload(tmp_path, "../../evil.gpx", GPX)

    assert name == "evil.gpx"
    assert (tmp_path / "evil.gpx").exists()


def test_rename_adds_extension_and_moves_file(tmp_path: Path) -> None:
    (tmp_path / "old.gpx").write_bytes(GPX)

    assert file_store.rename(tmp_path, "old.gpx", "Gold Coast") == "Gold_Coast.gpx"
    assert (tmp_path / "Gold_Coast.gpx").exists()
    assert not (tmp_path / "old.gpx").exists()


def test_rename_refuses_to_replace_another_file(tmp_path: Path) -> None:
    (tmp_path / "a.gpx").write_bytes(b"a")
    (tmp_path / "b.gpx").write_bytes(b"b")

    with pytest.raises(file_store.FileStoreError, match="already exists"):
        file_store.rename(tmp_path, "a.gpx", "b.gpx")

    assert (tmp_path / "a.gpx").read_bytes() == b"a"
    assert (tmp_path / "b.gpx").read_bytes() == b"b"


def test_rename_case_only_change(tmp_path: Path) -> None:
    (tmp_path / "ride.gpx").write_bytes(GPX)

    assert file_store.rename(tmp_path, "ride.gpx", "Ride.gpx") == "Ride.gpx"
    assert [p.name for p in tmp_path.iterdir()] == ["Ride.gpx"]


def test_rename_to_blank_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "ride.gpx").write_bytes(GPX)

    with pytest.raises(file_store.FileStoreError):
        file_store.rename(tmp_path, "ride.gpx", "  ")
