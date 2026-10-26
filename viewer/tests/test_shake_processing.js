const assert = require('node:assert/strict');
const { buildSmoothedShakeProfile, nearestShakeValue } = require('../static/shake_processing.js');

const profile = [];
for (let index = 0; index < 240; index += 1) {
  const km = index * 0.01;
  const terrain = km >= 1.7;
  profile.push({
    km,
    shakeScore: terrain ? 72 + (index % 5) : 18 + (index % 3),
    wheelSpeed: 10
  });
}
profile.push({ km: 0.8, shakeScore: 0, wheelSpeed: 0 });

const smoothed = buildSmoothedShakeProfile(profile, 30);
assert.ok(smoothed.length > 200);
assert.ok(nearestShakeValue(smoothed, 1.5) < 25);
assert.ok(nearestShakeValue(smoothed, 1.9) > 65);

const stopOnly = buildSmoothedShakeProfile([
  { km: 0, shakeScore: 20, wheelSpeed: 8 },
  { km: 0.015, shakeScore: 0, wheelSpeed: 0 },
  { km: 0.025, shakeScore: 25, wheelSpeed: 8 }
], 10);
assert.equal(stopOnly[1].shakeScore, null);

console.log('shake processing tests: OK');
