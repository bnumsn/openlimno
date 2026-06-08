"""Embedded browser assets for the fishtank Studio."""

from __future__ import annotations

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OpenLimno Fishtank Studio</title>
<style>
:root {
  --bg: #f6f7f9;
  --panel: #ffffff;
  --panel-2: #f0f4f8;
  --line: #d9e0e7;
  --text: #18212f;
  --muted: #607083;
  --brand: #0f766e;
  --brand-2: #0b5e59;
  --danger: #b42318;
  --warn: #a15c07;
  --blue: #2563eb;
  --green: #198754;
  --shadow: 0 1px 2px rgba(16, 24, 40, .08);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); }
button, input, select { font: inherit; }
.topbar {
  height: 56px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 18px; background: #0b3736; color: #fff; border-bottom: 1px solid #082b2a;
}
.brand { display: flex; align-items: center; gap: 10px; font-weight: 700; letter-spacing: .2px; }
.mark {
  width: 30px; height: 30px; display: grid; place-items: center; border-radius: 6px;
  background: #f2fbfa; color: #0b3736; font-weight: 800;
}
.status { font-size: 13px; color: #cde8e5; }
.shell { display: grid; grid-template-columns: 360px 1fr; min-height: calc(100vh - 56px); }
.sidebar { border-right: 1px solid var(--line); background: #fff; padding: 14px; overflow: auto; }
.main { padding: 14px; overflow: auto; }
.section { border: 1px solid var(--line); background: var(--panel); border-radius: 8px; box-shadow: var(--shadow); margin-bottom: 12px; }
.section h2 {
  margin: 0; padding: 11px 12px; border-bottom: 1px solid var(--line);
  font-size: 14px; font-weight: 700; color: #27364a;
}
.section-body { padding: 12px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.field { display: grid; gap: 5px; min-width: 0; }
.field label { font-size: 12px; color: var(--muted); font-weight: 650; }
.field input, .field select {
  width: 100%; height: 34px; border: 1px solid #ccd6e0; border-radius: 6px;
  padding: 6px 8px; background: #fff; color: var(--text);
}
.row { display: flex; align-items: center; gap: 8px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.btn {
  border: 1px solid #c7d1db; background: #fff; color: #172033; height: 34px;
  padding: 0 11px; border-radius: 6px; cursor: pointer; font-weight: 650;
}
.btn:hover { background: #f2f5f8; }
.btn.primary { background: var(--brand); color: #fff; border-color: var(--brand); }
.btn.primary:hover { background: var(--brand-2); }
.btn.danger { color: var(--danger); border-color: #f1b7b2; }
.tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--line); margin-bottom: 12px; }
.tab {
  border: 0; border-bottom: 3px solid transparent; background: transparent;
  padding: 10px 14px; color: var(--muted); cursor: pointer; font-weight: 700;
}
.tab.active { color: var(--brand); border-bottom-color: var(--brand); }
.view { display: none; }
.view.active { display: block; }
.tank-view.active { display: grid; min-height: calc(100vh - 126px); }
.tank-stage {
  position: relative; min-height: 590px; overflow: hidden; background: #071c24;
}
#tankCanvas { width: 100%; height: 100%; min-height: 590px; display: block; touch-action: none; }
.tank-hud {
  position: absolute; left: 16px; right: 16px; top: 14px; z-index: 2;
  display: grid; grid-template-columns: repeat(5, minmax(110px, 1fr)); gap: 8px;
  pointer-events: none;
}
.tank-stat {
  background: rgba(4, 22, 30, .72); border: 1px solid rgba(199, 222, 232, .18);
  color: #e7f7fb; border-radius: 8px; padding: 8px 10px; backdrop-filter: blur(6px);
}
.tank-stat .label { display: block; font-size: 10px; color: #a6cad5; font-weight: 700; }
.tank-stat .value { display: block; margin-top: 2px; font-size: 17px; font-weight: 800; }
.tank-badge {
  position: absolute; right: 16px; bottom: 14px; z-index: 2;
  color: #cde8e5; background: rgba(4, 22, 30, .62); border-radius: 8px;
  padding: 7px 10px; font-size: 12px; pointer-events: none;
}
.tank-fallback {
  position: absolute; inset: 0; display: none; place-items: center; padding: 24px;
  color: #d8eef0; text-align: center; background: #071c24;
}
.kpis { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; margin-bottom: 12px; }
.kpi { background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 12px; box-shadow: var(--shadow); }
.kpi .label { color: var(--muted); font-size: 12px; font-weight: 650; }
.kpi .value { margin-top: 5px; font-size: 23px; line-height: 1.1; font-weight: 780; }
.kpi .unit { color: var(--muted); font-size: 12px; margin-top: 2px; }
.abm-grid { display: grid; grid-template-columns: minmax(320px, .9fr) 1.1fr; gap: 12px; }
.agent-space {
  width: 100%; height: 360px; display: block; border: 1px solid var(--line);
  border-radius: 8px; background: #f7fafc;
}
.agent-pill {
  display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--line);
  border-radius: 999px; padding: 3px 8px; color: var(--muted); font-size: 12px; font-weight: 700;
}
.panel { background: #fff; border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); margin-bottom: 12px; }
.panel-head { padding: 10px 12px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; gap: 10px; }
.panel-title { font-weight: 760; color: #253246; }
.panel-body { padding: 12px; }
.chart { width: 100%; height: 310px; display: block; }
.chart-grid line { stroke: #edf1f5; stroke-width: 1; }
.axis text { fill: #607083; font-size: 11px; }
.legend { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; color: var(--muted); font-size: 12px; }
.legend span { display: inline-flex; align-items: center; gap: 5px; }
.swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #edf1f5; padding: 8px; text-align: left; white-space: nowrap; }
th { color: #536377; font-size: 12px; background: #f8fafc; }
.warn { background: #fff8eb; border: 1px solid #ffd9a3; color: #6a3a05; border-radius: 7px; padding: 9px 10px; margin-bottom: 8px; }
.ok { background: #edfbf4; border: 1px solid #bdebd1; color: #0f5132; border-radius: 7px; padding: 9px 10px; }
.event-row {
  display: grid;
  grid-template-columns: 58px minmax(92px, 1fr) 64px 32px;
  grid-template-areas:
    "day kind value remove"
    "repeat target target remove";
  gap: 6px; margin-bottom: 8px;
}
.event-row input, .event-row select { height: 32px; border: 1px solid #ccd6e0; border-radius: 6px; padding: 5px; min-width: 0; }
.event-row [data-k="day"] { grid-area: day; }
.event-row [data-k="kind"] { grid-area: kind; }
.event-row [data-k="value"] { grid-area: value; }
.event-row [data-k="target"] { grid-area: target; }
.event-row [data-k="repeat_days"] { grid-area: repeat; }
.event-row button { grid-area: remove; align-self: stretch; padding: 0; }
.muted { color: var(--muted); }
.table-note { margin-top: 8px; font-size: 12px; color: var(--muted); }
.table-gap td { text-align: center; color: var(--muted); font-weight: 700; background: #f8fafc; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
@media (max-width: 1050px) {
  .shell { grid-template-columns: 1fr; }
  .main { order: -1; }
  .sidebar { border-right: 0; border-bottom: 1px solid var(--line); }
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .abm-grid { grid-template-columns: 1fr; }
  .tank-view.active { min-height: 620px; }
  .tank-stage, #tankCanvas { min-height: 620px; }
  .tank-hud { grid-template-columns: repeat(3, minmax(92px, 1fr)); }
}
@media (max-width: 620px) {
  .grid-2, .grid-3, .kpis { grid-template-columns: 1fr; }
  .topbar { height: auto; min-height: 56px; align-items: flex-start; flex-direction: column; padding: 10px 14px; }
  .tabs { overflow-x: auto; }
  .tab { flex: 0 0 auto; padding: 10px 12px; }
  .tank-view.active { min-height: 560px; }
  .tank-stage, #tankCanvas { min-height: 560px; }
  .tank-hud { left: 10px; right: 10px; top: 10px; grid-template-columns: repeat(2, minmax(88px, 1fr)); }
  .tank-stat { padding: 7px 8px; }
  .tank-stat .value { font-size: 15px; }
  .tank-badge { left: 10px; right: auto; max-width: calc(100% - 20px); }
}
</style>
</head>
<body>
<header class="topbar">
  <div class="brand"><div class="mark">OL</div><div>OpenLimno Fishtank Studio</div></div>
  <div style="display:flex;align-items:center;gap:14px">
    <button id="langToggle" class="btn" type="button">中文 / EN</button>
    <div id="status" class="status">Ready</div>
  </div>
</header>
<div class="shell">
  <aside class="sidebar">
    <section class="section">
      <h2>Scenario</h2>
      <div class="section-body">
        <div class="field"><label for="scenarioPreset">Preset</label><select id="scenarioPreset"></select></div>
        <div class="field"><small id="scenarioPresetHint" class="hint"></small></div>
        <div class="grid-2">
          <div class="field"><label for="volume">Volume L</label><input id="volume" type="number" min="20" step="1"></div>
          <div class="field"><label for="days">Days</label><input id="days" type="number" min="0" step="1"></div>
          <div class="field"><label for="dt">Output hours</label><input id="dt" type="number" min="1" step="1"></div>
          <div class="field"><label for="temp">Temperature C</label><input id="temp" type="number" step="0.5"></div>
          <div class="field"><label for="ph">Fixed pH</label><input id="ph" type="number" step="0.1"></div>
          <div class="field"><label for="dose">Ammonia dose</label><input id="dose" type="number" min="0" step="0.1"></div>
        </div>
      </div>
    </section>
    <section class="section">
      <h2>Initial chemistry</h2>
      <div class="section-body">
        <div class="grid-3">
          <div class="field"><label for="tan0">TAN</label><input id="tan0" type="number" step="0.1"></div>
          <div class="field"><label for="no20">NO2</label><input id="no20" type="number" step="0.1"></div>
          <div class="field"><label for="no30">NO3</label><input id="no30" type="number" step="0.1"></div>
          <div class="field"><label for="xaob0">X_AOB</label><input id="xaob0" type="number" step="0.01"></div>
          <div class="field"><label for="xnob0">X_NOB</label><input id="xnob0" type="number" step="0.01"></div>
          <div class="field"><label for="do0">DO</label><input id="do0" type="number" step="0.1"></div>
        </div>
      </div>
    </section>
    <section class="section">
      <h2>Events</h2>
      <div class="section-body">
        <div id="events"></div>
        <div class="actions"><button class="btn" id="addEventBtn">Add event</button></div>
      </div>
    </section>
    <section class="section">
      <h2>Water and carbonate</h2>
      <div class="section-body">
        <div class="grid-2">
          <div class="field"><label for="tapNo3">Tap NO3</label><input id="tapNo3" type="number" step="0.1"></div>
          <div class="field"><label for="tapDo">Tap DO</label><input id="tapDo" type="number" step="0.1"></div>
          <div class="field"><label for="alk">Alk meq/L</label><input id="alk" type="number" step="0.1"></div>
          <div class="field"><label for="dic">DIC mmol/L</label><input id="dic" type="number" step="0.1"></div>
        </div>
      </div>
    </section>
    <section class="section">
      <h2>Agent-based model</h2>
      <div class="section-body">
        <div class="grid-2">
          <div class="field"><label for="agentSeed">Seed</label><input id="agentSeed" type="number" min="0" step="1"></div>
          <div class="field"><label for="agentDt">ABM step days</label><input id="agentDt" type="number" min="0.02" max="1" step="0.01"></div>
          <div class="field"><label for="fishCount">Fish agents</label><input id="fishCount" type="number" min="0" step="1"></div>
          <div class="field"><label for="fishBiomass">g per fish</label><input id="fishBiomass" type="number" min="0.1" step="0.1"></div>
          <div class="field"><label for="feedDay">Feed g/day</label><input id="feedDay" type="number" min="0" step="0.1"></div>
          <div class="field"><label for="aobAgents">AOB patches</label><input id="aobAgents" type="number" min="1" step="1"></div>
          <div class="field"><label for="nobAgents">NOB patches</label><input id="nobAgents" type="number" min="1" step="1"></div>
        </div>
      </div>
    </section>
    <div class="actions">
      <button class="btn primary" id="runBtn">Run</button>
      <button class="btn" id="calibrateBtn">Calibrate</button>
      <button class="btn" id="exportBtn">Export scenario</button>
      <button class="btn" id="resetBtn">Reset</button>
    </div>
  </aside>
  <main class="main">
    <div class="tabs">
      <button class="tab active" data-view="tank3d">3D Tank</button>
      <button class="tab" data-view="agentsView">ABM Agents</button>
      <button class="tab" data-view="dashboard">Dashboard</button>
      <button class="tab" data-view="chemistry">Chemistry</button>
      <button class="tab" data-view="eventsView">Events</button>
      <button class="tab" data-view="calibration">Calibration</button>
      <button class="tab" data-view="exportView">Export</button>
    </div>
    <section id="tank3d" class="view tank-view active">
      <div class="tank-stage">
        <canvas id="tankCanvas" aria-label="3D virtual aquarium"></canvas>
        <div class="tank-hud" id="tankHud"></div>
        <div class="tank-badge" id="tankBadge">day 0.0</div>
        <div class="tank-fallback" id="tankFallback">3D renderer unavailable</div>
      </div>
      <div class="tank-note" id="tankNote" style="padding:8px 12px;font-size:12px;color:var(--muted);line-height:1.5;">Illustration: dot positions are random; the number shown scales with concentration — not a real spatial distribution.</div>
    </section>
    <section id="agentsView" class="view">
      <div class="kpis" id="agentKpis"></div>
      <div class="abm-grid">
        <div class="panel">
          <div class="panel-head">
            <div class="panel-title">Agent tank map</div>
            <div class="actions"><button class="btn" id="agentRunBtn">Run ABM</button></div>
          </div>
          <div class="panel-body"><svg id="agentSpace" class="agent-space"></svg></div>
        </div>
        <div class="panel">
          <div class="panel-head"><div class="panel-title">Population dynamics</div><div class="legend" id="agentLegend"></div></div>
          <div class="panel-body"><svg id="agentChart" class="chart"></svg></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">ABM event log</div>
          <div class="legend"><span class="agent-pill">fish individuals</span><span class="agent-pill">AOB/NOB patches</span></div>
        </div>
        <div class="panel-body"><div id="agentEventsTable"></div></div>
      </div>
    </section>
    <section id="dashboard" class="view">
      <div class="kpis" id="kpis"></div>
      <div id="warnings"></div>
      <div class="panel">
        <div class="panel-head"><div class="panel-title">Nitrogen</div><div class="legend" id="nitrogenLegend"></div></div>
        <div class="panel-body"><svg id="nitrogenChart" class="chart"></svg></div>
      </div>
      <div class="panel">
        <div class="panel-head"><div class="panel-title">Biofilm and oxygen</div><div class="legend" id="bioLegend"></div></div>
        <div class="panel-body"><svg id="bioChart" class="chart"></svg></div>
      </div>
    </section>
    <section id="chemistry" class="view">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">pH diagnostic</div><div class="legend" id="phLegend"></div></div>
        <div class="panel-body"><svg id="phChart" class="chart"></svg></div>
      </div>
      <div class="panel"><div class="panel-head"><div class="panel-title">Timeseries</div></div><div class="panel-body"><div id="timeseriesTable"></div></div></div>
    </section>
    <section id="eventsView" class="view">
      <div class="panel"><div class="panel-head"><div class="panel-title">Applied event log</div></div><div class="panel-body"><div id="eventsTable"></div></div></div>
    </section>
    <section id="calibration" class="view">
      <div class="panel"><div class="panel-head"><div class="panel-title">Bundled calibration</div></div><div class="panel-body" id="calibrationPanel"><div class="muted">Click Calibrate to fit bundled tank_A_fishless.csv against mu_AOB and mu_NOB.</div></div></div>
    </section>
    <section id="exportView" class="view">
      <div class="panel"><div class="panel-head"><div class="panel-title">Scenario JSON</div></div><div class="panel-body"><pre id="scenarioJson" class="mono"></pre></div></div>
      <div class="panel"><div class="panel-head"><div class="panel-title">Provenance</div></div><div class="panel-body"><pre id="provenanceJson" class="mono"></pre></div></div>
    </section>
  </main>
</div>
<script>
const $ = id => document.getElementById(id);
let state = null;
let lastResult = null;
let lastAgents = null;
let presetMap = {};

function setStatus(text) { $('status').textContent = text; }
function number(id) { return Number($(id).value); }
function fixed(v, n=2) { return Number(v).toFixed(n); }

function eventRow(event) {
  const row = document.createElement('div');
  row.className = 'event-row';
  row.innerHTML = `
    <input data-k="day" type="number" min="0" step="0.25">
    <select data-k="kind">
      <option value="water_change">${t('water_change')}</option>
      <option value="wipe_biofilm">${t('wipe_biofilm')}</option>
      <option value="ammonia_dose">${t('ammonia_dose')}</option>
      <option value="feed">${t('feed')}</option>
      <option value="dose">${t('dose')}</option>
      <option value="set_param">${t('set_param')}</option>
    </select>
    <input data-k="value" type="number" step="0.1">
    <select data-k="target">
      <option value="">${t('target')}</option>
      <option value="TAN">${t('TAN')}</option><option value="NO2">${t('NO2')}</option><option value="NO3">${t('NO3')}</option><option value="X_AOB">${t('X_AOB')}</option><option value="X_NOB">${t('X_NOB')}</option>
      <option value="DO">${t('DO')}</option><option value="B_plant">${t('B_plant')}</option><option value="DIC">${t('DIC')}</option><option value="Alk">${t('Alk')}</option>
      <option value="temperature_c">${t('temperature_c')}</option><option value="ph">${t('ph')}</option><option value="k_a">${t('k_a')}</option><option value="DO_sat">${t('DO_sat')}</option><option value="R_fish">${t('R_fish')}</option>
    </select>
    <input data-k="repeat_days" type="number" min="0" step="1">
    <button class="btn danger" type="button">X</button>`;
  row.querySelector('[data-k="day"]').value = event.day ?? 0;
  row.querySelector('[data-k="kind"]').value = event.kind ?? 'water_change';
  row.querySelector('[data-k="value"]').value = event.value ?? 0.25;
  row.querySelector('[data-k="target"]').value = event.target ?? '';
  row.querySelector('[data-k="repeat_days"]').value = event.repeat_days ?? 0;
  row.querySelector('button').addEventListener('click', () => row.remove());
  return row;
}

function bind(payload) {
  state = payload;
  $('volume').value = payload.tank.volume_l;
  $('days').value = payload.run.days;
  $('dt').value = payload.run.dt_output_hours;
  $('temp').value = payload.tank.temperature_c;
  $('ph').value = payload.tank.ph;
  $('dose').value = payload.parameters.ammonia_dose_mg_n_l_day;
  $('tan0').value = payload.chemistry.TAN;
  $('no20').value = payload.chemistry.NO2;
  $('no30').value = payload.chemistry.NO3;
  $('xaob0').value = payload.chemistry.X_AOB;
  $('xnob0').value = payload.chemistry.X_NOB;
  $('do0').value = payload.chemistry.DO;
  $('tapNo3').value = payload.tap_water.NO3;
  $('tapDo').value = payload.tap_water.DO;
  $('alk').value = payload.carbonate.initial_alk_meq_l;
  $('dic').value = payload.carbonate.dic_mmol_l;
  const agents = payload.agents || {};
  $('agentSeed').value = agents.seed ?? 42;
  $('agentDt').value = agents.dt_days ?? 0.25;
  $('fishCount').value = agents.fish_count ?? 6;
  $('fishBiomass').value = agents.fish_biomass_g ?? 4;
  $('feedDay').value = agents.feed_g_day ?? 0.3;
  $('aobAgents').value = agents.aob_agents ?? 36;
  $('nobAgents').value = agents.nob_agents ?? 36;
  $('events').replaceChildren(...payload.events.map(eventRow));
}

function collect() {
  const events = Array.from($('events').children).map(row => ({
    day: Number(row.querySelector('[data-k="day"]').value),
    kind: row.querySelector('[data-k="kind"]').value,
    value: Number(row.querySelector('[data-k="value"]').value),
    target: row.querySelector('[data-k="target"]').value,
    repeat_days: Number(row.querySelector('[data-k="repeat_days"]').value || 0),
  }));
  // Start from the loaded preset so non-form fields survive a Run: the Tier-2
  // initial state (B_plant/DIC/Alk), the full parameter set (couple_ph,
  // mu_plant, k_denit, k_a, ...), and tap DIC/Alk. Only override the fields the
  // form actually edits. Without this, selecting e.g. ph_crash_coupled then
  // hitting Run silently dropped couple_ph and ran the uncoupled path.
  const base = state ? JSON.parse(JSON.stringify(state)) : {};
  return {
    ...base,
    scenario_id: base.scenario_id || 'studio-scenario',
    tank: {...base.tank, volume_l: number('volume'), temperature_c: number('temp'), ph: number('ph')},
    run: {...base.run, days: number('days'), dt_output_hours: number('dt')},
    chemistry: {
      ...base.chemistry,
      TAN: number('tan0'), NO2: number('no20'), NO3: number('no30'),
      X_AOB: number('xaob0'), X_NOB: number('xnob0'), DO: number('do0')
    },
    parameters: {...base.parameters, ammonia_dose_mg_n_l_day: number('dose')},
    tap_water: {...base.tap_water, NO3: number('tapNo3'), DO: number('tapDo')},
    carbonate: {...base.carbonate, initial_alk_meq_l: number('alk'), dic_mmol_l: number('dic')},
    agents: {
      ...base.agents,
      seed: number('agentSeed'),
      dt_days: number('agentDt'),
      fish_count: number('fishCount'),
      fish_biomass_g: number('fishBiomass'),
      feed_g_day: number('feedDay'),
      aob_agents: number('aobAgents'),
      nob_agents: number('nobAgents'),
    },
    events,
  };
}

async function api(path, payload=null) {
  const opts = payload ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)} : {};
  const response = await fetch(path, opts);
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || response.statusText);
  return data;
}

function lineChart(svg, rows, series, yLabel) {
  const width = svg.clientWidth || 800;
  const height = svg.clientHeight || 310;
  const pad = {l: 54, r: 18, t: 18, b: 34};
  const xs = rows.map(r => Number(r.day));
  const values = series.flatMap(s => rows.map(r => Number(r[s.key])));
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  let minY = Math.min(0, ...values), maxY = Math.max(...values);
  if (maxY === minY) maxY = minY + 1;
  const x = v => pad.l + (Number(v) - minX) / (maxX - minX || 1) * (width - pad.l - pad.r);
  const y = v => height - pad.b - (Number(v) - minY) / (maxY - minY) * (height - pad.t - pad.b);
  let html = `<g class="chart-grid">`;
  for (let i = 0; i <= 4; i++) {
    const yy = pad.t + i * (height - pad.t - pad.b) / 4;
    html += `<line x1="${pad.l}" x2="${width-pad.r}" y1="${yy}" y2="${yy}"></line>`;
  }
  html += `</g><g class="axis"><text x="8" y="18">${yLabel}</text><text x="${width-58}" y="${height-8}">${t('day')}</text></g>`;
  for (const s of series) {
    const d = rows.map((r, i) => `${i === 0 ? 'M' : 'L'}${x(r.day).toFixed(1)},${y(r[s.key]).toFixed(1)}`).join(' ');
    html += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2.2"></path>`;
  }
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.innerHTML = html;
}

function legend(id, series) {
  $(id).innerHTML = series.map(s => `<span><i class="swatch" style="background:${s.color}"></i>${s.label}</span>`).join('');
}

function table(id, rows, columns, opts={}) {
  // Escape cell values before interpolating into innerHTML — event-log fields
  // (target, notes) can carry arbitrary text, so render them as data, not HTML.
  const esc = v => String(v).replace(/[&<>"']/g, m => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[m]));
  if (!rows || rows.length === 0) {
    $(id).innerHTML = `<div class="muted">${t('No rows')}</div>`;
    return;
  }
  const limit = opts.limit ?? 160;
  const compact = opts.compact && rows.length > limit;
  let displayRows = rows.slice(0, limit);
  if (compact) {
    const edge = Math.floor(limit / 2);
    displayRows = [
      ...rows.slice(0, edge),
      {__gap: __lang === 'zh' ? `省略 ${rows.length - limit} 行` : `${rows.length - limit} rows omitted`},
      ...rows.slice(-edge),
    ];
  }
  const head = columns.map(c => `<th>${esc(t(c))}</th>`).join('');
  const body = displayRows.map(row => {
    if (row.__gap) return `<tr class="table-gap"><td colspan="${columns.length}">${esc(row.__gap)}</td></tr>`;
    return `<tr>${columns.map(c => `<td>${esc(row[c] ?? '')}</td>`).join('')}</tr>`;
  }).join('');
  const note = compact
    ? (__lang === 'zh'
        ? `<div class="table-note">仅显示前 ${Math.floor(limit / 2)} 行和后 ${Math.floor(limit / 2)} 行(共 ${rows.length} 行)。完整结果见 CLI/导出文件。</div>`
        : `<div class="table-note">Showing first ${Math.floor(limit / 2)} and last ${Math.floor(limit / 2)} of ${rows.length} rows. Full output is available through CLI/export artifacts.</div>`)
    : rows.length > displayRows.length
      ? (__lang === 'zh'
          ? `<div class="table-note">仅显示 ${rows.length} 行中的前 ${displayRows.length} 行。</div>`
          : `<div class="table-note">Showing first ${displayRows.length} of ${rows.length} rows.</div>`)
      : '';
  $(id).innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${note}`;
}

function render(result) {
  lastResult = result;
  const s = result.summary;
  $('kpis').innerHTML = [
    ['Final TAN', fixed(s.final_TAN), 'mg-N/L'],
    ['Final NO2', fixed(s.final_NO2), 'mg-N/L'],
    ['Final NO3', fixed(s.final_NO3), 'mg-N/L'],
    ['Min DO', fixed(s.min_DO), 'mg-O2/L'],
    ['Final pH', fixed(s.final_ph_dynamic), 'diagnostic'],
  ].map(k => `<div class="kpi"><div class="label">${t(k[0])}</div><div class="value">${k[1]}</div><div class="unit">${t(k[2])}</div></div>`).join('');

  $('warnings').innerHTML = result.warnings.length
    ? result.warnings.map(w => `<div class="warn">${w}</div>`).join('')
    : `<div class="ok">${t('No threshold warnings')}</div>`;

  const nSeries = [
    {key:'TAN', label:t('TAN'), color:'#d1495b'},
    {key:'NO2', label:t('NO2'), color:'#edae49'},
    {key:'NO3', label:t('NO3'), color:'#00798c'}
  ];
  const bSeries = [
    {key:'X_AOB', label:t('X_AOB'), color:'#2e933c'},
    {key:'X_NOB', label:t('X_NOB'), color:'#7d4f50'},
    {key:'DO', label:t('DO'), color:'#3066be'}
  ];
  const pSeries = [
    {key:'ph_dynamic', label:t('pH'), color:'#9b2226'},
    {key:'alk_meq_l', label:t('Alk'), color:'#0a9396'}
  ];
  legend('nitrogenLegend', nSeries); legend('bioLegend', bSeries); legend('phLegend', pSeries);
  lineChart($('nitrogenChart'), result.timeseries, nSeries, t('mg-N/L'));
  lineChart($('bioChart'), result.timeseries, bSeries, t('mg/L'));
  lineChart($('phChart'), result.ph_diagnostic, pSeries, t('pH / Alk'));
  table('timeseriesTable', result.timeseries, ['day','TAN','NO2','NO3','DO','NH3_free','pH'], {compact: true, limit: 80});
  table('eventsTable', result.events_log, ['day','kind','value','target','TAN_before','TAN_after','NO3_before','NO3_after','ammonia_dose_after']);
  $('scenarioJson').textContent = JSON.stringify(collect(), null, 2);
  $('provenanceJson').textContent = JSON.stringify(result.provenance, null, 2);
  window.dispatchEvent(new CustomEvent('fishtank:result', {detail: result}));
  setStatus(__lang === 'zh'
    ? `运行完成:${result.timeseries.length} 行 ODE,${result.events_log.length} 个事件`
    : `Run complete: ${result.timeseries.length} rows, ${result.events_log.length} event(s)`);
}

function renderAgentSpace(result) {
  const svg = $('agentSpace');
  const width = svg.clientWidth || 800;
  const height = svg.clientHeight || 360;
  const pad = 28;
  const snapshot = result.agents || {};
  const fish = snapshot.fish || [];
  const microbes = snapshot.microbes || [];
  const sx = value => pad + (Number(value || 0) + 1) / 2 * (width - pad * 2);
  const sy = value => height - pad - (Number(value || 0) + .8) / 1.6 * (height - pad * 2);
  const microHtml = microbes.map(agent => {
    const active = Math.max(0, Math.min(1, Number(agent.activity || 0) / 1.8));
    const size = 2 + Math.min(5, Math.sqrt(Number(agent.biomass_mg_l || 0)) * 9);
    const color = agent.guild === 'AOB' ? '#2e933c' : '#7d4f50';
    const opacity = .32 + active * .58;
    if (agent.guild === 'AOB') {
      return `<circle cx="${sx(agent.x).toFixed(1)}" cy="${sy(agent.y).toFixed(1)}" r="${size.toFixed(1)}" fill="${color}" opacity="${opacity.toFixed(2)}"></circle>`;
    }
    return `<rect x="${(sx(agent.x)-size).toFixed(1)}" y="${(sy(agent.y)-size).toFixed(1)}" width="${(size*2).toFixed(1)}" height="${(size*2).toFixed(1)}" fill="${color}" opacity="${opacity.toFixed(2)}" rx="2"></rect>`;
  }).join('');
  const fishHtml = fish.map(agent => {
    const stress = Math.max(0, Math.min(1, Number(agent.stress || 0) / 3));
    const radius = 6 + Math.min(9, Math.sqrt(Number(agent.biomass_g || 0)) * 1.8);
    const color = agent.alive ? (stress > .65 ? '#c2410c' : '#f59e0b') : '#94a3b8';
    return `<g transform="translate(${sx(agent.x).toFixed(1)} ${sy(agent.y).toFixed(1)})">
      <ellipse cx="0" cy="0" rx="${radius.toFixed(1)}" ry="${(radius*.55).toFixed(1)}" fill="${color}" opacity="${agent.alive ? .9 : .42}"></ellipse>
      <circle cx="${(radius*.35).toFixed(1)}" cy="${(-radius*.12).toFixed(1)}" r="1.8" fill="#172033" opacity="${agent.alive ? .78 : .25}"></circle>
    </g>`;
  }).join('');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.innerHTML = `
    <rect x="${pad}" y="${pad}" width="${width-pad*2}" height="${height-pad*2}" rx="8" fill="#eff8fb" stroke="#cbdce7"></rect>
    <rect x="${width-pad-96}" y="${pad+18}" width="42" height="${height-pad*2-36}" fill="#26333f" opacity=".16" rx="5"></rect>
    ${microHtml}${fishHtml}
    <g fill="#607083" font-size="12" font-weight="700">
      <text x="${pad}" y="${height-8}">${t('front glass')}</text>
      <text x="${width-128}" y="${pad+15}">${t('filter media')}</text>
    </g>`;
}

function renderAgents(result, silent=false) {
  lastAgents = result;
  const s = result.summary;
  $('agentKpis').innerHTML = [
    [t('Live fish'), `${s.fish_alive}`, `${t('mortality')} ${s.fish_mortality}`],
    [t('Mean stress'), fixed(s.mean_fish_stress, 2), t('0-6 index')],
    [t('AOB biomass'), fixed(s.AOB_biomass, 3), t('mg/L patches')],
    [t('NOB biomass'), fixed(s.NOB_biomass, 3), t('mg/L patches')],
    [t('Min DO'), fixed(s.min_DO), t('mg-O2/L')],
  ].map(k => `<div class="kpi"><div class="label">${k[0]}</div><div class="value">${k[1]}</div><div class="unit">${k[2]}</div></div>`).join('');
  const series = [
    {key:'fish_alive', label:t('live fish'), color:'#f59e0b'},
    {key:'fish_stress_mean', label:t('fish stress'), color:'#c2410c'},
    {key:'AOB_biomass', label:t('AOB biomass'), color:'#2e933c'},
    {key:'NOB_biomass', label:t('NOB biomass'), color:'#7d4f50'},
  ];
  legend('agentLegend', series);
  lineChart($('agentChart'), result.timeseries, series, t('agents / biomass'));
  renderAgentSpace(result);
  table('agentEventsTable', result.event_log, ['day','kind','value','target','TAN_before','TAN_after','NO2_before','NO2_after','NO3_before','NO3_after','DO_before','DO_after']);
  window.dispatchEvent(new CustomEvent('fishtank:agents', {detail: result}));
  if (!silent) setStatus(__lang === 'zh'
    ? `ABM 完成:${result.timeseries.length} 行,${result.provenance.agent_count} 个个体`
    : `ABM complete: ${result.timeseries.length} rows, ${result.provenance.agent_count} agent(s)`);
}

async function runAgents(silent=false) {
  if (!silent) setStatus(t('Running ABM'));
  try {
    const result = await api('/api/agents', collect());
    renderAgents(result, silent);
    if (silent && lastResult) {
      setStatus(__lang === 'zh'
        ? `运行完成:${lastResult.timeseries.length} 行 ODE;${result.provenance.agent_count} 个 ABM 个体`
        : `Run complete: ${lastResult.timeseries.length} ODE rows; ${result.provenance.agent_count} ABM agent(s)`);
    }
  } catch (err) {
    setStatus(err.message);
  }
}

async function run() {
  setStatus(t('Running'));
  try {
    render(await api('/api/run', collect()));
    await runAgents(true);
  }
  catch (err) { setStatus(err.message); }
}

async function calibrate() {
  setStatus(t('Calibrating'));
  try {
    const result = await api('/api/calibrate', collect());
    $('calibrationPanel').innerHTML = `
      <div class="grid-3">
        <div class="kpi"><div class="label">RMSE</div><div class="value">${fixed(result.best_rmse, 4)}</div><div class="unit">${t('normalised')}</div></div>
        <div class="kpi"><div class="label">mu_AOB</div><div class="value">${fixed(result.best_params.mu_AOB, 4)}</div><div class="unit">${t('1/day')}</div></div>
        <div class="kpi"><div class="label">mu_NOB</div><div class="value">${fixed(result.best_params.mu_NOB, 4)}</div><div class="unit">${t('1/day')}</div></div>
      </div>
      <div class="muted">${t('Evaluations')}: ${result.n_evals}; ${result.message}</div>`;
    setStatus(t('Calibration complete'));
  } catch (err) { setStatus(err.message); }
}

function downloadScenario() {
  const blob = new Blob([JSON.stringify(collect(), null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'fishtank_scenario.json';
  a.click();
  URL.revokeObjectURL(a.href);
}

function presetLabel(entry) { return (__lang === 'zh' && entry.label_zh) ? entry.label_zh : entry.label; }
function presetDesc(entry) { return (__lang === 'zh' && entry.description_zh) ? entry.description_zh : entry.description; }

function setPresetHint(id) {
  const entry = presetMap[id];
  $('scenarioPresetHint').textContent = entry ? presetDesc(entry) : '';
}

function refreshPresetLabels() {
  const select = $('scenarioPreset');
  if (!select) return;
  for (const opt of select.options) {
    const entry = presetMap[opt.value];
    if (entry) opt.textContent = presetLabel(entry);
  }
  setPresetHint(select.value);
}

async function loadPresets() {
  const data = await api('/api/scenarios');
  presetMap = {};
  const select = $('scenarioPreset');
  select.replaceChildren(...data.scenarios.map(s => {
    presetMap[s.id] = s;
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = presetLabel(s);
    return opt;
  }));
  select.value = data.default;
  setPresetHint(select.value);
}

$('scenarioPreset').addEventListener('change', async (e) => {
  const entry = presetMap[e.target.value];
  if (!entry) return;
  setPresetHint(e.target.value);
  bind(JSON.parse(JSON.stringify(entry.payload)));
  await run();
});

document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  tab.classList.add('active');
  $(tab.dataset.view).classList.add('active');
}));
$('runBtn').addEventListener('click', run);
$('agentRunBtn').addEventListener('click', () => runAgents(false));
$('calibrateBtn').addEventListener('click', calibrate);
$('exportBtn').addEventListener('click', downloadScenario);
$('resetBtn').addEventListener('click', async () => {
  await loadPresets();
  bind(await api('/api/default'));
  await run();
});
$('addEventBtn').addEventListener('click', () => $('events').appendChild(eventRow({day: 7, kind: 'water_change', value: 0.25, repeat_days: 7})));
window.addEventListener('resize', () => {
  if (lastResult) render(lastResult);
  if (lastAgents) {
    renderAgents(lastAgents, true);
    setStatus(__lang === 'zh'
      ? `运行完成:${lastResult?.timeseries?.length || 0} 行 ODE;${lastAgents.provenance.agent_count} 个 ABM 个体`
      : `Run complete: ${lastResult?.timeseries?.length || 0} ODE rows; ${lastAgents.provenance.agent_count} ABM agent(s)`);
  }
});
window.__fishtankAgentStatus = () => ({
  ok: Boolean(lastAgents),
  schema: lastAgents?.schema || null,
  rows: lastAgents?.timeseries?.length || 0,
  fish: lastAgents?.agents?.fish?.length || 0,
  microbes: lastAgents?.agents?.microbes?.length || 0,
  summary: lastAgents?.summary || null,
});

// ---- 中英文切换(i18n):全中文(连科学符号一起译);英文为源,ZH 为中文对照 ----
const ZH = {
  // 区块/标签页/面板标题
  "Scenario":"场景","Initial chemistry":"初始水质","Events":"事件",
  "Water and carbonate":"换水与碳酸盐","Agent-based model":"个体模型(ABM)",
  "Preset":"预设案例","Volume L":"缸体积 L","Days":"天数","Output hours":"输出间隔(小时)",
  "Temperature C":"温度 ℃","Fixed pH":"固定 pH","Ammonia dose":"投氨速率",
  "Tap NO3":"自来水硝酸盐","Tap DO":"自来水溶氧","Alk meq/L":"碱度 meq/L","DIC mmol/L":"DIC mmol/L",
  "Seed":"随机种子","ABM step days":"ABM 步长(天)","Fish agents":"鱼数量","g per fish":"每条鱼克数",
  "Feed g/day":"投喂 g/天","AOB patches":"氨氧化菌斑块数","NOB patches":"亚硝氧化菌斑块数",
  "Add event":"加事件","Run":"运行","Calibrate":"校准","Export scenario":"导出场景","Reset":"重置",
  "Run ABM":"运行 ABM",
  "3D Tank":"3D 鱼缸","ABM Agents":"个体(ABM)","Dashboard":"仪表盘","Chemistry":"水化学",
  "Calibration":"校准","Export":"导出",
  "Agent tank map":"个体分布图","Population dynamics":"种群动态","ABM event log":"ABM 事件日志",
  "Nitrogen":"氮","Biofilm and oxygen":"生物膜与溶氧","pH diagnostic":"pH 诊断",
  "Timeseries":"时间序列","Applied event log":"已应用事件日志","Bundled calibration":"内置校准",
  "Scenario JSON":"场景 JSON","Provenance":"溯源信息",
  "fish individuals":"鱼个体","AOB/NOB patches":"氨氧化菌/亚硝氧化菌斑块","3D renderer unavailable":"3D 渲染不可用",
  "Click Calibrate to fit bundled tank_A_fishless.csv against mu_AOB and mu_NOB.":
    "点「校准」用内置 tank_A_fishless.csv 拟合 mu_AOB 和 mu_NOB。",
  // 科学符号(全局对照)
  "TAN":"总氨氮","NO2":"亚硝酸盐","NO3":"硝酸盐","DO":"溶氧",
  "X_AOB":"氨氧化菌量","X_NOB":"亚硝氧化菌量","NH3_free":"游离氨","Alk":"碱度",
  // 仪表盘 KPI(ODE)
  "Final TAN":"最终总氨氮","Final NO2":"最终亚硝酸盐","Final NO3":"最终硝酸盐",
  "Min DO":"最低溶氧","Final pH":"最终 pH","diagnostic":"诊断",
  // 仪表盘 KPI(ABM)
  "Live fish":"存活鱼","Mean stress":"平均胁迫","AOB biomass":"氨氧化菌生物量",
  "NOB biomass":"亚硝氧化菌生物量","mortality":"死亡","0-6 index":"0–6 指数",
  "mg/L patches":"mg/L 斑块","mg-N/L":"mg-N/L","mg-O2/L":"mg-O₂/L",
  // 图表图例 + 坐标轴
  "live fish":"存活鱼","fish stress":"鱼胁迫","pH":"pH","day":"日",
  "pH / Alk":"pH / 碱度","agents / biomass":"个体数 / 生物量","mg/L":"mg/L",
  // 3D 个体分布图标注
  "front glass":"前玻璃","filter media":"滤材",
  // 数据表表头(前/后)
  "kind":"类型","value":"数值","target":"目标",
  "TAN_before":"总氨氮(前)","TAN_after":"总氨氮(后)",
  "NO2_before":"亚硝酸盐(前)","NO2_after":"亚硝酸盐(后)",
  "NO3_before":"硝酸盐(前)","NO3_after":"硝酸盐(后)",
  "DO_before":"溶氧(前)","DO_after":"溶氧(后)","ammonia_dose_after":"投氨后",
  // 事件类型(下拉显示文本;value 保持英文标识)
  "water_change":"换水","wipe_biofilm":"擦除生物膜","ammonia_dose":"投氨",
  "feed":"投喂","dose":"投加","set_param":"设参数",
  // 事件目标(下拉显示文本)
  "temperature_c":"温度","k_a":"复氧 k_a","DO_sat":"溶氧饱和","R_fish":"鱼耗氧",
  "B_plant":"植物氮","DIC":"DIC","ph":"pH",
  // 表格提示 + 校准
  "No rows":"无数据","No threshold warnings":"无阈值预警","RMSE":"RMSE",
  "normalised":"归一化","1/day":"1/天","Evaluations":"评估次数",
  "Running":"运行中","Running ABM":"运行 ABM 中","Calibrating":"校准中",
  "Calibration complete":"校准完成","Ready — click Run to start":"已就绪——点「运行」开始",
  // 3D 示意说明(默认英文为源)
  "Illustration: dot positions are random; the number shown scales with concentration — not a real spatial distribution.":
    "示意图:点的位置随机,亮起的数量随浓度示意,并非真实空间分布。"
};
function t(s) { return (__lang === 'zh' && ZH[s] != null) ? ZH[s] : s; }
const I18N_SEL = '.section h2, .tabs .tab, .panel-title, .sidebar label, .actions .btn, #calibrationPanel .muted, .tank-fallback, .agent-pill, #tankNote';
function applyLang(lang) {
  __lang = lang;
  // 静态界面(选择器命中)
  document.querySelectorAll(I18N_SEL).forEach(el => {
    if (el.dataset.en === undefined) el.dataset.en = el.textContent.trim();
    const en = el.dataset.en;
    el.textContent = (lang === 'zh' && ZH[en]) ? ZH[en] : en;
  });
  // 事件行下拉(保 value、重译显示文本)
  document.querySelectorAll('.event-row select[data-k="kind"] option, .event-row select[data-k="target"] option').forEach(opt => {
    opt.textContent = (opt.value === '') ? t('target') : t(opt.value);
  });
  // 预设下拉名/说明
  refreshPresetLabels();
  // 动态视图重渲染(KPI/图表/表头/状态/3D HUD 经事件转发)
  if (lastResult) render(lastResult);
  else setStatus(t('Ready — click Run to start'));
  if (lastAgents) renderAgents(lastAgents, true);
  const toggleBtn = $('langToggle');
  if (toggleBtn) toggleBtn.textContent = lang === 'zh' ? 'EN / 中文' : '中文 / EN';
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  try { localStorage.setItem('fishtank_lang', lang); } catch (e) {}
}
let __lang = (() => { try { return localStorage.getItem('fishtank_lang'); } catch (e) { return null; } })() || 'zh';
$('langToggle').addEventListener('click', () => { __lang = __lang === 'zh' ? 'en' : 'zh'; applyLang(__lang); });
applyLang(__lang);

(async function init() {
  await loadPresets();
  bind(await api('/api/default'));
  // 不自动运行:只加载默认参数,等用户点「运行」(避免一打开就跑)
  setStatus(t('Ready — click Run to start'));
})();
</script>
<script type="module">
import * as THREE from '/assets/three.module.min.js';

const canvas3d = document.getElementById('tankCanvas');
const hud3d = document.getElementById('tankHud');
const badge3d = document.getElementById('tankBadge');
const fallback3d = document.getElementById('tankFallback');

let renderer3d = null;
let camera3d = null;
let scene3d = null;
let tankRoot = null;
let waterMesh = null;
let glassMesh = null;
let bioAob = null;
let bioNob = null;
let fish = null;
let agentFishGroup = null;
let frames3d = 0;
let tankRows = [];
let currentStats = {day: 0, TAN: 0, NO2: 0, NO3: 0, DO: 0, NH3_free: 0, pH: 7.4};
let drag = {active: false, x: 0, y: 0, yaw: -0.35, pitch: -0.08};

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function norm(v, maxValue) { return clamp(Number(v || 0) / Math.max(maxValue || 1, 1e-6), 0, 1); }

function makeMaterial(color, opacity=1, roughness=.45, metalness=0) {
  return new THREE.MeshStandardMaterial({
    color, transparent: opacity < 1, opacity, roughness, metalness,
    side: THREE.DoubleSide,
  });
}

function particleCloud(color, count, radius) {
  const group = new THREE.Group();
  const geom = new THREE.SphereGeometry(radius, 10, 8);
  const mat = makeMaterial(color, .82, .4, 0);
  for (let i = 0; i < count; i += 1) {
    const mesh = new THREE.Mesh(geom, mat);
    mesh.position.set((Math.random()-.5)*5.1, -1 + Math.random()*2.1, (Math.random()-.5)*2.2);
    mesh.userData.seed = Math.random() * 1000;
    group.add(mesh);
  }
  return group;
}

function buildFish() {
  const group = new THREE.Group();
  const body = new THREE.Mesh(new THREE.SphereGeometry(.34, 24, 14), makeMaterial(0xf3a23a, .96, .35, 0));
  body.scale.set(1.55, .78, .58);
  const tail = new THREE.Mesh(new THREE.ConeGeometry(.22, .45, 3), makeMaterial(0xd45a2a, .94, .4, 0));
  tail.rotation.z = Math.PI / 2;
  tail.position.x = -.62;
  const eye = new THREE.Mesh(new THREE.SphereGeometry(.035, 10, 8), makeMaterial(0x101820));
  eye.position.set(.43, .12, .18);
  group.add(body, tail, eye);
  group.position.set(-1.8, .25, .25);
  return group;
}

function init3d() {
  try {
    renderer3d = new THREE.WebGLRenderer({
      canvas: canvas3d, antialias: true, alpha: false, preserveDrawingBuffer: true,
    });
    renderer3d.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer3d.setClearColor(0x071c24, 1);
    scene3d = new THREE.Scene();
    scene3d.fog = new THREE.Fog(0x071c24, 7, 16);
    camera3d = new THREE.PerspectiveCamera(44, 1, .1, 100);
    camera3d.position.set(0, 1.35, 8.2);
    camera3d.lookAt(0, -.05, 0);

    const hemi = new THREE.HemisphereLight(0xc7eef7, 0x18313a, 2.2);
    const key = new THREE.DirectionalLight(0xffffff, 2.4);
    key.position.set(3, 5, 4);
    scene3d.add(hemi, key);

    tankRoot = new THREE.Group();
    tankRoot.rotation.y = drag.yaw;
    tankRoot.rotation.x = drag.pitch;
    scene3d.add(tankRoot);

    const glassGeom = new THREE.BoxGeometry(5.8, 2.75, 2.55);
    glassMesh = new THREE.Mesh(glassGeom, makeMaterial(0xbfeaf5, .16, .08, 0));
    tankRoot.add(glassMesh);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(glassGeom),
      new THREE.LineBasicMaterial({color: 0xcbeaf1, transparent: true, opacity: .55}),
    );
    tankRoot.add(edges);

    waterMesh = new THREE.Mesh(
      new THREE.BoxGeometry(5.65, 2.12, 2.38),
      makeMaterial(0x2ca9c7, .34, .15, 0),
    );
    waterMesh.position.y = -.18;
    tankRoot.add(waterMesh);

    const substrate = new THREE.Mesh(new THREE.BoxGeometry(5.65, .18, 2.36), makeMaterial(0xb9925a, .95, .8, 0));
    substrate.position.y = -1.48;
    tankRoot.add(substrate);

    const filter = new THREE.Mesh(new THREE.CylinderGeometry(.22, .28, 2.1, 24), makeMaterial(0x26333f, .9, .55, 0));
    filter.position.set(2.35, -.25, -.88);
    tankRoot.add(filter);
    bioAob = new THREE.Mesh(new THREE.TorusGeometry(.34, .045, 10, 34), makeMaterial(0x2e933c, .9, .35, 0));
    bioAob.position.copy(filter.position); bioAob.position.y += .5; bioAob.rotation.x = Math.PI / 2;
    bioNob = new THREE.Mesh(new THREE.TorusGeometry(.45, .045, 10, 34), makeMaterial(0x7d4f50, .9, .35, 0));
    bioNob.position.copy(filter.position); bioNob.position.y += .15; bioNob.rotation.x = Math.PI / 2;
    tankRoot.add(bioAob, bioNob);

    tankRoot.add(particleCloud(0xd1495b, 34, .045));
    tankRoot.add(particleCloud(0xedae49, 34, .042));
    tankRoot.add(particleCloud(0x00798c, 42, .04));
    tankRoot.children.slice(-3).forEach((g, i) => { g.name = ['tanParticles', 'no2Particles', 'no3Particles'][i]; });

    const bubbleGroup = new THREE.Group();
    bubbleGroup.name = 'bubbles';
    const bubbleGeom = new THREE.SphereGeometry(.035, 10, 8);
    const bubbleMat = makeMaterial(0xd7f8ff, .72, .05, 0);
    for (let i = 0; i < 34; i += 1) {
      const b = new THREE.Mesh(bubbleGeom, bubbleMat);
      b.position.set(2.35 + (Math.random()-.5)*.35, -1.22 + Math.random()*2.1, -.88 + (Math.random()-.5)*.38);
      b.userData.seed = Math.random() * 1000;
      bubbleGroup.add(b);
    }
    tankRoot.add(bubbleGroup);

    fish = buildFish();
    fish.visible = false;  // 装饰占位鱼默认隐藏:只显示真实 ABM 鱼,无鱼即无鱼
    tankRoot.add(fish);
    agentFishGroup = new THREE.Group();
    agentFishGroup.name = 'agentFish';
    tankRoot.add(agentFishGroup);

    resize3d();
    new ResizeObserver(resize3d).observe(canvas3d.parentElement);
    canvas3d.addEventListener('pointerdown', onPointerDown);
    canvas3d.addEventListener('pointermove', onPointerMove);
    canvas3d.addEventListener('pointerup', onPointerUp);
    canvas3d.addEventListener('pointerleave', onPointerUp);
    renderer3d.setAnimationLoop(animate3d);
    window.__fishtank3dStatus = () => ({
      renderer: 'three.js',
      frames: frames3d,
      rows: tankRows.length,
      canvasWidth: canvas3d.width,
      canvasHeight: canvas3d.height,
      stats: currentStats,
    });
    window.__fishtank3dPixels = () => {
      const gl = renderer3d.getContext();
      const w = gl.drawingBufferWidth;
      const h = gl.drawingBufferHeight;
      const x0 = Math.floor(w * .2);
      const y0 = Math.floor(h * .2);
      const sw = Math.max(1, Math.floor(w * .6));
      const sh = Math.max(1, Math.floor(h * .6));
      const pixels = new Uint8Array(sw * sh * 4);
      gl.readPixels(x0, y0, sw, sh, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      let hits = 0;
      for (let i = 0; i < pixels.length; i += 16) {
        if (pixels[i] > 10 || pixels[i + 1] > 10 || pixels[i + 2] > 10) hits += 1;
      }
      return {nonblank: hits > 100, hits, checked: sw * sh};
    };
  } catch (err) {
    fallback3d.style.display = 'grid';
    fallback3d.textContent = `3D renderer unavailable: ${err.message}`;
    window.__fishtank3dStatus = () => ({renderer: 'unavailable', error: err.message, frames: frames3d});
  }
}

function resize3d() {
  if (!renderer3d || !camera3d) return;
  const box = canvas3d.parentElement.getBoundingClientRect();
  const width = Math.max(320, Math.floor(box.width));
  const height = Math.max(520, Math.floor(box.height));
  renderer3d.setSize(width, height, false);
  camera3d.aspect = width / height;
  camera3d.updateProjectionMatrix();
}

function onPointerDown(event) {
  drag.active = true;
  drag.x = event.clientX;
  drag.y = event.clientY;
  canvas3d.setPointerCapture(event.pointerId);
}

function onPointerMove(event) {
  if (!drag.active || !tankRoot) return;
  const dx = event.clientX - drag.x;
  const dy = event.clientY - drag.y;
  drag.x = event.clientX;
  drag.y = event.clientY;
  drag.yaw += dx * .006;
  drag.pitch = clamp(drag.pitch + dy * .004, -.45, .35);
  tankRoot.rotation.y = drag.yaw;
  tankRoot.rotation.x = drag.pitch;
}

function onPointerUp() { drag.active = false; }

function updateHud(row) {
  hud3d.innerHTML = [
    ['day', Number(row.day || 0).toFixed(1)],
    ['TAN', Number(row.TAN || 0).toFixed(2)],
    ['NO2', Number(row.NO2 || 0).toFixed(2)],
    ['NO3', Number(row.NO3 || 0).toFixed(1)],
    ['DO', Number(row.DO || 0).toFixed(2)],
  ].map(([label, value]) => `<div class="tank-stat"><span class="label">${t(label)}</span><span class="value">${value}</span></div>`).join('');
  const pH = Number(row.pH || currentStats.pH || 7.4);
  badge3d.textContent = `pH ${pH.toFixed(2)} | ${t('NH3_free')} ${Number(row.NH3_free || 0).toFixed(3)} mg/L`;
}

function updateAgentFish3d(snapshot) {
  if (!agentFishGroup || !fish) return;
  agentFishGroup.clear();
  const agents = Array.isArray(snapshot?.fish) ? snapshot.fish.filter(agent => agent.alive) : [];
  // 不再显示装饰占位鱼:鱼数=0 时缸内就没有鱼(与 KPI/ABM 图一致)
  fish.visible = false;
  for (const agent of agents.slice(0, 48)) {
    const mesh = buildFish();
    const stress = clamp(Number(agent.stress || 0) / 3, 0, 1);
    const scale = .32 + Math.min(.38, Math.sqrt(Number(agent.biomass_g || 1)) * .055);
    mesh.scale.setScalar(scale);
    mesh.position.set(Number(agent.x || 0) * 2.45, Number(agent.y || 0) * 1.15, Number(agent.z || 0) * 1.18);
    mesh.rotation.y = stress * -.35;
    mesh.children[0].material.color.set(stress > .65 ? 0xc75c45 : 0xf3a23a);
    agentFishGroup.add(mesh);
  }
}

function update3d(row, t) {
  currentStats = row;
  const maxes = tankRows.reduce((acc, r) => ({
    TAN: Math.max(acc.TAN, Number(r.TAN || 0)),
    NO2: Math.max(acc.NO2, Number(r.NO2 || 0)),
    NO3: Math.max(acc.NO3, Number(r.NO3 || 0)),
    X_AOB: Math.max(acc.X_AOB, Number(r.X_AOB || 0)),
    X_NOB: Math.max(acc.X_NOB, Number(r.X_NOB || 0)),
  }), {TAN: 1, NO2: 1, NO3: 1, X_AOB: 1, X_NOB: 1});

  const tanN = norm(row.TAN, maxes.TAN);
  const no2N = norm(row.NO2, maxes.NO2);
  const no3N = norm(row.NO3, maxes.NO3);
  const doN = norm(row.DO, 8);
  const stress = clamp(tanN * .42 + no2N * .42 + (1 - doN) * .35, 0, 1);

  const pH = Number(row.pH || 7.4);
  const waterColor = pH < 6.4 ? new THREE.Color(0x8a5d44) : new THREE.Color(0x2ca9c7);
  waterMesh.material.color.lerp(waterColor, .08);
  waterMesh.material.opacity = .25 + .18 * stress;
  glassMesh.material.opacity = .11 + .06 * (1 - doN);

  const groups = {
    tanParticles: [tanN, .9],
    no2Particles: [no2N, 1.3],
    no3Particles: [no3N, .55],
  };
  for (const group of tankRoot.children.filter(obj => groups[obj.name])) {
    const [level, speed] = groups[group.name];
    const visibleCount = Math.round(group.children.length * (.18 + .82 * level));
    group.children.forEach((p, i) => {
      p.visible = i < visibleCount;
      p.position.y += Math.sin(t * speed + p.userData.seed) * .0009 + .0008;
      if (p.position.y > 1.1) p.position.y = -1.15;
      p.position.x += Math.sin(t * .23 + p.userData.seed) * .002;
      p.position.z += Math.cos(t * .27 + p.userData.seed) * .002;
    });
  }

  bioAob.scale.setScalar(.45 + 1.45 * norm(row.X_AOB, maxes.X_AOB));
  bioNob.scale.setScalar(.45 + 1.45 * norm(row.X_NOB, maxes.X_NOB));

  const bubbles = tankRoot.getObjectByName('bubbles');
  const bubbleCount = Math.round(bubbles.children.length * clamp(.18 + doN, .12, 1));
  bubbles.children.forEach((b, i) => {
    b.visible = i < bubbleCount;
    b.position.y += .01 + doN * .012;
    b.position.x += Math.sin(t * 1.7 + b.userData.seed) * .003;
    if (b.position.y > 1.05) b.position.y = -1.2;
  });

  fish.position.x = Math.sin(t * .55) * 1.55 - stress * .55;
  fish.position.y = .08 + Math.sin(t * .8) * (.18 - stress * .08) - stress * .35;
  fish.rotation.y = Math.sin(t * .55) * .25;
  fish.rotation.z = Math.sin(t * 2.8) * (.05 + .13 * stress);
  fish.children[0].material.color.lerp(new THREE.Color(stress > .55 ? 0xc75c45 : 0xf3a23a), .08);
  if (agentFishGroup) {
    agentFishGroup.children.forEach((mesh, i) => {
      mesh.position.y += Math.sin(t * 1.4 + i) * .0009;
      mesh.rotation.z = Math.sin(t * 2.2 + i) * .05;
    });
  }
  updateHud(row);
}

function animate3d(timeMs) {
  frames3d += 1;
  const t = timeMs * .001;
  if (tankRows.length > 0) {
    const idx = Math.floor((t * 3) % tankRows.length);
    update3d(tankRows[idx], t);
  }
  if (tankRoot && !drag.active) {
    tankRoot.rotation.y = drag.yaw + Math.sin(t * .22) * .045;
  }
  renderer3d.render(scene3d, camera3d);
}

window.addEventListener('fishtank:result', event => {
  tankRows = Array.isArray(event.detail?.timeseries) ? event.detail.timeseries : [];
  if (tankRows.length) update3d(tankRows[0], performance.now() * .001);
});
window.addEventListener('fishtank:agents', event => {
  updateAgentFish3d(event.detail?.agents);
});

init3d();
</script>
</body>
</html>
"""

__all__ = ["INDEX_HTML"]
