"""Real execution tests for the ~1,550 lines of Studio JavaScript.

Both Studios are single-page apps whose behaviour used to be "verified" only by
substring assertions against the HTML string (``assert 'id="tankCanvas"' in
INDEX_HTML``). Those prove a literal exists; they cannot catch a misspelled
variable, a null dereference or a handler that throws on click.

These tests load the real page in a real Chromium via Playwright, stub the HTTP
API with payloads captured from the real Python handlers, and assert on what
the JavaScript actually does: no console errors, no uncaught exceptions, charts drawn, tables
filled, tabs switched, WebGL tank initialised, API failures surfaced.

Fixtures under ``tests/unit/studio_fixtures/`` were generated from the real
handlers (``openlimno.fishtank.studio_http`` /
``openlimno.ibm.studio``) with small day counts, so they are shape-accurate
without paying for a simulation on every test run.

Skipped when Playwright or its Chromium build is not installed; see the
``browser`` pixi environment / CI job.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="playwright is not installed")

from openlimno.fishtank.studio_assets import INDEX_HTML  # noqa: E402
from openlimno.ibm.studio_assets import _INDEX_HTML  # noqa: E402

pytestmark = pytest.mark.slow

FIXTURES = Path(__file__).resolve().parent / "studio_fixtures"
THREE_JS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "openlimno"
    / "fishtank"
    / "vendor"
    / "three.module.min.js"
)

JSON_CT = "application/json; charset=utf-8"
HTML_CT = "text/html; charset=utf-8"
JS_CT = "text/javascript; charset=utf-8"

# A generous budget: the pages do a couple of API round-trips and a WebGL build
# on load, and CI runners are slower than a laptop.
TIMEOUT_MS = 30_000

Route = tuple[int, str, str]


@cache
def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@cache
def _three_js() -> str:
    """The vendored three.js is 660 KB; read it once for the whole module."""

    return THREE_JS.read_text(encoding="utf-8")


def _json_route(name: str) -> Route:
    return (200, JSON_CT, _fixture(name))


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class Studio:
    """One loaded Studio page plus every error the browser reported."""

    def __init__(self, page: Any, errors: list[str]) -> None:
        self.page = page
        self.errors = errors

    def count(self, selector: str) -> int:
        return int(self.page.eval_on_selector_all(selector, "els => els.length"))

    def wait_for_count(self, selector: str, expected: int) -> None:
        """Wait on element *count*, not visibility — most panes start hidden."""

        self.page.wait_for_function(
            "([sel, n]) => document.querySelectorAll(sel).length >= n",
            arg=[selector, expected],
            timeout=TIMEOUT_MS,
        )

    def assert_clean(self, *, allow_failed_requests: bool = False) -> None:
        """Assert the browser reported no JavaScript problem at all.

        ``allow_failed_requests`` drops Chromium's own "Failed to load resource"
        console line, which it emits for *any* non-2xx response. The tests that
        deliberately stub a 4xx API use it; everything else stays strict, so a
        stray 404 for a missing asset still fails the suite.
        """

        errors = self.errors
        if allow_failed_requests:
            errors = [e for e in errors if "Failed to load resource" not in e]
        assert errors == [], "the page reported JavaScript errors:\n  " + "\n  ".join(errors)


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as driver:
        try:
            launched = driver.chromium.launch()
        except PlaywrightError as exc:  # browser binary not downloaded
            pytest.skip(f"chromium is not installed for playwright: {exc}")
        try:
            yield launched
        finally:
            launched.close()


def _open(browser: Any, routes: dict[str, Route], url: str) -> Studio:
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors: list[str] = []

    def on_console(message: Any) -> None:
        if message.type == "error":
            errors.append(f"console.error: {message.text}")

    def on_pageerror(exc: Any) -> None:
        errors.append(f"pageerror: {exc}")

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)

    def handler(route: Any) -> None:
        path = urlsplit(route.request.url).path
        entry = routes.get(path)
        if entry is None:
            route.fulfill(status=404, content_type="text/plain", body=f"no route for {path}")
            return
        status, content_type, body = entry
        route.fulfill(status=status, content_type=content_type, body=body)

    page.route("**/*", handler)
    page.goto(url, timeout=TIMEOUT_MS)
    return Studio(page, errors)


# ---------------------------------------------------------------------------
# Fishtank Studio
# ---------------------------------------------------------------------------

CALIBRATION_RESPONSE = json.dumps(
    {
        "ok": True,
        "best_params": {"mu_AOB": 0.7312, "mu_NOB": 0.6104},
        "best_rmse": 0.0432,
        "n_evals": 61,
        "converged": True,
        "message": "Nelder-Mead converged",
    }
)


def fishtank_routes() -> dict[str, Route]:
    return {
        "/": (200, HTML_CT, INDEX_HTML),
        "/assets/three.module.min.js": (200, JS_CT, _three_js()),
        "/api/default": _json_route("fishtank_default.json"),
        "/api/scenarios": _json_route("fishtank_scenarios.json"),
        "/api/run": _json_route("fishtank_run.json"),
        "/api/agents": _json_route("fishtank_agents.json"),
        "/api/calibrate": (200, JSON_CT, CALIBRATION_RESPONSE),
        "/favicon.ico": (204, "image/x-icon", ""),
    }


@pytest.fixture
def fishtank(browser: Any) -> Iterator[Studio]:
    studio = _open(browser, fishtank_routes(), "http://fishtank.studio.test/")
    # init() finishes by populating the preset dropdown from /api/scenarios.
    studio.page.wait_for_function(
        "() => document.getElementById('scenarioPreset').options.length > 0",
        timeout=TIMEOUT_MS,
    )
    yield studio
    studio.page.close()


def test_fishtank_studio_boots_without_javascript_errors(fishtank: Studio) -> None:
    """The highest-value assertion: 900 lines of JS run start to finish, clean."""

    fishtank.assert_clean()
    # /api/default was applied to the form, not merely fetched.
    assert fishtank.page.input_value("#volume") == "120"
    assert fishtank.page.input_value("#days") == "6"
    assert fishtank.count("#scenarioPreset option") == 16
    # One event row per event in the default payload.
    assert fishtank.count("#events .event-row") == 1
    assert fishtank.page.inner_text("#status").strip() != ""


def test_fishtank_run_button_renders_kpis_charts_and_tables(fishtank: Studio) -> None:
    fishtank.page.click("#runBtn")
    fishtank.page.wait_for_selector("#kpis .kpi", timeout=TIMEOUT_MS)

    assert fishtank.count("#kpis .kpi") == 5
    # One <path> per series: TAN/NO2/NO3, X_AOB/X_NOB/DO, pH/Alk.
    assert fishtank.count("#nitrogenChart path") == 3
    assert fishtank.count("#bioChart path") == 3
    assert fishtank.count("#phChart path") == 2
    assert fishtank.count("#nitrogenLegend span") == 3

    rows = json.loads(_fixture("fishtank_run.json"))["timeseries"]
    assert fishtank.count("#timeseriesTable table tbody tr") == len(rows)
    # First data cell is the day column of the first row.
    first_cell = fishtank.page.inner_text("#timeseriesTable table tbody tr:first-child td")
    assert float(first_cell) == pytest.approx(float(rows[0]["day"]))

    scenario_json = json.loads(fishtank.page.inner_text("#scenarioJson"))
    assert scenario_json["tank"]["volume_l"] == 120
    assert json.loads(fishtank.page.inner_text("#provenanceJson"))
    fishtank.assert_clean()


def test_fishtank_run_dispatches_the_result_event_to_the_3d_tank(fishtank: Studio) -> None:
    """render() → CustomEvent('fishtank:result') → the module script picks it up."""

    fishtank.page.click("#runBtn")
    fishtank.page.wait_for_selector("#kpis .kpi", timeout=TIMEOUT_MS)
    fishtank.page.wait_for_function(
        "() => window.__fishtank3dStatus && window.__fishtank3dStatus().rows > 0",
        timeout=TIMEOUT_MS,
    )
    status = fishtank.page.evaluate("window.__fishtank3dStatus()")
    assert status["renderer"] == "three.js", f"WebGL init failed: {status}"
    assert status["stats"]["pH"] > 0
    fishtank.assert_clean()


def test_fishtank_3d_tab_actually_renders_frames(fishtank: Studio) -> None:
    """The animation loop is a no-op until the 3D tab is active — prove it wakes."""

    if fishtank.page.evaluate("window.__fishtank3dStatus().renderer") != "three.js":
        pytest.skip("no WebGL in this browser build; the fallback path is tested separately")
    fishtank.page.click("#runBtn")
    fishtank.page.click('.tab[data-view="tank3d"]')
    fishtank.page.wait_for_function(
        "() => window.__fishtank3dStatus().frames > 2", timeout=TIMEOUT_MS
    )
    pixels = fishtank.page.evaluate("window.__fishtank3dPixels()")
    assert pixels["nonblank"], f"the WebGL tank rendered a blank frame: {pixels}"
    assert fishtank.page.inner_text("#tankBadge").startswith("pH")
    fishtank.assert_clean()


def test_fishtank_abm_run_renders_agent_space_and_kpis(fishtank: Studio) -> None:
    fishtank.page.click("#runAbmBtn")
    fishtank.page.wait_for_function("() => window.__fishtankAgentStatus().ok", timeout=TIMEOUT_MS)

    agents = json.loads(_fixture("fishtank_agents.json"))
    status = fishtank.page.evaluate("window.__fishtankAgentStatus()")
    assert status["fish"] == len(agents["agents"]["fish"])
    assert status["microbes"] == len(agents["agents"]["microbes"])
    assert status["rows"] == len(agents["timeseries"])

    assert fishtank.count("#agentKpis .kpi") == 5
    # One <ellipse> body per fish glyph in the 2D agent space.
    assert fishtank.count("#agentSpace ellipse") == len(agents["agents"]["fish"])
    assert fishtank.count("#agentChart path") == 4
    fishtank.assert_clean()


def test_fishtank_compare_tab_overlays_ode_and_abm(fishtank: Studio) -> None:
    fishtank.page.click("#runBothBtn")
    fishtank.page.wait_for_function("() => window.__fishtankAgentStatus().ok", timeout=TIMEOUT_MS)
    fishtank.page.click('.tab[data-view="compareView"]')
    fishtank.page.wait_for_selector("#compareChart path", timeout=TIMEOUT_MS)
    # Four shared variables, drawn twice (solid ODE + dashed ABM).
    assert fishtank.count("#compareChart path") == 8
    assert fishtank.count("#compareChart path[stroke-dasharray]") == 4
    assert fishtank.page.is_hidden("#compareHint")
    fishtank.assert_clean()


def test_fishtank_calibrate_button_renders_the_fit(fishtank: Studio) -> None:
    fishtank.page.click("#calibrateBtn")
    fishtank.page.click('.tab[data-view="calibration"]')
    fishtank.page.wait_for_selector("#calibrationPanel .kpi", timeout=TIMEOUT_MS)
    panel = fishtank.page.inner_text("#calibrationPanel")
    assert "0.0432" in panel
    assert "0.7312" in panel
    assert "Nelder-Mead converged" in panel
    fishtank.assert_clean()


def test_fishtank_event_rows_can_be_added_and_removed(fishtank: Studio) -> None:
    before = fishtank.count("#events .event-row")
    fishtank.page.click("#addEventBtn")
    assert fishtank.count("#events .event-row") == before + 1
    # The row's own X button wires up a working remove handler.
    fishtank.page.click("#events .event-row:last-child button")
    assert fishtank.count("#events .event-row") == before
    fishtank.assert_clean()


def test_fishtank_language_toggle_round_trips(fishtank: Studio) -> None:
    fishtank.page.click("#runBtn")
    fishtank.page.wait_for_selector("#kpis .kpi", timeout=TIMEOUT_MS)
    first = fishtank.page.inner_text("#kpis .kpi:first-child .label")
    fishtank.page.click("#langToggle")
    second = fishtank.page.inner_text("#kpis .kpi:first-child .label")
    assert first != second, "the language toggle changed nothing"
    fishtank.page.click("#langToggle")
    assert fishtank.page.inner_text("#kpis .kpi:first-child .label") == first
    fishtank.assert_clean()


def test_fishtank_preset_change_rebinds_the_form_and_reruns(fishtank: Studio) -> None:
    scenarios = json.loads(_fixture("fishtank_scenarios.json"))["scenarios"]
    other = next(s for s in scenarios if s["id"] == "staged_stocking")
    assert fishtank.count("#events .event-row") == 1  # from /api/default

    fishtank.page.select_option("#scenarioPreset", other["id"])
    fishtank.page.wait_for_selector("#kpis .kpi", timeout=TIMEOUT_MS)

    # The preset's own payload replaced the form, and its events replaced the rows.
    assert float(fishtank.page.input_value("#days")) == other["payload"]["run"]["days"]
    assert fishtank.count("#events .event-row") == len(other["payload"]["events"])
    assert fishtank.page.inner_text("#scenarioPresetHint").strip() != ""
    fishtank.assert_clean()


def test_fishtank_all_view_tabs_open_without_errors(fishtank: Studio) -> None:
    fishtank.page.click("#runBothBtn")
    fishtank.page.wait_for_function("() => window.__fishtankAgentStatus().ok", timeout=TIMEOUT_MS)
    views = fishtank.page.eval_on_selector_all(".tab", "els => els.map(e => e.dataset.view)")
    assert len(views) >= 8
    for view in views:
        fishtank.page.click(f'.tab[data-view="{view}"]')
        assert fishtank.page.is_visible(f"#{view}"), f"{view} pane did not become visible"
    fishtank.assert_clean()


def test_fishtank_long_run_is_compacted_with_an_omitted_rows_note(browser: Any) -> None:
    """The behaviour behind the old ``assert "rows omitted" in INDEX_HTML``."""

    payload = json.loads(_fixture("fishtank_run.json"))
    template = payload["timeseries"][0]
    payload["timeseries"] = [dict(template, day=float(i)) for i in range(200)]
    routes = fishtank_routes()
    routes["/api/run"] = (200, JSON_CT, json.dumps(payload))

    studio = _open(browser, routes, "http://fishtank.studio.test/")
    try:
        studio.page.wait_for_function(
            "() => document.getElementById('scenarioPreset').options.length > 0",
            timeout=TIMEOUT_MS,
        )
        studio.page.click("#runBtn")
        studio.page.click('.tab[data-view="chemistry"]')
        studio.page.wait_for_selector("#timeseriesTable .table-gap", timeout=TIMEOUT_MS)
        # limit=80 → 40 head + gap row + 40 tail.
        assert studio.count("#timeseriesTable table tbody tr") == 81
        assert "120" in studio.page.inner_text("#timeseriesTable .table-gap")
        assert studio.page.inner_text("#timeseriesTable .table-note").strip() != ""
        studio.assert_clean()
    finally:
        studio.page.close()


def test_fishtank_api_error_is_shown_and_not_thrown(browser: Any) -> None:
    routes = fishtank_routes()
    routes["/api/run"] = (400, JSON_CT, json.dumps({"ok": False, "error": "days must be > 0"}))

    studio = _open(browser, routes, "http://fishtank.studio.test/")
    try:
        studio.page.wait_for_function(
            "() => document.getElementById('scenarioPreset').options.length > 0",
            timeout=TIMEOUT_MS,
        )
        studio.page.click("#runBtn")
        studio.page.wait_for_function(
            "() => document.getElementById('status').textContent.includes('days must be > 0')",
            timeout=TIMEOUT_MS,
        )
        # A rejected run must surface in the status line, never as an
        # unhandled promise rejection.
        studio.assert_clean(allow_failed_requests=True)
    finally:
        studio.page.close()


# ---------------------------------------------------------------------------
# IBM Studio
# ---------------------------------------------------------------------------


def ibm_routes() -> dict[str, Route]:
    return {
        "/": (200, HTML_CT, _INDEX_HTML),
        "/api/default": _json_route("ibm_default.json"),
        "/api/run": _json_route("ibm_run.json"),
        "/api/validate": _json_route("ibm_validate.json"),
        "/favicon.ico": (204, "image/x-icon", ""),
    }


@pytest.fixture
def ibm(browser: Any) -> Iterator[Studio]:
    studio = _open(browser, ibm_routes(), "http://ibm.studio.test/")
    # loadDefault() binds the form, renders every panel, then auto-runs the model.
    studio.page.wait_for_selector("#kpis .kpi", timeout=TIMEOUT_MS)
    yield studio
    studio.page.close()


def test_ibm_studio_boots_and_autoruns_without_javascript_errors(ibm: Studio) -> None:
    ibm.assert_clean()
    default = json.loads(_fixture("ibm_default.json"))
    assert ibm.page.input_value("#scenario_id") == default["config"]["scenario_id"]
    assert ibm.page.input_value("#days") == str(default["config"]["days"])
    assert ibm.page.input_value("#river_name") == default["river"]["name"]
    # The five profile groups defined at the top of the module.
    assert ibm.count("#profileTabs button") == 5
    assert ibm.count("#profileFields [data-profile]") > 0
    assert ibm.count("#submodelFields select") == len(
        {m["slot"] for m in default["submodel_catalog"]}
    )
    assert ibm.count("#cellsTable tbody tr") == len(default["cells"])


def test_ibm_autorun_renders_kpis_chart_river_view_and_tables(ibm: Studio) -> None:
    run = json.loads(_fixture("ibm_run.json"))
    assert ibm.count("#kpis .kpi") == 5
    assert str(run["metrics"]["final_abundance"]) in ibm.page.inner_text("#kpis")
    assert ibm.count("#chart polyline") == 1
    assert ibm.count("#riverView *") > 0
    assert ibm.count("#fishTable tbody tr") == len(run["final_individuals"])
    assert ibm.count("#cellUseTable tbody tr") == len(run["cell_use_summary"])
    assert ibm.count("#historyTable tbody tr") == 1
    assert ibm.count("#paths li") == len(run["paths"])
    assert run["run_dir"] in ibm.page.inner_text("#status")
    ibm.assert_clean()


def test_ibm_profile_tabs_swap_the_editable_parameter_set(ibm: Studio) -> None:
    growth = ibm.page.eval_on_selector_all(
        "#profileFields [data-profile]", "els => els.map(e => e.dataset.profile)"
    )
    # The species profile lives in a collapsed <details>; open it like a user does.
    ibm.page.click('summary:has-text("Species Profile")')
    ibm.page.wait_for_selector('#profileTabs button[data-tab="Spawning"]', timeout=TIMEOUT_MS)
    ibm.page.click('#profileTabs button[data-tab="Spawning"]')
    spawning = ibm.page.eval_on_selector_all(
        "#profileFields [data-profile]", "els => els.map(e => e.dataset.profile)"
    )
    assert growth and spawning and growth != spawning
    assert "spawn_start_day" in spawning
    ibm.assert_clean()


def test_ibm_validate_button_fills_the_validation_table(ibm: Studio) -> None:
    validation = json.loads(_fixture("ibm_validate.json"))
    ibm.page.click("#validateBtn")
    ibm.wait_for_count("#validationTable tbody tr", len(validation["checks"]))
    assert ibm.count("#validationTable tbody tr") == len(validation["checks"])
    assert ibm.page.inner_text("#log").strip() != ""
    ibm.assert_clean()


def test_ibm_workspace_tabs_switch_panes(ibm: Studio) -> None:
    panes = ibm.page.eval_on_selector_all(
        ".workspace-tabs button", "els => els.map(e => e.dataset.pane)"
    )
    assert len(panes) >= 5
    for pane in panes:
        ibm.page.click(f'.workspace-tabs button[data-pane="{pane}"]')
        assert ibm.page.is_visible(f'.tabpane[data-pane="{pane}"]')
    ibm.assert_clean()


def test_ibm_map_controls_run_without_errors(ibm: Studio) -> None:
    signature_before = ibm.page.eval_on_selector("#riverView", "el => el.innerHTML.length")
    for button in ("#zoomInBtn", "#zoomOutBtn", "#fitMapBtn", "#inspectMapBtn"):
        ibm.page.click(button)
    ibm.page.click("#showFish")  # toggle a layer off and back on
    ibm.page.click("#showFish")
    ibm.page.select_option("#cellColorMetric", index=1)
    assert ibm.page.eval_on_selector("#riverView", "el => el.innerHTML.length") > 0
    assert signature_before > 0
    ibm.assert_clean()


def test_ibm_metric_select_redraws_the_population_chart(ibm: Studio) -> None:
    before = ibm.page.eval_on_selector("#chart", "el => el.innerHTML")
    options = ibm.page.eval_on_selector_all("#metricSelect option", "els => els.map(e => e.value)")
    assert len(options) > 1
    ibm.page.select_option("#metricSelect", options[1])
    after = ibm.page.eval_on_selector("#chart", "el => el.innerHTML")
    assert before != after, "changing the metric did not redraw the chart"
    ibm.assert_clean()


def test_ibm_api_error_is_logged_and_not_thrown(browser: Any) -> None:
    routes = ibm_routes()
    routes["/api/run"] = (
        400,
        JSON_CT,
        json.dumps({"ok": False, "error": "cells must not be empty"}),
    )

    studio = _open(browser, routes, "http://ibm.studio.test/")
    try:
        studio.page.wait_for_function(
            "() => document.getElementById('log').textContent.includes('cells must not be empty')",
            timeout=TIMEOUT_MS,
        )
        assert "cells must not be empty" in studio.page.inner_text("#status")
        # Buttons must be re-enabled by the finally-branch of runModel().
        assert studio.page.is_enabled("#runBtn")
        studio.assert_clean(allow_failed_requests=True)
    finally:
        studio.page.close()
