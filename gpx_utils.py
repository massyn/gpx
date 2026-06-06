from datetime import datetime
from pathlib import Path

import gpxpy
import gpxpy.gpx


def _track_distance_km(gpx) -> float:
    import math
    total = 0.0
    for track in gpx.tracks:
        for segment in track.segments:
            pts = segment.points
            for i in range(len(pts) - 1):
                lat1, lon1 = pts[i].latitude, pts[i].longitude
                lat2, lon2 = pts[i+1].latitude, pts[i+1].longitude
                r = math.pi / 180
                dlat, dlon = (lat2 - lat1) * r, (lon2 - lon1) * r
                a = math.sin(dlat/2)**2 + math.cos(lat1*r) * math.cos(lat2*r) * math.sin(dlon/2)**2
                total += 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(total, 1)


def list_gpx_files(directory: Path) -> list[dict]:
    files = []
    for path in sorted(directory.glob("*.gpx")):
        try:
            with open(path) as f:
                gpx = gpxpy.parse(f)
            files.append({
                "filename": path.name,
                "name": gpx.name or path.stem,
                "description": gpx.description or "",
                "author": gpx.author_name or "",
                "track_count": len(gpx.tracks),
                "point_count": gpx.get_track_points_no(),
                "distance_km": _track_distance_km(gpx),
            })
        except Exception:
            files.append({
                "filename": path.name,
                "name": path.stem,
                "description": "",
                "author": "",
                "track_count": 0,
                "point_count": 0,
                "distance_km": 0,
            })
    return files


def read_gpx(filepath: Path) -> dict:
    with open(filepath) as f:
        gpx = gpxpy.parse(f)

    trackpoints = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                trackpoints.append({
                    "lat": point.latitude,
                    "lon": point.longitude,
                    "ele": point.elevation,
                    "time": point.time.isoformat() if point.time else None,
                })

    waypoints = []
    for wp in gpx.waypoints:
        waypoints.append({
            "lat": wp.latitude,
            "lon": wp.longitude,
            "ele": wp.elevation,
            "time": wp.time.isoformat() if wp.time else None,
            "name": wp.name or "",
            "desc": wp.description or "",
            "cmt": wp.comment or "",
            "link": wp.link or "",
            "sym": wp.symbol or "",
            "type": wp.type or "",
        })

    return {
        "name": gpx.name or "",
        "description": gpx.description or "",
        "author": gpx.author_name or "",
        "trackpoints": trackpoints,
        "waypoints": waypoints,
    }


def update_metadata(filepath: Path, name: str, description: str, author: str) -> None:
    with open(filepath) as f:
        gpx = gpxpy.parse(f)

    gpx.name = name
    gpx.description = description
    gpx.author_name = author

    with open(filepath, "w") as f:
        f.write(gpx.to_xml())


def update_waypoints(filepath: Path, waypoints: list[dict]) -> None:
    with open(filepath) as f:
        gpx = gpxpy.parse(f)

    gpx.waypoints = []
    for wp in waypoints:
        point = gpxpy.gpx.GPXWaypoint(
            latitude=wp["lat"],
            longitude=wp["lon"],
            elevation=wp.get("ele"),
            time=_parse_time(wp.get("time")),
            name=wp.get("name", ""),
            description=wp.get("desc", ""),
            comment=wp.get("cmt", ""),
            symbol=wp.get("sym", ""),
            type=wp.get("type", ""),
        )
        point.link = wp.get("link", "")
        gpx.waypoints.append(point)

    with open(filepath, "w") as f:
        f.write(gpx.to_xml())


def apply_track(filepath: Path, trackpoints: list[dict]) -> None:
    with open(filepath) as f:
        gpx = gpxpy.parse(f)

    if not gpx.tracks:
        gpx.tracks.append(gpxpy.gpx.GPXTrack())

    track = gpx.tracks[0]
    track.segments = []
    current = gpxpy.gpx.GPXTrackSegment()
    for tp in trackpoints:
        if tp.get("_break"):
            if current.points:
                track.segments.append(current)
            current = gpxpy.gpx.GPXTrackSegment()
        else:
            current.points.append(gpxpy.gpx.GPXTrackPoint(
                latitude=tp["lat"],
                longitude=tp["lon"],
                elevation=tp.get("ele"),
                time=_parse_time(tp.get("time")),
            ))
    if current.points:
        track.segments.append(current)

    with open(filepath, "w") as f:
        f.write(gpx.to_xml())


def _parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
