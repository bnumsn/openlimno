"""Embedded browser assets for the fishtank Studio.

The page stays a single self-contained HTML document (the Studio is used
offline on classroom machines), but the CSS and JavaScript that make it up live
in real files under ``openlimno/fishtank/assets/`` so they can be linted,
syntax checked and executed by browser tests instead of hiding inside a Python
string literal.

``INDEX_HTML`` is assembled at import time by inlining those files into
``_INDEX_TEMPLATE`` at the ``@openlimno-asset:<name>@`` comment markers, so the
public surface (``INDEX_HTML: str``, byte-for-byte the document that used to be
hard-coded here) is unchanged for ``studio_http`` and the Studio tests.
"""

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
    "//@openlimno-asset:studio_tank3d.mjs@\n": "studio_tank3d.mjs",
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
<title>OpenLimno Fishtank Studio</title>
<style>
/*@openlimno-asset:studio.css@*/
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
      <button class="btn primary" id="runBtn">Run ODE</button>
      <button class="btn" id="runAbmBtn">Run ABM</button>
      <button class="btn" id="runBothBtn">Run ODE+ABM</button>
      <button class="btn" id="calibrateBtn">Calibrate</button>
      <button class="btn" id="exportBtn">Export scenario</button>
      <button class="btn" id="resetBtn">Reset</button>
    </div>
  </aside>
  <main class="main">
    <div class="tabs">
      <button class="tab" data-view="tank3d">3D Tank</button>
      <button class="tab" data-view="agentsView">ABM Agents</button>
      <button class="tab active" data-view="dashboard">Dashboard</button>
      <button class="tab" data-view="chemistry">Chemistry</button>
      <button class="tab" data-view="eventsView">Events</button>
      <button class="tab" data-view="calibration">Calibration</button>
      <button class="tab" data-view="compareView">Compare</button>
      <button class="tab" data-view="exportView">Export</button>
    </div>
    <section id="tank3d" class="view tank-view">
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
    <section id="dashboard" class="view active">
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
    <section id="compareView" class="view">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">ODE vs ABM</div><div class="legend" id="compareLegend"></div></div>
        <div class="panel-body">
          <div id="compareHint" class="muted">Run both models to compare</div>
          <svg id="compareChart" class="chart"></svg>
          <div id="compareNote" class="table-note">Solid = ODE, dashed = ABM</div>
        </div>
      </div>
    </section>
    <section id="exportView" class="view">
      <div class="panel"><div class="panel-head"><div class="panel-title">Scenario JSON</div></div><div class="panel-body"><pre id="scenarioJson" class="mono"></pre></div></div>
      <div class="panel"><div class="panel-head"><div class="panel-title">Provenance</div></div><div class="panel-body"><pre id="provenanceJson" class="mono"></pre></div></div>
    </section>
  </main>
</div>
<script>
//@openlimno-asset:studio_app.js@
</script>
<script type="module">
//@openlimno-asset:studio_tank3d.mjs@
</script>
</body>
</html>
"""

INDEX_HTML: Final[str] = _render(_INDEX_TEMPLATE)

__all__ = ["INDEX_HTML"]
