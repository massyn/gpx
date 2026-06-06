# GPX Editor

A local Flask app for cleaning up GPX tracks recorded on a phone before sharing or contributing to OSM.

## Features

- Upload, view, and download GPX files
- Smooth tracks (flatten stops + RDP simplification)
- Edit metadata (name, description, author)
- Add and edit waypoints on the map
- Detect and repair GPS dropout segments via OSRM routing
- Privacy zones — auto-strip track points near home/work on load

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000`.

GPX files are stored in `gpx_files/` (local only, gitignored).

## Privacy zones

Managed at `/privacy-zones`. Zones are stored in `privacy_zones.json`. Any track points or waypoints inside a zone are automatically removed when a file is opened.
