(function attachShakeProcessing(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ShakeProcessing = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function buildApi() {
  function median(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function buildSmoothedShakeProfile(profile, windowMeters, binMeters = 10, stopThresholdKmh = 0.5) {
    if (!Array.isArray(profile) || !profile.length) return [];
    const maxKm = Math.max(...profile.map((point) => Number(point.km)).filter(Number.isFinite));
    if (!Number.isFinite(maxKm) || maxKm <= 0) return [];
    const binCount = Math.max(1, Math.ceil(maxKm * 1000 / binMeters));
    const samples = Array.from({ length: binCount }, () => []);

    profile.forEach((point) => {
      const km = Number(point.km);
      const shake = Number(point.shakeScore);
      const speed = point.wheelSpeed === null || point.wheelSpeed === undefined
        ? null
        : Number(point.wheelSpeed);
      if (!Number.isFinite(km) || !Number.isFinite(shake)) return;
      if (Number.isFinite(speed) && speed <= stopThresholdKmh) return;
      const index = Math.min(binCount - 1, Math.max(0, Math.floor(km * 1000 / binMeters)));
      samples[index].push(shake);
    });

    const rawBins = samples.map((values) => median(values));
    const requestedBins = Math.max(1, Math.round(Number(windowMeters) / binMeters));
    const leftRadius = Math.floor((requestedBins - 1) / 2);
    const rightRadius = requestedBins - 1 - leftRadius;

    return rawBins.map((rawValue, index) => {
      const km = Math.min(maxKm, (index + 0.5) * binMeters / 1000);
      if (rawValue === null) return { km, shakeScore: null };
      const neighborhood = [];
      for (
        let neighbor = Math.max(0, index - leftRadius);
        neighbor <= Math.min(rawBins.length - 1, index + rightRadius);
        neighbor += 1
      ) {
        if (rawBins[neighbor] !== null) neighborhood.push(rawBins[neighbor]);
      }
      return { km, shakeScore: median(neighborhood) };
    });
  }

  function nearestShakeValue(profile, km) {
    if (!profile.length) return null;
    let low = 0;
    let high = profile.length - 1;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (profile[middle].km < km) low = middle + 1;
      else high = middle;
    }
    const candidates = [profile[low], profile[Math.max(0, low - 1)]];
    const selected = candidates
      .filter(Boolean)
      .sort((a, b) => Math.abs(a.km - km) - Math.abs(b.km - km))[0];
    return selected && Number.isFinite(Number(selected.shakeScore)) ? Number(selected.shakeScore) : null;
  }

  return { buildSmoothedShakeProfile, median, nearestShakeValue };
}));
