// Place search in the waypoint modal: "Find a place" by name (Nominatim) and
// "Find nearby" places of a category around a named place (Overpass).

const placeSearch = (() => {
  const { config } = editor;
  const $ = id => document.getElementById(id);

  // Category -> OSM tags to search, and the waypoint type it maps to.
  const NEARBY = {
    cafe:          { tags: ['amenity=cafe'], sym: 'Coffee' },
    food:          { tags: ['amenity=restaurant', 'amenity=fast_food'], sym: 'Food' },
    fuel:          { tags: ['amenity=fuel'], sym: 'Fuel' },
    accommodation: { tags: ['tourism=hotel', 'tourism=motel', 'tourism=guest_house'], sym: 'Accommodation' },
    scenic:        { tags: ['tourism=viewpoint'], sym: 'Scenic' },
    rest_area:     { tags: ['highway=rest_area', 'amenity=parking'], sym: 'Rest Stop' },
  };

  let onPick = () => {};

  async function geocode(query, limit) {
    const url = `${config.nominatim_url}?q=${encodeURIComponent(query)}&format=json&limit=${limit}`;
    const res = await fetch(url, { headers: { 'Accept-Language': navigator.language || 'en' } });
    if (!res.ok) throw new Error(`Nominatim HTTP ${res.status}`);
    return (await res.json()).map(item => ({
      name: item.name || item.display_name.split(',')[0].trim(),
      label: item.display_name,
      lat: parseFloat(item.lat),
      lon: parseFloat(item.lon),
    }));
  }

  async function findNearby(center, category, radiusM) {
    const clauses = NEARBY[category].tags
      .map(tag => `nwr(around:${radiusM},${center.lat},${center.lon})[${tag}];`).join('');
    const query = `[out:json][timeout:25];(${clauses});out center ${config.nearby_max_results};`;
    const res = await fetch(config.overpass_url, { method: 'POST', body: 'data=' + encodeURIComponent(query) });
    if (!res.ok) throw new Error(`Overpass HTTP ${res.status}`);
    return ((await res.json()).elements || [])
      .filter(el => el.tags?.name)
      .map(el => ({
        name: el.tags.name,
        label: el.tags.name,
        lat: el.lat ?? el.center?.lat,
        lon: el.lon ?? el.center?.lon,
        sym: NEARBY[category].sym,
      }))
      .filter(r => r.lat != null && r.lon != null);
  }

  // ── Results list ──────────────────────────────────────────
  function showMessage(text, isError = false) {
    const box = $('placeResults');
    box.innerHTML = '';
    const div = document.createElement('div');
    div.className = `list-group-item small py-1 ${isError ? 'text-danger' : 'text-muted'}`;
    div.textContent = text;
    box.appendChild(div);
    box.classList.remove('d-none');
  }

  function showResults(results, emptyText) {
    if (!results.length) { showMessage(emptyText); return; }
    const box = $('placeResults');
    box.innerHTML = '';
    results.forEach(r => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'list-group-item list-group-item-action small py-1';
      b.textContent = r.label;
      b.addEventListener('click', () => { box.classList.add('d-none'); onPick(r); });
      box.appendChild(b);
    });
    box.classList.remove('d-none');
  }

  // Run a search with the button showing a spinner; failures are reported in the results list.
  async function withSpinner(button, task) {
    const label = button.textContent;
    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
    try {
      await task();
    } catch (err) {
      showMessage(`Search failed (${err.message}). Check your connection.`, true);
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  }

  function searchPlace() {
    const q = $('placeQuery').value.trim();
    if (!q) return;
    withSpinner($('placeSearchBtn'), async () => showResults(await geocode(q, 5), 'No places found.'));
  }

  function searchNearby() {
    const place = $('nearbyPlace').value.trim();
    if (!place) return;
    withSpinner($('nearbySearchBtn'), async () => {
      const [center] = await geocode(place, 1);
      if (!center) { showMessage(`Couldn't find "${place}".`); return; }
      const results = await findNearby(center, $('nearbyCategory').value, $('nearbyRadius').value);
      showResults(results, `Nothing of that kind within ${$('nearbyRadius').selectedOptions[0].text} of ${center.name}.`);
    });
  }

  function setMode(mode) {
    $('searchModePlace').classList.toggle('active', mode === 'place');
    $('searchModeNearby').classList.toggle('active', mode === 'nearby');
    $('placePanel').classList.toggle('d-none', mode !== 'place');
    $('nearbyPanel').classList.toggle('d-none', mode !== 'nearby');
    $('placeResults').classList.add('d-none');
  }

  $('searchModePlace').addEventListener('click', () => setMode('place'));
  $('searchModeNearby').addEventListener('click', () => setMode('nearby'));
  $('placeSearchBtn').addEventListener('click', searchPlace);
  $('nearbySearchBtn').addEventListener('click', searchNearby);
  $('placeQuery').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); searchPlace(); } });
  $('nearbyPlace').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); searchNearby(); } });

  // Clear inputs and results; pickHandler receives {name, lat, lon, sym?} when a result is chosen.
  function reset(pickHandler) {
    onPick = pickHandler;
    $('placeQuery').value = '';
    $('nearbyPlace').value = '';
    setMode('place');
  }

  return { reset };
})();
