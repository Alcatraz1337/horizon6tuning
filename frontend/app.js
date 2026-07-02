// horizon6tuning dashboard client: WebSocket telemetry + LLM insights.
"use strict";

const $ = (id) => document.getElementById(id);

// ---- live sparkline (RPM + speed) ----
const ctx = $("sparkline").getContext("2d");
const chart = new Chart(ctx, {
  type: "line",
  data: {
    labels: [],
    datasets: [
      { label: "RPM", data: [], borderColor: "#ffb000", backgroundColor: "rgba(255,176,0,.12)", borderWidth: 2, pointRadius: 0, tension: .25, yAxisID: "y" },
      { label: "Speed km/h", data: [], borderColor: "#ff3b30", backgroundColor: "rgba(255,59,48,.10)", borderWidth: 2, pointRadius: 0, tension: .25, yAxisID: "y1" },
    ],
  },
  options: {
    animation: false,
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: "#8b97a6", boxWidth: 12 } } },
    scales: {
      x: { display: false },
      y:  { position: "left",  ticks: { color: "#8b97a6" }, grid: { color: "#1c2430" } },
      y1: { position: "right", ticks: { color: "#8b97a6" }, grid: { drawOnChartArea: false } },
    },
  },
});
const SPARK_MAX = 120;

function pushSpark(rpm, kmh) {
  const now = new Date().toLocaleTimeString();
  chart.data.labels.push(now);
  chart.data.datasets[0].data.push(rpm);
  chart.data.datasets[1].data.push(kmh);
  if (chart.data.labels.length > SPARK_MAX) {
    chart.data.labels.shift();
    chart.data.datasets.forEach((d) => d.data.shift());
  }
  chart.update("none");
}

// ---- tire temp color scale (cool -> good -> warm -> hot) ----
function tireColor(c) {
  if (c == null) return "#3a4452";
  // roughly: <70 cool, 70-90 good, 90-105 warm, >105 hot
  if (c < 70) return "#3aa0ff";
  if (c < 90) return "#2bd576";
  if (c < 105) return "#ffb000";
  return "#ff3b30";
}

function fmtTime(s) {
  if (s == null || s <= 0) return "–";
  const m = Math.floor(s / 60);
  const sec = (s - m * 60).toFixed(3);
  return `${m}:${sec.padStart(6, "0")}`;
}

function setTire(el, tempC) {
  el.querySelector("b").textContent = tempC == null ? "–" : Math.round(tempC) + "°";
  el.querySelector("i").style.background = tireColor(tempC);
}

// ---- render one frame ----
function render(f) {
  const rpm = f.current_engine_rpm || 0;
  const maxRpm = f.engine_max_rpm || 8000;
  $("rpm").textContent = Math.round(rpm);
  $("rpmFill").style.width = Math.min(100, (rpm / maxRpm) * 100) + "%";
  $("gearLabel").textContent = f.gear_display;
  $("speedKmh").textContent = f.speed_kmh == null ? "0" : Math.round(f.speed_kmh);
  $("speedMph").textContent = f.speed_mph == null ? "0" : Math.round(f.speed_mph);
  $("speedBig").textContent = f.speed_kmh == null ? "0" : Math.round(f.speed_kmh);

  // speed arc (0..360 km/h mapped to 0..100 of pathLength)
  const frac = Math.min(1, (f.speed_kmh || 0) / 360);
  $("speedArc").style.strokeDashoffset = (100 - frac * 100).toString();

  // pedals
  const p = (v) => (v == null ? 0 : v);
  $("throttleFill").style.height = p(f.throttle_pct) + "%";
  $("throttleVal").textContent = Math.round(p(f.throttle_pct)) + "%";
  $("brakeFill").style.height = p(f.brake_pct) + "%";
  $("brakeVal").textContent = Math.round(p(f.brake_pct)) + "%";
  $("clutchFill").style.height = p(f.clutch_pct) + "%";
  $("clutchVal").textContent = Math.round(p(f.clutch_pct)) + "%";
  $("handbrakeFill").style.height = p(f.handbrake_pct) + "%";
  $("handbrakeVal").textContent = Math.round(p(f.handbrake_pct)) + "%";

  // steer (-100..100)
  const steer = p(f.steer_pct);
  $("steerMark").style.left = (50 + steer * 0.5) + "%";
  $("steerFill").style.left = (steer >= 0 ? "50%" : (50 + steer * 0.5) + "%");
  $("steerFill").style.width = Math.abs(steer) * 0.5 + "%";

  // laps
  $("lapNum").textContent = f.lap_number == null ? "–" : f.lap_number;
  $("racePos").textContent = f.race_position == null ? "–" : f.race_position;
  $("curLap").textContent = fmtTime(f.current_lap);
  $("lastLap").textContent = fmtTime(f.last_lap);
  $("bestLap").textContent = fmtTime(f.best_lap);

  // tires
  const t = f.tire_temps_c || [null, null, null, null];
  setTire($("tireFL"), t[0]); setTire($("tireFR"), t[1]);
  setTire($("tireRL"), t[2]); setTire($("tireRR"), t[3]);

  // fuel / boost / power
  $("fuelFill").style.width = Math.min(100, (f.fuel || 0) * 100) + "%";
  $("boostFill").style.width = Math.min(100, (f.boost || 0) * 100) + "%";
  $("powerVal").textContent = f.power == null ? "–" : Math.round(f.power / 1000);
  $("torqueVal").textContent = f.torque == null ? "–" : Math.round(f.torque);

  pushSpark(rpm, f.speed_kmh || 0);
}

// ---- connection status poll ----
async function pollStatus() {
  try {
    const r = await fetch("/api/status");
    const s = await r.json();
    const live = s.listening && s.last_packet_age_ms != null && s.last_packet_age_ms < 2000;
    $("connDot").className = "dot " + (live ? "on" : "off");
    $("connLabel").textContent = live ? "telemetry live" : "waiting for telemetry…";
    $("stats").textContent = live
      ? `${s.packets_parsed} pkts · ${s.buffer_frames} buffered`
      : (s.last_error || "");
  } catch { /* server starting up */ }
}
setInterval(pollStatus, 1000);

// ---- WebSocket ----
let ws;
function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/telemetry`);
  ws.onmessage = (ev) => {
    try { render(JSON.parse(ev.data)); } catch (e) { console.warn(e); }
  };
  ws.onclose = () => { setTimeout(connectWS, 1500); };
  ws.onerror = () => ws.close();
}
connectWS();

// ---- insights ----
const btn = $("analyzeBtn");
const body = $("insightsBody");
const meta = $("insightsMeta");

// simple markdown-ish: **bold**, bullet lines starting with - or *
function renderInsight(text) {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const html = lines.map((l) => {
    const rich = l.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    if (/^[-*]\s+/.test(rich)) return `<li>${rich.replace(/^[-*]\s+/, "")}</li>`;
    return `<p>${rich}</p>`;
  }).join("");
  body.innerHTML = /^<li>/.test(html) ? `<ul>${html}</ul>` : html;
}

async function analyze() {
  btn.disabled = true;
  body.innerHTML = '<p class="placeholder">Analyzing current telemetry window…</p>';
  meta.textContent = "";
  try {
    const extra = $("extraContext").value.trim();
    const r = await fetch("/api/insights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ extra: extra || null }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "analysis failed");
    renderInsight(data.text);
    const u = data.usage ? ` · ${JSON.stringify(data.usage)}` : "";
    meta.textContent = `${data.provider} / ${data.model} · window ${data.summary.frames} frames (${data.summary.window_seconds}s)${u}`;
  } catch (e) {
    body.innerHTML = `<p class="err">${e.message}</p>`;
  } finally {
    btn.disabled = false;
  }
}
btn.addEventListener("click", analyze);
$("extraContext").addEventListener("keydown", (e) => { if (e.key === "Enter") analyze(); });