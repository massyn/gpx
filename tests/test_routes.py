from io import BytesIO
from pathlib import Path

import pytest
from flask.testing import FlaskClient

import app as app_module
import privacy_zones as pz

GPX = (
    '<?xml version="1.0"?><gpx version="1.1" creator="t">'
    '<trk><trkseg><trkpt lat="1" lon="2"/></trkseg></trk></gpx>'
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FlaskClient:
    monkeypatch.setattr(app_module, "GPX_DIR", tmp_path)
    monkeypatch.setattr(pz, "ZONES_FILE", tmp_path / "zones.json")
    return app_module.app.test_client()


def test_zone_api_returns_400_for_bad_input(client: FlaskClient) -> None:
    res = client.post("/api/privacy-zones", json={"name": "Home"})

    assert res.status_code == 400
    assert res.get_json() == {"error": "lat is required"}


def test_zone_api_partial_update(client: FlaskClient) -> None:
    zone = client.post(
        "/api/privacy-zones",
        json={"name": "Home", "lat": 1, "lon": 2, "radius_km": 0.5},
    ).get_json()

    res = client.put(f"/api/privacy-zones/{zone['id']}", json={"name": "Work"})

    assert res.status_code == 200
    assert res.get_json() == {**zone, "name": "Work"}


def test_edit_renames_file_and_redirects_to_new_name(
    client: FlaskClient, tmp_path: Path
) -> None:
    (tmp_path / "old.gpx").write_text(GPX, encoding="utf-8")

    res = client.post(
        "/view/old.gpx/edit",
        data={"name": "Ride", "description": "", "author": "", "filename": "new"},
    )

    assert res.status_code == 302
    assert res.headers["Location"].endswith("/view/new.gpx")
    assert (tmp_path / "new.gpx").exists()
    assert not (tmp_path / "old.gpx").exists()


def test_edit_with_taken_filename_saves_metadata_but_keeps_name(
    client: FlaskClient, tmp_path: Path
) -> None:
    (tmp_path / "a.gpx").write_text(GPX, encoding="utf-8")
    (tmp_path / "b.gpx").write_text(GPX, encoding="utf-8")

    res = client.post(
        "/view/a.gpx/edit",
        data={"name": "Renamed ride", "filename": "b.gpx"},
        follow_redirects=True,
    )

    assert "not renamed" in res.get_data(as_text=True)
    assert "Renamed ride" in (tmp_path / "a.gpx").read_text(encoding="utf-8")


def test_upload_of_invalid_file_is_refused(client: FlaskClient, tmp_path: Path) -> None:
    res = client.post(
        "/upload",
        data={"gpx_file": (BytesIO(b"nope"), "ride.gpx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert "valid GPX" in res.get_data(as_text=True)
    assert not (tmp_path / "ride.gpx").exists()
