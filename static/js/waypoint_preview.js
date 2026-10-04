// Small OSM map in the waypoint modal showing the waypoint's location against the track.

const waypointPreview = (() => {
  const { state, baseLayer } = editor;
  const algo = trackAlgorithms;
  const ZOOM = 17;
  let map = null, marker = null, trackLayer = null;

  // Leaflet can't size a map inside a hidden modal, so the map is built (and resized) once it's visible.
  function ensureMap() {
    if (map) { map.invalidateSize(); return; }
    map = L.map('wpPreviewMap');
    baseLayer().addTo(map);
  }

  function show(lat, lon) {
    ensureMap();
    if (trackLayer) map.removeLayer(trackLayer);
    trackLayer = L.featureGroup(algo.segments(state.track)
      .filter(s => s.length > 1)
      .map(s => L.polyline(s.map(p => [p.lat, p.lon]), { color: '#3b82f6', weight: 3 }))).addTo(map);
    if (isNaN(lat) || isNaN(lon)) {
      if (marker) { map.removeLayer(marker); marker = null; }
      if (trackLayer.getLayers().length) map.fitBounds(trackLayer.getBounds());
      return;
    }
    if (marker) marker.setLatLng([lat, lon]);
    else marker = L.marker([lat, lon]).addTo(map);
    map.setView([lat, lon], ZOOM);
  }

  return { show };
})();
