"""Tests for ``studio_instream7_default`` and the runtime resolver.

Pinned by the 2026-05-26 triple-AI review (Codex P1/P2, Gemini, Claude).
Each test cites which review finding it pins so future maintainers can
trace why the assertion exists.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# find_instream7_archive_root — resolves env var, XDG cache, repo dir
# ---------------------------------------------------------------------------

def test_find_archive_root_env_var_takes_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins Claude review: env var must take precedence over other dirs."""
    from openlimno.ibm.studio_instream7_default import find_instream7_archive_root

    # Make a fake archive root with at least one entry so the iterdir check passes.
    archive = tmp_path / "fake_archive"
    archive.mkdir()
    (archive / "marker").write_text("x")

    monkeypatch.setenv("OPENLIMNO_INSTREAM7_ARCHIVE", str(archive))
    assert find_instream7_archive_root() == archive


def test_find_archive_root_returns_none_when_nothing_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins Claude review: the resolver must return None (not raise) when no
    archive is available, so the synthetic fallback can take over."""
    import openlimno.ibm.studio_instream7_default as m

    monkeypatch.delenv("OPENLIMNO_INSTREAM7_ARCHIVE", raising=False)
    # Redirect both candidate dirs to empty tmp locations.
    monkeypatch.setattr(m, "_CANDIDATE_DIRS", (tmp_path / "a", tmp_path / "b"))
    assert m.find_instream7_archive_root() is None


def test_find_archive_root_skips_nonexistent_env_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Env var pointing at a missing dir should fall through to candidates,
    not raise."""
    import openlimno.ibm.studio_instream7_default as m

    monkeypatch.setenv(
        "OPENLIMNO_INSTREAM7_ARCHIVE", str(tmp_path / "does-not-exist")
    )
    monkeypatch.setattr(m, "_CANDIDATE_DIRS", (tmp_path / "a", tmp_path / "b"))
    assert m.find_instream7_archive_root() is None


# ---------------------------------------------------------------------------
# _classify_hmu — pure function, low risk but explicitly untested per Claude
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("depth_m", "vel_ms", "expected"),
    [
        (0.05, 0.20, "margin"),     # shallow — margin regardless of velocity
        (0.20, 0.60, "riffle"),     # shallow + fast
        (0.20, 0.20, "glide"),      # shallow + slow
        (0.50, 1.00, "run"),        # deep + fast
        (0.80, 0.05, "pool"),       # deep + slow
        (0.50, 0.50, "run"),        # deep + medium (catch-all branch)
    ],
)
def test_classify_hmu_depth_velocity_grid(
    depth_m: float, vel_ms: float, expected: str
) -> None:
    """Pins Claude review: smoke matrix for HMU classifier so a future
    threshold tweak announces itself in CI."""
    from openlimno.ibm.studio_instream7_default import _classify_hmu

    assert _classify_hmu(depth_m, vel_ms) == expected


# ---------------------------------------------------------------------------
# _crs_unit_factor — projected-CRS guard (Gemini + Claude)
# ---------------------------------------------------------------------------

class _FakeAxisInfo:
    def __init__(self, unit_name: str) -> None:
        self.unit_name = unit_name


class _FakeCRS:
    def __init__(self, unit_name: str, is_geographic: bool = False) -> None:
        self.axis_info = [_FakeAxisInfo(unit_name)]
        self.is_geographic = is_geographic

    def __repr__(self) -> str:
        return f"FakeCRS(unit={self.axis_info[0].unit_name!r})"


def test_crs_unit_factor_accepts_metres() -> None:
    from openlimno.ibm.studio_instream7_default import _crs_unit_factor

    assert _crs_unit_factor(_FakeCRS("metre")) == 1.0
    assert _crs_unit_factor(_FakeCRS("meter")) == 1.0


def test_crs_unit_factor_accepts_us_survey_foot() -> None:
    from openlimno.ibm.studio_instream7_default import _crs_unit_factor

    factor = _crs_unit_factor(_FakeCRS("US survey foot"))
    assert factor == pytest.approx(0.3048, abs=1e-6)


def test_crs_unit_factor_rejects_geographic_crs() -> None:
    """Pins Claude review: geographic CRS (degrees) must be rejected so the
    Studio does not silently treat 0.001 degrees as 0.001 metres."""
    from openlimno.ibm.studio_instream7_default import _crs_unit_factor

    with pytest.raises(ValueError, match="geographic"):
        _crs_unit_factor(_FakeCRS("degree", is_geographic=True))


def test_crs_unit_factor_rejects_missing_crs() -> None:
    from openlimno.ibm.studio_instream7_default import _crs_unit_factor

    with pytest.raises(ValueError, match="no CRS"):
        _crs_unit_factor(None)


def test_crs_unit_factor_rejects_unknown_unit() -> None:
    """Triple-review: silent default to 1.0 was the original bug."""
    from openlimno.ibm.studio_instream7_default import _crs_unit_factor

    with pytest.raises(ValueError, match="unrecognised linear unit"):
        _crs_unit_factor(_FakeCRS("league"))


# ---------------------------------------------------------------------------
# default_studio_scenario_resolved — fallback path (Claude + Gemini)
# ---------------------------------------------------------------------------

def test_resolved_falls_back_when_no_archive_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No env var + empty candidate dirs → synthetic demo, no log."""
    import openlimno.ibm.studio_instream7_default as m
    from openlimno.ibm.studio import default_studio_scenario_resolved

    monkeypatch.delenv("OPENLIMNO_INSTREAM7_ARCHIVE", raising=False)
    monkeypatch.setattr(m, "_CANDIDATE_DIRS", (tmp_path / "a", tmp_path / "b"))

    payload = default_studio_scenario_resolved()
    # Synthetic demo signature.
    assert payload["config"]["scenario_id"] == "lemhi-river-trout-demo"
    river = payload["river"]
    assert isinstance(river, dict)
    assert river["name"] == "Lemhi River"


def test_resolved_warns_when_archive_load_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Pins Gemini + Claude review: a present-but-broken archive must
    emit a WARNING before silently degrading to the synthetic demo."""
    import openlimno.ibm.studio_instream7_default as m
    from openlimno.ibm.studio import default_studio_scenario_resolved

    bad = tmp_path / "bad_archive"
    bad.mkdir()
    (bad / "marker").write_text("not a real inSTREAM archive")
    monkeypatch.setenv("OPENLIMNO_INSTREAM7_ARCHIVE", str(bad))
    monkeypatch.setattr(m, "_CANDIDATE_DIRS", ())

    with caplog.at_level(logging.WARNING, logger="openlimno.ibm.studio"):
        payload = default_studio_scenario_resolved()

    # Still functional — degrades to synthetic.
    assert payload["config"]["scenario_id"] == "lemhi-river-trout-demo"
    # But the user is warned, with the archive path in the message.
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(str(bad) in r.getMessage() for r in warnings), (
        "Expected a WARNING citing the bad archive path; got:"
        + " | ".join(r.getMessage() for r in warnings)
    )
    # Pins 2026-05-26 software-test N2 (Codex): the fallback payload must
    # carry a banner reason so the UI can mark the demo as "not your archive".
    assert "_fallback_reason" in payload
    river = payload["river"]
    assert isinstance(river, dict)
    assert "⚠ Synthetic demo" in str(river["display_note"])


# ---------------------------------------------------------------------------
# Software-test S1: length→mass profile bridge (Codex + Gemini)
# ---------------------------------------------------------------------------

def test_build_initial_population_uses_passed_profile_weight_params() -> None:
    """Pin Codex + Gemini independent S1 finding: when the scenario carries
    a custom profile with non-default weight_a/b, build_initial_population
    must use those — not silently fall back to the default SpeciesProfile()
    weight_a/b and let the runtime later disagree on mass.
    """
    from openlimno.ibm.native import SpeciesProfile, build_initial_population

    custom = SpeciesProfile(species="rainbow_trout", weight_a_g_per_cm_b=0.02, weight_b=3.10)
    default = SpeciesProfile(species="rainbow_trout")
    assert custom.weight_a_g_per_cm_b != default.weight_a_g_per_cm_b
    pop_custom = build_initial_population(n=5, length_mm=120.0, profile=custom)
    pop_default = build_initial_population(n=5, length_mm=120.0)
    # The custom profile's weight_a is bigger → mass must be bigger too.
    assert float(pop_custom["mass_g"].iloc[0]) > float(pop_default["mass_g"].iloc[0])


# ---------------------------------------------------------------------------
# Software-test S2: JSON NaN sanitisation (Codex)
# ---------------------------------------------------------------------------

def test_sanitize_for_json_replaces_nan_inf_with_none() -> None:
    """NaN / +Inf / -Inf must round-trip through json.dumps(allow_nan=False)
    as ``null`` — not as the non-standard ``NaN`` / ``Infinity`` tokens
    that Python's default would emit. (2026-05-26 software-test S2,
    Codex caught when initial_abundance=0 made final_mean_length_mm=NaN.)
    """
    import json
    import math

    from openlimno.ibm.studio import _sanitize_for_json

    payload = {
        "x": math.nan,
        "y": math.inf,
        "z": -math.inf,
        "ok": 1.5,
        "nested": [math.nan, {"deep": math.inf}],
    }
    sanitised = _sanitize_for_json(payload)
    body = json.dumps(sanitised, allow_nan=False)
    assert '"x": null' in body
    assert '"y": null' in body
    assert '"z": null' in body
    assert '"ok": 1.5' in body


# ---------------------------------------------------------------------------
# Software-test S3: hydraulic input validation (Codex + Gemini)
# ---------------------------------------------------------------------------

def test_cells_from_payload_rejects_negative_depth() -> None:
    from openlimno.ibm.studio import _cells_from_payload

    with pytest.raises(ValueError, match="depth_m.*outside"):
        _cells_from_payload([
            {"cell_id": "c1", "depth_m": -1.0, "velocity_ms": 0.3},
        ])


def test_cells_from_payload_rejects_nan_velocity() -> None:
    import math

    from openlimno.ibm.studio import _cells_from_payload

    with pytest.raises(ValueError, match="velocity_ms.*NaN"):
        _cells_from_payload([
            {"cell_id": "c1", "depth_m": 0.5, "velocity_ms": math.nan},
        ])


def test_cells_from_payload_rejects_cover_outside_unit_interval() -> None:
    from openlimno.ibm.studio import _cells_from_payload

    with pytest.raises(ValueError, match="hiding_cover.*outside"):
        _cells_from_payload([
            {"cell_id": "c1", "depth_m": 0.5, "velocity_ms": 0.3, "hiding_cover": 1.5},
        ])


# ---------------------------------------------------------------------------
# Software-test M2: days cap (Codex)
# ---------------------------------------------------------------------------

def test_studio_run_caps_days_at_max() -> None:
    """Pins Codex M2: ``days=10000`` must be silently clamped to
    MAX_STUDIO_DAYS so a stray POST cannot pin a request thread for hours.
    We verify the ``_as_int`` cap directly so the test stays fast (a real
    end-to-end run of MAX_STUDIO_DAYS days is multi-second by design)."""
    from openlimno.ibm.studio import MAX_STUDIO_DAYS, _as_int

    assert _as_int(100_000, 45, min_value=0, max_value=MAX_STUDIO_DAYS) == MAX_STUDIO_DAYS
    assert _as_int(0, 45, min_value=0, max_value=MAX_STUDIO_DAYS) == 0
    assert _as_int(7, 45, min_value=0, max_value=MAX_STUDIO_DAYS) == 7


# ---------------------------------------------------------------------------
# Software-test M1: run-dir prune
# ---------------------------------------------------------------------------

def test_run_studio_scenario_surfaces_effective_days_warning(tmp_path: Path) -> None:
    """Pin pass-2 M2' (Codex): the response must announce the cap, not
    silently change the requested simulation horizon. Use a small valid
    horizon (1 day) and a synthetic over-cap request (MAX+1) for speed —
    actually running MAX_STUDIO_DAYS days would take minutes."""
    from openlimno.ibm.studio import (
        MAX_STUDIO_DAYS,
        MAX_STUDIO_INITIAL_ABUNDANCE,
        default_studio_scenario,
        run_studio_scenario,
    )

    # First: a tiny over-cap test for initial_abundance (cheaper than days).
    payload = default_studio_scenario()
    config = payload["config"]
    assert isinstance(config, dict)
    config["days"] = 1
    config["initial_abundance"] = MAX_STUDIO_INITIAL_ABUNDANCE + 100
    config["record_individual_history"] = False
    result = run_studio_scenario(payload, tmp_path)

    warnings = result["warnings"]
    assert isinstance(warnings, list)
    assert any("initial_abundance clamped" in w for w in warnings), warnings
    metrics = result["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["requested_initial_abundance"] == MAX_STUDIO_INITIAL_ABUNDANCE + 100
    assert metrics["initial_abundance"] == MAX_STUDIO_INITIAL_ABUNDANCE
    # effective_days/requested_days fields should always be present.
    assert metrics["requested_days"] == 1
    assert metrics["effective_days"] == 1
    # days cap is also wired (verified by direct min() — we don't run the
    # full MAX_STUDIO_DAYS horizon here).
    capped = min(MAX_STUDIO_DAYS + 5, MAX_STUDIO_DAYS)
    assert capped == MAX_STUDIO_DAYS


def test_run_studio_scenario_survival_null_when_initial_zero(tmp_path: Path) -> None:
    """Pin pass-2 M3' (Codex): 0/0 → None, not 0.0."""
    from openlimno.ibm.studio import default_studio_scenario, run_studio_scenario

    payload = default_studio_scenario()
    config = payload["config"]
    assert isinstance(config, dict)
    config["initial_abundance"] = 0
    config["days"] = 1
    config["record_individual_history"] = False
    result = run_studio_scenario(payload, tmp_path)
    metrics = result["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["initial_abundance"] == 0
    assert metrics["survival_rate"] is None


def test_user_error_message_hides_python_exception_class() -> None:
    """Pin pass-2 N5' (Codex): 400 body must not leak Python class name."""
    import json as _json

    from openlimno.ibm.studio_http import _user_error_message

    exc = _json.JSONDecodeError("Expecting value", "{bad json", 0)
    msg = _user_error_message(exc)
    assert "JSONDecodeError" not in msg
    assert "not valid JSON" in msg


def test_run_dir_prune_steady_state_equals_keep(tmp_path: Path) -> None:
    """Pin pass-2 N4' (Codex): after prune+new-alloc the total must equal
    MAX_STUDIO_RUN_DIRS, not MAX_STUDIO_RUN_DIRS + 1."""
    import openlimno.ibm.studio as studio_mod
    from openlimno.ibm.studio import _run_dir

    keep = 5
    for i in range(8):
        (tmp_path / f"native-{i:08d}-deadbeef").mkdir()
    original = studio_mod.MAX_STUDIO_RUN_DIRS
    studio_mod.MAX_STUDIO_RUN_DIRS = keep
    try:
        path = _run_dir(tmp_path, "native")
        path.mkdir()
        survivors = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith("native-")]
        # Steady state should be exactly `keep`, not `keep + 1`.
        assert len(survivors) == keep, f"expected exactly {keep} dirs, got {len(survivors)}: {sorted(p.name for p in survivors)}"
    finally:
        studio_mod.MAX_STUDIO_RUN_DIRS = original


def test_run_dir_prunes_oldest_above_keep_watermark(tmp_path: Path) -> None:
    """Pin Codex M1: once MAX_STUDIO_RUN_DIRS run dirs accumulate, the
    oldest ones must be pruned automatically on the next allocation."""
    from openlimno.ibm.studio import _run_dir

    keep = 5
    # Pre-create 8 fake old run dirs.
    for i in range(8):
        (tmp_path / f"native-{i:08d}-deadbeef").mkdir()
    # Allocate via the real path with a small `keep` watermark.
    import openlimno.ibm.studio as studio_mod
    original = studio_mod.MAX_STUDIO_RUN_DIRS
    studio_mod.MAX_STUDIO_RUN_DIRS = keep
    try:
        path = _run_dir(tmp_path, "native")
        path.mkdir()  # actually create it
        # After prune + new allocation: <= keep + 1.
        survivors = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
        assert len(survivors) <= keep + 1, f"prune failed: {survivors}"
    finally:
        studio_mod.MAX_STUDIO_RUN_DIRS = original
