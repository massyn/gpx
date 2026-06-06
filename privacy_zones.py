import json
import math
import uuid
from pathlib import Path

ZONES_FILE = Path(__file__).parent / "privacy_zones.json"


def load_zones() -> list[dict]:
    if not ZONES_FILE.exists():
        return []
    with open(ZONES_FILE) as f:
        return json.load(f)


def _save(zones: list[dict]) -> None:
    with open(ZONES_FILE, "w") as f:
        json.dump(zones, f, indent=2)


def add_zone(name: str, lat: float, lon: float, radius_km: float) -> dict:
    zones = load_zones()
    zone = {"id": str(uuid.uuid4()), "name": name, "lat": lat, "lon": lon, "radius_km": radius_km}
    zones.append(zone)
    _save(zones)
    return zone


def update_zone(zone_id: str, name: str, lat: float, lon: float, radius_km: float) -> dict | None:
    zones = load_zones()
    for zone in zones:
        if zone["id"] == zone_id:
            zone.update({"name": name, "lat": lat, "lon": lon, "radius_km": radius_km})
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
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def in_any_zone(lat: float, lon: float, zones: list[dict]) -> bool:
    return any(_haversine_km(lat, lon, z["lat"], z["lon"]) <= z["radius_km"] for z in zones)
