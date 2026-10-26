const assert = require('assert');
const processing = require('../static/segment_processing.js');

function point(km, ele, heartRate, wheelSpeed, shakeScore) {
  return { km, ele, heartRate, wheelSpeed, shakeScore };
}

const profile = [];
for (let km = 0; km <= 3.0001; km += 0.1) {
  let ele;
  if (km <= 1) ele = 300 + km * 60;
  else if (km <= 2) ele = 360 + (km - 1) * 5;
  else ele = 365 - (km - 2) * 70;
  profile.push(point(Number(km.toFixed(3)), ele, 120 + km * 5, 20 + km, 10 + km * 2));
}

const segments = processing.buildSegments(profile);
assert(segments.length >= 3, 'trasa powinna zawierać podjazd, odcinek równy i zjazd');
assert.strictEqual(segments[0].kind, 'up');
assert.strictEqual(segments[segments.length - 1].kind, 'down');
assert(segments.every((segment) => segment.lengthKm >= 0.5 - 1e-6));
assert(segments.every((segment) => Number.isFinite(segment.heartRate)));
assert(segments.every((segment) => Number.isFinite(segment.wheelSpeed)));
assert(segments.every((segment) => Number.isFinite(segment.shakeScore)));

const referenceShake = processing.normalizeShakeScore(50, 5);
const slowShake = processing.normalizeShakeScore(50, 4);
const fastShake = processing.normalizeShakeScore(50, 7);
assert(Math.abs(referenceShake - 50) < 1e-9, 'prędkość odniesienia nie powinna zmieniać wyniku');
assert(slowShake > referenceShake, 'wolny przejazd powinien być przeliczony w górę do 5 km/h');
assert(fastShake < referenceShake, 'szybki przejazd powinien być przeliczony w dół do 5 km/h');
const expectedFast = 50 * Math.pow(5 / 7, processing.SHAKE_SPEED_EXPONENT);
assert(Math.abs(fastShake - expectedFast) < 1e-9, 'korekta musi używać procentowej relacji prędkości');
assert.strictEqual(processing.normalizeShakeScore(50, 0), null, 'postój nie może wejść do średniej drgań');

const noisyFlat = [];
for (let km = 0; km <= 2.0001; km += 0.05) {
  noisyFlat.push(point(Number(km.toFixed(3)), 200 + Math.sin(km * 40) * 1.5, 130, 22, 12));
}
const flatSegments = processing.buildSegments(noisyFlat);
assert(flatSegments.length <= 2, 'szum wysokości nie powinien tworzyć wielu krótkich odcinków');
assert(flatSegments.every((segment) => segment.lengthKm >= 0.5 - 1e-6));

const shortDirectionChanges = [
  point(0.0, 100, 120, 20, 10),
  point(0.2, 120, 121, 20, 11),
  point(0.4, 100, 122, 20, 12),
  point(0.6, 125, 123, 20, 13),
  point(0.8, 95, 124, 20, 14)
];
const directionSegments = processing.buildSegments(shortDirectionChanges, {
  sampleKm: 0.2,
  smoothRadiusKm: 0.01,
  minimumKm: 0.5
});
assert(directionSegments.some((segment) => segment.kind === 'up' && segment.lengthKm < 0.5));
assert(directionSegments.some((segment) => segment.kind === 'down' && segment.lengthKm < 0.5));
for (let index = 1; index < directionSegments.length; index += 1) {
  const before = directionSegments[index - 1];
  const after = directionSegments[index];
  assert(
    !(before.kind === 'up' && after.kind === 'up') &&
    !(before.kind === 'down' && after.kind === 'down'),
    'sąsiednie odcinki tego samego kierunku powinny zostać połączone'
  );
}

console.log(`OK: ${segments.length} odcinki testowe, ${flatSegments.length} odcinek/odcinki płaskie`);
