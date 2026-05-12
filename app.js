const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const saveBtn = document.getElementById("saveBtn");
const clearBtn = document.getElementById("clearBtn");
const statusEl = document.getElementById("status");
const warningEl = document.getElementById("warning");
const sampleCountEl = document.getElementById("sampleCount");
const elapsedEl = document.getElementById("elapsed");
const magnitudeEl = document.getElementById("magnitude");
const maxMagnitudeEl = document.getElementById("maxMagnitude");
const xValueEl = document.getElementById("xValue");
const yValueEl = document.getElementById("yValue");
const zValueEl = document.getElementById("zValue");
const chart = document.getElementById("chart");
const ctx = chart.getContext("2d");

let isRecording = false;
let startedAt = 0;
let rows = [];
let maxMagnitude = 0;
let lastEventAt = 0;
let noDataTimer = null;
let activeSensor = null;

function setStatus(text, type = "idle") {
  statusEl.textContent = text;
  statusEl.className = `status ${type}`;
}

function showWarning(text) {
  warningEl.textContent = text;
  warningEl.hidden = !text;
}

function formatNumber(value) {
  return Number.isFinite(value) ? value.toFixed(3) : "";
}

function getAcceleration(event) {
  const source = event.acceleration || event.accelerationIncludingGravity;
  return {
    x: source?.x ?? 0,
    y: source?.y ?? 0,
    z: source?.z ?? 0,
    source: event.acceleration ? "linear" : "including_gravity",
  };
}

function recordAcceleration(acceleration, intervalMs, source) {
  if (!isRecording) return;

  const now = performance.now();
  const elapsedMs = now - startedAt;
  const magnitude = Math.sqrt(
    acceleration.x * acceleration.x +
      acceleration.y * acceleration.y +
      acceleration.z * acceleration.z
  );

  lastEventAt = now;
  maxMagnitude = Math.max(maxMagnitude, magnitude);

  rows.push({
    isoTime: new Date().toISOString(),
    elapsedMs,
    x: acceleration.x,
    y: acceleration.y,
    z: acceleration.z,
    magnitude,
    intervalMs,
    source,
  });

  updateReadout(acceleration, magnitude, elapsedMs);
  drawChart();
}

function handleMotion(event) {
  const acceleration = getAcceleration(event);
  recordAcceleration(acceleration, event.interval ?? "", acceleration.source);
}

function updateReadout(acceleration, magnitude, elapsedMs) {
  sampleCountEl.textContent = String(rows.length);
  elapsedEl.textContent = `${(elapsedMs / 1000).toFixed(1)} s`;
  magnitudeEl.textContent = formatNumber(magnitude);
  maxMagnitudeEl.textContent = formatNumber(maxMagnitude);
  xValueEl.textContent = formatNumber(acceleration.x);
  yValueEl.textContent = formatNumber(acceleration.y);
  zValueEl.textContent = formatNumber(acceleration.z);
}

function drawChart() {
  const width = chart.width;
  const height = chart.height;
  const padding = 28;
  const plotWidth = width - padding * 2;
  const plotHeight = height - padding * 2;
  const visibleRows = rows.slice(-260);
  const maxY = Math.max(1, ...visibleRows.map((row) => row.magnitude));

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fbfdfd";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "#d8e1e5";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const y = padding + (plotHeight / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding, y);
    ctx.lineTo(width - padding, y);
    ctx.stroke();
  }

  ctx.fillStyle = "#66757f";
  ctx.font = "13px Arial";
  ctx.fillText("drgania", padding, 18);
  ctx.fillText(maxY.toFixed(1), width - padding - 32, padding - 8);

  if (visibleRows.length < 2) return;

  ctx.strokeStyle = "#0f766e";
  ctx.lineWidth = 3;
  ctx.beginPath();
  visibleRows.forEach((row, index) => {
    const x = padding + (index / (visibleRows.length - 1)) * plotWidth;
    const y = padding + plotHeight - (row.magnitude / maxY) * plotHeight;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();
}

async function requestMotionPermission() {
  if (
    typeof DeviceMotionEvent !== "undefined" &&
    typeof DeviceMotionEvent.requestPermission === "function"
  ) {
    const result = await DeviceMotionEvent.requestPermission();
    if (result !== "granted") {
      throw new Error("Brak zgody na dostep do czujnikow ruchu.");
    }
  }
}

async function startRecording() {
  if (!("Accelerometer" in window) && !("DeviceMotionEvent" in window)) {
    setStatus("Brak czujnika", "error");
    showWarning("Ta przegladarka nie udostepnia akcelerometru. Sprobuj w Chrome na telefonie.");
    return;
  }

  isRecording = true;
  startedAt = performance.now();
  lastEventAt = startedAt;
  maxMagnitude = 0;
  rows = [];
  drawChart();

  startBtn.disabled = true;
  stopBtn.disabled = false;
  saveBtn.disabled = true;
  clearBtn.disabled = true;
  setStatus("Nagrywanie", "recording");
  showWarning("");

  const startedSensor = startAccelerometer();
  if (!startedSensor) {
    try {
      await requestMotionPermission();
      window.addEventListener("devicemotion", handleMotion);
    } catch (error) {
      stopRecording();
      setStatus("Brak zgody", "error");
      showWarning(error.message);
      return;
    }
  }

  noDataTimer = window.setInterval(checkSensorData, 1000);
}

function startAccelerometer() {
  if (!("Accelerometer" in window)) return false;

  try {
    activeSensor = new Accelerometer({ frequency: 60 });
    activeSensor.addEventListener("reading", () => {
      recordAcceleration(
        { x: activeSensor.x ?? 0, y: activeSensor.y ?? 0, z: activeSensor.z ?? 0 },
        "",
        "accelerometer"
      );
    });
    activeSensor.addEventListener("error", (event) => {
      showWarning(`Blad akcelerometru: ${event.error?.message || "brak dostepu do czujnika"}.`);
    });
    activeSensor.start();
    return true;
  } catch (error) {
    activeSensor = null;
    showWarning(error.message);
    return false;
  }
}

function stopRecording() {
  isRecording = false;
  window.removeEventListener("devicemotion", handleMotion);
  if (activeSensor) {
    activeSensor.stop();
    activeSensor = null;
  }
  window.clearInterval(noDataTimer);

  startBtn.disabled = false;
  stopBtn.disabled = true;
  saveBtn.disabled = rows.length === 0;
  clearBtn.disabled = rows.length === 0;
  setStatus(rows.length ? "Zatrzymano" : "Brak danych", rows.length ? "idle" : "error");
}

function checkSensorData() {
  if (!isRecording) return;

  if (performance.now() - lastEventAt > 2500) {
    showWarning(
      "Nie ma danych z czujnika. Otworz strone w Chrome na telefonie przez HTTPS albo localhost i sprawdz uprawnienia strony."
    );
  }
}

function csvEscape(value) {
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function saveCsv() {
  if (rows.length === 0) return;

  const headers = [
    "iso_time",
    "elapsed_ms",
    "acceleration_x",
    "acceleration_y",
    "acceleration_z",
    "vibration_magnitude",
    "interval_ms",
    "source",
  ];

  const lines = [
    headers.join(","),
    ...rows.map((row) =>
      [
        row.isoTime,
        row.elapsedMs.toFixed(1),
        formatNumber(row.x),
        formatNumber(row.y),
        formatNumber(row.z),
        formatNumber(row.magnitude),
        row.intervalMs,
        row.source,
      ]
        .map(csvEscape)
        .join(",")
    ),
  ];

  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const timestamp = new Date().toISOString().replaceAll(":", "-").slice(0, 19);

  link.href = url;
  link.download = `drgania-${timestamp}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function clearData() {
  rows = [];
  maxMagnitude = 0;
  sampleCountEl.textContent = "0";
  elapsedEl.textContent = "0.0 s";
  magnitudeEl.textContent = "0.000";
  maxMagnitudeEl.textContent = "0.000";
  xValueEl.textContent = "0.000";
  yValueEl.textContent = "0.000";
  zValueEl.textContent = "0.000";
  saveBtn.disabled = true;
  clearBtn.disabled = true;
  setStatus("Gotowy");
  showWarning("");
  drawChart();
}

startBtn.addEventListener("click", startRecording);
stopBtn.addEventListener("click", stopRecording);
saveBtn.addEventListener("click", saveCsv);
clearBtn.addEventListener("click", clearData);

drawChart();
