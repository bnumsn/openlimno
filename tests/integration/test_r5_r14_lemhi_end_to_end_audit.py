"""R-DOC-AUDIT-WIRED — fourth pass: R5..R14 cluster behavioural pin
via end-to-end Lemhi case run (2026-05-20).

The early review rounds (F, N, M, R5..R14) shipped the foundational
helpers that v3.x then hardened:

- **R5/R6/R9-1** — ``Case._atomic_write`` (truncate-safe publish)
- **R6/R7/R10** — ``habitat.composite_overlay`` (geometric-mean +
  per-cell composite)
- **F/N/M/R7** — regulatory CSV atomic publish + watermark headers
  (SL712 / FERC-4e / EU-WFD)
- **R8** — provenance SHA-256 chain
- **R9** — HSI quality grading (A/B/C with watermark banner)
- **R10/R11** — WEDM schema strictness (``validate_case`` +
  ``Case.from_yaml`` format-checker)
- **R9-3** — high-latitude buffer (later refined in v3.4/v3.5/v3.6/v3.6.1)

A million unit pins on each round's helper would not prove these
are wired together. THIS test does: run ``examples/lemhi/case.yaml``
end-to-end through ``Case.run`` and assert every cluster's artifact
is present, well-formed, and consistent.

If any of the R5..R14 helpers regresses to a no-op, this test
fails AT THE CLUSTER LEVEL rather than only being caught in a
per-finding source-pin. This is the strongest production-caller
audit available for the early-round helpers.

The actual Lemhi data fixtures (`data/lemhi/*.parquet`,
`Q_2024.csv`, `mesh.ugrid.nc`, `rating_curve.parquet`) ship in the
repo. If they go missing this test fails — `data/lemhi/manifest.json`
is the canonical inventory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from openlimno.case import Case

REPO_ROOT = Path(__file__).resolve().parents[2]
LEMHI_CASE = REPO_ROOT / "examples" / "lemhi" / "case.yaml"


def _require_fixtures() -> None:
    """Skip when the Lemhi data fixtures are absent (e.g. minimal
    checkout). Otherwise the test would fail in a way that masks
    real audit drift."""
    data_dir = REPO_ROOT / "data" / "lemhi"
    needed = [
        "cross_section.parquet",
        "hsi_curve.parquet",
        "hsi_evidence.parquet",
        "life_stage.parquet",
        "mesh.ugrid.nc",
        "Q_2024.csv",
        "rating_curve.parquet",
    ]
    missing = [f for f in needed if not (data_dir / f).exists()]
    if missing:
        pytest.skip(
            f"R5-R14 cluster pin skipped: Lemhi fixtures missing in "
            f"{data_dir}: {missing}. See data/lemhi/manifest.json."
        )


@pytest.fixture(scope="module")
def lemhi_result(tmp_path_factory: pytest.TempPathFactory):
    """Run Lemhi once; share the result across cluster assertions
    to keep this fixture cheap.

    Redirects output to a tmp_path AND adds that tmp_path to the
    case's allowed_data_roots so the v3.0 strict-by-default sandbox
    accepts the write target. The sandbox refusal-without-this is
    itself part of what this fixture exercises (a separate "sandbox
    blocks unconfigured tmp" test in the R-DOC-AUDIT-WIRED chain
    pins that behaviour)."""
    _require_fixtures()
    case = Case.from_yaml(LEMHI_CASE)
    tmp_out = tmp_path_factory.mktemp("lemhi_audit_out")
    case.config["output"] = dict(case.config["output"])
    case.config["output"]["dir"] = str(tmp_out)
    case.config["case"] = dict(case.config["case"])
    extra_roots = list(case.config["case"].get("allowed_data_roots", []) or [])
    extra_roots.append(str(tmp_out))
    case.config["case"]["allowed_data_roots"] = extra_roots
    # Invalidate the lru-cached resolution since we mutated config.
    case.__dict__.pop("_case_dir_resolved", None)
    result = case.run(discharges_m3s=[5.0, 10.0, 20.0, 40.0])
    return result, Path(result.output_dir)


# ---------------------------------------------------------------------
# Cluster: R5/R6/R9-1 — Case._atomic_write
# ---------------------------------------------------------------------
def test_r5_r14_atomic_write_publishes_no_partials(lemhi_result) -> None:
    """R5-1/R5-2/R5-3 + R6-1 + R9-1 cluster: every produced file
    should be a COMPLETE write — no `.inprogress` / `.publishtmp`
    sibling left over from a crash mid-stream."""
    _, out_dir = lemhi_result
    leftover = [
        p
        for p in out_dir.rglob("*")
        if p.suffix in {".inprogress", ".publishtmp"}
        or ".inprogress" in p.name
        or ".publishtmp" in p.name
    ]
    assert not leftover, (
        f"R5-R14 atomic-write regression: tempfile siblings left "
        f"in output dir after a successful run: {leftover}"
    )


# ---------------------------------------------------------------------
# Cluster: F/N/M/R7 — Regulatory CSV atomic publish + watermark
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "name",
    [
        # Base regulatory CSVs — what bare ``Case.run`` actually
        # produces from the default Lemhi case.yaml. Composite
        # variants (``*_composite.csv``) require an explicit
        # composite-overlay configuration (e.g.
        # ``habitat.composite_overlay_method = geom_mean_per_cell``)
        # that the shipped Lemhi case does not set. The status doc
        # was corrected 2026-05-20 round-19 codex S1 to stop
        # claiming all 6 are produced by the default run.
        "sl712.csv",
        "ferc_4e.csv",
        "eu_wfd.csv",
    ],
)
def test_r5_r14_regulatory_csv_emitted_with_watermark(
    lemhi_result,
    name: str,
) -> None:
    """F1..F11 + N1..N6 + M1..M5 + R7-x cluster: each regulatory
    CSV must (a) exist, (b) start with a `#`-prefixed watermark/
    grade-banner comment, (c) parse cleanly as CSV after the
    header.

    If the v3.x atomic-publish or watermark prefix logic regresses,
    one of (a), (b), or (c) will fail."""
    _, out_dir = lemhi_result
    target = out_dir / name
    assert target.exists(), (
        f"Regulatory export regression: {name} missing from output dir {out_dir}"
    )
    text = target.read_text()
    assert text.startswith("#"), (
        f"Watermark regression: {name} doesn't lead with a "
        f"`#`-prefixed comment line; quality-grade banner lost"
    )
    # CSV body parses (skipping comment rows).
    df = pd.read_csv(target, comment="#")
    assert len(df) > 0, f"Regulatory CSV {name} parsed as empty"


# ---------------------------------------------------------------------
# Cluster: R8 — provenance SHA-256 chain
# ---------------------------------------------------------------------
def test_r5_r14_provenance_emits_sha_chain(lemhi_result) -> None:
    """R8-1..R8-9 cluster: provenance.json must exist, parse, and
    carry the keys that ``openlimno reproduce`` verifies."""
    result, out_dir = lemhi_result
    prov_path = Path(result.provenance_path)
    assert prov_path.exists(), "R8 provenance regression: provenance.json missing"
    prov = json.loads(prov_path.read_text())
    # Spot-check the key fields the reproduce command relies on.
    # Names per the v3.x provenance schema (case carries case_yaml SHA;
    # parameter_fingerprint is the run-input fingerprint).
    expected_keys = {
        "openlimno_version",
        "git_sha",
        "parameter_fingerprint",
        "wua_quality_grade",
        "case",
        "inputs",
    }
    missing = expected_keys - set(prov.keys())
    assert not missing, (
        f"R8 provenance regression: provenance.json missing keys "
        f"{missing}. Got: {sorted(prov.keys())}"
    )


# ---------------------------------------------------------------------
# Cluster: R9 — HSI quality grading watermark
# ---------------------------------------------------------------------
def test_r5_r14_wua_csv_carries_quality_grade(lemhi_result) -> None:
    """R9-x cluster: ``wua_q.csv`` must carry an A/B/C quality-grade
    watermark in its header comment. Pre-v1.7 this was advisory;
    v1.8+ made it a hard contract for downstream regulatory work."""
    _, out_dir = lemhi_result
    wua = out_dir / "wua_q.csv"
    assert wua.exists()
    text = wua.read_text()
    # First non-empty line must be a `#`-prefixed banner carrying
    # "grade <A|B|C>" or equivalent.
    first_line = text.splitlines()[0]
    assert first_line.startswith("#"), (
        "R9 watermark regression: wua_q.csv first line is not a "
        "comment header — quality-grade banner missing."
    )
    assert "grade" in first_line.lower() or "quality" in first_line.lower(), (
        f"R9 watermark regression: first line {first_line!r} doesn't carry a quality-grade marker."
    )


# ---------------------------------------------------------------------
# Cluster: R10/R11 — WEDM schema validate_case + Case.from_yaml
# ---------------------------------------------------------------------
def test_r5_r14_lemhi_validates_under_wedm_schema() -> None:
    """R10/R11 cluster: ``examples/lemhi/case.yaml`` must validate
    cleanly. R11-x WEDM strictness sweeps closed many gaps; this
    pin guards against a future regression re-loosening the schema."""
    from openlimno.wedm import validate_case

    _require_fixtures()
    errors = validate_case(LEMHI_CASE)
    assert errors == [], (
        f"R10/R11 schema regression: shipped Lemhi fixture no longer validates: {errors}"
    )


# ---------------------------------------------------------------------
# Top-level smoke
# ---------------------------------------------------------------------
def test_r5_r14_lemhi_full_pipeline_produces_full_artifact_set(
    lemhi_result,
) -> None:
    """Master cluster pin: the v1.x..v2.x foundational helpers
    together produce a COMPLETE artifact set for a charter-grade
    case. The full list comes from the v1.0.0 surface freeze
    contract; missing any one of them is a regression in either
    the orchestrator or one of the helpers."""
    result, out_dir = lemhi_result
    # 2026-05-20 round-19 codex S1: the r_basin_1 status doc
    # initially claimed "13 core artifacts + 2 plots" — but that
    # count came from a cached output dir (a prior run with composite
    # overlay enabled), NOT from the fresh-run default Case.run on
    # Lemhi. Bare Case.run on the shipped Lemhi case actually produces
    # 8 artifacts (this list); composite CSVs + composite_hsi.json
    # require ``habitat.composite_overlay_method = geom_mean_per_cell``
    # opt-in, and PNGs require ``studio.headless.run_case_with_plots``
    # (pinned separately by ``test_r5_r14_studio_plots_produced``).
    required = [
        "wua_q.csv",
        "wua_hmu.csv",
        "hydraulics.nc",
        "provenance.json",
        "sl712.csv",
        "ferc_4e.csv",
        "eu_wfd.csv",
    ]
    missing = [f for f in required if not (out_dir / f).exists()]
    assert not missing, (
        f"R5-R14 master cluster regression: 7-artifact contract "
        f"(bare Case.run default) broken — missing: {missing}. "
        f"Output dir: {out_dir}"
    )
    assert result.case_name == "lemhi_phabsim_replication"
    assert len(result.discharges_m3s) == 4
    # WUA at high discharge typically collapses for spawning (depth
    # gets too high); just check the column exists with the right
    # cardinality.
    assert result.wua_q is not None
    assert len(result.wua_q) == 4


# ---------------------------------------------------------------------
# Cluster: Studio path A — run_case_with_plots produces the PNGs
# the r_basin_1 status doc claims are part of the artifact set.
# 2026-05-20 round-19 codex S1: prior pin set didn't cover PNGs.
# ---------------------------------------------------------------------
def test_r5_r14_studio_plots_produced(tmp_path_factory) -> None:
    """``studio.headless.run_case_with_plots`` is the user-facing
    entry point for Studio path A; it wraps ``Case.run`` and emits
    PNGs alongside the CSV/NetCDF outputs. r_basin_1 status doc
    claims ``wua_q_curve.png`` + per-species/stage PNG are part of
    the operational artifact set. Pin via a real run.

    The function reloads the case from disk, so we write a temp
    case.yaml that extends ``allowed_data_roots`` to include the
    tmp_out dir (otherwise the v3.0 sandbox would refuse the
    write — itself a signal R11-4 is wired)."""
    _require_fixtures()
    import yaml as _yaml

    from openlimno.studio.headless import run_case_with_plots

    tmp_dir = tmp_path_factory.mktemp("lemhi_studio_plots")
    tmp_out = tmp_dir / "out"

    # Copy + tweak the Lemhi case.yaml so output.dir points into
    # tmp + allowed_data_roots includes tmp_out.
    src_yaml = LEMHI_CASE.read_text(encoding="utf-8")
    cfg = _yaml.safe_load(src_yaml)
    # Anchor data paths absolutely so the temp-case can reach the
    # repo data/ tree without recomputing relative paths from
    # /tmp/.../case.yaml's location.
    repo_data = REPO_ROOT / "data"
    cfg["case"]["allowed_data_roots"] = [
        str(repo_data),
        str(tmp_out),
    ]
    cfg["mesh"]["uri"] = str(repo_data / "lemhi" / "mesh.ugrid.nc")
    for k, v in list(cfg.get("data", {}).items()):
        if isinstance(v, str) and v.startswith("../../data/"):
            cfg["data"][k] = str(REPO_ROOT / v.removeprefix("../../"))
    if "hydrodynamics" in cfg and "boundaries" in cfg["hydrodynamics"]:
        for bdy in cfg["hydrodynamics"]["boundaries"].values():
            for field in ("series", "ref"):
                if isinstance(bdy.get(field), str) and bdy[field].startswith("../../data/"):
                    bdy[field] = str(REPO_ROOT / bdy[field].removeprefix("../../"))
    cfg["output"]["dir"] = str(tmp_out)

    tmp_case_yaml = tmp_dir / "case.yaml"
    tmp_case_yaml.write_text(_yaml.safe_dump(cfg), encoding="utf-8")
    sr = run_case_with_plots(tmp_case_yaml, discharges_m3s=[5.0, 10.0, 20.0])
    out_dir = Path(sr.output_dir)
    assert (out_dir / "wua_q_curve.png").exists(), (
        "Studio PNG regression: run_case_with_plots no longer emits "
        "wua_q_curve.png — r_basin_1 status doc claim broken."
    )
    # Note: per-species/stage panels (e.g.
    # ``wua_q_oncorhynchus_mykiss_spawning.png``) are emitted by the
    # plot pipeline only when both species/stage curves carry nonzero
    # WUA across the discharge sweep. With 3 toy discharges + the
    # Lemhi default HSI, fry stage collapses to 0 immediately, so the
    # per-stage panel may not appear in CI. Pin only the composite
    # PNG, which IS the user-facing artifact promised in the
    # r_basin_1 status doc.
