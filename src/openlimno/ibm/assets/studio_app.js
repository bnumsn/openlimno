const profileGroups = {
  Growth: ['thermal_min_c','thermal_optimum_c','thermal_max_c','max_daily_growth_mm','weight_a_g_per_cm_b','weight_b','max_consumption_fraction','respiration_fraction','activity_respiration_fraction','respiration_base_multiplier','respiration_thermal_multiplier'],
  Survival: ['base_daily_survival','predation_base_risk','predation_csi_risk','thermal_stress_mortality','velocity_stress_threshold_ms','velocity_stress_scale_ms','hydraulic_stress_mortality','max_mortality_risk','max_mass_loss_fraction','max_mass_gain_fraction','max_daily_shrinkage_mm'],
  Behavior: ['carrying_density_per_m2','min_cell_capacity','density_competition_strength','turbidity_half_saturation_ntu','feeding_cover_foraging_weight','utility_growth_weight','utility_mortality_weight','max_activity_velocity_ms'],
  Spawning: ['maturity_length_mm','spawn_start_day','spawn_end_day','spawner_female_fraction','fecundity_per_female','fecundity_length_exponent','fecundity_reference_length_mm','egg_to_fry_survival','egg_incubation_degree_days','spawning_cover_weight','spawning_csi_weight','redd_base_daily_survival','redd_min_depth_m','redd_scour_velocity_ms','redd_dewatering_mortality','redd_scour_mortality','fry_length_mm','fry_mass_g'],
  Movement: ['allow_cross_reach_movement','cross_reach_movement_penalty','cross_reach_movement_rate','cross_reach_movement_min_length_mm','cross_reach_movement_length_scale_mm','cross_reach_movement_max_steps','cross_reach_interior_movement_multiplier','cross_reach_upstream_bias','cross_reach_habitat_utility_weight']
};
const cellColumns = ['cell_id','habitat_type','station_m','center_x_m','center_y_m','length_m','width_m','reach_id','reach_order','area_m2','depth_m','velocity_ms','csi','temperature_c','turbidity_ntu','hiding_cover','feeding_cover','spawning_cover'];
const habitatColors = {riffle:'#77c8a6',run:'#70b7d5',pool:'#3b82c4',margin:'#b7d48b',tailout:'#d9c16f','side-channel':'#88d4c0',glide:'#7ab7e8',chute:'#e18b5a',cell:'#9fc5d8'};
let state = null;
let activeProfileGroup = 'Growth';
let lastResult = null;
let lastEnsemble = null;
let runHistory = [];
/* ---- New-model wizard ------------------------------------------------
   Sticky horizontal stepper that walks first-time users through the
   six modeling steps (河道 → 栖境 → 物种参数 → 初始种群 → 校验 → 运行).
   - Auto-activates on first visit (unless dismissed via localStorage).
   - "New model" sidebar button re-activates on demand.
   - Click on a step → smooth-scrolls to the relevant UI region and
     pulses an outline around it for ~3 s.
   - updateWizardProgress() is called whenever state changes (bindState,
     renderResult, importGIS, etc.) so step pills auto-tick to
     "completed" without user clicks. */
const WIZARD_DISMISS_KEY = 'openlimno-studio-wizard-dismissed';
const wizardSteps = [
  {
    id: 'river',
    targetSelector: '.sidebar section.panel:nth-of-type(2)',  /* River */
    detect: () => {
      const r = state?.river || {};
      return !!(r.name && r.name.trim() && Number(r.length_m) > 0);
    },
    activateTab: 'overview',
  },
  {
    id: 'habitat',
    targetSelector: '.workspace-tabs button[data-pane="cells"]',
    detect: () => Array.isArray(state?.cells) && state.cells.length > 0,
    activateTab: 'cells',
  },
  {
    id: 'species',
    targetSelector: '.sidebar details.collapsible:nth-of-type(1)',
    detect: () => !!(state?.profile && Object.keys(state.profile).length > 5),
    activateTab: null,
  },
  {
    id: 'population',
    targetSelector: '#initial_abundance',
    detect: () => {
      const c = state?.config || {};
      return Number(c.initial_abundance) > 0 && Number(c.days) > 0;
    },
    activateTab: null,
  },
  {
    id: 'validate',
    targetSelector: '#validateBtn',
    detect: () => wizardState.validated,
    activateTab: null,
  },
  {
    id: 'run',
    targetSelector: '#runBtn',
    detect: () => lastResult != null,
    activateTab: 'overview',
  },
];
const wizardState = {active: false, current: 0, validated: false};
let lastRiverViewPayload = null;
let dragStart = null;
const mapState = {
  zoom: 1,
  panX: 0,
  panY: 0,
  signature: '',
  inspect: false,
  showBoundary: true,
  showCenterline: true,
  showCells: true,
  showFish: true,
  showRedds: true,
  transform: null
};
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num = v => {
  if (v === '' || v === null || v === undefined) return v;
  const p = Number(v);
  return Number.isFinite(p) ? p : v;
};
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const fmt = (value, digits = 1) => {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : '-';
};
function riverDefaults(){return {name:'Lemhi River', reach_name:'Hayden Creek demo reach', length_m:380, flow_m3s:5.8, display_note:'', geometry:null};}
function gisDefaults(){return {centerline_path:'', centerline_layer:'', boundary_path:'', boundary_layer:'', cells_path:'', cells_layer:''};}
function setStatus(t){$('status').textContent=t;}
function log(t){const el=$('log'); el.textContent=`${new Date().toLocaleTimeString()}  ${t}\n`+el.textContent;}
async function api(path,payload){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); const data=await res.json(); if(!res.ok||data.ok===false) throw new Error(data.error||res.statusText); return data;}
async function loadDefault(){const res=await fetch('/api/default'); state=await res.json(); bindState(); renderAll(); /* First-time visitors get the wizard automatically; returning visitors who
     dismissed it stay on the regular UI. The wizard also coexists with the
     auto-run, so the user lands on a populated Studio with the strip up. */
  if (!wizardWasDismissed() && !wizardState.active){
    wizardState.active = true;
    wizardState.current = 0;
    renderWizardStrip();
  }
  await runModel();}
function bindState(){
  state.river = {...riverDefaults(), ...(state.river || {})};
  state.gis = {...gisDefaults(), ...(state.gis || {})};
  state.submodels = state.submodels || {};
  state.submodel_catalog = state.submodel_catalog || [];
  state.experiments = state.experiments || {ensemble:{}, calibration:{}};
  state.experiments.ensemble = state.experiments.ensemble || {};
  state.experiments.calibration = state.experiments.calibration || {};
  const c=state.config;
  ['scenario_id','reach_id','species','initial_abundance','initial_length_mm','days','seed'].forEach(id=>{$(id).value=c[id];});
  $('stochastic').checked=!!c.stochastic;
  $('record_individual_history').checked=!!c.record_individual_history;
  $('river_name').value=state.river.name || '';
  $('river_reach_name').value=state.river.reach_name || '';
  $('river_length_m').value=state.river.length_m ?? '';
  $('river_flow_m3s').value=state.river.flow_m3s ?? '';
  $('gis_centerline_path').value=state.gis.centerline_path || state.gis.river_path || '';
  $('gis_centerline_layer').value=state.gis.centerline_layer || state.gis.river_layer || '';
  $('gis_boundary_path').value=state.gis.boundary_path || '';
  $('gis_boundary_layer').value=state.gis.boundary_layer || '';
  $('gis_cells_path').value=state.gis.cells_path || '';
  $('gis_cells_layer').value=state.gis.cells_layer || '';
  const i=state.instream;
  $('instream_fixture').value=i.fixture||'';
  $('instream_case_id').value=i.case_id||'ExampleA';
  $('instream_days').value=i.days||2;
  $('instream_seed').value=i.seed||11;
  $('native_summary').value=i.native_summary||'';
  $('brief_pop').value=i.brief_pop||'';
  const e=state.experiments.ensemble;
  $('ensemble_seeds').value=e.seeds || '20260524,20260525,20260526';
  $('ensemble_params').value=e.parameter_specs || '';
  const cal=state.experiments.calibration;
  $('calibration_method').value=cal.method || 'grid';
  $('observed_path').value=cal.observed || '';
  $('calibration_params').value=cal.parameter_specs || '';
  $('calibration_samples').value=cal.samples ?? 8;
  $('acceptance_fraction').value=cal.acceptance_fraction ?? 0.25;
  $('calibration_tolerance').value=cal.tolerance ?? '';
}
function collectState(){
  /* Preserve population_cohorts coming from /api/default (real inSTREAM 7
     archive). The form has no cohort editor, so we copy the field through
     from state.config rather than letting it default to undefined; without
     this the immediate runModel() after loadDefault drops the cohorts and
     reverts to a uniform initial population (2026-05-28 review A1). */
  const config={scenario_id:$('scenario_id').value,reach_id:$('reach_id').value,species:$('species').value,initial_abundance:Number($('initial_abundance').value),initial_length_mm:Number($('initial_length_mm').value),days:Number($('days').value),seed:Number($('seed').value),stochastic:$('stochastic').checked,record_individual_history:$('record_individual_history').checked,population_cohorts:Array.isArray(state.config?.population_cohorts)?state.config.population_cohorts:undefined};
  const river={...riverDefaults(), name:$('river_name').value, reach_name:$('river_reach_name').value, length_m:Number($('river_length_m').value), flow_m3s:Number($('river_flow_m3s').value), display_note:state.river?.display_note || '', geometry:state.river?.geometry || null};
  const profile={...state.profile};
  document.querySelectorAll('[data-profile]').forEach(input=>{const key=input.getAttribute('data-profile'); profile[key]=input.type==='checkbox'?input.checked:num(input.value);});
  const submodels={...state.submodels};
  document.querySelectorAll('[data-submodel]').forEach(select=>{submodels[select.dataset.submodel]=select.value;});
  /* Merge edited rows back onto the full cells array. With large cases (e.g.
     inSTREAM ExampleA = 1373 surveyed cells) we render only the first
     MAX_CELL_ROWS in the table; the rest stay in state.cells untouched and
     are still sent to the IBM run. Without this preservation, switching to
     a real archive would silently truncate the IBM input to 80 cells. */
  const editedRows=[...document.querySelectorAll('#cellsTable tbody tr[data-cell-idx]')].map(tr=>{const idx=Number(tr.dataset.cellIdx); const base={...(state.cells?.[idx]||{})}; tr.querySelectorAll('input').forEach(input=>base[input.dataset.column]=num(input.value)); return [idx,base];});
  const cells=Array.isArray(state.cells)?[...state.cells]:[]; editedRows.forEach(([idx,row])=>{cells[idx]=row;});
  const experiments={ensemble:{seeds:$('ensemble_seeds').value,parameter_specs:$('ensemble_params').value},calibration:{method:$('calibration_method').value,observed:$('observed_path').value,parameter_specs:$('calibration_params').value,samples:Number($('calibration_samples').value),acceptance_fraction:Number($('acceptance_fraction').value),tolerance:$('calibration_tolerance').value}};
  const instream={fixture:$('instream_fixture').value,case_id:$('instream_case_id').value,days:Number($('instream_days').value),seed:Number($('instream_seed').value),native_summary:$('native_summary').value,brief_pop:$('brief_pop').value,abundance_tolerance:state.instream.abundance_tolerance??0,biomass_relative_tolerance:state.instream.biomass_relative_tolerance??0.05,mean_length_tolerance_mm:state.instream.mean_length_tolerance_mm??1.0};
  const gis={centerline_path:$('gis_centerline_path').value,centerline_layer:$('gis_centerline_layer').value,boundary_path:$('gis_boundary_path').value,boundary_layer:$('gis_boundary_layer').value,cells_path:$('gis_cells_path').value,cells_layer:$('gis_cells_layer').value};
  state={config,river,gis,profile,cells,submodels,submodel_catalog:state.submodel_catalog||[],experiments,instream};
  return state;
}
function renderGisGuidance(){
  const gis=state?.gis || {};
  const geometry=state?.river?.geometry || {};
  const quality=geometry.boundary_quality || {};
  const rows=[
    {ok:!!gis.boundary_path || Array.isArray(geometry.channel_polygon_m), warn:!gis.boundary_path && !geometry.channel_polygon_m, text:'Boundary polygon loaded or selected'},
    {ok:quality.status==='usable', warn:quality.status==='coarse', text:`Boundary quality: ${quality.status || 'not checked'}`},
    {ok:!!gis.cells_path || (state?.cells || []).some(cell=>Array.isArray(cell.polygon_m)), warn:!gis.cells_path, text:'Habitat-cell polygons for IBM fish positions'},
    {ok:!!gis.centerline_path || Array.isArray(geometry.centerline_m), warn:!gis.centerline_path, text:'Centerline for flow direction and stationing'}
  ];
  $('gisChecks').innerHTML=rows.map(row=>`<div class="gis-check"><span class="gis-dot ${row.ok?'ok':row.warn?'warn':''}"></span><span>${esc(row.text)}</span></div>`).join('');
}
function renderProfileTabs(){$('profileTabs').innerHTML=Object.keys(profileGroups).map(name=>`<button class="tab ${name===activeProfileGroup?'active':''}" data-tab="${esc(name)}">${esc(name)}</button>`).join(''); document.querySelectorAll('[data-tab]').forEach(btn=>btn.addEventListener('click',()=>{activeProfileGroup=btn.dataset.tab; renderProfileTabs(); renderProfileFields();}));}
function renderProfileFields(){const keys=profileGroups[activeProfileGroup]; $('profileFields').innerHTML=keys.map(key=>{const value=state.profile[key]; if(typeof value==='boolean') return `<div class="field check"><input data-profile="${key}" id="p_${key}" type="checkbox" ${value?'checked':''}><label for="p_${key}">${key}</label></div>`; const step=Number.isInteger(value)?'1':'0.001'; return `<div class="field"><label>${key}</label><input data-profile="${key}" type="number" step="${step}" value="${esc(value)}"></div>`;}).join('');}
function renderSubmodels(){const catalog=state.submodel_catalog||[]; const slots=[...new Set(catalog.map(m=>m.slot))]; $('submodelFields').innerHTML=slots.map(slot=>{const options=catalog.filter(m=>m.slot===slot).map(m=>`<option value="${esc(m.id)}" ${state.submodels?.[slot]===m.id?'selected':''}>${esc(m.label)}</option>`).join(''); return `<div class="field"><label>${esc(slot)}</label><select data-submodel="${esc(slot)}">${options}</select></div>`;}).join('');}
/* Render up to MAX_CELL_ROWS habitat cells in the editor table. Cases like
   inSTREAM ExampleA ship 1373 surveyed micro-cells — rendering them all
   produced a 71k-px-tall page with ~25000 input boxes. The IBM still uses
   every cell (see collectState above); editing past the cap requires
   exporting JSON. */
const MAX_CELL_ROWS=80;
function renderCells(){const head=`<thead><tr>${cellColumns.map(c=>`<th>${c}</th>`).join('')}<th></th></tr></thead>`; const total=state.cells.length; const rendered=Math.min(total,MAX_CELL_ROWS); const body=state.cells.slice(0,rendered).map((row,idx)=>`<tr data-cell-idx="${idx}">${cellColumns.map(c=>`<td><input data-column="${c}" value="${esc(row[c]??'')}"></td>`).join('')}<td><button class="btn warn" data-del-cell="${idx}">Del</button></td></tr>`).join(''); const overflow=total>MAX_CELL_ROWS?`<tr class="cells-overflow"><td colspan="${cellColumns.length+1}" style="font-style:italic;opacity:.75;text-align:center;padding:8px">Showing ${rendered} of ${total} cells — full set sent to IBM run. Use Export JSON to edit all cells.</td></tr>`:''; $('cellsTable').innerHTML=`${head}<tbody>${body}${overflow}</tbody>`; document.querySelectorAll('[data-del-cell]').forEach(btn=>btn.addEventListener('click',()=>{state.cells.splice(Number(btn.dataset.delCell),1); renderCells();}));}
function renderAll(){renderProfileTabs(); renderProfileFields(); renderSubmodels(); renderCells(); renderGisGuidance(); renderOfficialPlaceholder(); updateWizardProgress();}
function renderKpis(m){const items=[['Initial',m?.initial_abundance??'-'],['Final',m?.final_abundance??'-'],['Biomass g',m?.final_biomass_g?.toFixed?m.final_biomass_g.toFixed(1):'-'],['Mean length',m?.final_mean_length_mm?.toFixed?m.final_mean_length_mm.toFixed(1):'-'],['Survival',m?.survival_rate?.toFixed?m.survival_rate.toFixed(3):'-']]; $('kpis').innerHTML=items.map(([l,v])=>`<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div></div>`).join('');}
function acceptanceCard(label,value){return `<div class="acceptance-card"><div class="label">${esc(label)}</div><div class="value">${esc(value ?? '-')}</div></div>`;}
function workflowStatusClass(value){return ['passed','warning','error'].includes(value)?value:'warning';}
function workflowEvidence(evidence){
  const rows=Object.entries(evidence||{});
  if(!rows.length) return '<div class="mini-note">No evidence captured.</div>';
  return `<dl class="workflow-evidence">${rows.map(([label,value])=>`<dt>${esc(label)}</dt><dd>${esc(value ?? '-')}</dd>`).join('')}</dl>`;
}
function renderOfficialWorkflowPlaceholder(){
  const steps=[
    {label:'1 Case',summary:'select fixture and case'},
    {label:'2 GIS',summary:'read official polygons'},
    {label:'3 Hydraulics',summary:'load flow and velocity tables'},
    {label:'4 Population',summary:'build fish cohorts'},
    {label:'5 Run',summary:'execute native IBM'},
    {label:'6 Acceptance',summary:'capture outputs'}
  ];
  $('officialWorkflow').innerHTML=steps.map(step=>`<div class="workflow-step warning"><div class="workflow-step-label">${esc(step.label)}</div><div class="workflow-step-summary">${esc(step.summary)}</div><span class="workflow-step-status">waiting</span></div>`).join('');
  $('officialWorkflowDetails').innerHTML='<div class="workflow-empty">No official case has been run. The workflow will show the exact modeling evidence after execution.</div>';
}
function renderOfficialWorkflow(result){
  const steps=result?.workflow?.steps || [];
  if(!steps.length){renderOfficialWorkflowPlaceholder(); return;}
  $('officialWorkflow').innerHTML=steps.map(step=>{const cls=workflowStatusClass(step.status); return `<div class="workflow-step ${cls}"><div class="workflow-step-label">${esc(step.label)}</div><div class="workflow-step-summary">${esc(step.summary)}</div><span class="workflow-step-status">${esc(step.status)}</span></div>`;}).join('');
  $('officialWorkflowDetails').innerHTML=steps.map(step=>{const cls=workflowStatusClass(step.status); return `<div class="workflow-detail-card ${cls}"><div class="workflow-detail-title">${esc(step.label)}</div><div class="workflow-detail-summary">${esc(step.summary)}</div>${workflowEvidence(step.evidence)}</div>`;}).join('');
}
function renderOfficialPlaceholder(){
  $('officialStatus').textContent='no run';
  $('officialStatus').className='status-pill warning';
  $('officialSubtitle').textContent='Run an official inSTREAM or InSALMO fixture to populate this capture panel.';
  renderOfficialWorkflowPlaceholder();
  $('officialSummary').innerHTML=[
    acceptanceCard('Suite','-'),
    acceptanceCard('Cases','-'),
    acceptanceCard('Reaches','-'),
    acceptanceCard('Species','-'),
    acceptanceCard('Final abundance','-'),
    acceptanceCard('Adult arrivals','-')
  ].join('');
  table('officialFinalTable',[]);
  table('officialInventoryTable',[]);
  table('officialEventsTable',[]);
}
function renderOfficialBenchmark(result){
  const m=result.metrics||{};
  const events=m.event_counts||{};
  const eventSummary=Object.entries(events).map(([k,v])=>`${k}:${v}`).join(', ') || 'none';
  /* Reveal the official-result panel on first real capture (it starts
     display:none on page load so the workflow tab opens clean). */
  $('officialResult').style.display='';
  $('officialStatus').textContent='passed';
  $('officialStatus').className='status-pill pass';
  $('officialSubtitle').textContent=`${m.suite||'official'} ${result.run_id||''} · ${result.run_dir||''}`;
  renderOfficialWorkflow(result);
  $('officialSummary').innerHTML=[
    acceptanceCard('Suite',m.suite||'official'),
    acceptanceCard('Cases',m.case_count),
    acceptanceCard('Reaches',m.reach_count),
    acceptanceCard('Species',Array.isArray(m.species)?m.species.join(', '):m.species_count),
    acceptanceCard('GIS cells',m.gis_cells),
    acceptanceCard('Boundary vertices',m.gis_boundary_vertices),
    acceptanceCard('Final abundance',m.final_abundance),
    acceptanceCard('Adult arrivals',m.adult_arrival_fish),
    acceptanceCard('Flow range',m.min_flow_m3s!==null&&m.min_flow_m3s!==undefined?`${m.min_flow_m3s} - ${m.max_flow_m3s}`:'-'),
    acceptanceCard('Population rows',m.population_rows),
    acceptanceCard('Events',eventSummary)
  ].join('');
  table('officialFinalTable',result.final_population||[],['scenario_id','reach_id','species','day','abundance','biomass_g','mean_length_mm','n_spawners','n_recruits']);
  table('officialInventoryTable',result.inventory||[],['case_id','reach_id','species','n_initial_fish','n_adult_arrival_fish','n_cells','n_time_series_rows','min_flow_m3s','max_flow_m3s']);
  table('officialEventsTable',result.events||[],['day','event','reach_id','species','n','n_eggs']);
  table('compareTable',result.final_population||[],['scenario_id','reach_id','species','day','abundance','biomass_g','mean_length_mm']);
  table('cellUseTable',result.cell_use||[],['scenario_id','reach_id','species','day','phase','cell_id','n_fish','mean_growth_mm','mean_mortality_risk']);
  table('eventsTable',result.events||[],['day','event','reach_id','species','n','n_eggs']);
  table('fishTable',result.final_individuals||[],['fish_id','species','age_days','length_mm','mass_g','cell_id','alive','reach_id']);
  table('reddsTable',result.redds||[],['redd_id','day','reach_id','cell_id','eggs_remaining','degree_days','active']);
  if(result.river_view) drawRiverView(result);
}
function drawChart(rows){const metric=$('metricSelect').value, svg=$('chart'); const w=900,h=280,l=48,r=18,t=18,b=34,pw=w-l-r,ph=h-t-b; if(!rows||!rows.length){svg.innerHTML='';return;} const xs=rows.map(d=>Number(d.day)), ys=rows.map(d=>Number(d[metric])); const maxX=Math.max(...xs,1); let minY=Math.min(...ys), maxY=Math.max(...ys); if(minY===maxY){minY-=1; maxY+=1;} const point=(x,y)=>[l+x/maxX*pw,t+(1-(y-minY)/(maxY-minY))*ph]; const pts=rows.map(d=>point(Number(d.day),Number(d[metric])).map(v=>v.toFixed(1)).join(',')).join(' '); svg.innerHTML=`<line class="axis" x1="${l}" y1="${t}" x2="${l}" y2="${t+ph}"/><line class="axis" x1="${l}" y1="${t+ph}" x2="${l+pw}" y2="${t+ph}"/><line class="grid" x1="${l}" y1="${t}" x2="${l+pw}" y2="${t}"/><line class="grid" x1="${l}" y1="${t+ph/2}" x2="${l+pw}" y2="${t+ph/2}"/><polyline class="line" points="${pts}"/><text x="8" y="${t+4}" font-size="12" fill="#526173">${maxY.toFixed(1)}</text><text x="8" y="${t+ph+4}" font-size="12" fill="#526173">${minY.toFixed(1)}</text><text x="${l}" y="${h-8}" font-size="12" fill="#526173">day 0</text><text x="${l+pw-54}" y="${h-8}" font-size="12" fill="#526173">day ${maxX}</text>`;}
function drawBandChart(rows){const metric=$('bandMetricSelect').value, svg=$('bandChart'); const w=900,h=280,l=48,r=18,t=18,b=34,pw=w-l-r,ph=h-t-b; if(!rows||!rows.length){svg.innerHTML='';return;} const lo=`${metric}_p05`, mid=`${metric}_p50`, hi=`${metric}_p95`; const xs=rows.map(d=>Number(d.day)), lows=rows.map(d=>Number(d[lo])), mids=rows.map(d=>Number(d[mid])), highs=rows.map(d=>Number(d[hi])); const maxX=Math.max(...xs,1); let minY=Math.min(...lows.filter(Number.isFinite),...mids.filter(Number.isFinite)), maxY=Math.max(...highs.filter(Number.isFinite),...mids.filter(Number.isFinite)); if(!Number.isFinite(minY)||!Number.isFinite(maxY)){svg.innerHTML='';return;} if(minY===maxY){minY-=1; maxY+=1;} const point=(x,y)=>[l+x/maxX*pw,t+(1-(y-minY)/(maxY-minY))*ph]; const upper=rows.map(d=>point(Number(d.day),Number(d[hi])).map(v=>v.toFixed(1)).join(',')).join(' '); const lower=[...rows].reverse().map(d=>point(Number(d.day),Number(d[lo])).map(v=>v.toFixed(1)).join(',')).join(' '); const median=rows.map(d=>point(Number(d.day),Number(d[mid])).map(v=>v.toFixed(1)).join(',')).join(' '); svg.innerHTML=`<line class="axis" x1="${l}" y1="${t}" x2="${l}" y2="${t+ph}"/><line class="axis" x1="${l}" y1="${t+ph}" x2="${l+pw}" y2="${t+ph}"/><polygon points="${upper} ${lower}" fill="#0f766e" opacity=".18"/><polyline class="line" points="${median}"/><text x="8" y="${t+4}" font-size="12" fill="#526173">${maxY.toFixed(1)}</text><text x="8" y="${t+ph+4}" font-size="12" fill="#526173">${minY.toFixed(1)}</text><text x="${l}" y="${h-8}" font-size="12" fill="#526173">day 0</text><text x="${l+pw-54}" y="${h-8}" font-size="12" fill="#526173">day ${maxX}</text>`;}
function hexToRgb(hex){const m=hex.replace('#',''); return [parseInt(m.slice(0,2),16),parseInt(m.slice(2,4),16),parseInt(m.slice(4,6),16)];}
function mixHex(a,b,t){const ar=hexToRgb(a), br=hexToRgb(b), p=clamp(t,0,1); const out=ar.map((v,i)=>Math.round(v+(br[i]-v)*p)); return `rgb(${out[0]},${out[1]},${out[2]})`;}
function cellColor(cell, metric, cells){
  if(metric==='habitat_type') return habitatColors[String(cell.habitat_type || 'cell')] || habitatColors.cell;
  const raw = Number(cell[metric] ?? 0);
  let t = 0;
  if(metric==='csi') t = clamp(raw,0,1);
  else if(metric==='depth_m') t = clamp(raw / 1.3,0,1);
  else if(metric==='velocity_ms') t = clamp(raw / 1.3,0,1);
  else if(metric==='total_fish_use') {const maxUse=Math.max(1,...cells.map(c=>Number(c.total_fish_use||0))); t=clamp(raw/maxUse,0,1);}
  if(metric==='velocity_ms') return mixHex('#d7f0ff','#e36c42',t);
  if(metric==='total_fish_use') return mixHex('#f4e9b5','#0f766e',t);
  return mixHex('#e8f6ec','#2563eb',t);
}
function renderRiverLegend(view, metric){
  const cells=Array.isArray(view?.cells)?view.cells:[];
  const fish=Array.isArray(view?.fish)?view.fish:[];
  const redds=Array.isArray(view?.redds)?view.redds:[];
  const riverGeometry=view?.river?.geometry || {};
  const showDead=$('showDeadFish')?.checked;
  const liveFishVisible=mapState.showFish && fish.some(f=>f.alive);
  const deadFishVisible=mapState.showFish && showDead && fish.some(f=>!f.alive);
  const reddsVisible=mapState.showRedds && redds.length;
  if(!cells.length){
    const rows=[
      mapState.showBoundary && Array.isArray(riverGeometry.channel_polygon_m) && riverGeometry.channel_polygon_m.length>=3 ? '<div class="legend-row"><span class="legend-swatch" style="background:#9fd3e7"></span>River boundary</div>' : '',
      mapState.showCenterline && Array.isArray(riverGeometry.centerline_m) && riverGeometry.centerline_m.length>=2 ? '<div class="legend-row"><span class="legend-swatch" style="background:#2563eb"></span>Centerline</div>' : '',
      liveFishVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#f59e0b"></span>Preview fish</div>' : '',
      deadFishVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#6b7280"></span>Dead fish</div>' : '',
      reddsVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#dc6b19"></span>Redd</div>' : '',
    ].join('');
    $('riverLegend').innerHTML=`<strong>Layers</strong>${rows || '<div class="legend-row">No visible layers</div>'}`;
    return;
  }
  if(metric==='habitat_type'){
    const rows=Object.entries(habitatColors).slice(0,8).map(([name,color])=>`<div class="legend-row"><span class="legend-swatch" style="background:${color}"></span>${esc(name)}</div>`).join('');
    $('riverLegend').innerHTML=`<strong>Habitat</strong>${rows}`;
    return;
  }
  const label={csi:'CSI low to high',depth_m:'Depth shallow to deep',velocity_ms:'Velocity slow to fast',total_fish_use:'Fish use low to high'}[metric] || metric;
  const overlayRows=[
    liveFishVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#f59e0b"></span>Live fish</div>' : '',
    deadFishVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#6b7280"></span>Dead fish</div>' : '',
    reddsVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#dc6b19"></span>Redd</div>' : '',
  ].join('');
  $('riverLegend').innerHTML=`<strong>${esc(label)}</strong><div class="legend-row"><span class="legend-swatch" style="background:#e8f6ec"></span>Low</div><div class="legend-row"><span class="legend-swatch" style="background:#2563eb"></span>High</div>${overlayRows}`;
}
function svgPoints(points,sx,sy){return (points||[]).map(p=>`${sx(Number(p[0])).toFixed(1)},${sy(Number(p[1])).toFixed(1)}`).join(' ');}
function previewBounds(river,cells){
  const geometry=river?.geometry || {}; const points=[];
  ['centerline_m','channel_polygon_m'].forEach(key=>{if(Array.isArray(geometry[key])) geometry[key].forEach(point=>points.push(point));});
  (cells||[]).forEach(cell=>{if(Array.isArray(cell.polygon_m)) cell.polygon_m.forEach(point=>points.push(point)); else points.push([cell.center_x_m || 0, cell.center_y_m || 0]);});
  const valid=points.map(point=>[Number(point[0]),Number(point[1])]).filter(point=>Number.isFinite(point[0])&&Number.isFinite(point[1]));
  if(!valid.length) return {min_x:0,max_x:1,min_y:0,max_y:1};
  const xs=valid.map(point=>point[0]), ys=valid.map(point=>point[1]); const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys); const pad=Math.max(Math.max(maxX-minX,maxY-minY)*0.04,12);
  return {min_x:minX-pad,max_x:maxX+pad,min_y:minY-pad,max_y:maxY+pad};
}
function seededUnit(index,salt){let v=(index*1103515245+salt*12345+0x9e3779b9)>>>0; v^=v<<13; v^=v>>>17; v^=v<<5; return ((v>>>0)%1000000)/1000000;}
function pointInPolygon(x,y,polygon){
  let inside=false;
  for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
    const xi=Number(polygon[i][0]), yi=Number(polygon[i][1]), xj=Number(polygon[j][0]), yj=Number(polygon[j][1]);
    const intersect=((yi>y)!==(yj>y)) && (x < (xj-xi)*(y-yi)/(yj-yi+1e-12)+xi);
    if(intersect) inside=!inside;
  }
  return inside;
}
function previewFish(river){
  const polygon=river?.geometry?.channel_polygon_m;
  if(!Array.isArray(polygon) || polygon.length<3) return [];
  const xs=polygon.map(p=>Number(p[0])).filter(Number.isFinite), ys=polygon.map(p=>Number(p[1])).filter(Number.isFinite);
  if(!xs.length || !ys.length) return [];
  const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
  const target=Math.min(Math.max(Number(state.config?.initial_abundance || 0),0),80);
  const fish=[];
  for(let attempt=0; fish.length<target && attempt<target*120+400; attempt++){
    const x=minX+seededUnit(attempt,17)*(maxX-minX);
    const y=minY+seededUnit(attempt,29)*(maxY-minY);
    if(!pointInPolygon(x,y,polygon)) continue;
    fish.push({fish_id:`preview-${fish.length+1}`,species:state.config?.species || 'fish',age_days:0,length_mm:Number(state.config?.initial_length_mm || 100),x_m:x,y_m:y,cell_id:'boundary-preview',alive:true,display_size:3.2});
  }
  return fish;
}
function riverViewSignature(view){
  const b=view?.bounds || {};
  const g=view?.geometry || {};
  return [b.min_x,b.max_x,b.min_y,b.max_y,(g.channel_polygon_m||[]).length,(g.centerline_m||[]).length,(view?.cells||[]).length,(view?.fish||[]).length,!!view?.fish_preview].join('|');
}
function syncLayerState(){
  ['showBoundary','showCenterline','showCells','showFish','showRedds'].forEach(id=>{const el=$(id); if(el) mapState[id]=el.checked;});
}
function resetMapView(){
  mapState.zoom=1;
  mapState.panX=0;
  mapState.panY=0;
  mapState.signature='';
}
function rerenderRiverView(){
  if(lastRiverViewPayload) drawRiverView(lastRiverViewPayload);
}
function zoomMap(multiplier){
  mapState.zoom=clamp(mapState.zoom*multiplier,0.4,8);
  rerenderRiverView();
}
function niceScaleLength(raw){
  if(!Number.isFinite(raw) || raw<=0) return 1;
  const power=Math.pow(10,Math.floor(Math.log10(raw)));
  const scaled=raw/power;
  const base=scaled>=5?5:scaled>=2?2:1;
  return base*power;
}
function renderQualityStrip(view){
  const geometry=view?.geometry || {};
  const quality=geometry.boundary_quality || {};
  const status=quality.status || 'missing';
  const statusClass=status==='usable'?'good':status==='coarse'?'warn':status==='invalid'?'bad':'';
  const cells=Array.isArray(view?.cells)?view.cells.length:0;
  const fishMode=view?.fish_preview?'preview fish':(Array.isArray(view?.fish)&&view.fish.length?'IBM fish':'no fish');
  const items=[
    {label:`Boundary ${status}`, cls:statusClass},
    {label:`CRS ${geometry.crs || '-'}`, cls:''},
    {label:`Vertices ${quality.boundary_vertices || 0}`, cls:''},
    {label:`Cells ${cells}`, cls:cells?'good':'warn'},
    {label:fishMode, cls:view?.fish_preview?'warn':fishMode==='IBM fish'?'good':''}
  ];
  $('qualityStrip').innerHTML=items.map(item=>`<span class="quality-pill ${item.cls}">${esc(item.label)}</span>`).join('');
}
function renderGisPreview(){
  const river=state.river || {}; const cells=state.cells || [];
  const fish=cells.length?[]:previewFish(river);
  const payload={river_view:{river,cells,fish,redds:[],geometry:river.geometry || {},bounds:previewBounds(river,cells),fish_preview:!cells.length && fish.length>0}};
  drawRiverView(payload);
}
function drawRiverView(result){
  const svg=$('riverView'); const view=result?.river_view;
  lastRiverViewPayload=result;
  syncLayerState();
  if(!view){svg.innerHTML=''; $('riverMeta').innerHTML=''; $('qualityStrip').innerHTML=''; return;}
  const cells=Array.isArray(view.cells)?[...view.cells].sort((a,b)=>Number(a.station_m)-Number(b.station_m)):[];
  const geometry=view.geometry || {}; const centerline=Array.isArray(geometry.centerline_m)?geometry.centerline_m:[]; const channel=Array.isArray(geometry.channel_polygon_m)?geometry.channel_polygon_m:[];
  if(!cells.length && centerline.length<2 && channel.length<3){svg.innerHTML=''; $('riverMeta').innerHTML=''; $('qualityStrip').innerHTML=''; return;}
  const signature=riverViewSignature(view);
  if(signature!==mapState.signature){mapState.signature=signature; mapState.zoom=1; mapState.panX=0; mapState.panY=0;}
  renderQualityStrip(view);
  const w=900,h=360,pad=42, bounds=view.bounds || {}; const minX=Number(bounds.min_x ?? 0), maxX=Number(bounds.max_x ?? 1), minY=Number(bounds.min_y ?? 0), maxY=Number(bounds.max_y ?? 1); const spanX=Math.max(maxX-minX,1), spanY=Math.max(maxY-minY,1);
  const scale=Math.min((w-pad*2)/spanX,(h-pad*2)/spanY);
  const drawW=spanX*scale, drawH=spanY*scale, offsetX=(w-drawW)/2, offsetY=(h-drawH)/2;
  mapState.transform={minX,maxY,scale,offsetX,offsetY};
  const sx=x=>offsetX+(Number(x)-minX)*scale; const sy=y=>offsetY+(maxY-Number(y))*scale;
  const metric=$('cellColorMetric').value;
  let water='';
  if(mapState.showBoundary && channel.length>=3){
    water=`<polygon class="bank-shape" points="${svgPoints(channel,sx,sy)}"><title>${esc(geometry.source || 'river channel geometry')}</title></polygon>`;
  }
  const centerlineShape=mapState.showCenterline&&centerline.length>=2?`<polyline class="${channel.length>=3?'centerline-shape':'centerline-only'}" points="${svgPoints(centerline,sx,sy)}"><title>${channel.length>=3?'flow centerline':'GIS centerline only; no channel polygon imported'}</title></polyline>`:'';
  const showCellLabels=cells.length<=180;
  const cellShapes=mapState.showCells?cells.map(cell=>{const fill=cellColor(cell,metric,cells); const polygon=Array.isArray(cell.polygon_m)?cell.polygon_m:[]; const title=`${esc(cell.cell_id)} | ${esc(cell.habitat_type)} | CSI ${fmt(cell.csi,2)} | depth ${fmt(cell.depth_m,2)} m | velocity ${fmt(cell.velocity_ms,2)} m/s | fish-use ${esc(cell.total_fish_use)}`; if(polygon.length>=3){const label=showCellLabels?`<text class="cell-label" x="${sx(cell.center_x_m).toFixed(1)}" y="${(sy(cell.center_y_m)+3).toFixed(1)}" text-anchor="middle">${esc(cell.cell_id)}</text>`:''; return `<g><polygon class="cell-shape" points="${svgPoints(polygon,sx,sy)}" fill="${fill}" opacity=".78"><title>${title}</title></polygon>${label}</g>`;} const x1=sx(Number(cell.center_x_m)-Number(cell.length_m)/2), x2=sx(Number(cell.center_x_m)+Number(cell.length_m)/2), y1=sy(Number(cell.center_y_m)-Number(cell.width_m)/2), y2=sy(Number(cell.center_y_m)+Number(cell.width_m)/2); const x=Math.min(x1,x2), y=Math.min(y1,y2), cw=Math.max(Math.abs(x2-x1),22), ch=Math.max(Math.abs(y2-y1),12); const label=showCellLabels?`<text class="cell-label" x="${(x+cw/2).toFixed(1)}" y="${(y+ch/2+3).toFixed(1)}" text-anchor="middle">${esc(cell.cell_id)}</text>`:''; return `<g><rect class="cell-shape" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${cw.toFixed(1)}" height="${ch.toFixed(1)}" rx="7" fill="${fill}" opacity=".78"><title>${title}</title></rect>${label}</g>`;}).join(''):'';
  const showDead=$('showDeadFish').checked; const fish=mapState.showFish?(view.fish||[]).filter(f=>showDead || f.alive):[];
  const fishShapes=fish.map(f=>{const x=sx(f.x_m), y=sy(f.y_m), s=Number(f.display_size || 3)/3.1, fill=f.alive?'#f59e0b':'#6b7280', stroke=f.alive?'#1d4ed8':'#374151'; return `<g transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${s.toFixed(2)})"><title>fish ${esc(f.fish_id)} | ${esc(f.cell_id)} | ${fmt(f.length_mm,1)} mm | ${f.alive?'alive':'dead'}</title><path class="fish-shape" d="M-2.6 0 C-1.2 -1.45 1.35 -1.45 2.75 0 C1.35 1.45 -1.2 1.45 -2.6 0 Z" fill="${fill}" stroke="${stroke}"/><path d="M-2.45 0 L-4.0 -1.25 L-4.0 1.25 Z" fill="${fill}" stroke="${stroke}" stroke-width=".35"/><circle cx="1.5" cy="-.32" r=".22" fill="#102030"/></g>`;}).join('');
  const reddShapes=mapState.showRedds?(view.redds||[]).map(r=>{const x=sx(r.x_m), y=sy(r.y_m), s=Number(r.display_size || 5); return `<g><title>redd ${esc(r.redd_id)} | ${esc(r.cell_id)} | eggs ${esc(r.eggs_remaining)}</title><path class="redd-shape" d="M ${x.toFixed(1)} ${(y-s).toFixed(1)} L ${(x+s).toFixed(1)} ${y.toFixed(1)} L ${x.toFixed(1)} ${(y+s).toFixed(1)} L ${(x-s).toFixed(1)} ${y.toFixed(1)} Z" opacity="${r.active ? '.92' : '.42'}"/></g>`;}).join(''):'';
  const arrow=`<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#1f5f78"/></marker></defs><line x1="${w-160}" y1="34" x2="${w-72}" y2="34" stroke="#1f5f78" stroke-width="3" marker-end="url(#arrow)"/><text x="${w-158}" y="24" fill="#1f5f78" font-size="12">flow</text>`;
  const metersPerPx=1/(scale*mapState.zoom);
  const scaleMeters=niceScaleLength(110*metersPerPx);
  const scalePx=scaleMeters/metersPerPx;
  const scaleLabel=scaleMeters>=1000?`${fmt(scaleMeters/1000,1)} km`:`${fmt(scaleMeters,0)} m`;
  const scaleBar=`<g><line x1="28" y1="${h-28}" x2="${(28+scalePx).toFixed(1)}" y2="${h-28}" stroke="#1f5f78" stroke-width="3"/><line x1="28" y1="${h-33}" x2="28" y2="${h-23}" stroke="#1f5f78" stroke-width="2"/><line x1="${(28+scalePx).toFixed(1)}" y1="${h-33}" x2="${(28+scalePx).toFixed(1)}" y2="${h-23}" stroke="#1f5f78" stroke-width="2"/><text x="28" y="${h-36}" fill="#1f5f78" font-size="12">${scaleLabel}</text></g>`;
  const previewBadge=view.fish_preview?`<g><rect class="preview-badge" x="28" y="24" width="186" height="24" rx="5"/><text x="38" y="40" fill="#fff7ed" font-size="12" font-weight="700">Preview fish, not IBM output</text></g>`:'';
  const transform=`translate(${mapState.panX.toFixed(1)} ${mapState.panY.toFixed(1)}) scale(${mapState.zoom.toFixed(3)})`;
  svg.innerHTML=`<rect x="0" y="0" width="${w}" height="${h}" fill="#f4f8f6"/><g id="mapContent" transform="${transform}">${water}${centerlineShape}${cellShapes}${reddShapes}${fishShapes}</g>${arrow}${scaleBar}${previewBadge}`;
  const river=view.river || {}; const alive=fish.filter(f=>f.alive).length; const dead=fish.length-alive; const reddCount=mapState.showRedds?(view.redds||[]).length:0;
  $('riverTitle').textContent=`${river.name || 'River'} / ${river.reach_name || 'Reach'}`;
  const shapeLabel=channel.length>=3?'channel polygon':(centerline.length>=2?'centerline only':'no river geometry');
  const quality=geometry.boundary_quality || {};
  const vertexLabel=Number(quality.boundary_vertices || 0)>0?` · ${Number(quality.boundary_vertices)} boundary vertices`:'';
  const qualityLabel=quality.status?` · ${esc(quality.status)}`:'';
  const geometryLabel=centerline.length||channel.length?`${esc(geometry.source || 'payload geometry')} · ${esc(geometry.crs || 'local_m')} · ${shapeLabel}${vertexLabel}${qualityLabel}`:'no river boundary loaded; habitat cells only';
  const warning=quality.status==='coarse'||quality.status==='invalid'?`<div class="river-warning">Boundary quality: ${esc(quality.status)}. Do not treat this view as surveyed bank-line evidence.</div>`:'';
  const fishLayer=view.fish_preview?'<div>Fish layer: preview only inside boundary; import habitat cells for IBM positions.</div>':'';
  const note=river.display_note?`<div>Note: ${esc(river.display_note)}</div>`:'';
  $('riverMeta').innerHTML=`<strong>${esc(river.name || 'River')}</strong><div>${esc(river.reach_name || '')}</div><div>Geometry: ${geometryLabel}</div>${warning}<div>Length: ${fmt(river.length_m,0)} m</div><div>Flow: ${fmt(river.flow_m3s,1)} m3/s</div><div>Cells: ${cells.length}</div><div>Fish visible: ${fish.length} (${alive} alive, ${dead} dead)</div>${fishLayer}<div>Redds: ${reddCount}</div>${note}`;
  renderRiverLegend(view, metric);
}
function updateMapCoordinates(event){
  const tr=mapState.transform;
  if(!tr){$('mapCoords').textContent='x -, y -'; return;}
  const rect=$('riverView').getBoundingClientRect();
  const px=(event.clientX-rect.left)*(900/rect.width);
  const py=(event.clientY-rect.top)*(360/rect.height);
  const baseX=(px-mapState.panX)/mapState.zoom;
  const baseY=(py-mapState.panY)/mapState.zoom;
  const x=tr.minX+(baseX-tr.offsetX)/tr.scale;
  const y=tr.maxY-(baseY-tr.offsetY)/tr.scale;
  if(Number.isFinite(x)&&Number.isFinite(y)) $('mapCoords').textContent=`x ${fmt(x,1)} m, y ${fmt(y,1)} m`;
}
function inspectFeature(event){
  if(!mapState.inspect) return;
  const holder=event.target.closest('g, polygon, polyline, rect, path');
  const title=holder?.querySelector?.('title')?.textContent || event.target.querySelector?.('title')?.textContent || '';
  if(title) setStatus(`Inspect: ${title}`);
}
function setInspectMode(enabled){
  mapState.inspect=enabled;
  $('inspectMapBtn').classList.toggle('active',enabled);
  $('riverView').style.cursor=enabled?'crosshair':'grab';
}
function toggleFullscreen(){
  const card=$('riverCard');
  card.classList.toggle('fullscreen');
  const enabled=card.classList.contains('fullscreen');
  document.body.classList.toggle('map-fullscreen-open',enabled);
  $('fullMapBtn').classList.toggle('active',enabled);
  $('fullMapBtn').textContent=enabled?'Exit':'Full';
  setTimeout(rerenderRiverView,0);
}
function cellValue(c,v){if(c==='status') return `<span class="status-pill ${esc(v)}">${esc(v)}</span>`; return esc(v);}
/* Cap read-only result tables (cell_use_summary, events, individuals, etc.)
   at MAX_TABLE_ROWS to avoid blowing up the page on large cases. */
const MAX_TABLE_ROWS=120;
function table(id,rows,columns){if(!rows||!rows.length){$(id).innerHTML='<tbody><tr><td>No rows</td></tr></tbody>';return;} const cols=columns||Object.keys(rows[0]).slice(0,12); const total=rows.length; const rendered=Math.min(total,MAX_TABLE_ROWS); const body=rows.slice(0,rendered).map(row=>`<tr>${cols.map(c=>`<td>${cellValue(c,row[c])}</td>`).join('')}</tr>`).join(''); const overflow=total>MAX_TABLE_ROWS?`<tr><td colspan="${cols.length}" style="font-style:italic;opacity:.75;text-align:center;padding:6px">Showing ${rendered} of ${total} rows</td></tr>`:''; $(id).innerHTML=`<thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${body}${overflow}</tbody>`;}
function renderPaths(paths){$('paths').innerHTML=Object.entries(paths||{}).map(([name,path])=>`<li><strong>${esc(name)}</strong>: ${esc(path)}</li>`).join('');}
function addHistory(result){if(!result?.metrics) return; runHistory.unshift({run_id:result.run_id,final_abundance:result.metrics.final_abundance,biomass_g:fmt(result.metrics.final_biomass_g,1),mean_length_mm:fmt(result.metrics.final_mean_length_mm,1),survival:fmt(result.metrics.survival_rate,3),run_dir:result.run_dir}); runHistory=runHistory.slice(0,12); table('historyTable',runHistory,['run_id','final_abundance','biomass_g','mean_length_mm','survival']);}
function renderValidation(result){table('validationTable',result.checks||[],['area','status','message','detail']);}
function renderEnsemble(result){lastEnsemble=result; table('ensembleTable',result.summary||[],['run_index','seed','parameter_index','final_abundance','final_biomass_g','final_mean_length_mm']); table('sensitivityTable',result.sensitivity||[],['parameter','target','pearson_r','abs_pearson_r','n']); drawBandChart(result.daily_bands||[]); renderPaths(result.paths); log(`Ensemble ${result.run_id}: ${result.metrics.n_runs} runs`); setStatus(`Ensemble complete: ${result.run_dir}`);}
function renderCalibration(result){const params=Object.entries(result.best_parameters||{}).map(([k,v])=>`${esc(k)}=${fmt(v,4)}`).join(', '); $('bestParams').innerHTML=params?`Best: ${params} · score ${fmt(result.metrics.best_score,3)}`:''; table('calibrationTable',result.summary||[],['candidate_id','score','accepted','final_abundance','param_base_daily_survival','param_predation_base_risk']); renderPaths(result.paths); log(`Calibration ${result.run_id}: score ${fmt(result.metrics.best_score,3)}`); setStatus(`Calibration complete: ${result.run_dir}`);}
function renderResult(result){lastResult=result; renderKpis(result.metrics); drawRiverView(result); drawChart(result.population_summary); addHistory(result); table('cellUseTable',result.cell_use_summary,['cell_id','total_fish_use','mean_growth_mm','mean_mortality_risk']); table('eventsTable',result.events,['day','event','n','n_eggs']); table('fishTable',result.final_individuals,['fish_id','species','age_days','length_mm','mass_g','cell_id','alive','reach_id']); table('reddsTable',result.redds,['redd_id','day','reach_id','cell_id','eggs_remaining','degree_days','active']); renderPaths(result.paths);}
async function runModel(){setBusy(true); try{const result=await api('/api/run',collectState()); renderResult(result); updateWizardProgress(); log(`Run ${result.run_id}: final abundance ${result.metrics.final_abundance}`); setStatus(`Run complete: ${result.run_dir}`);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
async function validateModel(){setBusy(true); try{const result=await api('/api/validate',collectState()); renderValidation(result); renderPaths(result.paths); wizardState.validated = result.ok && (result.metrics?.errors|0)===0; updateWizardProgress(); log(`Validation ${result.run_id}: ${result.metrics.errors} errors, ${result.metrics.warnings} warnings`); setStatus(result.ok?`Validation passed: ${result.run_dir}`:`Validation needs attention: ${result.run_dir}`);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}

/* ---- Wizard implementation ---- */
function wizardStartFresh(){
  wizardState.active = true;
  wizardState.current = 0;
  wizardState.validated = false;
  try { localStorage.removeItem(WIZARD_DISMISS_KEY); } catch (e) {}
  renderWizardStrip();
  wizardFocusStep(0);
}
function wizardDismiss(){
  wizardState.active = false;
  try { localStorage.setItem(WIZARD_DISMISS_KEY, String(Date.now())); } catch (e) {}
  renderWizardStrip();
}
function wizardWasDismissed(){
  try { return !!localStorage.getItem(WIZARD_DISMISS_KEY); } catch (e) { return false; }
}
function renderWizardStrip(){
  const strip = $('wizardStrip');
  if (!wizardState.active){ strip.style.display = 'none'; return; }
  strip.style.display = 'flex';
  wizardSteps.forEach((step, idx) => {
    const pill = document.querySelector(`[data-wizard-step="${step.id}"]`);
    if (!pill) return;
    const done = !!step.detect();
    pill.classList.toggle('completed', done);
    pill.classList.toggle('active', idx === wizardState.current && !done);
    if (done){ pill.querySelector('.wizard-num').textContent = '✓'; }
    else { pill.querySelector('.wizard-num').textContent = String(idx + 1); }
  });
}
function updateWizardProgress(){
  if (!wizardState.active) return;
  /* Auto-advance current pointer past completed steps. */
  while (wizardState.current < wizardSteps.length
         && wizardSteps[wizardState.current].detect()){
    wizardState.current += 1;
  }
  renderWizardStrip();
}
function wizardFocusStep(idx){
  const step = wizardSteps[idx];
  if (!step) return;
  /* Switch to the appropriate workspace tab if the step lives there. */
  if (step.activateTab){
    const tabBtn = document.querySelector(`.workspace-tabs button[data-pane="${step.activateTab}"]`);
    if (tabBtn) tabBtn.click();
  }
  setTimeout(() => {
    const target = document.querySelector(step.targetSelector);
    if (!target) return;
    target.scrollIntoView({behavior: 'smooth', block: 'center'});
    target.classList.add('wizard-focus');
    setTimeout(() => target.classList.remove('wizard-focus'), 3000);
  }, 60);
}
document.querySelectorAll('.wizard-step').forEach(pill => {
  pill.addEventListener('click', () => {
    const stepId = pill.dataset.wizardStep;
    const idx = wizardSteps.findIndex(s => s.id === stepId);
    if (idx < 0) return;
    wizardState.current = idx;
    wizardFocusStep(idx);
    renderWizardStrip();
  });
  pill.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' || ev.key === ' '){ ev.preventDefault(); pill.click(); }
  });
});
async function runEnsemble(){setBusy(true); try{const result=await api('/api/ensemble',collectState()); renderEnsemble(result);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
async function runCalibration(){setBusy(true); try{const result=await api('/api/calibrate',collectState()); renderCalibration(result);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
async function importGIS(){setBusy(true); try{collectState(); const result=await api('/api/gis/import',{...state.gis,river_name:state.river.name,reach_name:state.river.reach_name,flow_m3s:state.river.flow_m3s,reach_id:state.config.reach_id}); state.river={...state.river,...result.river}; state.cells=Array.isArray(result.cells)?result.cells:[]; bindState(); renderAll(); const msg=(result.messages||[]).join(' '); log(`GIS import: ${result.metrics.centerline_points} centerline points, ${result.metrics.channel_polygon_points} channel points, ${result.metrics.cell_features} cells, boundary ${result.metrics.boundary_quality}/${result.metrics.boundary_vertices} vertices${msg?` · ${msg}`:''}`); if(!state.cells.length){renderGisPreview(); setStatus(`GIS imported: ${result.metrics.target_crs} · boundary ${result.metrics.boundary_quality} · no habitat cells`); return;} const run=await api('/api/run',collectState()); renderResult(run); setStatus(`GIS imported: ${result.metrics.target_crs} · boundary ${result.metrics.boundary_quality}`);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
function setBusy(busy){['runBtn','validateBtn','stepBtn','ensembleBtn','calibrateBtn','gisImportBtn','benchBtn','compareBtn'].forEach(id=>$(id).disabled=busy);}
async function runBenchmark(){setBusy(true); try{const result=await api('/api/instream7/benchmark',collectState().instream); renderOfficialBenchmark(result); renderPaths(result.paths); log(`Official acceptance ${result.run_id}: ${result.metrics.suite} final abundance ${result.metrics.final_abundance}`); setStatus(`Official acceptance complete: ${result.run_dir}`); $('officialResult').scrollIntoView({block:'start',behavior:'smooth'});}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
async function runCompare(){setBusy(true); try{const result=await api('/api/instream7/compare',collectState().instream); table('compareTable',result.comparison); renderPaths(result.paths); log(`Compare ${result.run_id}: ${result.metrics.outside_tolerance} outside tolerance`); setStatus(`Comparison complete: ${result.run_dir}`);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
$('runBtn').addEventListener('click',runModel);
$('validateBtn').addEventListener('click',validateModel);
$('stepBtn').addEventListener('click',()=>{collectState(); $('days').value=Number(state.config.days)+1; runModel();});
$('resetBtn').addEventListener('click',loadDefault);
$('newModelBtn').addEventListener('click',wizardStartFresh);
$('wizardSkipBtn').addEventListener('click',wizardDismiss);
$('addCellBtn').addEventListener('click',()=>{collectState(); const maxStation=Math.max(0,...state.cells.map(c=>Number(c.station_m||0))); const station=maxStation+42; state.cells.push({cell_id:`cell-${state.cells.length+1}`,habitat_type:'run',station_m:station,center_x_m:station,center_y_m:52,length_m:40,width_m:10,reach_id:state.config.reach_id,reach_order:1,area_m2:400,depth_m:.5,velocity_ms:.3,csi:.6,temperature_c:12,turbidity_ntu:0,hiding_cover:.2,feeding_cover:.2,spawning_cover:.2}); renderCells();});
$('exportBtn').addEventListener('click',()=>{const blob=new Blob([JSON.stringify(collectState(),null,2)],{type:'application/json'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='openlimno-ibm-scenario.json'; a.click(); URL.revokeObjectURL(a.href);});
$('importBtn').addEventListener('click',()=>$('importFile').click());
$('importFile').addEventListener('change',async event=>{const file=event.target.files[0]; if(!file) return; state=JSON.parse(await file.text()); bindState(); renderAll();});
$('ensembleBtn').addEventListener('click',runEnsemble);
$('calibrateBtn').addEventListener('click',runCalibration);
$('gisImportBtn').addEventListener('click',importGIS);
$('benchBtn').addEventListener('click',runBenchmark);
$('compareBtn').addEventListener('click',runCompare);
$('zoomInBtn').addEventListener('click',()=>zoomMap(1.25));
$('zoomOutBtn').addEventListener('click',()=>zoomMap(0.8));
$('fitMapBtn').addEventListener('click',()=>{resetMapView(); rerenderRiverView();});
$('inspectMapBtn').addEventListener('click',()=>setInspectMode(!mapState.inspect));
$('fullMapBtn').addEventListener('click',toggleFullscreen);
['showBoundary','showCenterline','showCells','showFish','showRedds'].forEach(id=>$(id).addEventListener('change',rerenderRiverView));
['gis_boundary_path','gis_boundary_layer','gis_centerline_path','gis_centerline_layer','gis_cells_path','gis_cells_layer'].forEach(id=>$(id).addEventListener('input',()=>{
  if(!state) return;
  const key=id.replace('gis_','');
  state.gis[key]=$(id).value;
  renderGisGuidance();
}));
$('riverView').addEventListener('mousemove',event=>{
  updateMapCoordinates(event);
  if(dragStart && !mapState.inspect){
    mapState.panX=dragStart.panX+(event.clientX-dragStart.x)*(900/$('riverView').getBoundingClientRect().width);
    mapState.panY=dragStart.panY+(event.clientY-dragStart.y)*(360/$('riverView').getBoundingClientRect().height);
    rerenderRiverView();
  }
});
$('riverView').addEventListener('mousedown',event=>{if(!mapState.inspect) dragStart={x:event.clientX,y:event.clientY,panX:mapState.panX,panY:mapState.panY};});
window.addEventListener('mouseup',()=>{dragStart=null;});
$('riverView').addEventListener('mouseleave',()=>{$('mapCoords').textContent='x -, y -';});
$('riverView').addEventListener('click',inspectFeature);
$('riverView').addEventListener('wheel',event=>{event.preventDefault(); zoomMap(event.deltaY<0?1.12:0.9);},{passive:false});
$('metricSelect').addEventListener('change',()=>{if(lastResult) drawChart(lastResult.population_summary);});
$('bandMetricSelect').addEventListener('change',()=>{if(lastEnsemble) drawBandChart(lastEnsemble.daily_bands);});
$('cellColorMetric').addEventListener('change',rerenderRiverView);
$('showDeadFish').addEventListener('change',rerenderRiverView);
/* Workspace tab switching: hidden panes use display:none so a long
   results tab never extends the page. */
document.querySelectorAll('.workspace-tabs button').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const pane=btn.dataset.pane;
    document.querySelectorAll('.workspace-tabs button').forEach(b=>b.classList.toggle('active',b===btn));
    document.querySelectorAll('.tabpane').forEach(p=>p.classList.toggle('active',p.dataset.pane===pane));
  });
});
loadDefault();
