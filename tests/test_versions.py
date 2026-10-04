from datetime import datetime, timezone
from pathlib import Path

import pytest
from flask.testing import FlaskClient

import app as app_module
import file_index
import file_store
import gpx_utils
import versions

GPX = (
    '<?xml version="1.0"?><gpx version="1.1" creator="t"><metadata><name>{name}</name></metadata>'
    '<trk><trkseg><trkpt lat="1" lon="2"/></trkseg></trk></gpx>'
)
T1 = datetime(2026, 10, 4, 9, 0, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 10, 4, 9, 5, 0, tzinfo=timezone.utc)
T3 = datetime(2026, 10, 4, 9, 10, 0, tzinfo=timezone.utc)
T4 = datetime(2026, 10, 4, 9, 15, 0, tzinfo=timezone.utc)


def write(tmp_path: Path, name: str = "Original", filename: str = "ride.gpx") -> Path:
    path = tmp_path / filename
    path.write_text(GPX.format(name=name), encoding="utf-8")
    return path


def version_names(tmp_path: Path) -> list[str]:
    folder = tmp_path / versions.VERSION_DIR_NAME
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_snapshot_copies_file_with_timestamped_name(tmp_path: Path) -> None:
    path = write(tmp_path)

    versions.snapshot(path, now=T1)

    assert version_names(tmp_path) == ["ride.20261004090000.gpx"]
    assert "Original" in (tmp_path / ".version" / "ride.20261004090000.gpx").read_text(
        encoding="utf-8"
    )


def test_same_second_snapshot_keeps_the_content_from_before_the_change(
    tmp_path: Path,
) -> None:
    path = write(tmp_path)
    versions.snapshot(path, now=T1)
    path.write_text(GPX.format(name="Half-saved"), encoding="utf-8")

    versions.snapshot(path, now=T1)

    assert version_names(tmp_path) == ["ride.20261004090000.gpx"]
    assert "Original" in versions.version_path(path, "20261004090000").read_text(
        encoding="utf-8"
    )


def test_every_gpx_save_takes_a_version_first(tmp_path: Path) -> None:
    path = write(tmp_path)

    gpx_utils.update_metadata(path, "Edited", "", "")

    [stamp] = [v["stamp"] for v in versions.list_versions(path)]
    assert "Original" in versions.version_path(path, stamp).read_text(encoding="utf-8")
    assert gpx_utils.read_gpx(path)["name"] == "Edited"


def test_list_is_newest_first(tmp_path: Path) -> None:
    path = write(tmp_path)
    versions.snapshot(path, now=T1)
    versions.snapshot(path, now=T2)

    assert [v["stamp"] for v in versions.list_versions(path)] == [
        "20261004090500",
        "20261004090000",
    ]


def test_versions_of_similarly_named_files_are_kept_apart(tmp_path: Path) -> None:
    ride = write(tmp_path, filename="ride.gpx")
    ride2 = write(tmp_path, filename="ride 2.gpx")
    versions.snapshot(ride, now=T1)
    versions.snapshot(ride2, now=T2)

    assert [v["stamp"] for v in versions.list_versions(ride)] == ["20261004090000"]
    assert [v["stamp"] for v in versions.list_versions(ride2)] == ["20261004090500"]


def test_old_versions_are_pruned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(versions, "MAX_VERSIONS", 2)
    path = write(tmp_path)

    for minute in range(4):
        versions.snapshot(
            path, now=datetime(2026, 10, 4, 9, minute, tzinfo=timezone.utc)
        )

    assert [v["stamp"] for v in versions.list_versions(path)] == [
        "20261004090300",
        "20261004090200",
    ]


def test_restore_brings_back_old_content_and_keeps_current_as_a_version(
    tmp_path: Path,
) -> None:
    path = write(tmp_path)
    versions.snapshot(path, now=T1)
    path.write_text(GPX.format(name="Messed up"), encoding="utf-8")

    versions.restore(path, "20261004090000")

    assert "Original" in path.read_text(encoding="utf-8")
    kept = [
        versions.version_path(path, v["stamp"]) for v in versions.list_versions(path)
    ]
    assert any("Messed up" in v.read_text(encoding="utf-8") for v in kept)


def test_undo_steps_back_one_version_at_a_time(tmp_path: Path) -> None:
    path = write(tmp_path, name="First")
    versions.snapshot(path, now=T1)
    path.write_text(GPX.format(name="Second"), encoding="utf-8")
    versions.snapshot(path, now=T2)
    path.write_text(GPX.format(name="Third"), encoding="utf-8")

    assert versions.undo(path, now=T3) == "20261004090500"
    assert "Second" in path.read_text(encoding="utf-8")

    assert versions.undo(path, now=T4) == "20261004090000"
    assert "First" in path.read_text(encoding="utf-8")
    assert not versions.can_undo(path)
    with pytest.raises(versions.VersionError):
        versions.undo(path)


def test_undo_keeps_what_it_replaced_as_a_restorable_undone_copy(
    tmp_path: Path,
) -> None:
    path = write(tmp_path)
    versions.snapshot(path, now=T1)
    path.write_text(GPX.format(name="Messed up"), encoding="utf-8")

    versions.undo(path, now=T3)

    listed = versions.list_versions(path)
    assert [(v["stamp"], v["undone"]) for v in listed] == [
        ("20261004091000.undone", True)
    ]
    versions.restore(path, "20261004091000.undone")
    assert "Messed up" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("stamp", ["20990101000000", "../../etc", "2026"])
def test_unknown_or_malformed_version_is_rejected(tmp_path: Path, stamp: str) -> None:
    path = write(tmp_path)

    with pytest.raises(versions.VersionError):
        versions.restore(path, stamp)


def test_versions_follow_a_rename(tmp_path: Path) -> None:
    path = write(tmp_path)
    versions.snapshot(path, now=T1)

    new_name = file_store.rename(tmp_path, "ride.gpx", "Gold Coast")

    assert version_names(tmp_path) == ["Gold_Coast.20261004090000.gpx"]
    assert [v["stamp"] for v in versions.list_versions(tmp_path / new_name)] == [
        "20261004090000"
    ]


def test_file_list_ignores_the_version_folder(tmp_path: Path) -> None:
    path = write(tmp_path)
    versions.snapshot(path, now=T1)

    assert [f["filename"] for f in file_index.list_gpx_files(tmp_path)] == ["ride.gpx"]


# ── Routes ───────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FlaskClient:
    monkeypatch.setattr(app_module, "GPX_DIR", tmp_path)
    return app_module.app.test_client()


def test_version_routes_list_download_and_restore(
    client: FlaskClient, tmp_path: Path
) -> None:
    path = write(tmp_path)
    versions.snapshot(path, now=T1)
    path.write_text(GPX.format(name="Messed up"), encoding="utf-8")

    listed = client.get("/view/ride.gpx/versions").get_json()["versions"]
    assert [v["stamp"] for v in listed] == ["20261004090000"]

    download = client.get("/view/ride.gpx/versions/20261004090000")
    assert download.status_code == 200
    assert b"Original" in download.data

    res = client.post("/view/ride.gpx/versions/20261004090000/restore")
    assert res.status_code == 302
    assert "Original" in path.read_text(encoding="utf-8")


def test_restore_of_missing_version_flashes_error(
    client: FlaskClient, tmp_path: Path
) -> None:
    write(tmp_path)

    res = client.post(
        "/view/ride.gpx/versions/20990101000000/restore", follow_redirects=True
    )

    assert "No version 20990101000000" in res.get_data(as_text=True)


def test_undo_route_steps_back_and_reports_when_nothing_is_left(
    client: FlaskClient, tmp_path: Path
) -> None:
    path = write(tmp_path)
    versions.snapshot(path, now=T1)
    path.write_text(GPX.format(name="Messed up"), encoding="utf-8")

    assert client.post("/view/ride.gpx/undo").status_code == 302
    assert "Original" in path.read_text(encoding="utf-8")

    res = client.post("/view/ride.gpx/undo", follow_redirects=True)
    assert "no earlier version to undo to" in res.get_data(as_text=True)
