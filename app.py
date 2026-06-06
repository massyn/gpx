import os
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

import gpx_utils
import privacy_zones as pz

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

GPX_DIR = Path(__file__).parent / "gpx_files"
GPX_DIR.mkdir(exist_ok=True)


def _gpx_path(filename: str) -> Path:
    """Resolve a filename within GPX_DIR, rejecting any path traversal attempt."""
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        abort(400)
    return GPX_DIR / filename


@app.route("/")
def index():
    files = gpx_utils.list_gpx_files(GPX_DIR)
    return render_template("index.html", files=files)


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("gpx_file")
    if not file or not file.filename:
        flash("No file selected.", "warning")
        return redirect(url_for("index"))

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".gpx"):
        flash("Only .gpx files are accepted.", "danger")
        return redirect(url_for("index"))

    file.save(GPX_DIR / filename)
    flash(f"Uploaded {filename}.", "success")
    return redirect(url_for("view", filename=filename))


@app.route("/view/<filename>")
def view(filename: str):
    filepath = _gpx_path(filename)
    if not filepath.exists():
        flash("File not found.", "danger")
        return redirect(url_for("index"))

    try:
        data = gpx_utils.read_gpx(filepath)
    except Exception as exc:
        flash(f"Could not parse GPX file: {exc}", "danger")
        return redirect(url_for("index"))

    return render_template("view.html", filename=filename, **data)


@app.route("/view/<filename>/edit", methods=["POST"])
def edit(filename: str):
    filepath = _gpx_path(filename)
    if not filepath.exists():
        flash("File not found.", "danger")
        return redirect(url_for("index"))

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    author = request.form.get("author", "").strip()

    try:
        gpx_utils.update_metadata(filepath, name, description, author)
        flash("Metadata saved.", "success")
    except Exception as exc:
        flash(f"Could not save metadata: {exc}", "danger")

    return redirect(url_for("view", filename=filename))


@app.route("/view/<filename>/apply-track", methods=["POST"])
def apply_track(filename: str):
    filepath = _gpx_path(filename)
    if not filepath.exists():
        return {"error": "File not found"}, 404

    trackpoints = request.get_json()
    if trackpoints is None:
        return {"error": "Invalid JSON"}, 400

    try:
        gpx_utils.apply_track(filepath, trackpoints)
        return {"ok": True}
    except Exception as exc:
        return {"error": str(exc)}, 500


@app.route("/view/<filename>/waypoints", methods=["POST"])
def save_waypoints(filename: str):
    filepath = _gpx_path(filename)
    if not filepath.exists():
        return {"error": "File not found"}, 404

    waypoints = request.get_json()
    if waypoints is None:
        return {"error": "Invalid JSON"}, 400

    try:
        gpx_utils.update_waypoints(filepath, waypoints)
        return {"ok": True}
    except Exception as exc:
        return {"error": str(exc)}, 500


@app.route("/download/<filename>")
def download(filename: str):
    filepath = _gpx_path(filename)
    if not filepath.exists():
        flash("File not found.", "danger")
        return redirect(url_for("index"))
    return send_file(filepath, as_attachment=True, download_name=filename, mimetype="application/gpx+xml")


@app.route("/privacy-zones")
def privacy_zones_page():
    return render_template("privacy_zones.html")


@app.route("/api/privacy-zones", methods=["GET"])
def api_get_zones():
    return pz.load_zones()


@app.route("/api/privacy-zones", methods=["POST"])
def api_add_zone():
    data = request.get_json()
    zone = pz.add_zone(data["name"], data["lat"], data["lon"], data["radius_km"])
    return zone, 201


@app.route("/api/privacy-zones/<zone_id>", methods=["PUT"])
def api_update_zone(zone_id: str):
    data = request.get_json()
    zone = pz.update_zone(zone_id, data["name"], data["lat"], data["lon"], data["radius_km"])
    if not zone:
        return {"error": "Not found"}, 404
    return zone


@app.route("/api/privacy-zones/<zone_id>", methods=["DELETE"])
def api_delete_zone(zone_id: str):
    if not pz.delete_zone(zone_id):
        return {"error": "Not found"}, 404
    return {"ok": True}


@app.route("/delete/<filename>", methods=["POST"])
def delete(filename: str):
    filepath = _gpx_path(filename)
    if filepath.exists():
        filepath.unlink()
        flash(f"Deleted {filename}.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
