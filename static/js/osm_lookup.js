// OSM lookup for the waypoint modal: find named features near the waypoint (Overpass)
// and turn their tags into waypoint fields; plus openstreetmap.org links for editing.

const osmLookup = (() => {
  const { config } = editor;

  // OSM tag -> waypoint type, checked in order; the first match wins.
  const SYM_BY_TAG = [
    ['amenity', ['fuel', 'charging_station'], 'Fuel'],
    ['amenity', ['cafe'], 'Coffee'],
    ['amenity', ['restaurant', 'fast_food', 'pub', 'bar', 'food_court', 'ice_cream'], 'Food'],
    ['shop', ['bakery'], 'Food'],
    ['tourism', ['hotel', 'motel', 'guest_house', 'hostel', 'camp_site', 'caravan_site', 'chalet'], 'Accommodation'],
    ['tourism', ['viewpoint', 'attraction'], 'Scenic'],
    ['natural', ['peak', 'waterfall'], 'Scenic'],
    ['highway', ['rest_area', 'services'], 'Rest Stop'],
    ['amenity', ['parking', 'toilets'], 'Rest Stop'],
  ];
  const CATEGORY_KEYS = ['amenity', 'tourism', 'shop', 'leisure', 'natural', 'historic', 'highway'];

  // Escape for an Overpass regex, then for the double-quoted QL string that holds it.
  const regexLiteral = text => text
    .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"');

  // Equirectangular approximation; plenty accurate within a lookup radius.
  const distanceM = (a, lat, lon) => {
    const k = Math.cos(lat * Math.PI / 180);
    return Math.hypot(a.lat - lat, (a.lon - lon) * k) * 111320;
  };

  function toWaypoint(el) {
    const t = el.tags;
    const sym = SYM_BY_TAG.find(([key, values]) => values.includes(t[key]))?.[2] || '';
    const categoryKey = CATEGORY_KEYS.find(k => t[k]);
    const street = [t['addr:housenumber'], t['addr:street']].filter(Boolean).join(' ');
    const address = [street, t['addr:suburb'] || t['addr:city'] || t['addr:place'], t['addr:postcode']]
      .filter(Boolean).join(', ');
    const desc = [t.description, address, t.opening_hours && `Hours: ${t.opening_hours}`]
      .filter(Boolean).join('\n');
    const ele = parseFloat(t.ele);
    return {
      name: t.name,
      sym,
      type: categoryKey ? t[categoryKey].replace(/_/g, ' ') : '',
      desc,
      link: t.website || t['contact:website'] || t.url || '',
      ele: isNaN(ele) ? null : ele,
      osmUrl: elementUrl(el),
    };
  }

  // Named features near (lat, lon) as waypoint candidates ({...fields, label, distanceM}), best first.
  // With a name, features whose name contains it (exact matches first); without one, named
  // points of interest (not plain roads), nearest first.
  async function find(name, lat, lon) {
    const around = `nwr(around:${config.osm_lookup_radius_m},${lat},${lon})`;
    const filter = name
      ? `${around}["name"~"${regexLiteral(name)}",i];`
      : `(${around}["name"][~"^(${CATEGORY_KEYS.filter(k => k !== 'highway').join('|')})$"~"."];` +
        `${around}["name"][highway~"^(rest_area|services)$"];);`;
    const query = `[out:json][timeout:25];${filter}out center tags;`;
    const res = await fetch(config.overpass_url, { method: 'POST', body: 'data=' + encodeURIComponent(query) });
    if (!res.ok) throw new Error(`Overpass HTTP ${res.status}`);
    const wanted = name.toLowerCase();
    return ((await res.json()).elements || [])
      .map(el => ({ el, lat: el.lat ?? el.center?.lat, lon: el.lon ?? el.center?.lon }))
      .filter(c => c.lat != null && c.lon != null)
      .map(c => ({ ...c, exact: c.el.tags.name.toLowerCase() === wanted, distanceM: distanceM(c, lat, lon) }))
      .sort((a, b) => b.exact - a.exact || a.distanceM - b.distanceM)
      .slice(0, config.nearby_max_results)
      .map(c => {
        const wp = toWaypoint(c.el);
        return { ...wp, distanceM: c.distanceM, label: [wp.name, wp.type].filter(Boolean).join(' — ') };
      });
  }

  const elementUrl = el => `${config.osm_url}/${el.type}/${el.id}`;
  const mapUrl = (lat, lon) => `${config.osm_url}/?mlat=${lat}&mlon=${lon}#map=19/${lat}/${lon}`;

  return { find, mapUrl };
})();
