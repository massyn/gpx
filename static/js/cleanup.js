// Clean up: one table of detected issues (privacy zones, stops, GPS gaps, smoothing), each with its repair actions.
// Issues are re-detected from the current track after every change, so indices are always fresh.

(() => {
  const { map, state, config, zones, esc } = editor;
  const algo = trackAlgorithms;
  const $ = id => document.getElementById(id);

  // Keys of issues the user chose to ignore this visit.
  const ignored = new Set();
  const coordKey = (kind, p) => `${kind}:${p.lat.toFixed(5)},${p.lon.toFixed(5)}`;

  // A gap with an OSRM suggestion on screen: {key, points}.
  let suggestion = null;

  const zoneCircles = {};
  zones.forEach(z => {
    zoneCircles[z.id] = L.circle([z.lat, z.lon], {
      radius: z.radius_km * 1000, color: '#ff69b4', fillColor: '#ff69b4', fillOpacity: 0.15, weight: 2,
    }).addTo(map).bindTooltip(z.name);
  });

  const overlays = L.layerGroup().addTo(map);  // stop markers, gap highlights, suggested routes
  let issues = [];

  function formatDuration(sec) {
    const m = Math.round(sec / 60);
    return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m` : `${m} min`;
  }

  // ── Detection ─────────────────────────────────────────────
  function detect() {
    const { track, waypoints } = state;
    const found = [];

    zones.forEach(z => {
      const key = `zone:${z.id}`;
      if (ignored.has(key)) return;
      const trackCount = track.filter(p => !p._break && algo.inZone(p, z)).length;
      const wpCount = waypoints.filter(w => algo.inZone(w, z)).length;
      if (trackCount || wpCount) found.push({ kind: 'zone', key, zone: z, trackCount, wpCount });
    });

    const stops = algo.mergeNearbyStops(
      track, algo.detectStops(track, config.stop_radius_m, config.stop_min_duration_sec), config.stop_merge_radius_m,
    );
    stops.forEach(s => {
      const key = coordKey('stop', s);
      // A stop with a waypoint on it has already been dealt with.
      const hasWaypoint = waypoints.some(w => algo.haversineM(w.lat, w.lon, s.lat, s.lon) <= config.stop_radius_m);
      if (!ignored.has(key) && !hasWaypoint) found.push({ kind: 'stop', key, stop: s });
    });

    algo.detectGaps(track, config.gap_min_km).forEach(g => {
      const key = coordKey('gap', g.from);
      if (!ignored.has(key)) found.push({ kind: 'gap', key, gap: g });
    });

    if (!ignored.has('smooth')) {
      const smoothed = algo.smooth(track, config.rdp_epsilon);
      const before = algo.pointCount(track), after = algo.pointCount(smoothed);
      if (before && (before - after) / before * 100 >= config.smooth_min_reduction_pct) {
        found.push({ kind: 'smooth', key: 'smooth', smoothed, before, after });
      }
    }
    return found;
  }

  // ── Rendering ─────────────────────────────────────────────
  const btn = (action, label, style) =>
    `<button class="btn btn-sm btn-${style}" data-action="${action}">${label}</button>`;

  function describe(issue) {
    switch (issue.kind) {
      case 'zone': {
        const parts = [];
        if (issue.trackCount) parts.push(`${issue.trackCount.toLocaleString()} track pt(s)`);
        if (issue.wpCount) parts.push(`${issue.wpCount} waypoint(s)`);
        return {
          title: `Privacy zone: ${esc(issue.zone.name)}`,
          detail: `${parts.join(', ')} inside the ${issue.zone.radius_km} km zone`,
          actions: btn('fix-zone', 'Strip', 'outline-danger') + btn('ignore', 'Ignore', 'outline-secondary'),
        };
      }
      case 'stop': {
        const s = issue.stop;
        const at = s.time ? ` at ${new Date(s.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : '';
        return {
          title: `Stop: ~${formatDuration(s.durationSec)}${at}`,
          detail: `${s.pointCount.toLocaleString()} track points while stationary`,
          actions: btn('stop-waypoint', 'Waypoint', 'outline-amber')
            + btn('stop-flatten', 'Flatten', 'outline-danger') + btn('ignore', 'Ignore', 'outline-secondary'),
        };
      }
      case 'gap': {
        const g = issue.gap;
        const speed = g.speedKmh ? `, ${Math.round(g.speedKmh).toLocaleString()} km/h implied` : '';
        const actions = suggestion?.key === issue.key
          ? btn('gap-accept', 'Accept route', 'amber') + btn('gap-reject', 'Reject', 'outline-secondary')
          : btn('gap-suggest', 'Suggest route', 'outline-amber') + btn('gap-split', 'Split track', 'outline-danger')
            + btn('ignore', 'Ignore', 'outline-secondary');
        return {
          title: `GPS gap: ${g.km.toFixed(1)} km`,
          detail: `Straight-line jump between two points${speed}`,
          actions,
        };
      }
      case 'smooth': {
        const removed = issue.before - issue.after;
        return {
          title: 'Track smoothing',
          detail: `${issue.before.toLocaleString()} → ${issue.after.toLocaleString()} points (−${Math.round(removed / issue.before * 100)}%)`,
          actions: btn('fix-smooth', 'Smooth', 'outline-danger') + btn('ignore', 'Ignore', 'outline-secondary'),
        };
      }
    }
  }

  function drawOverlays() {
    overlays.clearLayers();
    issues.forEach((issue, idx) => {
      if (issue.kind === 'stop') {
        L.circleMarker([issue.stop.lat, issue.stop.lon], {
          radius: 10, color: '#888', fillColor: '#555', fillOpacity: 0.45, weight: 2, dashArray: '5 4',
        }).bindTooltip(`Stop ~${formatDuration(issue.stop.durationSec)}: click to add a waypoint`)
          .on('click', e => { L.DomEvent.stopPropagation(e); run('stop-waypoint', idx); })
          .addTo(overlays);
      } else if (issue.kind === 'gap') {
        const { from, to } = issue.gap;
        L.polyline([[from.lat, from.lon], [to.lat, to.lon]], { color: '#ef4444', weight: 4, dashArray: '2 6' })
          .bindTooltip(`GPS gap ${issue.gap.km.toFixed(1)} km`).addTo(overlays);
      }
    });
    if (suggestion) {
      L.polyline(suggestion.points.map(p => [p.lat, p.lon]), { color: '#f97316', weight: 3, dashArray: '8 4' })
        .addTo(overlays);
    }
  }

  function render() {
    issues = detect();
    if (suggestion && !issues.some(i => i.key === suggestion.key)) suggestion = null;
    drawOverlays();

    $('cleanupCount').textContent = issues.length || '';
    const body = $('cleanupBody');
    if (!issues.length) {
      body.innerHTML = '<p class="text-muted small mb-0 p-3">No issues found.</p>';
      return;
    }
    body.innerHTML = `<table class="table table-hover align-middle mb-0">
      <tbody>${issues.map((issue, idx) => {
        const d = describe(issue);
        return `<tr data-idx="${idx}" style="cursor:pointer">
          <td><div class="fw-semibold">${d.title}</div><div class="text-muted small">${d.detail}</div></td>
          <td class="text-end text-nowrap"><span class="d-inline-flex gap-1">${d.actions}</span></td>
        </tr>`;
      }).join('')}</tbody></table>`;
  }

  // ── Actions ───────────────────────────────────────────────
  function zoomTo(issue) {
    if (issue.kind === 'zone') map.fitBounds(zoneCircles[issue.zone.id].getBounds(), { padding: [40, 40] });
    else if (issue.kind === 'stop') map.setView([issue.stop.lat, issue.stop.lon], 16);
    else if (issue.kind === 'gap') {
      const { from, to } = issue.gap;
      map.fitBounds([[from.lat, from.lon], [to.lat, to.lon]], { padding: [80, 80], maxZoom: 15 });
    }
  }

  async function run(action, idx, button) {
    const issue = issues[idx];
    const { track, waypoints } = state;
    switch (action) {
      case 'ignore':
        ignored.add(issue.key);
        render();
        break;

      case 'fix-zone': {
        const z = issue.zone;
        await editor.apply({
          track: issue.trackCount ? algo.stripZone(track, z) : undefined,
          waypoints: issue.wpCount ? waypoints.filter(w => !algo.inZone(w, z)) : undefined,
          message: `${z.name}: removed ${issue.trackCount + issue.wpCount} point(s).`,
        });
        break;
      }

      case 'stop-waypoint':
        waypointsUi.openAdd(issue.stop, {
          track: algo.flattenStop(track, issue.stop, config.stop_radius_m),
          title: 'Add Waypoint for Stop',
          withMap: true,
        });
        break;

      case 'stop-flatten':
        await editor.apply({
          track: algo.flattenStop(track, issue.stop, config.stop_radius_m),
          message: `Stop flattened (${issue.stop.pointCount} points → 1).`,
        });
        break;

      case 'gap-suggest': {
        zoomTo(issue);
        button.disabled = true;
        button.textContent = 'Routing…';
        try {
          const { from, to } = issue.gap;
          suggestion = { key: issue.key, points: await editor.routeThrough([[from.lat, from.lon], [to.lat, to.lon]]) };
        } catch (err) {
          $('editStatus').textContent = `No route found for that gap (${err.message}).`;
        }
        render();
        break;
      }

      case 'gap-accept': {
        const i = issue.gap.idx;
        const points = suggestion.points;
        suggestion = null;
        await editor.apply({
          track: [...track.slice(0, i + 1), ...points, ...track.slice(i + 1)],
          message: `Gap repaired with ${points.length} routed points.`,
        });
        break;
      }

      case 'gap-reject':
        suggestion = null;
        render();
        break;

      case 'gap-split': {
        const i = issue.gap.idx;
        await editor.apply({
          track: [...track.slice(0, i + 1), { _break: true }, ...track.slice(i + 1)],
          message: 'Track split at the gap.',
        });
        break;
      }

      case 'fix-smooth':
        await editor.apply({
          track: issue.smoothed,
          message: `Smoothed: ${issue.before.toLocaleString()} → ${issue.after.toLocaleString()} points.`,
        });
        break;
    }
  }

  $('cleanupBody').addEventListener('click', e => {
    const row = e.target.closest('tr[data-idx]');
    if (!row) return;
    const idx = +row.dataset.idx;
    const button = e.target.closest('button[data-action]');
    if (button) run(button.dataset.action, idx, button);
    else zoomTo(issues[idx]);
  });

  editor.onChange(render);
})();
