import json
import math
import uuid
from pathlib import Path

ZONES_FILE = Path(__file__).parent / "privacy_zones.json"


class ZoneError(ValueError):
    """Zone data from a request is missing or invalid."""


def load_zones() -> list[dict]:
    if not ZONES_FILE.exists():
        return []
    with open(ZONES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save(zones: list[dict]) -> None:
    with open(ZONES_FILE, "w", encoding="utf-8") as f:
        json.dump(zones, f, indent=2)


def _number(data: dict, key: str, low: float, high: float) -> float:
    try:
        value = float(data[key])
    except KeyError:
        raise ZoneError(f"{key} is required") from None
    except (TypeError, ValueError):
        raise ZoneError(f"{key} must be a number") from None
    if not low <= value <= high:
        raise ZoneError(f"{key} must be between {low:g} and {high:g}")
    return value


def _validated(data: object) -> dict:
    """Name, lat, lon and radius_km from request data, checked and normalised."""
    if not isinstance(data, dict):
        raise ZoneError("expected a JSON object")
    name = str(data.get("name", "")).strip()
    if not name:
        raise ZoneError("name is required")
    return {
        "name": name,
        "lat": _number(data, "lat", -90, 90),
        "lon": _number(data, "lon", -180, 180),
        "radius_km": _number(data, "radius_km", 0.01, 1000),
    }


def add_zone(data: object) -> dict:
    zone = {"id": str(uuid.uuid4()), **_validated(data)}
    zones = load_zones()
    zones.append(zone)
    _save(zones)
    return zone


def update_zone(zone_id: str, data: object) -> dict | None:
    """Update a zone; fields missing from data keep their current values. None if not found."""
    if not isinstance(data, dict):
        raise ZoneError("expected a JSON object")
    zones = load_zones()
    for zone in zones:
        if zone["id"] == zone_id:
            zone.update(_validated({**zone, **data}))
            _save(zones)
            return zone
    return None


def delete_zone(zone_id: str) -> bool:
    zones = load_zones()
    filtered = [z for z in zones if z["id"] != zone_id]
    if len(filtered) == len(zones):
        return False
    _save(filtered)
    return True


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = math.pi / 180
    dlat = (lat2 - lat1) * r
    dlon = (lon2 - lon1) * r
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin(dlon / 2) ** 2
    )
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def in_any_zone(lat: float, lon: float, zones: list[dict]) -> bool:
    return any(
        _haversine_km(lat, lon, z["lat"], z["lon"]) <= z["radius_km"] for z in zones
    )
