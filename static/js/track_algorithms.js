// Pure track geometry: distances, segments, smoothing, stop/gap detection and privacy-zone stripping.
// A track is a flat array of {lat, lon, ele, time} points with {_break: true} markers between segments.

const trackAlgorithms = (() => {
  function haversineM(lat1, lon1, lat2, lon2) {
    const R = 6371000, r = Math.PI / 180;
    const dLat = (lat2 - lat1) * r, dLon = (lon2 - lon1) * r;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function segments(track) {
    const result = [[]];
    for (const p of track) {
      if (p._break) result.push([]);
      else result[result.length - 1].push(p);
    }
    return result.filter(s => s.length);
  }

  function joinSegments(segs) {
    return segs.filter(s => s.length).flatMap((s, i) => (i ? [{ _break: true }, ...s] : s));
  }

  function pointCount(track) {
    return track.filter(p => !p._break).length;
  }

  function distanceKm(track) {
    let m = 0;
    for (let i = 0; i < track.length - 1; i++) {
      const a = track[i], b = track[i + 1];
      if (!a._break && !b._break) m += haversineM(a.lat, a.lon, b.lat, b.lon);
    }
    return m / 1000;
  }

  // Perpendicular distance in degrees, with longitude scaled by cos(latitude) so it isn't
  // exaggerated away from the equator.
  function perpDist(p, a, b) {
    const cosLat = Math.cos(((a.lat + b.lat) / 2) * Math.PI / 180);
    const dx = (b.lon - a.lon) * cosLat, dy = b.lat - a.lat;
    const px = (p.lon - a.lon) * cosLat, py = p.lat - a.lat;
    if (dx === 0 && dy === 0) return Math.hypot(py, px);
    const t = Math.max(0, Math.min(1, (py * dy + px * dx) / (dx * dx + dy * dy)));
    return Math.hypot(py - t * dy, px - t * dx);
  }

  function rdpSegment(points, epsilon) {
    if (points.length <= 2) return [...points];
    const keep = new Uint8Array(points.length);
    keep[0] = keep[points.length - 1] = 1;
    const stack = [[0, points.length - 1]];
    while (stack.length) {
      const [s, e] = stack.pop();
      let maxD = 0, maxI = s;
      for (let i = s + 1; i < e; i++) {
        const d = perpDist(points[i], points[s], points[e]);
        if (d > maxD) { maxD = d; maxI = i; }
      }
      if (maxD > epsilon) { keep[maxI] = 1; stack.push([s, maxI], [maxI, e]); }
    }
    return points.filter((_, i) => keep[i]);
  }

  function smooth(track, epsilon) {
    return joinSegments(segments(track).map(s => rdpSegment(s, epsilon)));
  }

  // Runs of points that stay within radiusM of their first point for at least minDurSec.
  // Indices refer to the flat track; a stop never spans a segment break.
  function detectStops(track, radiusM, minDurSec) {
    const stops = [];
    let i = 0;
    while (i < track.length) {
      const p0 = track[i];
      if (p0._break || !p0.time) { i++; continue; }
      let j = i + 1;
      while (j < track.length && !track[j]._break && track[j].time &&
             haversineM(p0.lat, p0.lon, track[j].lat, track[j].lon) <= radiusM) j++;
      const durSec = j > i + 1 ? (new Date(track[j - 1].time) - new Date(p0.time)) / 1000 : 0;
      if (durSec >= minDurSec) {
        let sLat = 0, sLon = 0, sEle = 0, eCount = 0;
        for (let k = i; k < j; k++) {
          sLat += track[k].lat; sLon += track[k].lon;
          if (track[k].ele != null) { sEle += track[k].ele; eCount++; }
        }
        const n = j - i;
        stops.push({
          startIdx: i, endIdx: j - 1,
          lat: sLat / n, lon: sLon / n, ele: eCount ? sEle / eCount : null,
          time: p0.time, durationSec: durSec, pointCount: n,
        });
        i = j;
      } else {
        i++;
      }
    }
    return stops;
  }

  // Consecutive stops closer than mergeRadiusM are the same place detected as several clusters.
  function mergeNearbyStops(track, stops, mergeRadiusM) {
    const merged = [];
    for (const s of stops) {
      const cur = merged[merged.length - 1];
      const sameSegment = cur && !track.slice(cur.endIdx, s.startIdx).some(p => p._break);
      if (cur && sameSegment && haversineM(cur.lat, cur.lon, s.lat, s.lon) <= mergeRadiusM) {
        const n = cur.pointCount + s.pointCount;
        merged[merged.length - 1] = {
          startIdx: cur.startIdx, endIdx: s.endIdx,
          lat: (cur.lat * cur.pointCount + s.lat * s.pointCount) / n,
          lon: (cur.lon * cur.pointCount + s.lon * s.pointCount) / n,
          ele: cur.ele != null && s.ele != null
            ? (cur.ele * cur.pointCount + s.ele * s.pointCount) / n
            : (cur.ele ?? s.ele),
          time: cur.time,
          durationSec: cur.durationSec + s.durationSec,
          pointCount: n,
        };
      } else {
        merged.push({ ...s });
      }
    }
    return merged;
  }

  // Replace a stop with its centre point. The range is widened to neighbouring points that are
  // also within radiusM of the centre, otherwise they would re-form a stop around the new point.
  function flattenStop(track, stop, radiusM) {
    const near = p => p && !p._break && haversineM(p.lat, p.lon, stop.lat, stop.lon) <= radiusM;
    let start = stop.startIdx, end = stop.endIdx;
    while (near(track[start - 1])) start--;
    while (near(track[end + 1])) end++;
    return [
      ...track.slice(0, start),
      { lat: stop.lat, lon: stop.lon, ele: stop.ele, time: stop.time },
      ...track.slice(end + 1),
    ];
  }

  // Consecutive points at least minKm apart: usually a GPS dropout.
  function detectGaps(track, minKm) {
    const gaps = [];
    for (let i = 0; i < track.length - 1; i++) {
      const a = track[i], b = track[i + 1];
      if (a._break || b._break) continue;
      const km = haversineM(a.lat, a.lon, b.lat, b.lon) / 1000;
      if (km < minKm) continue;
      let speedKmh = null;
      if (a.time && b.time) {
        const hours = (new Date(b.time) - new Date(a.time)) / 3600000;
        if (hours > 0) speedKmh = km / hours;
      }
      gaps.push({ idx: i, km, speedKmh, time: a.time, from: a, to: b });
    }
    return gaps;
  }

  function inZone(p, zone) {
    return haversineM(p.lat, p.lon, zone.lat, zone.lon) <= zone.radius_km * 1000;
  }

  // Remove in-zone points, splitting the track where they were so no line is drawn across the zone.
  function stripZone(track, zone) {
    return joinSegments(segments(track).flatMap(seg => {
      const pieces = [[]];
      for (const p of seg) {
        if (inZone(p, zone)) pieces.push([]);
        else pieces[pieces.length - 1].push(p);
      }
      return pieces;
    }));
  }

  function nearestIndex(track, lat, lon) {
    let best = -1, minD = Infinity;
    track.forEach((p, i) => {
      if (p._break) return;
      const d = (p.lat - lat) ** 2 + (p.lon - lon) ** 2;
      if (d < minD) { minD = d; best = i; }
    });
    return best;
  }

  // Replace the track from the point nearest `from` up to the point nearest `to` with a routed line
  // (if `to` lies earlier along the track, the route is inserted at `from`). With no track, the route is the track.
  function spliceRoute(track, from, to, route) {
    if (!pointCount(track)) return route;
    const fromIdx = nearestIndex(track, from.lat, from.lon);
    const toIdx = nearestIndex(track, to.lat, to.lon);
    return [...track.slice(0, fromIdx), ...route, ...track.slice(Math.max(fromIdx, toIdx) + 1)];
  }

  return {
    haversineM, segments, joinSegments, pointCount, distanceKm, smooth,
    detectStops, mergeNearbyStops, flattenStop, detectGaps, inZone, stripZone, spliceRoute,
  };
})();
