import math
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import gpxpy
import gpxpy.gpx

import versions


def load(path: Path) -> gpxpy.gpx.GPX:
    """Parse a GPX file as UTF-8 (a leading byte-order mark is allowed)."""
    with open(path, encoding="utf-8-sig") as f:
        return gpxpy.parse(f)


def save(path: Path, gpx: gpxpy.gpx.GPX) -> None:
    """Write a GPX file, first keeping its current content as a version."""
    versions.snapshot(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_gpx_xml(gpx))


def to_gpx_xml(gpx: gpxpy.gpx.GPX) -> str:
    """Serialise a GPX document, escaping link hrefs.

    gpxpy writes ``href`` attributes verbatim, so a link containing '&' or '"' would produce
    invalid XML that can never be parsed again. It also hands back plain '&' when reading a
    file, so every read-modify-write needs this. Mutates the given document's links.
    """

    def safe(href: str | None) -> str | None:
        return escape(href, {'"': "&quot;"}) if href else href

    gpx.author_link = safe(gpx.author_link)
    items = [gpx, *gpx.waypoints, *gpx.routes, *gpx.tracks]
    items += [point for route in gpx.routes for point in route.points]
    items += [point for track in gpx.tracks for segment in track.segments for point in segment.points]
    for item in items:
        item.link = safe(item.link)
    return gpx.to_xml()


def _track_distance_km(gpx) -> float:
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


def summarise_gpx(path: Path) -> dict:
    """Parse a GPX file into the summary shown in the file list. Raises if the file is unreadable."""
    gpx = load(path)
    return {
        "filename": path.name,
        "name": gpx.name or path.stem,
        "description": gpx.description or "",
        "author": gpx.author_name or "",
        "track_count": len(gpx.tracks),
        "point_count": gpx.get_track_points_no(),
        "distance_km": _track_distance_km(gpx),
        "date": _gpx_date(gpx),
    }


def _gpx_date(gpx) -> str:
    """Local date (YYYY-MM-DD) from the metadata time, else the first timestamped track point."""
    when = gpx.time or gpx.get_time_bounds().start_time
    return when.astimezone().date().isoformat() if when else ""


def read_gpx(filepath: Path) -> dict:
    gpx = load(filepath)

    # Segments (and tracks) are flattened into one list, separated by {"_break": True} markers.
    trackpoints = []
    segments = [s for track in gpx.tracks for s in track.segments if s.points]
    for i, segment in enumerate(segments):
        if i:
            trackpoints.append({"_break": True})
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

    start, end = gpx.get_time_bounds()
    modified = datetime.fromtimestamp(filepath.stat().st_mtime)
    return {
        "name": gpx.name or "",
        "description": gpx.description or "",
        "author": gpx.author_name or "",
        "track_count": len(gpx.tracks),
        "recorded": _format_datetime(start.astimezone()) if start else "",
        "duration": _format_duration((end - start).total_seconds()) if start and end else "",
        "modified": _format_datetime(modified),
        "trackpoints": trackpoints,
        "waypoints": waypoints,
    }


def _format_datetime(when: datetime) -> str:
    return when.strftime("%a %d %b %Y, %H:%M")


def _format_duration(seconds: float) -> str:
    hours, rem = divmod(int(seconds), 3600)
    days, hours = divmod(hours, 24)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes:02d}m"


def update_metadata(filepath: Path, name: str, description: str, author: str) -> None:
    gpx = load(filepath)

    # Blank fields are removed rather than written as empty elements.
    gpx.name = name or None
    gpx.description = description or None
    gpx.author_name = author or None

    save(filepath, gpx)


def update_waypoints(filepath: Path, waypoints: list[dict]) -> None:
    gpx = load(filepath)

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
        if wp.get("link"):
            point.link = wp["link"]
        gpx.waypoints.append(point)

    save(filepath, gpx)


def apply_track(filepath: Path, trackpoints: list[dict]) -> None:
    gpx = load(filepath)

    # read_gpx flattens every track into one list, so it is written back as a single track
    # (keeping the first track's name etc.) rather than leaving the other tracks to duplicate it.
    track = gpx.tracks[0] if gpx.tracks else gpxpy.gpx.GPXTrack()
    gpx.tracks = [track]
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

    save(filepath, gpx)


def _parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
