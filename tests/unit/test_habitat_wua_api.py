"""Numerical contract tests for the public WUA-Q library API. SPEC §4.2.3.

Covers ``openlimno.habitat.wua.wua_q_curve`` and its per-section helper
``evaluate_section_csi`` — the library-level entry point exported from
``openlimno.habitat`` for callers who want a WUA-Q sweep without building a
full :class:`openlimno.case.Case`.

Three layers of assertion, deliberately independent of the implementation:

1. **Closed-form arithmetic** — a stub solver with hand-picked
   depth/velocity/area triples and identity HSI curves, so every WUA is a
   number that can be computed on paper.
2. **Closed-form hydraulics** — the Bovee-style wide rectangular prismatic
   reach where Manning normal depth is analytic (same recipe as
   ``benchmarks/phabsim_bovee1997/test_bovee_1997.py``).
3. **Cross-validation against the production path** — the same inputs pushed
   through ``Case._compute_cell_wua`` (``cell_wua`` + ``composite_csi``), which
   is what ``Case.run`` actually writes into ``wua_q.csv``. The two paths must
   agree to floating-point identity, otherwise regulatory outputs (SL/Z 712,
   FERC 4(e), EU WFD) would depend on which entry point the caller picked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from openlimno.case import Case
from openlimno.habitat import HSICurve, wua_q_curve
from openlimno.habitat.wua import evaluate_section_csi
from openlimno.hydro.builtin_1d import Builtin1D, CrossSection, MANSQResult

SPECIES = "oncorhynchus_mykiss"
STAGE = "spawning"


# ---------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------
def identity_curve(variable: str) -> HSICurve:
    """SI(x) = clamp(x, 0, 1) — keeps hand-computed CSI exact."""
    return HSICurve(
        species=SPECIES,
        life_stage=STAGE,
        variable=variable,  # type: ignore[arg-type]
        points=[(0.0, 0.0), (1.0, 1.0)],
        category="III",
        geographic_origin="Pacific-Northwest-USA",
        transferability_score=0.6,
        quality_grade="B",
    )


def identity_curves(*variables: str) -> dict[tuple[str, str, str], HSICurve]:
    return {(SPECIES, STAGE, v): identity_curve(v) for v in variables}


def make_result(depth: float, velocity: float, area: float, station: float = 0.0) -> MANSQResult:
    """A hydraulic solution stub carrying only the fields WUA consumes."""
    return MANSQResult(
        station_m=station,
        discharge_m3s=1.0,
        water_surface_m=depth,
        depth_mean_m=depth,
        velocity_mean_ms=velocity,
        area_m2=area,
        top_width_m=max(area / depth, 0.0) if depth > 0 else 0.0,
        hydraulic_radius_m=depth,
    )


# (depth, velocity, area) per section, keyed by discharge.
# Identity curves make SI == the raw value, so CSI is exact:
#   Q=1: geom = sqrt(.25*.64) = 0.40 ; sqrt(.81*.36) = 0.54
#   Q=2: geom = sqrt(.36*1.0) = 0.60 ; sqrt(1.0*.25) = 0.50
STUB_TABLE: dict[float, list[tuple[float, float, float]]] = {
    1.0: [(0.25, 0.64, 10.0), (0.81, 0.36, 20.0)],
    2.0: [(0.36, 1.00, 15.0), (1.00, 0.25, 25.0)],
}


def stub_solver(sections: list[Any], discharge_m3s: float) -> list[MANSQResult]:
    return [
        make_result(d, v, a, station=float(i) * 100.0)
        for i, (d, v, a) in enumerate(STUB_TABLE[discharge_m3s])
    ]


# ---------------------------------------------------------------------
# evaluate_section_csi — per-section composite arithmetic
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("composite", "expected"),
    [
        ("geometric_mean", 0.4),  # sqrt(0.25 * 0.64)
        ("arithmetic_mean", 0.445),  # (0.25 + 0.64) / 2
        ("min", 0.25),
        ("weighted_geometric", 0.4),  # equal weights == geometric mean
    ],
)
def test_evaluate_section_csi_composite_methods(composite: str, expected: float) -> None:
    csi = evaluate_section_csi(
        depth=0.25,
        velocity=0.64,
        hsi_curves=identity_curves("depth", "velocity"),
        species=SPECIES,
        life_stage=STAGE,
        composite=composite,
        acknowledge_independence=True,
    )
    assert csi == pytest.approx(expected, rel=1e-12)


def test_evaluate_section_csi_extras_add_a_third_variable() -> None:
    """``extras`` variables join the composite when a curve exists for them."""
    d, v, s = 0.10, 0.40, 0.25
    csi = evaluate_section_csi(
        depth=d,
        velocity=v,
        hsi_curves=identity_curves("depth", "velocity", "substrate"),
        species=SPECIES,
        life_stage=STAGE,
        composite="geometric_mean",
        acknowledge_independence=True,
        extras={"substrate": s},
    )
    assert csi == pytest.approx(float(np.cbrt(d * v * s)), rel=1e-12)


def test_evaluate_section_csi_extras_without_curve_are_ignored() -> None:
    """An extras key with no matching curve must not change the CSI."""
    curves = identity_curves("depth", "velocity")
    with_extra = evaluate_section_csi(
        depth=0.25,
        velocity=0.64,
        hsi_curves=curves,
        species=SPECIES,
        life_stage=STAGE,
        composite="geometric_mean",
        acknowledge_independence=True,
        extras={"cover": 0.9},  # no cover curve loaded
    )
    assert with_extra == pytest.approx(0.4, rel=1e-12)


def test_evaluate_section_csi_missing_variable_uses_the_rest() -> None:
    """Depth-only curve set collapses the composite onto SI_depth."""
    csi = evaluate_section_csi(
        depth=0.25,
        velocity=0.64,
        hsi_curves=identity_curves("depth"),
        species=SPECIES,
        life_stage=STAGE,
        composite="geometric_mean",
        acknowledge_independence=True,
    )
    assert csi == pytest.approx(0.25, rel=1e-12)


def test_evaluate_section_csi_no_curves_returns_zero() -> None:
    """No resolvable variable => 0.0, never a composite_csi ValueError."""
    csi = evaluate_section_csi(
        depth=0.25,
        velocity=0.64,
        hsi_curves={},
        species=SPECIES,
        life_stage=STAGE,
        composite="min",
    )
    assert csi == 0.0


def test_evaluate_section_csi_wrong_species_returns_zero() -> None:
    csi = evaluate_section_csi(
        depth=0.25,
        velocity=0.64,
        hsi_curves=identity_curves("depth", "velocity"),
        species="salmo_trutta",
        life_stage=STAGE,
        composite="min",
    )
    assert csi == 0.0


# ---------------------------------------------------------------------
# ADR-0006 / SPEC §4.2.2.2 independence hard gate
# ---------------------------------------------------------------------
@pytest.mark.parametrize("composite", ["geometric_mean", "arithmetic_mean"])
def test_evaluate_section_csi_requires_independence_ack(composite: str) -> None:
    with pytest.raises(ValueError, match="acknowledge_independence"):
        evaluate_section_csi(
            depth=0.25,
            velocity=0.64,
            hsi_curves=identity_curves("depth", "velocity"),
            species=SPECIES,
            life_stage=STAGE,
            composite=composite,
        )


@pytest.mark.parametrize("composite", ["min", "weighted_geometric"])
def test_evaluate_section_csi_ungated_methods_need_no_ack(composite: str) -> None:
    csi = evaluate_section_csi(
        depth=0.25,
        velocity=0.64,
        hsi_curves=identity_curves("depth", "velocity"),
        species=SPECIES,
        life_stage=STAGE,
        composite=composite,
    )
    assert csi > 0.0


@pytest.mark.parametrize("composite", ["geometric_mean", "arithmetic_mean"])
def test_wua_q_curve_gate_fires_before_any_hydraulics(composite: str) -> None:
    """The guard must reject up front — no solver call, no partial output."""
    calls: list[float] = []

    def counting_solver(sections: list[Any], discharge_m3s: float) -> list[MANSQResult]:
        calls.append(discharge_m3s)
        return stub_solver(sections, discharge_m3s)

    with pytest.raises(ValueError, match="acknowledge_independence"):
        wua_q_curve(
            sections_solver=counting_solver,
            sections=[],
            discharges_m3s=[1.0, 2.0],
            hsi_curves=identity_curves("depth", "velocity"),
            species=SPECIES,
            life_stage=STAGE,
            composite=composite,
        )
    assert calls == [], "solver ran despite the SPEC §4.2.2.2 independence gate"


# ---------------------------------------------------------------------
# wua_q_curve — hand-computable arithmetic
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("composite", "expected"),
    [
        # Q=1: 0.40*10 + 0.54*20 = 14.8 ; Q=2: 0.60*15 + 0.50*25 = 21.5
        ("geometric_mean", [14.8, 21.5]),
        # Q=1: 0.445*10 + 0.585*20 = 16.15 ; Q=2: 0.68*15 + 0.625*25 = 25.825
        ("arithmetic_mean", [16.15, 25.825]),
        # Q=1: 0.25*10 + 0.36*20 = 9.7 ; Q=2: 0.36*15 + 0.25*25 = 11.65
        ("min", [9.7, 11.65]),
    ],
)
def test_wua_q_curve_hand_computed_values(composite: str, expected: list[float]) -> None:
    df = wua_q_curve(
        sections_solver=stub_solver,
        sections=[None, None],
        discharges_m3s=[1.0, 2.0],
        hsi_curves=identity_curves("depth", "velocity"),
        species=SPECIES,
        life_stage=STAGE,
        composite=composite,
        acknowledge_independence=True,
    )
    assert list(df.columns) == ["discharge_m3s", "wua_m2", "n_sections_used"]
    assert df["discharge_m3s"].tolist() == [1.0, 2.0]
    assert df["wua_m2"].tolist() == pytest.approx(expected, rel=1e-12)
    assert df["n_sections_used"].tolist() == [2, 2]


def test_wua_q_curve_preserves_discharge_order_and_duplicates() -> None:
    """Rows follow the caller's sweep order verbatim — no sorting, no dedup."""
    df = wua_q_curve(
        sections_solver=stub_solver,
        sections=[None, None],
        discharges_m3s=[2.0, 1.0, 2.0],
        hsi_curves=identity_curves("depth", "velocity"),
        species=SPECIES,
        life_stage=STAGE,
        composite="min",
    )
    assert df["discharge_m3s"].tolist() == [2.0, 1.0, 2.0]
    assert df["wua_m2"].tolist() == pytest.approx([11.65, 9.7, 11.65], rel=1e-12)


def test_wua_q_curve_empty_sweep_returns_empty_frame() -> None:
    df = wua_q_curve(
        sections_solver=stub_solver,
        sections=[],
        discharges_m3s=[],
        hsi_curves=identity_curves("depth", "velocity"),
        species=SPECIES,
        life_stage=STAGE,
        composite="min",
    )
    assert len(df) == 0


def test_wua_q_curve_no_curves_gives_zero_wua_but_counts_wet_sections() -> None:
    df = wua_q_curve(
        sections_solver=stub_solver,
        sections=[None, None],
        discharges_m3s=[1.0],
        hsi_curves={},
        species=SPECIES,
        life_stage=STAGE,
        composite="min",
    )
    assert df["wua_m2"].tolist() == [0.0]
    # n_sections_used counts *wetted* sections, not sections with a CSI > 0.
    assert df["n_sections_used"].tolist() == [2]


# ---------------------------------------------------------------------
# wua_q_curve — dry-section skipping and area weighting
# ---------------------------------------------------------------------
@pytest.mark.parametrize("dry_area", [0.0, -1.0])
def test_wua_q_curve_skips_dry_sections(dry_area: float) -> None:
    """``area_m2 <= 0`` sections drop out of both WUA and n_sections_used."""

    def solver_with_dry(sections: list[Any], discharge_m3s: float) -> list[MANSQResult]:
        return [
            make_result(0.25, 0.64, 10.0),
            make_result(0.0, 0.0, dry_area),  # dewatered / degenerate section
            make_result(0.81, 0.36, 20.0),
        ]

    df = wua_q_curve(
        sections_solver=solver_with_dry,
        sections=[None, None, None],
        discharges_m3s=[1.0],
        hsi_curves=identity_curves("depth", "velocity"),
        species=SPECIES,
        life_stage=STAGE,
        composite="geometric_mean",
        acknowledge_independence=True,
    )
    assert df["wua_m2"].tolist() == pytest.approx([14.8], rel=1e-12)
    assert df["n_sections_used"].tolist() == [1 + 1]


def test_wua_q_curve_section_areas_weights_stay_index_aligned() -> None:
    """Explicit weights are indexed by *section*, not by used-section counter.

    The dry section sits in the middle with a poison weight; if the skip
    logic ever compacted the index, the third section would pick up 999.0.
    """

    def solver_with_dry(sections: list[Any], discharge_m3s: float) -> list[MANSQResult]:
        return [
            make_result(0.25, 0.64, 10.0),
            make_result(0.0, 0.0, 0.0),
            make_result(0.81, 0.36, 20.0),
        ]

    df = wua_q_curve(
        sections_solver=solver_with_dry,
        sections=[None, None, None],
        discharges_m3s=[1.0],
        hsi_curves=identity_curves("depth", "velocity"),
        species=SPECIES,
        life_stage=STAGE,
        section_areas_m2=[5.0, 999.0, 50.0],
        composite="geometric_mean",
        acknowledge_independence=True,
    )
    # 0.40 * 5 + 0.54 * 50 = 29.0 (the 999.0 weight is dewatered away)
    assert df["wua_m2"].tolist() == pytest.approx([29.0], rel=1e-12)
    assert df["n_sections_used"].tolist() == [2]


def test_wua_q_curve_weights_override_wetted_area() -> None:
    """``section_areas_m2=None`` uses ``area_m2``; a list replaces it entirely."""
    kwargs: dict[str, Any] = {
        "sections_solver": stub_solver,
        "sections": [None, None],
        "discharges_m3s": [1.0],
        "hsi_curves": identity_curves("depth", "velocity"),
        "species": SPECIES,
        "life_stage": STAGE,
        "composite": "geometric_mean",
        "acknowledge_independence": True,
    }
    default = wua_q_curve(**kwargs)
    weighted = wua_q_curve(section_areas_m2=[100.0, 200.0], **kwargs)
    assert default["wua_m2"].tolist() == pytest.approx([14.8], rel=1e-12)
    # 0.40 * 100 + 0.54 * 200 = 148.0
    assert weighted["wua_m2"].tolist() == pytest.approx([148.0], rel=1e-12)


# ---------------------------------------------------------------------
# Closed-form hydraulics: Bovee-style rectangular prismatic reach
# ---------------------------------------------------------------------
BED_SLOPE = 0.001
CHANNEL_WIDTH_M = 10.0
MANNING_N = 0.030
SECTION_SPACING_M = 100.0
N_SECTIONS = 6

DEPTH_SI_POINTS = [(0.0, 0.0), (0.30, 1.0), (0.60, 1.0), (1.20, 0.5), (2.00, 0.0)]
VELOCITY_SI_POINTS = [(0.00, 0.0), (0.50, 1.0), (1.00, 1.0), (1.50, 0.3), (2.00, 0.0)]


def bovee_curves() -> dict[tuple[str, str, str], HSICurve]:
    def curve(variable: str, points: list[tuple[float, float]]) -> HSICurve:
        return HSICurve(
            species=SPECIES,
            life_stage=STAGE,
            variable=variable,  # type: ignore[arg-type]
            points=points,
            category="III",
            geographic_origin="Pacific-Northwest-USA",
            transferability_score=0.6,
            quality_grade="B",
        )

    return {
        (SPECIES, STAGE, "depth"): curve("depth", DEPTH_SI_POINTS),
        (SPECIES, STAGE, "velocity"): curve("velocity", VELOCITY_SI_POINTS),
    }


def bovee_reach() -> list[CrossSection]:
    """Wide rectangular prism, walls high enough never to be overtopped."""
    half = CHANNEL_WIDTH_M / 2
    sections = []
    for i in range(N_SECTIONS):
        bed = 1.0 - BED_SLOPE * i * SECTION_SPACING_M
        sections.append(
            CrossSection(
                station_m=i * SECTION_SPACING_M,
                distance_m=np.array([-half - 0.01, -half, half, half + 0.01]),
                elevation_m=np.array([bed + 5.0, bed, bed, bed + 5.0]),
                manning_n=MANNING_N,
            )
        )
    return sections


def manning_rect_depth(Q: float) -> float:
    """Exact rectangular Manning normal depth (full P = b + 2h)."""
    from scipy.optimize import brentq

    b, n, S = CHANNEL_WIDTH_M, MANNING_N, BED_SLOPE

    def residual(h: float) -> float:
        A = b * h
        R = A / (b + 2 * h)
        return (1.0 / n) * A * R ** (2.0 / 3.0) * np.sqrt(S) - Q

    return float(brentq(residual, 1e-4, 50.0))


def expected_wua(Q: float) -> float:
    """Hand-computed WUA for the prismatic reach, area_m2 weighting."""
    h = manning_rect_depth(Q)
    u = Q / (CHANNEL_WIDTH_M * h)
    s_h = float(np.interp(h, *zip(*DEPTH_SI_POINTS, strict=True)))
    s_u = float(np.interp(u, *zip(*VELOCITY_SI_POINTS, strict=True)))
    csi = float(np.sqrt(s_h * s_u))  # geometric mean of two variables
    return csi * (CHANNEL_WIDTH_M * h) * N_SECTIONS


@pytest.mark.parametrize("Q", [0.5, 1.5, 4.0, 8.0])
def test_wua_q_curve_matches_manning_closed_form(Q: float) -> None:
    """End-to-end: Builtin1D + wua_q_curve reproduce the analytic WUA."""
    solver = Builtin1D(slope=BED_SLOPE)
    df = wua_q_curve(
        sections_solver=solver.solve_reach,
        sections=bovee_reach(),
        discharges_m3s=[Q],
        hsi_curves=bovee_curves(),
        species=SPECIES,
        life_stage=STAGE,
        composite="geometric_mean",
        acknowledge_independence=True,
    )
    assert df["n_sections_used"].tolist() == [N_SECTIONS]
    assert df["wua_m2"].iloc[0] == pytest.approx(expected_wua(Q), rel=1e-3, abs=1e-3)


def test_wua_q_curve_is_unimodal_over_a_flow_sweep() -> None:
    """Domain check: WUA-Q must rise then fall, not saturate monotonically."""
    solver = Builtin1D(slope=BED_SLOPE)
    df = wua_q_curve(
        sections_solver=solver.solve_reach,
        sections=bovee_reach(),
        discharges_m3s=[0.2, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 20.0],
        hsi_curves=bovee_curves(),
        species=SPECIES,
        life_stage=STAGE,
        composite="geometric_mean",
        acknowledge_independence=True,
    )
    wuas = df["wua_m2"].to_numpy()
    peak = int(np.argmax(wuas))
    assert 0 < peak < len(wuas) - 1, f"WUA-Q curve not unimodal: {wuas.round(2)}"


def test_wua_q_curve_zero_discharge_dewaters_the_reach() -> None:
    solver = Builtin1D(slope=BED_SLOPE)
    df = wua_q_curve(
        sections_solver=solver.solve_reach,
        sections=bovee_reach(),
        discharges_m3s=[0.0],
        hsi_curves=bovee_curves(),
        species=SPECIES,
        life_stage=STAGE,
        composite="min",
    )
    assert df["wua_m2"].tolist() == [0.0]
    assert df["n_sections_used"].tolist() == [0]


# ---------------------------------------------------------------------
# Cross-validation against the production Case pipeline
# ---------------------------------------------------------------------
def _case_path_wua(
    results: list[MANSQResult],
    curves: dict[tuple[str, str, str], HSICurve],
    composite: str,
) -> tuple[float, list[str]]:
    """Run the exact code path ``Case.run`` uses to fill ``wua_q.csv``.

    ``Case`` is a plain dataclass, so an unconfigured instance is enough to
    reach ``_compute_cell_wua`` (``cell_wua`` + ``composite_csi`` over the
    per-cell arrays); no YAML, no filesystem.
    """
    case = Case(config={}, case_yaml_path=Path("unused.yaml"))
    warnings: list[str] = []
    wua = case._compute_cell_wua(
        results,
        curves,
        SPECIES,
        STAGE,
        composite=composite,
        ack=True,
        warnings=warnings,
    )
    return wua, warnings


@pytest.mark.parametrize("composite", ["geometric_mean", "arithmetic_mean", "min"])
@pytest.mark.parametrize("Q", [0.2, 0.5, 1.5, 4.0, 8.0, 20.0])
def test_wua_q_curve_agrees_with_case_pipeline(composite: str, Q: float) -> None:
    """The library API and ``Case.run``'s path must not disagree numerically.

    ``wua_q_curve`` loops section-by-section through ``evaluate_section_csi``;
    ``Case._compute_cell_wua`` composites whole numpy arrays and sums with
    ``cell_wua``. Regulatory deliverables (SL/Z 712, FERC 4(e), EU WFD) must
    not depend on which of the two a caller reached for.
    """
    sections = bovee_reach()
    curves = bovee_curves()
    solver = Builtin1D(slope=BED_SLOPE)

    df = wua_q_curve(
        sections_solver=solver.solve_reach,
        sections=sections,
        discharges_m3s=[Q],
        hsi_curves=curves,
        species=SPECIES,
        life_stage=STAGE,
        composite=composite,
        acknowledge_independence=True,
    )
    case_wua, warnings = _case_path_wua(solver.solve_reach(sections, Q), curves, composite)

    assert warnings == []
    assert df["wua_m2"].iloc[0] == pytest.approx(case_wua, rel=1e-12, abs=1e-12)


def test_wua_q_curve_agrees_with_case_pipeline_when_a_curve_is_missing() -> None:
    """Depth-only curve set: both paths collapse onto SI_depth, same total."""
    sections = bovee_reach()
    curves = {k: v for k, v in bovee_curves().items() if k[2] == "depth"}
    solver = Builtin1D(slope=BED_SLOPE)

    df = wua_q_curve(
        sections_solver=solver.solve_reach,
        sections=sections,
        discharges_m3s=[4.0],
        hsi_curves=curves,
        species=SPECIES,
        life_stage=STAGE,
        composite="geometric_mean",
        acknowledge_independence=True,
    )
    case_wua, warnings = _case_path_wua(solver.solve_reach(sections, 4.0), curves, "geometric_mean")

    assert df["wua_m2"].iloc[0] == pytest.approx(case_wua, rel=1e-12, abs=1e-12)
    # The Case path additionally reports the dropped variable; the library
    # path has no warnings channel — the only behavioural difference.
    assert any("velocity" in w for w in warnings)


def test_wua_q_curve_agrees_with_case_pipeline_when_no_curves_resolve() -> None:
    sections = bovee_reach()
    solver = Builtin1D(slope=BED_SLOPE)

    df = wua_q_curve(
        sections_solver=solver.solve_reach,
        sections=sections,
        discharges_m3s=[4.0],
        hsi_curves={},
        species=SPECIES,
        life_stage=STAGE,
        composite="min",
    )
    case_wua, _ = _case_path_wua(solver.solve_reach(sections, 4.0), {}, "min")

    assert df["wua_m2"].iloc[0] == 0.0
    assert case_wua == 0.0
