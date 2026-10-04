// Shared editor state: the map, the track and waypoints, undo, saving, and the live stats.
// Other modules read editor.state, change it only through editor.apply(), and redraw via editor.onChange().

const editor = (() => {
  const data = window.GPX_EDITOR;
  const algo = trackAlgorithms;

  const baseLayer = () => L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  });
  const map = L.map('map');
  baseLayer().addTo(map);

  const state = { track: data.trackpoints, waypoints: data.waypoints };
  const listeners = [];
  let trackLayer = null;
  let trackClickHandler = null;

  const statusEl = document.getElementById('editStatus');
  const undoBtn = document.getElementById('undoBtn');

  function setStatus(text, isError = false) {
    statusEl.textContent = text;
    statusEl.classList.toggle('text-danger', isError);
    statusEl.classList.toggle('text-muted', !isError);
  }

  function updateStats() {
    const km = algo.distanceKm(state.track);
    document.getElementById('statDistance').textContent = km > 0 ? `${km.toFixed(1)} km` : '—';
    document.getElementById('statPoints').textContent = algo.pointCount(state.track).toLocaleString();
    document.getElementById('statSegments').textContent = algo.segments(state.track).length;
    document.getElementById('statWaypoints').textContent = state.waypoints.length;
  }

  function drawTrack() {
    if (trackLayer) map.removeLayer(trackLayer);
    const lines = algo.segments(state.track)
      .filter(s => s.length > 1)
      .map(s => L.polyline(s.map(p => [p.lat, p.lon]), { color: '#3b82f6', weight: 3 }));
    trackLayer = lines.length ? L.featureGroup(lines).addTo(map) : null;
    if (trackLayer && trackClickHandler) trackLayer.on('click', trackClickHandler);
  }

  function render() {
    drawTrack();
    updateStats();
    listeners.forEach(fn => fn());
  }

  async function postJson(url, body) {
    const res = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  }

  // Sequential on purpose: both endpoints read-modify-write the same file, so running them in
  // parallel could let one save overwrite the other.
  async function persist(parts) {
    if (parts.waypoints) await postJson(data.urls.waypoints, state.waypoints);
    if (parts.track) await postJson(data.urls.track, state.track);
  }

  // Undo steps back to the previous version on the server, so it waits while a save is in flight;
  // each save keeps the file's previous content as a version, so there is then something to undo.
  async function save(parts, message) {
    undoBtn.disabled = true;
    try {
      await persist(parts);
      setStatus(message);
    } catch (err) {
      setStatus(`Could not save changes (${err.message}). Reload to see what is on disk.`, true);
    } finally {
      undoBtn.disabled = false;
    }
  }

  // Apply a change to the track and/or waypoints: redraw, then save.
  async function apply({ track, waypoints, message }) {
    if (track) state.track = track;
    if (waypoints) state.waypoints = waypoints;
    render();
    await save({ track: !!track, waypoints: !!waypoints }, message);
  }

  function onChange(fn) { listeners.push(fn); }

  function onTrackClick(fn) {
    trackClickHandler = fn;
    if (trackLayer) trackLayer.on('click', fn);
  }

  // Fetch a road route through [lat, lon] points from OSRM, as track points.
  async function routeThrough(points) {
    const coords = points.map(([lat, lon]) => `${lon},${lat}`).join(';');
    const res = await fetch(`${data.config.osrm_url}/${coords}?overview=full&geometries=geojson`);
    if (!res.ok) throw new Error(`OSRM HTTP ${res.status}`);
    const json = await res.json();
    if (json.code !== 'Ok' || !json.routes.length) throw new Error(json.message || json.code);
    return json.routes[0].geometry.coordinates.map(([lon, lat]) => ({ lat, lon, ele: null, time: null }));
  }

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function start() {
    render();
    if (trackLayer) map.fitBounds(trackLayer.getBounds(), { padding: [20, 20] });
    else if (state.waypoints.length) map.fitBounds(state.waypoints.map(w => [w.lat, w.lon]), { padding: [40, 40] });
    else map.setView([0, 0], 2);
  }

  return { map, baseLayer, state, config: data.config, zones: data.zones, apply, onChange, onTrackClick, routeThrough, esc, start };
})();
