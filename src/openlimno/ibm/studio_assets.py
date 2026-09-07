"""IBM Studio embedded HTML/CSS/JS template asset.

R-IBM-GOD-OBJECT partial split (ADR-0016, 2026-05-26): extracted from
openlimno.ibm.studio so the inline browser template (~720 lines of
HTML/CSS/JS) lives in a dedicated asset file rather than mixed in with
Python business logic. studio.py and studio_http.py both
import ``_INDEX_HTML`` from here.

The CSS and JavaScript themselves now live in real files under
``openlimno/ibm/assets/`` so they can be linted, syntax checked and executed by
browser tests; they are inlined at import time at the
``@openlimno-asset:<name>@`` comment markers, which keeps ``_INDEX_HTML`` a
single self-contained (offline-capable) document, byte-for-byte identical to
the string that used to be hard-coded in this module.

⚠️ This asset is part of the R-IBM-STUDIO-CONSOLIDATE dev-only surface.
Do not add new UX features here. Migration target is the PyQt6 Studio
(``openlimno.studio``) per ADR-0016 cleanup track."""

from __future__ import annotations

from pathlib import Path
from typing import Final

_ASSETS_DIR: Final[Path] = Path(__file__).resolve().parent / "assets"

#: Marker comment (including its own trailing newline) -> asset file name.
#: Each marker is a comment in its host language, so the template below stays
#: valid HTML/CSS/JS even before the assets are inlined.
_ASSET_MARKERS: Final[dict[str, str]] = {
    "/*@openlimno-asset:studio.css@*/\n": "studio.css",
    "//@openlimno-asset:studio_app.js@\n": "studio_app.js",
}


def _read_asset(name: str) -> str:
    """Return the text of a bundled Studio asset.

    Read in text mode (universal newlines) so a Windows checkout with CRLF line
    endings still produces the same LF-only document as a POSIX one.
    """
    return (_ASSETS_DIR / name).read_text(encoding="utf-8")


def _render(template: str) -> str:
    """Inline every asset marker in ``template`` and return the whole page."""
    html = template
    for marker, name in _ASSET_MARKERS.items():
        found = html.count(marker)
        if found != 1:
            raise RuntimeError(
                f"Studio template must hold exactly one {marker.strip()!r} marker "
                f"for asset {name!r}; found {found}."
            )
        html = html.replace(marker, _read_asset(name))
    return html


_INDEX_TEMPLATE: Final[str] = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OpenLimno IBM Studio</title>
<style>
/*@openlimno-asset:studio.css@*/
</style>
</head>
<body>
<div class="app">
  <div class="topbar"><div class="brand"><div class="mark">OL</div><div>OpenLimno IBM Studio</div><span class="badge">native agent model</span></div><div id="status" class="status">Ready</div></div>
  <div class="shell">
    <aside class="sidebar">
      <section class="panel"><header><h2>Run Setup</h2></header><div class="panel-body"><div class="grid2">
        <div class="field"><label>Scenario</label><input id="scenario_id"></div><div class="field"><label>Reach</label><input id="reach_id"></div>
        <div class="field"><label>Species</label><input id="species"></div><div class="field"><label>Initial fish</label><input id="initial_abundance" type="number" min="0"></div>
        <div class="field"><label>Initial length mm</label><input id="initial_length_mm" type="number" step="0.1" min="1"></div><div class="field"><label>Days</label><input id="days" type="number" min="0"></div>
        <div class="field"><label>Seed</label><input id="seed" type="number"></div><div class="field check"><input id="stochastic" type="checkbox"><label for="stochastic">Stochastic</label></div>
        <div class="field check"><input id="record_individual_history" type="checkbox"><label for="record_individual_history">Fish history</label></div>
      </div><div class="actions" style="margin-top: 12px;"><button id="newModelBtn" class="btn">New model</button><button id="runBtn" class="btn primary">Run</button><button id="validateBtn" class="btn">Validate</button><button id="stepBtn" class="btn">Step +1 day</button><button id="resetBtn" class="btn">Reset</button><button id="exportBtn" class="btn">Export JSON</button><button id="importBtn" class="btn">Import JSON</button><input id="importFile" type="file" accept="application/json" style="display:none"></div></div></section>
      <section class="panel"><header><h2>River</h2></header><div class="panel-body"><div class="grid2">
        <div class="field"><label>River name</label><input id="river_name"></div><div class="field"><label>Reach name</label><input id="river_reach_name"></div>
        <div class="field"><label>Length m</label><input id="river_length_m" type="number" min="1" step="1"></div><div class="field"><label>Flow m3/s</label><input id="river_flow_m3s" type="number" min="0" step="0.1"></div>
      </div></div></section>
      <section class="panel"><header><h2>GIS Import</h2><span class="badge">boundary first</span></header><div class="panel-body">
        <div class="gis-steps">
          <div class="gis-step">
            <div class="gis-step-head"><div class="gis-step-title">1. River Boundary</div><div class="gis-required">required for true channel shape</div></div>
            <div class="grid2"><div class="field"><label>Boundary path or URL</label><input id="gis_boundary_path" placeholder="/path/banks_or_channel_polygon.geojson, .shp, .gpkg, or https://...f=geojson"></div><div class="field"><label>Boundary layer</label><input id="gis_boundary_layer"></div></div>
          </div>
          <div class="gis-step">
            <div class="gis-step-head"><div class="gis-step-title">2. Flow Centerline</div><span class="badge">optional</span></div>
            <div class="grid2"><div class="field"><label>Centerline path or URL</label><input id="gis_centerline_path" placeholder="/path/centerline.geojson, .shp, .gpkg, or https://...f=geojson"></div><div class="field"><label>Centerline layer</label><input id="gis_centerline_layer"></div></div>
          </div>
          <div class="gis-step">
            <div class="gis-step-head"><div class="gis-step-title">3. Habitat Cells</div><span class="badge">required for IBM fish positions</span></div>
            <div class="grid2"><div class="field"><label>Habitat cells path or URL</label><input id="gis_cells_path" placeholder="/path/habitat_cells.geojson, .shp, .gpkg, or https://...f=geojson"></div><div class="field"><label>Cells layer</label><input id="gis_cells_layer"></div></div>
          </div>
        </div>
        <div id="gisChecks" class="gis-checks"></div>
        <div class="actions" style="margin-top: 12px;"><button id="gisImportBtn" class="btn primary">Import GIS</button></div>
      </div></section>
      <details class="collapsible"><summary>Species Profile</summary><div class="collapsible-body"><div class="tabs" id="profileTabs"></div><div class="profile-grid" id="profileFields"></div></div></details>
      <details class="collapsible"><summary>Submodels</summary><div class="collapsible-body"><div class="profile-grid" id="submodelFields"></div></div></details>
    </aside>
    <main class="workspace">
      <nav class="wizard-strip" id="wizardStrip" style="display:none" aria-label="New-model wizard">
        <span class="wizard-strip-title">建模向导</span>
        <div class="wizard-step" data-wizard-step="river" tabindex="0"><span class="wizard-num">1</span><span class="wizard-label">河道</span></div>
        <span class="wizard-arrow">›</span>
        <div class="wizard-step" data-wizard-step="habitat" tabindex="0"><span class="wizard-num">2</span><span class="wizard-label">栖境</span></div>
        <span class="wizard-arrow">›</span>
        <div class="wizard-step" data-wizard-step="species" tabindex="0"><span class="wizard-num">3</span><span class="wizard-label">物种参数</span></div>
        <span class="wizard-arrow">›</span>
        <div class="wizard-step" data-wizard-step="population" tabindex="0"><span class="wizard-num">4</span><span class="wizard-label">初始种群</span></div>
        <span class="wizard-arrow">›</span>
        <div class="wizard-step" data-wizard-step="validate" tabindex="0"><span class="wizard-num">5</span><span class="wizard-label">校验</span></div>
        <span class="wizard-arrow">›</span>
        <div class="wizard-step" data-wizard-step="run" tabindex="0"><span class="wizard-num">6</span><span class="wizard-label">运行</span></div>
        <button class="wizard-skip" id="wizardSkipBtn" title="退出向导">退出</button>
      </nav>
      <div class="kpis" id="kpis"></div>
      <nav class="workspace-tabs" id="workspaceTabs">
        <button class="active" data-pane="overview">Overview</button>
        <button data-pane="cells">Habitat Cells</button>
        <button data-pane="workflow">Workflow &amp; Compare</button>
        <button data-pane="results">Results</button>
        <button data-pane="logs">Experiments &amp; Output</button>
      </nav>

      <div class="tabpane active" data-pane="overview">
        <section id="riverCard" class="river-card"><div class="river-head"><div><h2>River View</h2><div id="riverTitle" class="river-title">No run loaded</div></div><div class="river-controls"><label for="cellColorMetric">Cell color</label><select id="cellColorMetric"><option value="csi">CSI</option><option value="depth_m">Depth</option><option value="velocity_ms">Velocity</option><option value="total_fish_use">Fish use</option><option value="habitat_type">Habitat</option></select><div class="map-toolbar"><button id="zoomInBtn" class="icon-btn" title="Zoom in">+</button><button id="zoomOutBtn" class="icon-btn" title="Zoom out">-</button><button id="fitMapBtn" class="icon-btn" title="Fit map">Fit</button><button id="inspectMapBtn" class="icon-btn" title="Inspect features">Inspect</button><button id="fullMapBtn" class="icon-btn" title="Fullscreen map">Full</button></div></div></div><div id="qualityStrip" class="quality-strip"></div><div class="map-layers"><div class="check"><input id="showBoundary" type="checkbox" checked><label for="showBoundary">Boundary</label></div><div class="check"><input id="showCenterline" type="checkbox" checked><label for="showCenterline">Centerline</label></div><div class="check"><input id="showCells" type="checkbox" checked><label for="showCells">Cells</label></div><div class="check"><input id="showFish" type="checkbox" checked><label for="showFish">Fish</label></div><div class="check"><input id="showDeadFish" type="checkbox"><label for="showDeadFish">Dead fish</label></div><div class="check"><input id="showRedds" type="checkbox" checked><label for="showRedds">Redds</label></div></div><div class="river-stage"><div class="river-svg-wrap"><svg id="riverView" viewBox="0 0 900 360" role="img" aria-label="River reach with habitat cells and fish"></svg><div id="mapCoords" class="map-coordinates">x -, y -</div></div><div class="river-side"><div id="riverMeta" class="river-meta"></div><div id="riverLegend" class="river-legend"></div></div></div></section>
        <section class="chart-card"><div class="chart-head"><h2>Population Trajectory</h2><select id="metricSelect"><option value="abundance">Abundance</option><option value="biomass_g">Biomass</option><option value="mean_length_mm">Mean length</option></select></div><svg id="chart" viewBox="0 0 900 280"></svg></section>
        <section class="chart-card"><div class="chart-head"><h2>Uncertainty Bands</h2><select id="bandMetricSelect"><option value="abundance">Abundance</option><option value="biomass_g">Biomass</option><option value="mean_length_mm">Mean length</option></select></div><svg id="bandChart" viewBox="0 0 900 280"></svg></section>
      </div>

      <div class="tabpane" data-pane="cells">
        <section class="panel"><header><h2>Habitat Cells</h2><button id="addCellBtn" class="btn">Add row</button></header><div class="panel-body"><div class="table-wrap"><table id="cellsTable"></table></div></div></section>
      </div>

      <div class="tabpane" data-pane="workflow">
        <section id="officialResult" class="official-result" style="display:none">
          <div class="official-result-head"><div><h2>Official Acceptance Result</h2><div id="officialSubtitle" class="official-subtitle">Run an official inSTREAM or InSALMO fixture to populate this capture panel.</div></div><span id="officialStatus" class="status-pill warning">no run</span></div>
          <div id="officialWorkflow" class="official-workflow"></div>
          <div id="officialWorkflowDetails" class="workflow-detail-grid"></div>
          <div id="officialSummary" class="acceptance-grid"></div>
          <div class="split result-split">
            <div><div class="result-table-title">Final Population</div><div class="table-wrap"><table id="officialFinalTable"></table></div></div>
            <div><div class="result-table-title">Official Inventory</div><div class="table-wrap"><table id="officialInventoryTable"></table></div></div>
          </div>
          <div class="official-events"><div class="result-table-title">Acceptance Events</div><div class="table-wrap"><table id="officialEventsTable"></table></div></div>
        </section>
        <section class="panel"><header><h2>Official IBM Workflow</h2><span class="badge">inSTREAM / InSALMO</span></header><div class="panel-body">
          <div class="official-setup-steps">
            <div class="official-setup-block"><div class="official-setup-title">1. Official case source</div><div class="grid2"><div class="field"><label>Official fixture</label><input id="instream_fixture" placeholder="/path/to/InSTREAM-7.4 or InSALMO-7.4 zip"></div><div class="field"><label>Case</label><input id="instream_case_id"></div></div></div>
            <div class="official-setup-block"><div class="official-setup-title">2. Native IBM run</div><div class="grid2"><div class="field"><label>Days</label><input id="instream_days" type="number" min="1"></div><div class="field"><label>Seed</label><input id="instream_seed" type="number"></div></div></div>
            <div class="official-setup-block"><div class="official-setup-title">3. NetLogo comparison</div><div class="grid2"><div class="field"><label>Native summary CSV</label><input id="native_summary" placeholder="instream7_native_population_summary.csv"></div><div class="field"><label>BriefPop CSV</label><input id="brief_pop" placeholder="BriefPopOut-r1.csv"></div></div></div>
          </div>
          <div class="actions" style="margin-top: 12px;"><button id="benchBtn" class="btn primary">Run workflow</button><button id="compareBtn" class="btn">Compare BriefPop</button></div>
        </div></section>
        <section class="panel"><header><h2>inSTREAM Comparison</h2></header><div class="panel-body"><div class="table-wrap"><table id="compareTable"></table></div></div></section>
      </div>

      <div class="tabpane" data-pane="results">
        <div class="triptych"><section class="panel"><header><h2>Validation</h2></header><div class="panel-body"><div class="table-wrap"><table id="validationTable"></table></div></div></section><section class="panel"><header><h2>Run History</h2></header><div class="panel-body"><div class="table-wrap"><table id="historyTable"></table></div></div></section><section class="panel"><header><h2>Calibration</h2></header><div class="panel-body"><div id="bestParams" class="mini-note"></div><div class="table-wrap" style="margin-top: 8px;"><table id="calibrationTable"></table></div></div></section></div>
        <div class="split"><section class="panel"><header><h2>Ensemble Summary</h2></header><div class="panel-body"><div class="table-wrap"><table id="ensembleTable"></table></div></div></section><section class="panel"><header><h2>Sensitivity</h2></header><div class="panel-body"><div class="table-wrap"><table id="sensitivityTable"></table></div></div></section></div>
        <div class="split"><section class="panel"><header><h2>Habitat Use</h2></header><div class="panel-body"><div class="table-wrap"><table id="cellUseTable"></table></div></div></section><section class="panel"><header><h2>Events</h2></header><div class="panel-body"><div class="table-wrap"><table id="eventsTable"></table></div></div></section></div>
        <section class="panel"><header><h2>Fish State</h2></header><div class="panel-body"><div class="table-wrap"><table id="fishTable"></table></div></div></section>
        <section class="panel"><header><h2>Redds</h2></header><div class="panel-body"><div class="table-wrap"><table id="reddsTable"></table></div></div></section>
      </div>

      <div class="tabpane" data-pane="logs">
        <section class="panel"><header><h2>Experiments</h2></header><div class="panel-body">
          <div class="field"><label>Ensemble seeds</label><input id="ensemble_seeds"></div>
          <div class="field" style="margin-top: 10px;"><label>Ensemble parameters</label><textarea id="ensemble_params"></textarea></div>
          <div class="actions" style="margin-top: 12px;"><button id="ensembleBtn" class="btn">Run ensemble</button></div>
          <div class="grid2" style="margin-top: 12px;">
            <div class="field"><label>Calibration method</label><select id="calibration_method"><option value="grid">grid</option><option value="abc">abc</option></select></div>
            <div class="field"><label>ABC samples</label><input id="calibration_samples" type="number" min="1"></div>
            <div class="field"><label>Acceptance fraction</label><input id="acceptance_fraction" type="number" min="0.001" max="1" step="0.01"></div>
            <div class="field"><label>Tolerance</label><input id="calibration_tolerance" type="number" min="0" step="0.1"></div>
          </div>
          <div class="field" style="margin-top: 10px;"><label>Observed CSV</label><input id="observed_path" placeholder="leave blank to use current run"></div>
          <div class="field" style="margin-top: 10px;"><label>Calibration parameters</label><textarea id="calibration_params"></textarea></div>
          <div class="actions" style="margin-top: 12px;"><button id="calibrateBtn" class="btn">Calibrate</button></div>
        </div></section>
        <section class="panel"><header><h2>Output</h2></header><div class="panel-body"><ul id="paths" class="path-list"></ul><div id="log" class="log"></div></div></section>
      </div>
    </main>
  </div>
</div>
<script>
//@openlimno-asset:studio_app.js@
</script>
</body>
</html>
"""

_INDEX_HTML: Final[str] = _render(_INDEX_TEMPLATE)
