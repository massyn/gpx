// Waypoints: map markers with type icons, the side list (click, delete, drag to reorder) and the edit modal.

const waypointsUi = (() => {
  const { map, state, config, esc } = editor;
  const $ = id => document.getElementById(id);

  const SYM_META = {
    fuel:          { icon: '⛽', color: '#e67e22' },
    food:          { icon: '🍴', color: '#c0392b' },
    coffee:        { icon: '☕', color: '#8e5a3c' },
    scenic:        { icon: '📷', color: '#27ae60' },
    hazard:        { icon: '⚠️', color: '#e74c3c' },
    accommodation: { icon: '🛏️', color: '#8e44ad' },
    'rest stop':   { icon: '🅿️', color: '#2980b9' },
    other:         { icon: '📍', color: '#7f8c8d' },
  };
  const DEFAULT_META = { icon: '📍', color: '#3b82f6' };
  const symMeta = sym => SYM_META[(sym || '').trim().toLowerCase()] || DEFAULT_META;

  function pinIcon(sym) {
    const meta = symMeta(sym);
    return L.divIcon({
      className: '',
      html: `<div class="wp-pin" style="background:${meta.color}"><span>${meta.icon}</span></div>`,
      iconSize: [28, 28], iconAnchor: [14, 28],
    });
  }

  // ── Markers and list ──────────────────────────────────────
  let markers = [];

  function renderMarkers() {
    markers.forEach(m => map.removeLayer(m));
    markers = state.waypoints.map((wp, i) => {
      const m = L.marker([wp.lat, wp.lon], { icon: pinIcon(wp.sym) }).addTo(map);
      m.bindTooltip([wp.sym, wp.name].filter(Boolean).join(' — ') || 'Waypoint');
      m.on('click', e => { L.DomEvent.stopPropagation(e); openEdit(i); });
      return m;
    });
  }

  function renderList() {
    const list = $('wpList');
    const n = state.waypoints.length;
    $('wpCount').textContent = n ? `${n} waypoint${n === 1 ? '' : 's'}` : '';
    if (!n) {
      list.innerHTML = '<p class="text-muted small text-center py-3 mb-0">No waypoints yet</p>';
      return;
    }
    list.innerHTML = state.waypoints.map((wp, i) => `
      <div class="wp-row" data-idx="${i}" draggable="true">
        <span class="wp-drag" title="Drag to reorder">⠿</span>
        <span class="badge bg-secondary wp-num">${i + 1}</span>
        <span class="wp-badge-icon" title="${esc(wp.sym)}">${wp.sym ? symMeta(wp.sym).icon : ''}</span>
        <div class="flex-grow-1 overflow-hidden">
          <div class="small fw-semibold text-truncate">${esc(wp.name || '(unnamed)')}</div>
          ${wp.cmt ? `<div class="text-muted text-truncate wp-cmt">${esc(wp.cmt)}</div>` : ''}
        </div>
        <button class="btn btn-outline-danger btn-sm wp-del" title="Delete">×</button>
      </div>`).join('');
  }

  $('wpList').addEventListener('click', e => {
    const row = e.target.closest('.wp-row');
    if (!row) return;
    const idx = +row.dataset.idx;
    if (e.target.classList.contains('wp-del')) {
      const wp = state.waypoints[idx];
      editor.apply({ waypoints: state.waypoints.filter((_, i) => i !== idx), message: `Deleted waypoint "${wp.name}".` });
      return;
    }
    map.panTo([state.waypoints[idx].lat, state.waypoints[idx].lon]);
    openEdit(idx);
  });

  // ── Drag to reorder ───────────────────────────────────────
  let dragIdx = null;
  const list = $('wpList');
  list.addEventListener('dragstart', e => {
    dragIdx = +e.target.closest('.wp-row').dataset.idx;
    e.dataTransfer.effectAllowed = 'move';
  });
  list.addEventListener('dragover', e => {
    const row = e.target.closest('.wp-row');
    if (!row) return;
    e.preventDefault();
    list.querySelectorAll('.drag-over').forEach(r => r.classList.remove('drag-over'));
    row.classList.add('drag-over');
  });
  list.addEventListener('dragleave', e => e.target.closest('.wp-row')?.classList.remove('drag-over'));
  list.addEventListener('drop', async e => {
    const row = e.target.closest('.wp-row');
    if (!row || dragIdx === null) return;
    e.preventDefault();
    const dropIdx = +row.dataset.idx;
    const from = dragIdx;
    dragIdx = null;
    if (from === dropIdx) { renderList(); return; }
    const reordered = [...state.waypoints];
    reordered.splice(dropIdx, 0, ...reordered.splice(from, 1));
    await editor.apply({ waypoints: reordered, message: 'Waypoints reordered.' });
    $('reorderPrompt').classList.toggle('d-none', reordered.length < 2);
  });

  $('recalcNo').addEventListener('click', () => $('reorderPrompt').classList.add('d-none'));

  $('recalcYes').addEventListener('click', async () => {
    const btn = $('recalcYes');
    btn.disabled = true;
    btn.textContent = 'Routing…';
    try {
      const track = await editor.routeThrough(state.waypoints.map(w => [w.lat, w.lon]));
      await editor.apply({ track, message: 'Track re-routed through the waypoints in order.' });
      $('reorderPrompt').classList.add('d-none');
    } catch (err) {
      $('reorderMsg').textContent = `Routing failed (${err.message}). Try again?`;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Recalculate';
    }
  });

  // ── Modal ─────────────────────────────────────────────────
  const modal = new bootstrap.Modal($('waypointModal'));
  const FIELDS = ['name', 'desc', 'cmt', 'link', 'ele', 'time', 'sym', 'type', 'lat', 'lon'];
  let editingIdx = null;
  let pendingTrack = null;  // track change to save alongside a new waypoint (e.g. a flattened stop)
  let offTrack = false;     // location came from a search result or a free map click, not the track
  let osmElementUrl = null; // OSM feature chosen by "OSM lookup", linked in place of the bare location
  let preview = false;      // wide modal with a map of the location beside the form

  function setPreview(on) {
    preview = on;
    $('waypointDialog').classList.toggle('modal-xl', on);
    $('wpPreviewCol').classList.toggle('d-none', !on);
  }

  // Offer to re-route from the previous waypoint when a new waypoint is placed off the track.
  function updateReroute() {
    const offer = editingIdx === null && offTrack && state.waypoints.length > 0;
    $('rerouteRow').classList.toggle('d-none', !offer);
    if (offer) $('rerouteFrom').textContent = state.waypoints[state.waypoints.length - 1].name || 'the previous waypoint';
  }

  function showLocation(error = '') {
    const el = $('wpLocation');
    const lat = parseFloat($('wp-lat').value), lon = parseFloat($('wp-lon').value);
    el.classList.toggle('text-danger', !!error);
    const located = !isNaN(lat) && !isNaN(lon);
    el.textContent = error || (located ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : 'No location yet');
    $('wpOsmLink').classList.toggle('d-none', !located);
    if (located) $('wpOsmLink').href = osmElementUrl || osmLookup.mapUrl(lat, lon);
    if (preview && $('waypointModal').classList.contains('show')) waypointPreview.show(lat, lon);
  }

  function resetOsm() {
    osmElementUrl = null;
    $('wpOsmStatus').classList.add('d-none');
    $('wpOsmResults').classList.add('d-none');
  }

  function fill(wp) {
    FIELDS.forEach(f => { $(`wp-${f}`).value = wp[f] ?? ''; });
    $('wp-name').classList.remove('is-invalid');
    resetOsm();
    showLocation();
  }

  function read() {
    const wp = Object.fromEntries(FIELDS.map(f => [f, $(`wp-${f}`).value.trim()]));
    return {
      ...wp,
      ele: wp.ele === '' ? null : parseFloat(wp.ele),
      time: wp.time || null,
      lat: parseFloat(wp.lat),
      lon: parseFloat(wp.lon),
    };
  }

  // A chosen search result sets the location; a "find nearby" result also names and types the waypoint.
  function pickPlace(place) {
    $('wp-lat').value = place.lat;
    $('wp-lon').value = place.lon;
    $('wp-ele').value = '';
    $('wp-time').value = '';
    resetOsm();
    if (place.sym || !$('wp-name').value.trim()) $('wp-name').value = place.name;
    if (place.sym) $('wp-sym').value = place.sym;
    offTrack = true;
    updateReroute();
    showLocation();
    $('wp-name').focus();
  }

  function show({ title, deletable, search }) {
    $('waypointModalLabel').textContent = title;
    $('wpDelete').classList.toggle('d-none', !deletable);
    $('placeSearch').classList.toggle('d-none', !search);
    if (search) placeSearch.reset(pickPlace);
    updateReroute();
    modal.show();
  }

  // point may be null when the location is still to be found by search or picked on the map.
  function openAdd(point, { track = null, title = 'Add Waypoint', search = false, withMap = false } = {}) {
    editingIdx = null;
    setPreview(withMap);
    pendingTrack = track;
    offTrack = false;
    $('wpReroute').checked = true;
    fill(point || {});
    show({ title, deletable: false, search });
  }

  function openEdit(i) {
    editingIdx = i;
    setPreview(false);
    pendingTrack = null;
    offTrack = false;
    fill(state.waypoints[i]);
    show({ title: 'Edit Waypoint', deletable: true, search: false });
  }

  // ── OSM lookup ────────────────────────────────────────────
  function osmStatus(text, isError = false) {
    const el = $('wpOsmStatus');
    el.textContent = text;
    el.classList.toggle('text-danger', isError);
    el.classList.remove('d-none');
  }

  // A chosen OSM feature fills the fields it has data for; the location stays where it is.
  function applyOsm(c) {
    $('wp-name').value = c.name;
    $('wp-name').classList.remove('is-invalid');
    if (c.sym) $('wp-sym').value = c.sym;
    if (c.type) $('wp-type').value = c.type;
    if (c.desc) $('wp-desc').value = c.desc;
    if (c.link) $('wp-link').value = c.link;
    if (c.ele != null && !$('wp-ele').value) $('wp-ele').value = c.ele;
    osmElementUrl = c.osmUrl;
    $('wpOsmResults').classList.add('d-none');
    osmStatus(`Filled from OSM: ${c.label}`);
    showLocation();
  }

  function showOsmResults(candidates) {
    const box = $('wpOsmResults');
    box.innerHTML = '';
    candidates.forEach(c => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'list-group-item list-group-item-action small py-1 d-flex justify-content-between';
      b.innerHTML = `<span>${esc(c.label)}</span><span class="text-muted ms-2 text-nowrap">${Math.round(c.distanceM)} m</span>`;
      b.addEventListener('click', () => applyOsm(c));
      box.appendChild(b);
    });
    box.classList.remove('d-none');
  }

  // With a name, look that name up near the waypoint; without one, list named places around it.
  $('wpOsmLookup').addEventListener('click', async () => {
    const lat = parseFloat($('wp-lat').value), lon = parseFloat($('wp-lon').value);
    if (isNaN(lat) || isNaN(lon)) { osmStatus('Set a location first: search for a place or pick it on the map.', true); return; }
    const name = $('wp-name').value.trim();
    const btn = $('wpOsmLookup');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
    $('wpOsmResults').classList.add('d-none');
    try {
      const candidates = await osmLookup.find(name, lat, lon);
      const radius = `${config.osm_lookup_radius_m} m`;
      if (!candidates.length) {
        osmStatus(name ? `No OSM feature named "${name}" within ${radius}.` : `No named places within ${radius}.`);
        return;
      }
      osmStatus(`${candidates.length} match${candidates.length === 1 ? '' : 'es'} on OSM — pick one:`);
      showOsmResults(candidates);
    } catch (err) {
      osmStatus(`OSM lookup failed (${err.message}). Check your connection.`, true);
    } finally {
      btn.disabled = false;
      btn.textContent = 'OSM lookup';
    }
  });

  $('waypointModal').addEventListener('shown.bs.modal', () => {
    const searching = !$('placeSearch').classList.contains('d-none') && !$('wp-name').value;
    $(searching ? 'placeQuery' : 'wp-name').focus();
    if (preview) waypointPreview.show(parseFloat($('wp-lat').value), parseFloat($('wp-lon').value));
  });

  $('wpSave').addEventListener('click', async () => {
    const wp = read();
    if (!wp.name) { $('wp-name').classList.add('is-invalid'); return; }
    if (isNaN(wp.lat) || isNaN(wp.lon)) { showLocation('Location required: search for a place or pick it on the map.'); return; }
    let track = pendingTrack;
    let note = '';
    if (!$('rerouteRow').classList.contains('d-none') && $('wpReroute').checked) {
      const prev = state.waypoints[state.waypoints.length - 1];
      const saveBtn = $('wpSave');
      saveBtn.disabled = true;
      saveBtn.textContent = 'Routing…';
      try {
        const route = await editor.routeThrough([[prev.lat, prev.lon], [wp.lat, wp.lon]]);
        track = trackAlgorithms.spliceRoute(state.track, prev, wp, route);
        note = ` Track re-routed from "${prev.name}".`;
      } catch (err) {
        showLocation(`Routing failed (${err.message}). Untick re-route to save without it.`);
        return;
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
      }
    }
    const waypoints = [...state.waypoints];
    if (editingIdx === null) waypoints.push(wp);
    else waypoints[editingIdx] = wp;
    pendingTrack = null;
    modal.hide();
    const verb = editingIdx === null ? 'Added' : 'Saved';
    await editor.apply({ waypoints, track: track || undefined, message: `${verb} waypoint "${wp.name}".${note}` });
  });

  $('wpDelete').addEventListener('click', async () => {
    if (editingIdx === null) return;
    const name = state.waypoints[editingIdx].name;
    const waypoints = state.waypoints.filter((_, i) => i !== editingIdx);
    modal.hide();
    await editor.apply({ waypoints, message: `Deleted waypoint "${name}".` });
  });

  // ── Picking a location on the map ─────────────────────────
  // "Pick on map" hides the modal, keeping what was typed, and reopens it with the clicked location.
  let picking = null;  // {form, editingIdx, pendingTrack, search, title, deletable, preview} while picking

  function setPicking(next) {
    picking = next;
    $('addWpHint').classList.toggle('d-none', !next);
    map.getContainer().style.cursor = next ? 'crosshair' : '';
  }

  function nearestTrackPoint(lat, lon) {
    let best = null, minD = Infinity;
    for (const p of state.track) {
      if (p._break) continue;
      const d = (p.lat - lat) ** 2 + (p.lon - lon) ** 2;
      if (d < minD) { minD = d; best = p; }
    }
    return best;
  }

  function placeAt(point, isOffTrack) {
    const p = picking;
    setPicking(null);
    if (!p) { openAdd(point); return; }
    editingIdx = p.editingIdx;
    pendingTrack = p.pendingTrack;
    offTrack = isOffTrack;
    setPreview(p.preview);
    fill({ ...p.form, lat: point.lat, lon: point.lon, ele: point.ele ?? null, time: point.time ?? null });
    $('waypointModalLabel').textContent = p.title;
    $('wpDelete').classList.toggle('d-none', !p.deletable);
    $('placeSearch').classList.toggle('d-none', !p.search);
    updateReroute();
    modal.show();
  }

  $('wpPickMap').addEventListener('click', e => {
    e.preventDefault();
    setPicking({
      form: read(), editingIdx, pendingTrack,
      search: !$('placeSearch').classList.contains('d-none'),
      title: $('waypointModalLabel').textContent,
      deletable: !$('wpDelete').classList.contains('d-none'),
      preview,
    });
    modal.hide();
  });

  $('addWaypointBtn').addEventListener('click', () => {
    setPicking(null);
    openAdd(null, { search: true });
  });
  $('addWpCancel').addEventListener('click', e => { e.preventDefault(); setPicking(null); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && picking) setPicking(null); });

  // A map click places the waypoint exactly where clicked.
  map.on('click', e => {
    if (picking) placeAt({ lat: e.latlng.lat, lon: e.latlng.lng }, true);
  });

  // A track click snaps to the nearest track point, so the waypoint picks up its elevation and time.
  editor.onTrackClick(e => {
    L.DomEvent.stopPropagation(e);
    placeAt(nearestTrackPoint(e.latlng.lat, e.latlng.lng), false);
  });

  editor.onChange(() => { renderMarkers(); renderList(); });

  return { openAdd };
})();
