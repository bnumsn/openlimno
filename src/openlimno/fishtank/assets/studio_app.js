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

// Overlay two datasets on shared axes: ODE solid, ABM dashed, same colour per
// variable, so a student can read how the agent model tracks (or departs from)
// the ODE for each shared state variable.
function compareChart(svg, odeRows, abmRows, series, yLabel) {
  const width = svg.clientWidth || 800;
  const height = svg.clientHeight || 310;
  const pad = {l: 54, r: 18, t: 18, b: 34};
  const all = odeRows.concat(abmRows);
  const xs = all.map(r => Number(r.day));
  const values = series.flatMap(s => all.map(r => Number(r[s.key])));
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
    const ode = odeRows.map((r, i) => `${i === 0 ? 'M' : 'L'}${x(r.day).toFixed(1)},${y(r[s.key]).toFixed(1)}`).join(' ');
    const abm = abmRows.map((r, i) => `${i === 0 ? 'M' : 'L'}${x(r.day).toFixed(1)},${y(r[s.key]).toFixed(1)}`).join(' ');
    html += `<path d="${ode}" fill="none" stroke="${s.color}" stroke-width="2.2"></path>`;
    html += `<path d="${abm}" fill="none" stroke="${s.color}" stroke-width="2" stroke-dasharray="5 4" opacity="0.85"></path>`;
  }
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.innerHTML = html;
}

// Render the ODE-vs-ABM overlay from the last results of each model. Needs both
// (use "Run both"); otherwise show a hint and clear the chart.
function renderCompare() {
  const hint = $('compareHint');
  if (!lastResult || !lastAgents) {
    if (hint) hint.style.display = '';
    $('compareChart').innerHTML = '';
    $('compareLegend').innerHTML = '';
    return;
  }
  if (hint) hint.style.display = 'none';
  const series = [
    {key:'TAN', label:t('TAN'), color:'#d1495b'},
    {key:'NO2', label:t('NO2'), color:'#edae49'},
    {key:'NO3', label:t('NO3'), color:'#00798c'},
    {key:'DO',  label:t('DO'),  color:'#3066be'}
  ];
  compareChart($('compareChart'), lastResult.timeseries, lastAgents.timeseries, series, t('mg/L'));
  legend('compareLegend', series);
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
  // silent=true is used by runBoth(): render the ABM view but leave the status
  // line to the caller (so a combined ODE+ABM status can be set once). silent=false
  // is the standalone "Run ABM" button and owns its own "ABM 完成" status.
  if (!silent) setStatus(t('Running ABM'));
  try {
    const result = await api('/api/agents', collect());
    renderAgents(result, silent);
  } catch (err) {
    setStatus(err.message);
  }
}

// ODE only. The companion "Run ABM" button (ABM view) runs the agent model
// independently; the two are decoupled so each can be run and read on its own.
async function run() {
  setStatus(t('Running'));
  try {
    render(await api('/api/run', collect()));
  }
  catch (err) { setStatus(err.message); }
}

// Run both models in one click; each still renders to its own view (ODE →
// dashboard/3D, ABM → ABM view), then a single combined status reports both.
async function runBoth() {
  setStatus(t('Running'));
  try {
    render(await api('/api/run', collect()));
    await runAgents(true);
    renderCompare();
    if (lastResult && lastAgents) {
      setStatus(__lang === 'zh'
        ? `运行完成:${lastResult.timeseries.length} 行 ODE,${lastResult.events_log.length} 个事件;${lastAgents.provenance.agent_count} 个 ABM 个体`
        : `Run complete: ${lastResult.timeseries.length} ODE rows, ${lastResult.events_log.length} event(s); ${lastAgents.provenance.agent_count} ABM agent(s)`);
    }
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
  // The compare overlay reads both models' last results; (re)draw it when its
  // tab is opened, including after a resize while it was hidden (svg had 0 width).
  if (tab.dataset.view === 'compareView') renderCompare();
}));
$('runBtn').addEventListener('click', run);
$('runAbmBtn').addEventListener('click', () => runAgents(false));
$('runBothBtn').addEventListener('click', runBoth);
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
  // Re-render whatever has been run; render() restores the ODE status line.
  // Only override with the combined status when BOTH models have results, so a
  // resize after an ODE-only run never sprouts a phantom ABM tail.
  if (lastResult) render(lastResult);
  if (lastAgents) renderAgents(lastAgents, true);
  if (lastResult && lastAgents) {
    setStatus(__lang === 'zh'
      ? `运行完成:${lastResult.timeseries.length} 行 ODE,${lastResult.events_log.length} 个事件;${lastAgents.provenance.agent_count} 个 ABM 个体`
      : `Run complete: ${lastResult.timeseries.length} ODE rows, ${lastResult.events_log.length} event(s); ${lastAgents.provenance.agent_count} ABM agent(s)`);
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
  "Add event":"加事件","Run":"运行","Run ODE":"运行 方程模型(ODE)","Run ODE+ABM":"运行 两者(ODE+ABM)","Run both":"运行 两者(ODE+ABM)",
  "Calibrate":"校准","Export scenario":"导出场景","Reset":"重置",
  "Run ABM":"运行 个体模型(ABM)",
  "Compare":"对比","ODE vs ABM":"ODE 对比 ABM","Run both models to compare":"先点「运行 ODE+ABM」生成对比",
  "Solid = ODE, dashed = ABM":"实线 = ODE,虚线 = ABM",
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
const I18N_SEL = '.section h2, .tabs .tab, .panel-title, .sidebar label, .actions .btn, #calibrationPanel .muted, #compareHint, #compareNote, .tank-fallback, .agent-pill, #tankNote';
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
  renderCompare();
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
