import os
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import editor_config
import file_index
import file_store
import gpx_utils
import privacy_zones as pz
import versions

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
    files = file_index.list_gpx_files(GPX_DIR)
    return render_template("index.html", files=files)


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("gpx_file")
    try:
        filename = file_store.save_upload(
            GPX_DIR, file.filename if file else "", file.read() if file else b""
        )
    except file_store.FileStoreError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("index"))
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

    return render_template(
        "view.html",
        filename=filename,
        zones=pz.load_zones(),
        config=editor_config.load(),
        can_undo=versions.can_undo(filepath),
        **data,
    )


@app.route("/view/<filename>/edit", methods=["POST"])
def edit(filename: str):
    filepath = _gpx_path(filename)
    if not filepath.exists():
        flash("File not found.", "danger")
        return redirect(url_for("index"))

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    author = request.form.get("author", "").strip()
    new_filename = request.form.get("filename", "").strip() or filename

    try:
        gpx_utils.update_metadata(filepath, name, description, author)
    except Exception as exc:
        flash(f"Could not save metadata: {exc}", "danger")
        return redirect(url_for("view", filename=filename))

    try:
        filename = file_store.rename(GPX_DIR, filename, new_filename)
        flash("Metadata saved.", "success")
    except file_store.FileStoreError as exc:
        flash(f"Metadata saved, but the file was not renamed: {exc}", "warning")

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
    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype="application/gpx+xml",
    )


@app.route("/view/<filename>/versions")
def list_versions(filename: str):
    filepath = _gpx_path(filename)
    if not filepath.exists():
        return {"error": "File not found"}, 404
    return {"versions": versions.list_versions(filepath)}


@app.route("/view/<filename>/versions/<stamp>")
def download_version(filename: str, stamp: str):
    filepath = _gpx_path(filename)
    try:
        version = versions.version_path(filepath, stamp)
    except versions.VersionError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("view", filename=filename))
    return send_file(
        version,
        as_attachment=True,
        download_name=f"{filepath.stem}.{stamp}.gpx",
        mimetype="application/gpx+xml",
    )


@app.route("/view/<filename>/versions/<stamp>/restore", methods=["POST"])
def restore_version(filename: str, stamp: str):
    filepath = _gpx_path(filename)
    try:
        versions.restore(filepath, stamp)
        flash(
            "Earlier version restored. The version you replaced was kept too.",
            "success",
        )
    except versions.VersionError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("view", filename=filename))


@app.route("/view/<filename>/undo", methods=["POST"])
def undo_version(filename: str):
    filepath = _gpx_path(filename)
    try:
        versions.undo(filepath)
        flash(
            "Undone: back to the previous version. Use Versions to bring back what was undone.",
            "success",
        )
    except versions.VersionError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("view", filename=filename))


@app.route("/privacy-zones")
def privacy_zones_page():
    return render_template("privacy_zones.html")


@app.route("/api/privacy-zones", methods=["GET"])
def api_get_zones():
    return pz.load_zones()


@app.route("/api/privacy-zones", methods=["POST"])
def api_add_zone():
    try:
        return pz.add_zone(request.get_json(silent=True)), 201
    except pz.ZoneError as exc:
        return {"error": str(exc)}, 400


@app.route("/api/privacy-zones/<zone_id>", methods=["PUT"])
def api_update_zone(zone_id: str):
    try:
        zone = pz.update_zone(zone_id, request.get_json(silent=True))
    except pz.ZoneError as exc:
        return {"error": str(exc)}, 400
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
