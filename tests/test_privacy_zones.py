from pathlib import Path

import pytest

import privacy_zones as pz


@pytest.fixture(autouse=True)
def zones_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "zones.json"
    monkeypatch.setattr(pz, "ZONES_FILE", path)
    return path


def test_add_and_load_zone() -> None:
    zone = pz.add_zone(
        {"name": " Home ", "lat": "-27.5", "lon": 153.0, "radius_km": 0.5}
    )

    assert pz.load_zones() == [zone]
    assert (zone["name"], zone["lat"]) == ("Home", -27.5)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (None, "JSON object"),
        ({"lat": 1, "lon": 1, "radius_km": 1}, "name is required"),
        ({"name": "x", "lon": 1, "radius_km": 1}, "lat is required"),
        ({"name": "x", "lat": "abc", "lon": 1, "radius_km": 1}, "lat must be a number"),
        ({"name": "x", "lat": 95, "lon": 1, "radius_km": 1}, "lat must be between"),
        (
            {"name": "x", "lat": 1, "lon": 1, "radius_km": 0},
            "radius_km must be between",
        ),
    ],
)
def test_invalid_zone_is_rejected(data: object, message: str) -> None:
    with pytest.raises(pz.ZoneError, match=message):
        pz.add_zone(data)
    assert pz.load_zones() == []


def test_update_keeps_fields_not_supplied() -> None:
    zone = pz.add_zone({"name": "Home", "lat": -27.5, "lon": 153.0, "radius_km": 0.5})

    updated = pz.update_zone(zone["id"], {"radius_km": 1.2})

    assert updated == {**zone, "radius_km": 1.2}
    assert pz.load_zones() == [updated]


def test_update_unknown_zone_returns_none() -> None:
    assert pz.update_zone("missing", {"name": "x"}) is None
