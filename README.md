# GPX Editor

A local Flask app for cleaning up GPX tracks recorded on a phone before sharing or contributing to OSM.

## Features

- Upload, view, and download GPX files; sortable, filterable file list (cached for speed)
- Metadata panel: recorded date, duration, distance, points, segments, waypoints; edit name, description, author
- Waypoint panel: typed icons, click to edit, drag to reorder, optionally re-route the track through them
- Clean up table, re-detected after every change, with Undo:
  - Privacy zones — strip track points and waypoints near home/work
  - Stops — turn into a waypoint, flatten, or ignore
  - GPS gaps — suggest a road route (OSRM), split the track, or ignore
  - Smoothing (RDP), offered when it would make a meaningful reduction

- Waypoint search: find a place by name, or find nearby coffee/fuel/food/etc. around a place; pick on map
- Optional re-route of the track when a waypoint is placed off it
- Uploads are checked to be GPX and never overwrite an existing file; files can be renamed from Edit Metadata
- Versions: every save first keeps a copy in `gpx_files/.version/` as `{name}.{yyyymmddhhmmss}.gpx`;
  the editor's **Versions** dialog downloads or restores them (a restore keeps the replaced file as a version too)

Clean-up thresholds, the OSRM endpoint and the place-search services are set in `gpx_config.ini`
(or a path in `GPX_CONFIG`). `GPX_MAX_VERSIONS` (default 50, 0 = unlimited) caps the versions kept per file.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000`.

GPX files are stored in `gpx_files/` (local only, gitignored).

## Privacy zones

Managed at `/privacy-zones`. Zones are stored in `privacy_zones.json`. When a file is opened, any zone containing track points or waypoints is listed under **Privacy Zones** with **Fix** (strip the points, splitting the track at the gap) and **Ignore**. Nothing is removed until you choose Fix, and Undo reverses it.
