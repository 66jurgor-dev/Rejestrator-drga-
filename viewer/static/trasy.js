const message = document.querySelector('#message');
const routeDetails = document.querySelector('#route-details');
const routeList = document.querySelector('#route-list');
const reloadButton = document.querySelector('#reload');
const saveGpxButton = document.querySelector('#save-gpx');
const profileTitle = document.querySelector('#profile-title');
const profileSvg = document.querySelector('#elevation-profile');
const profileEmpty = document.querySelector('#profile-empty');
const profileReadout = document.querySelector('#profile-readout');
const heartRateSvg = document.querySelector('#heart-rate-chart');
const shakeSvg = document.querySelector('#shake-chart');
const wheelSpeedSvg = document.querySelector('#speed-chart');
const heartRateReadout = document.querySelector('#heart-rate-readout');
const heartRateCalories = document.querySelector('#heart-rate-calories');
const shakeReadout = document.querySelector('#shake-readout');
const wheelSpeedReadout = document.querySelector('#speed-readout');
const shakeWindowButtons = [...document.querySelectorAll('[data-shake-window]')];
const mergeGpxInput = document.querySelector('#merge-gpx');
const mergeCsvInput = document.querySelector('#merge-csv');
const mergeSubmit = document.querySelector('#merge-submit');
const mergeResult = document.querySelector('#merge-result');
const sumRoutes = document.querySelector('#sum-routes');
const sumDistance = document.querySelector('#sum-distance');
const avgDistance = document.querySelector('#avg-distance');
const sumAscent = document.querySelector('#sum-ascent');
const sumDuration = document.querySelector('#sum-duration');
const avgDuration = document.querySelector('#avg-duration');
const sumSpeed = document.querySelector('#sum-speed');

const SVG_NS = 'http://www.w3.org/2000/svg';
const COLORS = ['#159447', '#f2cf18', '#f58b24', '#df2f2f', '#111111', '#3166d6', '#8e44ad', '#008c99'];
const OLD_GPX_COLOR = '#1d66d6';
const OLD_GPX_HOVER_COLOR = '#df2f2f';
const SELECTED_COLOR = '#df2f2f';
const FALLBACK_SURFACE_COLORS = {
  asfalt: '#8a8a8a',
  'asfalt/bita': '#ffe100',
  bita: '#ffe100',
  szuter: '#ff9b00',
  'żwir': '#d9b928',
  zwir: '#d9b928',
  piach: '#ff00eb',
  piasek: '#ff00eb',
  ziemia: '#8b5a2b',
  błoto: '#af7119',
  bloto: '#af7119',
  trawa: '#55ff00',
  korzenie: '#7b3f00',
  kamyki: '#ff6e00',
  kamyczki: '#ff6e00',
  kamienie: '#ff0000',
  bruk: '#8e44ad',
  kostka: '#8e44ad',
  'płyty': '#607d8b',
  plyty: '#607d8b',
  'skały': '#000000',
  skaly: '#000000',
  nieznana: '#7a8581'
};

let map;
let routeLayer;
let waypointLayer;
let routes = [];
let summary = {};
let selectedRoute = null;
let selectedRouteLayers = [];
let routeLayersById = new Map();
let profileMarker = null;
let profileState = null;
let shakeWindowMeters = 30;

function showMessage(text, type = '') {
  message.className = `message ${type}`.trim();
  message.textContent = text;
}

function showMergeResult(text, type = '') {
  mergeResult.hidden = false;
  mergeResult.className = `merge-result ${type}`.trim();
  mergeResult.textContent = text;
}

function ensureMap() {
  if (map) return;
  if (!window.L) throw new Error('Nie udało się wczytać mapy. Sprawdź połączenie z internetem.');
  map = L.map('map', { zoomControl: true });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);
  routeLayer = L.layerGroup().addTo(map);
  waypointLayer = L.layerGroup().addTo(map);
}

function routeStatsHtml(route) {
  const stats = route.stats || {};
  const source = route.kind === 'gpxold' ? 'Zwykły GPX' : 'GPXNAV';
  const displayName = route.display_name || route.file || route.name;
  return `
    <dl class="route-stats">
      <div><dt>Nazwa</dt><dd>${escapeHtml(displayName)}</dd></div>
      <div><dt>Typ</dt><dd>${source}</dd></div>
      <div><dt>Długość trasy</dt><dd>${formatDistance(stats.distance_km)}</dd></div>
      <div><dt>Wznios</dt><dd>${formatMeters(stats.ascent_m)}</dd></div>
      <div><dt>Spadek</dt><dd>${formatMeters(stats.descent_m)}</dd></div>
      <div><dt>Czas przejazdu</dt><dd>${formatDuration(stats.duration_seconds)}</dd></div>
      <div><dt>Średnia prędkość</dt><dd>${formatSpeed(stats.average_speed_kmh)}</dd></div>
      <div><dt>Waypointy</dt><dd>${route.waypoints?.length || 0}</dd></div>
    </dl>
  `;
}

function showWaypoints(route) {
  waypointLayer.clearLayers();
  (route.waypoints || []).forEach((waypoint, index) => {
    const name = waypoint.name || `Waypoint ${index + 1}`;
    const marker = L.circleMarker([waypoint.lat, waypoint.lon], {
      radius: 7,
      color: '#ffffff',
      weight: 2,
      fillColor: '#7b2cbf',
      fillOpacity: .95,
      pane: 'markerPane'
    }).addTo(waypointLayer);
    marker.bindTooltip(escapeHtml(name), {
      direction: 'top',
      offset: [0, -6],
      opacity: .95
    });
    const details = [
      waypoint.description,
      waypoint.comment && waypoint.comment !== waypoint.description ? waypoint.comment : '',
      waypoint.ele === null ? '' : `Wysokość: ${formatProfileNumber(waypoint.ele, 0)} m`,
      waypoint.symbol ? `Symbol: ${waypoint.symbol}` : '',
      waypoint.type ? `Typ: ${waypoint.type}` : ''
    ].filter(Boolean);
    marker.bindPopup(
      `<strong>${escapeHtml(name)}</strong>${details.map((item) => `<div>${escapeHtml(item)}</div>`).join('')}`
    );
  });
}

function showRouteDetails(route) {
  if (!route || route.error) {
    routeDetails.className = 'route-details empty';
    routeDetails.textContent = route?.error || 'Kliknij trasę na mapie.';
    return;
  }
  routeDetails.className = 'route-details';
  routeDetails.innerHTML = routeStatsHtml(route);
}

function clearRouteDetails() {
  routeDetails.className = 'route-details empty';
  routeDetails.textContent = 'Kliknij trasę na mapie.';
}

function formatRouteDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'data nieznana';
  return new Intl.DateTimeFormat('pl-PL', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function renderRouteList() {
  routeList.innerHTML = '';
  routes.forEach((route) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = [
      'route-list-button',
      route.has_full_telemetry ? 'full-telemetry' : '',
      route.error ? 'error' : '',
      selectedRoute?.id === route.id ? 'selected' : ''
    ].filter(Boolean).join(' ');
    button.disabled = Boolean(route.error || !route.points?.length);

    const name = document.createElement('span');
    name.textContent = route.file || route.display_name || route.name;
    const date = document.createElement('span');
    date.className = 'route-list-date';
    date.textContent = formatRouteDate(route.route_date);
    button.append(name, date);
    button.addEventListener('click', () => {
      const layers = routeLayersById.get(route.id) || [];
      selectRoute(route, layers);
      if (route.points?.length) map.fitBounds(route.points, { padding: [34, 34] });
    });
    routeList.appendChild(button);
  });
}

function formatDistance(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2).replace('.', ',')} km` : 'brak danych';
}

function formatMeters(value) {
  return Number.isFinite(Number(value)) ? `${Math.round(Number(value))} m` : 'brak danych';
}

function formatSpeed(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(1).replace('.', ',')} km/h` : 'brak danych';
}

function formatDuration(seconds) {
  const total = Number(seconds);
  if (!Number.isFinite(total) || total <= 0) return 'brak danych';
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = Math.floor(total % 60);
  if (hours > 0) return `${hours} h ${String(minutes).padStart(2, '0')} min`;
  if (minutes > 0) return `${minutes} min ${String(secs).padStart(2, '0')} s`;
  return `${secs} s`;
}

function formatProfileNumber(value, digits = 1) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits).replace('.', ',') : '—';
}

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value || '';
  return div.innerHTML;
}

function haversineKm(first, second) {
  const radians = (value) => value * Math.PI / 180;
  const phi1 = radians(first[0]);
  const phi2 = radians(second[0]);
  const dPhi = phi2 - phi1;
  const dLambda = radians(second[1] - first[1]);
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function cumulativeKm(points) {
  const distances = [0];
  for (let index = 1; index < points.length; index += 1) {
    distances.push(distances[index - 1] + haversineKm(points[index - 1], points[index]));
  }
  return distances;
}

function pointAtKm(points, distances, distanceKm) {
  const routeLength = distances[distances.length - 1] || 0;
  const target = Math.max(0, Math.min(routeLength, Number(distanceKm)));
  let low = 0;
  let high = distances.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (distances[middle] < target) low = middle + 1;
    else high = middle;
  }
  if (low === 0) return points[0];
  const before = low - 1;
  const span = distances[low] - distances[before];
  const ratio = span ? (target - distances[before]) / span : 0;
  return [
    points[before][0] + (points[low][0] - points[before][0]) * ratio,
    points[before][1] + (points[low][1] - points[before][1]) * ratio
  ];
}

function routeSlice(points, distances, fromKm, toKm) {
  const routeLength = distances[distances.length - 1] || 0;
  const start = Math.max(0, Math.min(Number(fromKm), Number(toKm), routeLength));
  const end = Math.max(0, Math.min(Math.max(Number(fromKm), Number(toKm)), routeLength));
  if (end <= start) return [];
  const sliced = [pointAtKm(points, distances, start)];
  for (let index = 1; index < points.length - 1; index += 1) {
    if (distances[index] > start && distances[index] < end) sliced.push(points[index]);
  }
  sliced.push(pointAtKm(points, distances, end));
  return sliced;
}

function surfaceTypeKey(value) {
  const key = String(value || 'nieznana').trim().toLowerCase();
  const aliases = {
    'asfalt/bita': 'bita',
    'asfalt bita': 'bita',
    'asfalt-bita': 'bita',
    'asfalt_bita': 'bita',
    kamyczki: 'kamyki',
    piach: 'piasek',
    skaly: 'skaly',
    bloto: 'bloto'
  };
  return aliases[key] || key;
}

function surfaceColor(segment, routeIndex) {
  const key = surfaceTypeKey(segment.type);
  return FALLBACK_SURFACE_COLORS[key] || segment.color || COLORS[routeIndex % COLORS.length];
}

function highlightLayers(layers, highlighted, selected = false) {
  layers.forEach((item) => {
    item.layer.setStyle({
      color: selected ? (item.selectedColor || SELECTED_COLOR) : highlighted && item.highlightColor ? item.highlightColor : item.normalColor,
      weight: selected ? item.selectedWeight : highlighted ? item.highlightWeight : item.normalWeight,
      opacity: highlighted || selected ? 1 : item.normalOpacity
    });
  });
}

function bringRouteToFront(layers) {
  layers.forEach((item) => {
    if (typeof item.layer.bringToFront === 'function') {
      item.layer.bringToFront();
    }
  });
  if (profileMarker && typeof profileMarker.bringToFront === 'function') {
    profileMarker.bringToFront();
  }
}

function isSelectedRoute(route) {
  return selectedRoute && selectedRoute.id === route.id;
}

function updateSummaryPanel() {
  sumRoutes.textContent = summary.routes ?? 0;
  sumDistance.textContent = formatDistance(summary.distance_km);
  avgDistance.textContent = formatDistance(summary.average_distance_km);
  sumAscent.textContent = formatMeters(summary.ascent_m);
  sumDuration.textContent = formatDuration(summary.duration_seconds);
  avgDuration.textContent = formatDuration(summary.average_duration_seconds);
  sumSpeed.textContent = formatSpeed(summary.average_speed_kmh);
}

function clearProfile() {
  profileSvg.innerHTML = '';
  heartRateSvg.innerHTML = '';
  shakeSvg.innerHTML = '';
  wheelSpeedSvg.innerHTML = '';
  profileState = null;
  profileTitle.textContent = 'Kliknij trasę na mapie, aby wyświetlić profil.';
  profileEmpty.hidden = false;
  profileEmpty.textContent = 'Brak wybranej trasy';
  profileReadout.textContent = 'Kąt: —';
  heartRateReadout.textContent = '— bpm';
  heartRateCalories.textContent = 'Mężczyzna 83 kg: — kcal';
  shakeReadout.textContent = '— / 100';
  wheelSpeedReadout.textContent = '— km/h';
  if (profileMarker) {
    profileMarker.remove();
    profileMarker = null;
  }
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function profilePointToScreen(point, bounds) {
  const x = bounds.left + ((point.km - bounds.minKm) / (bounds.maxKm - bounds.minKm || 1)) * bounds.width;
  const y = bounds.top + (1 - ((point.ele - bounds.minEle) / (bounds.maxEle - bounds.minEle || 1))) * bounds.height;
  return { x, y };
}

function elevationAtKm(profile, targetKm) {
  if (!profile.length) return null;
  if (targetKm <= profile[0].km) return profile[0];
  if (targetKm >= profile[profile.length - 1].km) return profile[profile.length - 1];
  let low = 0;
  let high = profile.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (profile[middle].km < targetKm) low = middle + 1;
    else high = middle;
  }
  if (low === 0) return profile[0];
  const before = profile[low - 1];
  const after = profile[low];
  const span = after.km - before.km;
  const ratio = span ? (targetKm - before.km) / span : 0;
  return {
    km: targetKm,
    ele: before.ele + (after.ele - before.ele) * ratio,
    angle: before.angle,
    lat: before.lat + (after.lat - before.lat) * ratio,
    lon: before.lon + (after.lon - before.lon) * ratio
  };
}

function profileSegmentPoints(profile, fromKm, toKm) {
  const start = Math.max(0, Math.min(Number(fromKm), Number(toKm)));
  const end = Math.max(start, Math.max(Number(fromKm), Number(toKm)));
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return [];
  const points = [];
  const startPoint = elevationAtKm(profile, start);
  if (startPoint) points.push(startPoint);
  profile.forEach((point) => {
    if (point.km > start && point.km < end) points.push(point);
  });
  const endPoint = elevationAtKm(profile, end);
  if (endPoint) points.push(endPoint);
  return points;
}

function drawProfileLine(profile, bounds, route) {
  const segments = (route.segments || [])
    .filter((segment) => Number.isFinite(Number(segment.from_km)) && Number.isFinite(Number(segment.to_km)));

  if (!segments.length) {
    const points = profile
      .map((point) => profilePointToScreen(point, bounds))
      .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
      .join(' ');
    profileSvg.appendChild(svgElement('polyline', {
      points,
      fill: 'none',
      stroke: '#185f50',
      'stroke-width': '3',
      'stroke-linejoin': 'round',
      'stroke-linecap': 'round'
    }));
    return;
  }

  segments.forEach((segment, index) => {
    const points = profileSegmentPoints(profile, Number(segment.from_km), Number(segment.to_km));
    if (points.length < 2) return;
    const screenPoints = points
      .map((point) => profilePointToScreen(point, bounds))
      .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
      .join(' ');
    profileSvg.appendChild(svgElement('polyline', {
      points: screenPoints,
      fill: 'none',
      stroke: surfaceColor(segment, index),
      'stroke-width': '5',
      'stroke-linejoin': 'round',
      'stroke-linecap': 'round'
    }));
  });
}

function drawWalkingOverlay(profile, bounds) {
  let current = [];
  const runs = [];
  profile.forEach((point) => {
    if (point.rideMode === 'prowadzenie') {
      current.push(point);
    } else if (current.length) {
      if (current.length > 1) runs.push(current);
      current = [];
    }
  });
  if (current.length > 1) runs.push(current);

  runs.forEach((run) => {
    const points = run
      .map((point) => profilePointToScreen(point, bounds))
      .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
      .join(' ');
    profileSvg.appendChild(svgElement('polyline', {
      points,
      fill: 'none',
      stroke: '#d52424',
      'stroke-width': '5',
      'stroke-dasharray': '8 6',
      'stroke-linejoin': 'round',
      'stroke-linecap': 'round'
    }));
  });
}

function gradeSegmentColor(kind) {
  if (kind === 'up') return '#c43b2f';
  if (kind === 'down') return '#2468a2';
  return '#3f8b4f';
}

function drawGradeSegments(profile, bounds, segments) {
  const points = profile
    .map((point) => profilePointToScreen(point, bounds))
    .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
    .join(' ');
  profileSvg.appendChild(svgElement('polyline', {
    points,
    fill: 'none',
    stroke: '#2468a2',
    'stroke-width': '4',
    'stroke-linejoin': 'round',
    'stroke-linecap': 'round'
  }));
}

function metricValue(point, key) {
  if (point[key] === null || point[key] === undefined || point[key] === '') return null;
  const value = Number(point[key]);
  return Number.isFinite(value) ? value : null;
}

function metricPointToScreen(point, key, bounds) {
  const value = metricValue(point, key);
  if (value === null) return null;
  const x = bounds.left + ((point.km - bounds.minKm) / (bounds.maxKm - bounds.minKm || 1)) * bounds.width;
  const y = bounds.top + (1 - ((value - bounds.minValue) / (bounds.maxValue - bounds.minValue || 1))) * bounds.height;
  return { x, y };
}

function splitMetricSeries(profile, key) {
  const series = [];
  let current = [];
  profile.forEach((point) => {
    if (metricValue(point, key) !== null) {
      current.push(point);
    } else if (current.length) {
      if (current.length > 1) series.push(current);
      current = [];
    }
  });
  if (current.length > 1) series.push(current);
  return series;
}

function drawMetricChart(svg, profile, key, options, maxKm) {
  svg.innerHTML = '';
  const values = profile.map((point) => metricValue(point, key)).filter((value) => value !== null);
  const bounds = {
    left: 44,
    right: 14,
    top: 10,
    bottom: 24,
    minKm: 0,
    maxKm,
    minValue: 0,
    maxValue: 1
  };
  bounds.width = 900 - bounds.left - bounds.right;
  bounds.height = 130 - bounds.top - bounds.bottom;

  svg.appendChild(svgElement('rect', {
    x: bounds.left,
    y: bounds.top,
    width: bounds.width,
    height: bounds.height,
    fill: '#fffdf8',
    stroke: '#e5ded1'
  }));

  if (!values.length) {
    const empty = svgElement('text', { x: 450, y: 70, 'text-anchor': 'middle', class: 'chart-empty' });
    empty.textContent = 'Brak danych';
    svg.appendChild(empty);
  } else {
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const span = Math.max(options.minSpan || 1, rawMax - rawMin);
    bounds.minValue = options.fixedMin ?? Math.max(options.floor ?? -Infinity, rawMin - span * 0.1);
    bounds.maxValue = options.fixedMax ?? (rawMax + span * 0.1);
    if (bounds.maxValue <= bounds.minValue) bounds.maxValue = bounds.minValue + (options.minSpan || 1);

    for (let index = 0; index <= 3; index += 1) {
      const y = bounds.top + bounds.height * index / 3;
      svg.appendChild(svgElement('line', {
        x1: bounds.left,
        y1: y,
        x2: bounds.left + bounds.width,
        y2: y,
        stroke: '#e7dfd2',
        'stroke-width': '1'
      }));
    }

    splitMetricSeries(profile, key).forEach((series) => {
      const points = series
        .map((point) => metricPointToScreen(point, key, bounds))
        .filter(Boolean)
        .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
        .join(' ');
      svg.appendChild(svgElement('polyline', {
        points,
        fill: 'none',
        stroke: options.color,
        'stroke-width': '3',
        'stroke-linejoin': 'round',
        'stroke-linecap': 'round'
      }));
    });

    const topLabel = svgElement('text', { x: 8, y: bounds.top + 8, fill: '#60736f', 'font-size': '12' });
    topLabel.textContent = options.axisFormat(bounds.maxValue);
    svg.appendChild(topLabel);
    const bottomLabel = svgElement('text', { x: 8, y: bounds.top + bounds.height, fill: '#60736f', 'font-size': '12' });
    bottomLabel.textContent = options.axisFormat(bounds.minValue);
    svg.appendChild(bottomLabel);
  }

  const startLabel = svgElement('text', { x: bounds.left, y: 124, fill: '#60736f', 'font-size': '12' });
  startLabel.textContent = '0 km';
  svg.appendChild(startLabel);
  const endLabel = svgElement('text', { x: 820, y: 124, fill: '#60736f', 'font-size': '12' });
  endLabel.textContent = `${formatProfileNumber(maxKm, 2)} km`;
  svg.appendChild(endLabel);

  const indicator = svgElement('line', {
    x1: 0,
    y1: bounds.top,
    x2: 0,
    y2: bounds.top + bounds.height,
    stroke: '#263238',
    'stroke-width': '1.5'
  });
  svg.appendChild(indicator);
  svg.onmousemove = handleProfileMove;
  svg.onclick = handleProfileMove;
  return { svg, bounds, indicator, key };
}

function drawMetricCharts(profile, shakeProfile, maxKm) {
  return [
    drawMetricChart(heartRateSvg, profile, 'heartRate', {
      color: '#b4235a', floor: 0, minSpan: 10, axisFormat: (value) => `${Math.round(value)}`
    }, maxKm),
    drawMetricChart(shakeSvg, shakeProfile, 'shakeScore', {
      color: '#d96a1b', fixedMin: 0, fixedMax: 100, minSpan: 10, axisFormat: (value) => `${Math.round(value)}`
    }, maxKm),
    drawMetricChart(wheelSpeedSvg, profile, 'wheelSpeed', {
      color: '#2468a2', floor: 0, minSpan: 5, axisFormat: (value) => `${value.toFixed(0)}`
    }, maxKm)
  ];
}

function drawElevationProfile(route) {
  const profile = (route.profile || [])
    .filter((point) => Number.isFinite(Number(point.km)) && Number.isFinite(Number(point.ele)) && Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lon)))
    .map((point) => ({
      km: Number(point.km),
      ele: Number(point.ele),
      angle: Number(point.angle),
      lat: Number(point.lat),
      lon: Number(point.lon),
      heartRate: metricValue(point, 'heart_rate_bpm'),
      shakeScore: metricValue(point, 'shake_score'),
      wheelSpeed: metricValue(point, 'wheel_speed_kmh'),
      rideMode: point.ride_mode === 'prowadzenie' ? 'prowadzenie' : 'jazda'
    }));
  const segments = window.SegmentProcessing.buildSegments(profile, { minimumKm: 0.5 });
  const segmentedProfile = window.SegmentProcessing.segmentedProfile(profile, segments);

  profileSvg.innerHTML = '';
  heartRateSvg.innerHTML = '';
  shakeSvg.innerHTML = '';
  wheelSpeedSvg.innerHTML = '';
  profileState = null;
  profileTitle.textContent = route.display_name || route.file || route.name || 'Wybrana trasa';
  const routeCalories = Number(route.stats?.active_calories_83kg);
  heartRateCalories.textContent = Number.isFinite(routeCalories)
    ? `Mężczyzna 83 kg: ${Math.round(routeCalories)} kcal`
    : 'Mężczyzna 83 kg: brak danych kcal';

  if (profile.length < 2) {
    profileEmpty.hidden = false;
    profileEmpty.textContent = 'Brak danych wysokości dla tej trasy';
    profileReadout.textContent = 'Kąt: —';
    if (profileMarker) {
      profileMarker.remove();
      profileMarker = null;
    }
    return;
  }

  profileEmpty.hidden = true;
  const eleValues = profile.map((point) => point.ele);
  const minEleRaw = Math.min(...eleValues);
  const maxEleRaw = Math.max(...eleValues);
  const padEle = Math.max(8, (maxEleRaw - minEleRaw) * 0.12);
  const bounds = {
    left: 44,
    right: 14,
    top: 18,
    bottom: 28,
    minKm: 0,
    maxKm: Math.max(...profile.map((point) => point.km)),
    minEle: minEleRaw - padEle,
    maxEle: maxEleRaw + padEle
  };
  bounds.width = 900 - bounds.left - bounds.right;
  bounds.height = 190 - bounds.top - bounds.bottom;

  const screenPoints = profile.map((point) => profilePointToScreen(point, bounds));
  const linePoints = screenPoints.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
  const areaPoints = `${bounds.left},${bounds.top + bounds.height} ${linePoints} ${bounds.left + bounds.width},${bounds.top + bounds.height}`;

  profileSvg.appendChild(svgElement('rect', { x: bounds.left, y: bounds.top, width: bounds.width, height: bounds.height, fill: '#fffaf0', stroke: '#e5ded1' }));
  for (let i = 0; i <= 4; i += 1) {
    const y = bounds.top + (bounds.height * i / 4);
    profileSvg.appendChild(svgElement('line', { x1: bounds.left, y1: y, x2: bounds.left + bounds.width, y2: y, stroke: '#e7dfd2', 'stroke-width': '1' }));
  }
  profileSvg.appendChild(svgElement('polygon', { points: areaPoints, fill: 'rgba(24,95,80,.16)' }));
  drawGradeSegments(profile, bounds, segments);
  drawWalkingOverlay(profile, bounds);
  profileSvg.appendChild(svgElement('text', { x: 8, y: bounds.top + 8, fill: '#60736f', 'font-size': '12' })).textContent = `${Math.round(maxEleRaw)} m`;
  profileSvg.appendChild(svgElement('text', { x: 8, y: bounds.top + bounds.height, fill: '#60736f', 'font-size': '12' })).textContent = `${Math.round(minEleRaw)} m`;
  profileSvg.appendChild(svgElement('text', { x: bounds.left, y: 182, fill: '#60736f', 'font-size': '12' })).textContent = '0 km';
  profileSvg.appendChild(svgElement('text', { x: 820, y: 182, fill: '#60736f', 'font-size': '12' })).textContent = `${formatProfileNumber(bounds.maxKm, 2)} km`;

  const indicator = svgElement('line', { x1: 0, y1: bounds.top, x2: 0, y2: bounds.top + bounds.height, stroke: '#df2f2f', 'stroke-width': '2' });
  const dot = svgElement('circle', { cx: 0, cy: 0, r: 5, fill: '#df2f2f', stroke: 'white', 'stroke-width': '2' });
  profileSvg.appendChild(indicator);
  profileSvg.appendChild(dot);

  const metricCharts = drawMetricCharts(segmentedProfile, segmentedProfile, bounds.maxKm);
  profileState = {
    route,
    profile: segmentedProfile,
    shakeProfile: segmentedProfile,
    segments,
    bounds,
    indicator,
    dot,
    metricCharts
  };
  profileSvg.onmousemove = handleProfileMove;
  profileSvg.onclick = handleProfileMove;
  updateProfileIndicator(Math.floor(profile.length / 2));
}

function handleProfileMove(event) {
  if (!profileState) return;
  const sourceSvg = event.currentTarget || profileSvg;
  const rect = sourceSvg.getBoundingClientRect();
  const svgX = ((event.clientX - rect.left) / rect.width) * 900;
  const { profile, bounds } = profileState;
  const ratio = Math.max(0, Math.min(1, (svgX - bounds.left) / bounds.width));
  const targetKm = bounds.minKm + ratio * (bounds.maxKm - bounds.minKm);
  let bestIndex = 0;
  let bestDiff = Infinity;
  profile.forEach((point, index) => {
    const diff = Math.abs(point.km - targetKm);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestIndex = index;
    }
  });
  updateProfileIndicator(bestIndex);
}

function updateProfileIndicator(index) {
  if (!profileState) return;
  const { profile, shakeProfile, bounds, indicator, dot, metricCharts } = profileState;
  const safeIndex = Math.max(0, Math.min(profile.length - 1, index));
  const point = profile[safeIndex];
  const screen = profilePointToScreen(point, bounds);
  indicator.setAttribute('x1', screen.x);
  indicator.setAttribute('x2', screen.x);
  dot.setAttribute('cx', screen.x);
  dot.setAttribute('cy', screen.y);
  const modeLabel = point.rideMode === 'prowadzenie' ? 'Prowadzenie' : 'Jazda';
  const segment = point.segment;
  const segmentKind = segment?.kind === 'up' ? 'podjazd' : (segment?.kind === 'down' ? 'zjazd' : 'równo');
  profileReadout.textContent = segment
    ? `Odcinek ${segment.index}: ${formatProfileNumber(segment.fromKm, 2)}–${formatProfileNumber(segment.toKm, 2)} km · ${segmentKind} ${formatProfileNumber(segment.grade, 1)}% · ${modeLabel}`
    : `Km: ${formatProfileNumber(point.km, 2)} · Wys.: ${formatProfileNumber(point.ele, 0)} m · ${modeLabel}`;
  (metricCharts || []).forEach((chart) => {
    const x = chart.bounds.left + ((point.km - chart.bounds.minKm) / (chart.bounds.maxKm - chart.bounds.minKm || 1)) * chart.bounds.width;
    chart.indicator.setAttribute('x1', x);
    chart.indicator.setAttribute('x2', x);
  });
  heartRateReadout.textContent = point.heartRate === null ? '— bpm' : `${Math.round(point.heartRate)} bpm`;
  const smoothedShake = metricValue(point, 'shakeScore');
  shakeReadout.textContent = smoothedShake === null ? '— / 100' : `${formatProfileNumber(smoothedShake, 1)} / 100`;
  wheelSpeedReadout.textContent = point.wheelSpeed === null ? '— km/h' : `${formatProfileNumber(point.wheelSpeed, 1)} km/h`;

  if (!profileMarker) {
    profileMarker = L.circleMarker([point.lat, point.lon], {
      radius: 8,
      color: '#ffffff',
      weight: 3,
      fillColor: '#df2f2f',
      fillOpacity: .95,
      pane: 'markerPane'
    }).addTo(map);
  } else {
    profileMarker.setLatLng([point.lat, point.lon]);
  }
}

function selectRoute(route, layers) {
  if (selectedRouteLayers.length && (!selectedRoute || selectedRoute.id !== route.id)) {
    highlightLayers(selectedRouteLayers, false, false);
  }
  selectedRoute = route;
  selectedRouteLayers = layers;
  highlightLayers(selectedRouteLayers, true, true);
  bringRouteToFront(selectedRouteLayers);
  showRouteDetails(route);
  showWaypoints(route);
  drawElevationProfile(route);
  bringRouteToFront(selectedRouteLayers);
  saveGpxButton.disabled = false;
  renderRouteList();
  showMessage(`Wybrano trasę: ${route.display_name || route.file || route.name}. Profil jest aktywny, a GPX zapiszesz przyciskiem „Zapisz GPX”.`, 'success');
}

function drawRoutes() {
  ensureMap();
  routeLayer.clearLayers();
  waypointLayer.clearLayers();
  selectedRoute = null;
  selectedRouteLayers = [];
  routeLayersById = new Map();
  saveGpxButton.disabled = true;
  clearRouteDetails();
  clearProfile();
  const bounds = [];
  let visible = 0;

  routes.forEach((route, index) => {
    if (route.error || !route.points?.length) {
      return;
    }
    const routeLayers = [];
    const isOldGpx = route.kind === 'gpxold';
    const baseLayer = L.polyline(route.points, {
      color: isOldGpx ? OLD_GPX_COLOR : '#7a8581',
      weight: isOldGpx ? 6 : 3,
      opacity: isOldGpx ? .9 : .45
    }).addTo(routeLayer);
    routeLayers.push({
      layer: baseLayer,
      normalColor: isOldGpx ? OLD_GPX_COLOR : '#7a8581',
      highlightColor: isOldGpx ? OLD_GPX_HOVER_COLOR : null,
      selectedColor: isOldGpx ? OLD_GPX_HOVER_COLOR : SELECTED_COLOR,
      normalWeight: isOldGpx ? 6 : 3,
      highlightWeight: isOldGpx ? 10 : 5,
      selectedWeight: isOldGpx ? 10 : 6,
      normalOpacity: isOldGpx ? .9 : .45
    });
    baseLayer.on('click', () => selectRoute(route, routeLayers));
    baseLayer.on('mouseover', () => highlightLayers(routeLayers, true, isSelectedRoute(route)));
    baseLayer.on('mouseout', () => highlightLayers(routeLayers, false, isSelectedRoute(route)));

    const distances = cumulativeKm(route.points);
    const segments = route.segments || [];
    segments.forEach((segment) => {
      const line = routeSlice(route.points, distances, Number(segment.from_km), Number(segment.to_km));
      if (line.length < 2) return;
      const segmentColor = surfaceColor(segment, index);
      const layer = L.polyline(line, {
        color: segmentColor,
        weight: 8,
        opacity: .95,
        lineCap: 'round'
      }).addTo(routeLayer);
      layer.on('mouseover', () => highlightLayers(routeLayers, true, isSelectedRoute(route)));
      layer.on('mouseout', () => highlightLayers(routeLayers, false, isSelectedRoute(route)));
      layer.on('click', () => selectRoute(route, routeLayers));
      routeLayers.push({
        layer,
        normalColor: segmentColor,
        highlightColor: null,
        selectedColor: segmentColor,
        normalWeight: 8,
        highlightWeight: 11,
        selectedWeight: 11,
        normalOpacity: .95
      });
    });

    if (!segments.length) {
      baseLayer.setStyle({ color: isOldGpx ? OLD_GPX_COLOR : COLORS[index % COLORS.length], weight: isOldGpx ? 6 : 5, opacity: isOldGpx ? .9 : .8 });
      routeLayers[0].normalColor = isOldGpx ? OLD_GPX_COLOR : COLORS[index % COLORS.length];
    }
    routeLayersById.set(route.id, routeLayers);
    route.points.forEach((point) => bounds.push(point));
    visible += 1;
  });

  document.querySelector('#empty-map').hidden = visible > 0;
  renderRouteList();
  if (bounds.length) map.fitBounds(bounds, { padding: [26, 26] });
  showMessage(visible ? `Wczytano tras: ${visible}. Kliknij trasę, aby ustawić dane i profil pionowy.` : 'Brak plików .gpxnav lub .gpx w katalogach GPXNAV i GPXOLD.', visible ? 'success' : '');
}

async function loadRoutes() {
  reloadButton.disabled = true;
  saveGpxButton.disabled = true;
  showMessage('Wczytuję trasy z katalogów GPXNAV i GPXOLD…');
  try {
    const response = await fetch('/api/routes');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Nie udało się wczytać tras.');
    routes = data.routes || [];
    summary = data.summary || {};
    updateSummaryPanel();
    drawRoutes();
  } catch (error) {
    showMessage(error.message, 'error');
  } finally {
    reloadButton.disabled = false;
  }
}

async function saveRoute(route) {
  if (!route) {
    showMessage('Najpierw kliknij trasę na mapie.', 'error');
    return;
  }
  saveGpxButton.disabled = true;
  const originalButtonText = saveGpxButton.textContent;
  saveGpxButton.textContent = 'Zapisuję...';
  try {
    const response = await fetch(`/api/download/${route.id}`, { method: 'POST' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Nie udało się zapisać pliku GPX.');
  } catch (error) {
    showMessage(error.message, 'error');
  } finally {
    saveGpxButton.textContent = originalButtonText;
    saveGpxButton.disabled = !selectedRoute;
  }
}

async function mergeGpxCsv() {
  const gpxFile = mergeGpxInput.files?.[0];
  const csvFile = mergeCsvInput.files?.[0];
  if (!gpxFile || !csvFile) {
    showMergeResult('Wybierz plik GPX i plik CSV.', 'error');
    return;
  }
  const originalText = mergeSubmit.textContent;
  mergeSubmit.disabled = true;
  mergeSubmit.textContent = 'Łączę...';
  mergeResult.hidden = true;
  try {
    const form = new FormData();
    form.append('gpx', gpxFile);
    form.append('csv', csvFile);
    const response = await fetch('/api/merge-gpx-csv', { method: 'POST', body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Nie udało się połączyć GPX z CSV.');
    showMergeResult(`Zapisano CSV dla sieci: ${data.csv_path}. Zapisano GPXNAV: ${data.gpxnav_path}. Segmenty nawierzchni: ${data.gpxnav_segments}. Dopasowano ${data.matched_rows} z ${data.csv_rows} rekordów, pominięto ${data.skipped_rows}.`, 'success');
    loadRoutes();
  } catch (error) {
    showMergeResult(error.message, 'error');
  } finally {
    mergeSubmit.textContent = originalText;
    mergeSubmit.disabled = false;
  }
}

reloadButton.addEventListener('click', loadRoutes);
saveGpxButton.addEventListener('click', () => saveRoute(selectedRoute));
mergeSubmit.addEventListener('click', mergeGpxCsv);
shakeWindowButtons.forEach((button) => {
  button.addEventListener('click', () => {
    shakeWindowMeters = Number(button.dataset.shakeWindow) || 30;
    shakeWindowButtons.forEach((item) => item.classList.toggle('active', item === button));
    if (selectedRoute) drawElevationProfile(selectedRoute);
  });
});
loadRoutes();
