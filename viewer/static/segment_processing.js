(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.SegmentProcessing = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const MIN_SEGMENT_KM = 0.5;
  const SAMPLE_KM = 0.1;
  const SMOOTH_RADIUS_KM = 0.2;
  const MAX_GRADE_DRIFT = 3;
  // Calibrated from labeled, non-transition ML segments in the Turbacz ride.
  // A 10% speed change corresponds to about a 1.63% shake-score change after
  // controlling for the surface class. Five km/h is reachable off-road.
  const SHAKE_REFERENCE_SPEED_KMH = 5;
  const SHAKE_SPEED_EXPONENT = 0.162524;
  const SHAKE_MIN_SPEED_KMH = 3;

  function finite(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function interpolate(profile, km, key) {
    if (!profile.length) return null;
    if (km <= profile[0].km) return finite(profile[0][key]);
    if (km >= profile[profile.length - 1].km) return finite(profile[profile.length - 1][key]);
    let low = 0;
    let high = profile.length - 1;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (profile[middle].km < km) low = middle + 1;
      else high = middle;
    }
    const after = profile[low];
    const before = profile[Math.max(0, low - 1)];
    const first = finite(before[key]);
    const second = finite(after[key]);
    if (first === null || second === null) return first ?? second;
    const span = after.km - before.km;
    const ratio = span > 0 ? (km - before.km) / span : 0;
    return first + (second - first) * ratio;
  }

  function gradeKind(grade) {
    if (grade > 2) return 'up';
    if (grade < -2) return 'down';
    return 'flat';
  }

  function normalizeShakeScore(score, speed) {
    const shake = finite(score);
    const speedKmh = finite(speed);
    if (shake === null || speedKmh === null || speedKmh < SHAKE_MIN_SPEED_KMH) return null;
    const speedRatioCorrection = Math.pow(SHAKE_REFERENCE_SPEED_KMH / speedKmh, SHAKE_SPEED_EXPONENT);
    return Math.max(0, Math.min(100, shake * speedRatioCorrection));
  }

  function weightedAverage(profile, fromKm, toKm, key, resolver = null) {
    let sum = 0;
    let weight = 0;
    for (let index = 1; index < profile.length; index += 1) {
      const left = Math.max(fromKm, profile[index - 1].km);
      const right = Math.min(toKm, profile[index].km);
      const distance = right - left;
      if (distance <= 0) continue;
      const a = resolver ? resolver(profile[index - 1]) : finite(profile[index - 1][key]);
      const b = resolver ? resolver(profile[index]) : finite(profile[index][key]);
      const value = a === null ? b : (b === null ? a : (a + b) / 2);
      if (value === null) continue;
      sum += value * distance;
      weight += distance;
    }
    return weight > 0 ? sum / weight : null;
  }

  function refresh(segment) {
    segment.lengthKm = segment.toKm - segment.fromKm;
    segment.grade = segment.lengthKm > 0
      ? (segment.endEle - segment.startEle) / (segment.lengthKm * 10)
      : 0;
    segment.kind = gradeKind(segment.grade);
    return segment;
  }

  function mergePair(left, right) {
    return refresh({
      fromKm: left.fromKm,
      toKm: right.toKm,
      startEle: left.startEle,
      endEle: right.endEle
    });
  }

  function mergeShortSegments(segments, minimumKm) {
    const result = segments.slice();
    const protectedIndexes = new Set();
    while (result.length > 1) {
      let index = result.findIndex((segment, itemIndex) =>
        segment.lengthKm + 1e-6 < minimumKm && !protectedIndexes.has(itemIndex));
      if (index < 0) break;
      const current = result[index];
      const left = index > 0 ? result[index - 1] : null;
      const right = index < result.length - 1 ? result[index + 1] : null;

      // A climb and a descent are never merged, even when one of them is
      // shorter than the requested minimum. Direction changes are hard edges.
      const compatible = (neighbor) => {
        if (!neighbor) return false;
        if (
          (current.kind === 'up' && neighbor.kind === 'down') ||
          (current.kind === 'down' && neighbor.kind === 'up')
        ) return false;
        return current.kind === neighbor.kind || current.kind === 'flat' || neighbor.kind === 'flat';
      };
      const canMergeLeft = compatible(left);
      const canMergeRight = compatible(right);

      // A short flat saddle between a climb and a descent is retained. Folding
      // it into either side could make a later merge cross the direction edge.
      if (
        current.kind === 'flat' &&
        left && right &&
        ((left.kind === 'up' && right.kind === 'down') ||
         (left.kind === 'down' && right.kind === 'up'))
      ) {
        protectedIndexes.add(index);
        continue;
      }

      if (!canMergeLeft && !canMergeRight) {
        protectedIndexes.add(index);
        continue;
      }
      if (index === 0) {
        result.splice(0, 2, mergePair(result[0], result[1]));
        protectedIndexes.clear();
        continue;
      }
      if (index === result.length - 1) {
        result.splice(index - 1, 2, mergePair(result[index - 1], result[index]));
        protectedIndexes.clear();
        continue;
      }
      if (!canMergeLeft) {
        result.splice(index, 2, mergePair(current, right));
        protectedIndexes.clear();
        continue;
      }
      if (!canMergeRight) {
        result.splice(index - 1, 2, mergePair(left, current));
        protectedIndexes.clear();
        continue;
      }
      const leftPenalty = (left.kind === current.kind ? 0 : 20) + Math.abs(left.grade - current.grade);
      const rightPenalty = (right.kind === current.kind ? 0 : 20) + Math.abs(right.grade - current.grade);
      if (leftPenalty <= rightPenalty) {
        result.splice(index - 1, 2, mergePair(left, current));
      } else {
        result.splice(index, 2, mergePair(current, right));
      }
      protectedIndexes.clear();
    }
    return result;
  }

  function buildSegments(profile, options = {}) {
    if (!Array.isArray(profile) || profile.length < 2) return [];
    const minimumKm = options.minimumKm || MIN_SEGMENT_KM;
    const sampleKm = options.sampleKm || SAMPLE_KM;
    const radiusKm = options.smoothRadiusKm || SMOOTH_RADIUS_KM;
    const maxKm = profile[profile.length - 1].km;
    if (!(maxKm > 0)) return [];

    const samples = [];
    for (let km = 0; km < maxKm; km += sampleKm) samples.push(km);
    if (!samples.length || samples[samples.length - 1] !== maxKm) samples.push(maxKm);
    const smoothed = samples.map((km) => {
      const nearby = profile.filter((point) => Math.abs(point.km - km) <= radiusKm);
      if (!nearby.length) return interpolate(profile, km, 'ele');
      let sum = 0;
      let weight = 0;
      nearby.forEach((point) => {
        const value = finite(point.ele);
        if (value === null) return;
        const itemWeight = Math.max(0.05, 1 - Math.abs(point.km - km) / (radiusKm || 1));
        sum += value * itemWeight;
        weight += itemWeight;
      });
      return weight ? sum / weight : interpolate(profile, km, 'ele');
    });

    const micro = [];
    for (let index = 1; index < samples.length; index += 1) {
      const lengthKm = samples[index] - samples[index - 1];
      if (!(lengthKm > 0)) continue;
      micro.push(refresh({
        fromKm: samples[index - 1],
        toKm: samples[index],
        startEle: smoothed[index - 1],
        endEle: smoothed[index]
      }));
    }

    const grouped = [];
    micro.forEach((item) => {
      const previous = grouped[grouped.length - 1];
      if (previous && previous.kind === item.kind && Math.abs(previous.grade - item.grade) <= MAX_GRADE_DRIFT) {
        grouped[grouped.length - 1] = mergePair(previous, item);
      } else {
        grouped.push(item);
      }
    });

    return mergeShortSegments(grouped, minimumKm).map((segment, index) => ({
      ...segment,
      index: index + 1,
      heartRate: weightedAverage(profile, segment.fromKm, segment.toKm, 'heartRate'),
      wheelSpeed: weightedAverage(profile, segment.fromKm, segment.toKm, 'wheelSpeed'),
      shakeScore: weightedAverage(
        profile,
        segment.fromKm,
        segment.toKm,
        'shakeScore',
        (point) => normalizeShakeScore(point.shakeScore, point.wheelSpeed)
      )
    }));
  }

  function segmentedProfile(profile, segments) {
    return profile.map((point) => {
      const segment = segments.find((item, index) =>
        point.km >= item.fromKm && (point.km < item.toKm || (index === segments.length - 1 && point.km <= item.toKm)));
      return segment ? {
        ...point,
        segment,
        heartRate: segment.heartRate,
        wheelSpeed: segment.wheelSpeed,
        shakeScore: segment.shakeScore
      } : point;
    });
  }

  return {
    buildSegments,
    segmentedProfile,
    gradeKind,
    normalizeShakeScore,
    SHAKE_REFERENCE_SPEED_KMH,
    SHAKE_SPEED_EXPONENT
  };
}));
