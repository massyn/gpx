from pathlib import Path

import gpxpy

import gpx_utils

TWO_TRACKS = """<?xml version="1.0"?>
<gpx version="1.1" creator="test">
  <trk><name>First</name>
    <trkseg>
      <trkpt lat="-27.0" lon="153.00"><time>2026-09-12T23:00:00Z</time></trkpt>
      <trkpt lat="-27.0" lon="153.01"><time>2026-09-12T23:01:00Z</time></trkpt>
    </trkseg>
    <trkseg>
      <trkpt lat="-27.0" lon="153.02"><time>2026-09-12T23:02:00Z</time></trkpt>
    </trkseg>
  </trk>
  <trk><name>Second</name>
    <trkseg>
      <trkpt lat="-27.0" lon="153.03"><time>2026-09-13T01:30:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>
"""


def write(tmp_path: Path, content: str = TWO_TRACKS) -> Path:
    path = tmp_path / "ride.gpx"
    path.write_text(content, encoding="utf-8")
    return path


def lons(trackpoints: list[dict]) -> list:
    return ["|" if p.get("_break") else p["lon"] for p in trackpoints]


def test_read_marks_segment_and_track_boundaries(tmp_path: Path) -> None:
    data = gpx_utils.read_gpx(write(tmp_path))

    assert lons(data["trackpoints"]) == [153.0, 153.01, "|", 153.02, "|", 153.03]


def test_read_reports_track_count_and_duration(tmp_path: Path) -> None:
    data = gpx_utils.read_gpx(write(tmp_path))

    assert data["track_count"] == 2
    assert data["duration"] == "2h 30m"


def test_saved_splits_survive_a_reload(tmp_path: Path) -> None:
    path = write(tmp_path)
    data = gpx_utils.read_gpx(path)

    gpx_utils.apply_track(path, data["trackpoints"])

    assert lons(gpx_utils.read_gpx(path)["trackpoints"]) == lons(data["trackpoints"])


def test_apply_track_does_not_duplicate_other_tracks(tmp_path: Path) -> None:
    path = write(tmp_path)
    data = gpx_utils.read_gpx(path)

    gpx_utils.apply_track(path, data["trackpoints"])

    gpx = gpxpy.parse(path.read_text(encoding="utf-8"))
    assert len(gpx.tracks) == 1
    assert gpx.tracks[0].name == "First"
    assert gpx.get_track_points_no() == 4


# ── Link escaping (ported from Kickstand) ────────────────────────────────────

LINK = 'https://example.com/stop?a=1&b=2&name="Joe\'s"'

# A valid file whose waypoint link contains an escaped '&', as a well-behaved tool would write it.
GPX_WITH_LINK = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1">
  <wpt lat="-27.55" lon="152.75"><name>Cafe</name><link href="https://example.com/?a=1&amp;b=2"></link></wpt>
  <trk><name>Ride</name><trkseg>
    <trkpt lat="-27.5" lon="152.7"/><trkpt lat="-27.6" lon="152.8"/><trkpt lat="-27.7" lon="152.9"/>
  </trkseg></trk>
</gpx>"""


def link_of(path: Path) -> str:
    return gpx_utils.read_gpx(path)["waypoints"][0]["link"]


def test_saving_a_waypoint_link_with_ampersand_and_quotes_keeps_the_file_valid(
    tmp_path: Path,
) -> None:
    path = write(tmp_path, GPX_WITH_LINK)

    gpx_utils.update_waypoints(
        path, [{"lat": -27.55, "lon": 152.75, "name": "Cafe", "link": LINK}]
    )

    assert link_of(path) == LINK


def test_every_read_modify_write_keeps_existing_links_valid(tmp_path: Path) -> None:
    # gpxpy reads '&amp;' back as '&'; writing it out again must re-escape it.
    path = write(tmp_path, GPX_WITH_LINK)

    gpx_utils.update_metadata(path, "New name", "Desc", "Me")
    assert link_of(path) == "https://example.com/?a=1&b=2"

    gpx_utils.apply_track(
        path, [{"lat": -27.5, "lon": 152.7}, {"lat": -27.7, "lon": 152.9}]
    )
    assert link_of(path) == "https://example.com/?a=1&b=2"


def test_all_link_attributes_are_escaped() -> None:
    gpx = gpxpy.gpx.GPX()
    gpx.link = gpx.author_link = LINK
    route = gpxpy.gpx.GPXRoute()
    route.link = LINK
    route_point = gpxpy.gpx.GPXRoutePoint(1, 2)
    route_point.link = LINK
    route.points.append(route_point)
    track = gpxpy.gpx.GPXTrack()
    track.link = LINK
    track_point = gpxpy.gpx.GPXTrackPoint(1, 2)
    track_point.link = LINK
    track.segments.append(gpxpy.gpx.GPXTrackSegment([track_point]))
    gpx.routes.append(route)
    gpx.tracks.append(track)

    parsed = gpxpy.parse(gpx_utils.to_gpx_xml(gpx))
    assert parsed.link == parsed.author_link == LINK
    assert parsed.routes[0].link == parsed.routes[0].points[0].link == LINK
    assert parsed.tracks[0].link == parsed.tracks[0].segments[0].points[0].link == LINK


# ── Encoding and metadata ────────────────────────────────────────────────────


def test_non_ascii_text_survives_a_save(tmp_path: Path) -> None:
    path = write(tmp_path)

    gpx_utils.update_metadata(path, "Māori Road → Cafe ☕", "Brekkie at Ōtaki", "Zoë")

    data = gpx_utils.read_gpx(path)
    assert (data["name"], data["description"], data["author"]) == (
        "Māori Road → Cafe ☕",
        "Brekkie at Ōtaki",
        "Zoë",
    )


def test_blank_metadata_fields_are_removed(tmp_path: Path) -> None:
    path = write(tmp_path)
    gpx_utils.update_metadata(path, "Name", "Desc", "Me")

    gpx_utils.update_metadata(path, "Name", "", "")

    xml = path.read_text(encoding="utf-8")
    assert "<desc>" not in xml and "<author>" not in xml
    assert gpx_utils.read_gpx(path)["name"] == "Name"


def test_blank_waypoint_link_is_not_written(tmp_path: Path) -> None:
    path = write(tmp_path)

    gpx_utils.update_waypoints(
        path, [{"lat": -27.0, "lon": 153.0, "name": "Stop", "link": ""}]
    )

    assert "<link" not in path.read_text(encoding="utf-8")
