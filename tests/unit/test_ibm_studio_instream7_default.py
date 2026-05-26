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
