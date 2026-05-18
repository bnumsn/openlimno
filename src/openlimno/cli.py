"""OpenLimno command-line interface.

SPEC §8.2. Subcommands stub-implemented in M0; real functionality lands in M1+.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="openlimno")
def main() -> None:
    """OpenLimno: ecological-flow and fish-habitat decision platform.

    Connects field data, hydraulic-model outputs, habitat suitability, passage
    analysis, provenance, and regulatory reporting.
    """


@main.command()
@click.argument("project_name")
@click.option("--basin", default="my-basin", help="Basin name for documentation")
def init(project_name: str, basin: str) -> None:
    """Initialise a new OpenLimno project directory.

    Creates a skeleton case.yaml + studyplan.yaml + data/ directory.
    """
    from textwrap import dedent

    target = Path(project_name)
    if target.exists():
        console.print(f"[red]✗[/] {target} already exists")
        sys.exit(1)
    target.mkdir(parents=True)
    (target / "data").mkdir()

    case_yaml = dedent(f"""\
        openlimno: '0.1'

        case:
          name: {project_name}
          description: |
            New OpenLimno case for {basin}.
            Replace data paths with your actual cross-section + HSI files.
          crs: EPSG:32612

        mesh:
          uri: data/mesh.ugrid.nc

        data:
          cross_section: data/cross_section.parquet
          hsi_curve: data/hsi_curve.parquet

        hydrodynamics:
          backend: builtin-1d
          builtin_1d:
            scheme: preissmann

        habitat:
          species: [TARGET_SPECIES_HERE]
          stages: [spawning]
          metric: wua-q
          composite: min                  # avoids HSI independence assumption

        output:
          dir: ./out/
          formats: [netcdf, csv]
        """)
    (target / "case.yaml").write_text(case_yaml)

    studyplan = dedent(f"""\
        problem_statement: |
          State the management problem this study addresses for {basin}.
          Min 50 characters required.

        target_species_rationale:
          - species: TARGET_SPECIES_HERE
            rationale: "Why this species, why these stages"

        objective_variables: [wua-q, persistent_habitat]
        """)
    (target / "studyplan.yaml").write_text(studyplan)

    (target / "README.md").write_text(
        f"# {project_name}\n\nOpenLimno case directory.\n\n"
        f"Edit `case.yaml` and `studyplan.yaml`, supply data files in `data/`,\n"
        f"then run `openlimno run case.yaml`.\n"
    )
    console.print(f"[green]✓[/] {target}/ created with case + studyplan + data/")
    console.print(f"  Edit {target}/case.yaml + {target}/studyplan.yaml")
    console.print(f"  Run:  cd {target} && openlimno run case.yaml")


@main.command()
@click.argument("case_yaml", type=click.Path(exists=True))
def validate(case_yaml: str) -> None:
    """Validate a case YAML against WEDM JSON-Schema."""
    from openlimno.wedm import validate_case

    errors = validate_case(case_yaml)
    if errors:
        for err in errors:
            console.print(f"[red]✗[/] {err}")
        sys.exit(1)
    console.print(f"[green]✓[/] {case_yaml} validates against WEDM 0.1")


@main.command()
@click.argument("case_yaml", type=click.Path(exists=True))
@click.option(
    "--executor",
    type=click.Choice(["local"]),
    default="local",
    help="v1.x/2.x supports only local; HPC/cloud per SPEC §13",
)
@click.option("--manning-n", default=0.035, type=float, help="Channel roughness")
@click.option("--slope", default=0.002, type=float, help="Bed slope")
def run(case_yaml: str, executor: str, manning_n: float, slope: float) -> None:
    """Run a case end-to-end (M1: builtin-1d hydraulics + cell WUA-Q)."""
    from openlimno.case import Case

    case = Case.from_yaml(case_yaml)
    result = case.run(manning_n=manning_n, slope=slope)
    console.print(f"[green]✓[/] {result.summary()}")
    console.print(f"  WUA-Q rows: {len(result.wua_q)}")
    console.print(f"  provenance: {result.provenance_path}")
    if result.warnings:
        console.print(f"[yellow]  {len(result.warnings)} warnings:[/]")
        for w in result.warnings[:5]:
            console.print(f"    - {w}")


@main.command()
@click.argument("case_yaml", type=click.Path(exists=True))
@click.option("--species", required=True)
@click.option("--stage", required=True)
@click.option("--plot/--no-plot", default=False)
@click.option("--n-q", default=12, type=int, help="Number of discharges to sweep")
def wua(case_yaml: str, species: str, stage: str, plot: bool, n_q: int) -> None:
    """Compute WUA-Q curve for given species/stage.

    Runs the case at log-spaced discharges and prints the WUA column for the
    target (species, stage) plus optional PNG plot.
    """
    import numpy as np

    from openlimno.case import Case

    case = Case.from_yaml(case_yaml)
    Qs = list(np.logspace(0, np.log10(30), n_q))
    result = case.run(discharges_m3s=Qs)
    col = f"wua_m2_{species}_{stage}"
    if col not in result.wua_q.columns:
        console.print(
            f"[red]✗[/] no WUA column for ({species}, {stage}); "
            f"available: {[c for c in result.wua_q.columns if c.startswith('wua_m2_')]}"
        )
        sys.exit(1)
    df_show = result.wua_q[["discharge_m3s", col]].rename(columns={col: "wua_m2"})
    console.print(df_show.to_string(index=False))

    if plot:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(df_show["discharge_m3s"], df_show["wua_m2"], "o-", lw=2)
        ax.set_xscale("log")
        ax.set_xlabel("Discharge (m³/s)")
        ax.set_ylabel("WUA (m²)")
        ax.set_title(f"{case.name}: {species} / {stage}")
        ax.grid(True, alpha=0.3)
        png = result.output_dir / f"wua_q_{species}_{stage}.png"
        fig.tight_layout()
        # v1.9.2 (5th-review R5-3): atomic publish for the WUA-Q plot
        # so the CLI's --plot output inherits the same atomic+umask
        # contract as the rest of the OpenLimno output suite.
        from openlimno.case import Case
        Case._atomic_write(png, lambda p: fig.savefig(p, dpi=120))
        console.print(f"[green]✓[/] plot saved: {png}")


@main.command("wua-cells")
@click.option(
    "--cells",
    "cells_path",
    type=click.Path(exists=True),
    required=True,
    help="Hydraulic-cell table from `preprocess import-model` (.csv/.parquet).",
)
@click.option(
    "--hsi",
    "hsi_path",
    type=click.Path(exists=True),
    required=True,
    help="WEDM hsi_curve.parquet.",
)
@click.option("--species", required=True)
@click.option("--stage", required=True)
@click.option(
    "--composite",
    type=click.Choice(["geometric_mean", "arithmetic_mean", "min", "weighted_geometric"]),
    default="min",
    help="Composite CSI method; min avoids the HSI independence assumption.",
)
@click.option(
    "--acknowledge-independence",
    is_flag=True,
    help="Required for geometric/arithmetic mean composites.",
)
@click.option(
    "--out-dir",
    type=click.Path(),
    required=True,
    help="Directory for habitat_cells, wua_summary, and wua_hmu outputs.",
)
@click.option("--format", "output_format", type=click.Choice(["csv", "parquet"]), default="csv")
def wua_cells(
    cells_path: str,
    hsi_path: str,
    species: str,
    stage: str,
    composite: str,
    acknowledge_independence: bool,
    out_dir: str,
    output_format: str,
) -> None:
    """Evaluate habitat directly from imported hydraulic-cell tables."""
    import pandas as pd

    from openlimno.habitat import evaluate_habitat_cells, load_hsi_from_parquet

    src = Path(cells_path)
    if src.suffix.lower() == ".parquet":
        cells = pd.read_parquet(src)
    else:
        cells = pd.read_csv(src, comment="#")
    curves = load_hsi_from_parquet(hsi_path)
    result = evaluate_habitat_cells(
        cells,
        curves,
        species=species,
        life_stage=stage,
        composite=composite,  # type: ignore[arg-type]
        acknowledge_independence=acknowledge_independence,
    )

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    outputs = {
        "habitat_cells": result.cells,
        "wua_summary": result.summary,
        "wua_hmu": result.hmu_summary,
    }
    for stem, df in outputs.items():
        target = out / f"{stem}.{output_format}"
        if output_format == "parquet":
            df.to_parquet(target, index=False)
        else:
            df.to_csv(target, index=False)

    total_wua = float(result.summary["wua_m2"].sum()) if "wua_m2" in result.summary else 0.0
    console.print(
        f"[green]✓[/] evaluated {len(result.cells)} cells for {species}/{stage}; "
        f"total WUA={total_wua:.3f} m²"
    )
    console.print(f"  outputs: {out}")


@main.command("ibm-export")
@click.option(
    "--cells",
    "cells_path",
    type=click.Path(exists=True),
    required=True,
    help="OpenLimno hydraulic/habitat cell table (.csv/.parquet).",
)
@click.option(
    "--target",
    type=click.Choice(["instream-netlogo"]),
    default="instream-netlogo",
    show_default=True,
    help="IBM exchange target.",
)
@click.option("--scenario-id", default="baseline", show_default=True)
@click.option("--reach-id", default="reach-1", show_default=True)
@click.option("--out-dir", type=click.Path(), required=True)
def ibm_export(
    cells_path: str,
    target: str,
    scenario_id: str,
    reach_id: str,
    out_dir: str,
) -> None:
    """Export OpenLimno habitat cells to a population-model exchange package."""
    import pandas as pd

    from openlimno.preprocess import write_instream_exchange

    if target != "instream-netlogo":  # pragma: no cover - guarded by click
        raise click.UsageError(f"Unsupported IBM target: {target}")
    src = Path(cells_path)
    if src.suffix.lower() == ".parquet":
        cells = pd.read_parquet(src)
    else:
        cells = pd.read_csv(src, comment="#")

    result = write_instream_exchange(
        cells,
        out_dir,
        scenario_id=scenario_id,
        reach_id=reach_id,
    )
    console.print(
        f"[green]✓[/] wrote {target} exchange package: "
        f"{len(result.habitat_cells)} cells, {len(result.flow_summary)} summary rows"
    )
    for name, path in (result.paths or {}).items():
        console.print(f"  {name}: {path}")


@main.command()
@click.option(
    "--culvert",
    type=click.Path(exists=True),
    required=True,
    help="Culvert YAML config (geometry + material)",
)
@click.option(
    "--swim",
    "swim_path",
    type=click.Path(exists=True),
    required=True,
    help="swimming_performance.parquet",
)
@click.option("--species", required=True)
@click.option("--stage", default="adult")
@click.option(
    "--discharge", "Q", type=float, required=True, help="Discharge through culvert (m³/s)"
)
@click.option("--temp", "T", type=float, default=12.0)
@click.option(
    "--monte-carlo",
    "n_mc",
    type=int,
    default=0,
    help="Number of Monte Carlo samples (0 = deterministic)",
)
@click.option(
    "--attraction-eta",
    type=float,
    default=1.0,
    help="η_A user input (ADR-0007); 1.0 = no attraction effect",
)
def passage(
    culvert: str,
    swim_path: str,
    species: str,
    stage: str,
    Q: float,
    T: float,
    n_mc: int,
    attraction_eta: float,
) -> None:
    """Compute fish passage success rate (η_P) for a culvert.

    See SPEC §4.3 / ADR-0007 on η_A vs η_P decomposition.
    """
    import yaml as _yaml

    from openlimno.passage import (
        Culvert,
        load_swimming_model_from_parquet,
        passage_success_rate,
    )

    cv_cfg = _yaml.safe_load(Path(culvert).read_text())
    cv = Culvert(**{k: v for k, v in cv_cfg.items() if k != "attraction_efficiency"})
    swim = load_swimming_model_from_parquet(swim_path, species, stage)  # type: ignore[arg-type]
    res = passage_success_rate(cv, swim, discharge_m3s=Q, temp_C=T, monte_carlo=n_mc, seed=42)

    eta_total = attraction_eta * res.eta_P
    console.print(res.summary())
    console.print(f"  η_A (user input): {attraction_eta:.2f}  → η = η_A × η_P = {eta_total:.3f}")


@main.command()
@click.argument("case_yaml", type=click.Path(exists=True))
@click.option(
    "--observed",
    type=click.Path(exists=True),
    required=True,
    help="Rating curve Parquet/CSV with columns h_m, Q_m3s",
)
@click.option(
    "--algo",
    default="scipy",
    type=click.Choice(["scipy", "pestpp-glm"]),
    help="scipy = built-in 1-parameter; pestpp-glm = multi-parameter (v3.x research route)",
)
@click.option("--initial-n", default=0.035, type=float)
@click.option("--slope", default=0.002, type=float)
def calibrate(case_yaml: str, observed: str, algo: str, initial_n: float, slope: float) -> None:
    """Calibrate Manning's n against an observed rating curve.

    v2.x: scipy-based 1-parameter; PEST++ multi-parameter on the v3.x
    research route.
    """
    import pandas as pd

    if algo == "pestpp-glm":
        raise NotImplementedError(
            "PEST++ multi-parameter calibration is on the v3.x research route"
        )

    from openlimno.case import Case
    from openlimno.hydro.builtin_1d import load_sections_from_parquet
    from openlimno.workflows import calibrate_manning_n

    case = Case.from_yaml(case_yaml)
    cross_section_path = case._resolve(case.config["data"]["cross_section"])
    sections = load_sections_from_parquet(cross_section_path, manning_n=initial_n)
    if not sections:
        console.print("[red]✗[/] no cross-sections found in case data")
        sys.exit(1)

    obs_path = Path(observed)
    if obs_path.suffix == ".parquet":
        obs = pd.read_parquet(obs_path)
    else:
        obs = pd.read_csv(obs_path)

    res = calibrate_manning_n(
        cross_section=sections[0],
        observed_rating=obs,
        slope=slope,
        initial_n=initial_n,
    )
    console.print(
        f"[green]✓[/] Manning n: {res.initial_value:.4f} → "
        f"{res.calibrated_value:.4f}  "
        f"(RMSE: {res.rmse_initial:.3f} → {res.rmse_final:.3f} m³/s)"
    )


@main.command()
@click.argument("provenance_json", type=click.Path(exists=True))
@click.option(
    "--check-only/--rerun",
    default=True,
    help="check-only verifies SHA-256 fingerprints; rerun re-executes",
)
def reproduce(provenance_json: str, check_only: bool) -> None:
    """Reproduce a previous run from its provenance.json.

    Default mode (--check-only): verifies that all input files referenced by
    the provenance still match their recorded SHA-256, plus the case YAML.
    --rerun: re-executes the case at the recorded discharges and writes a
    fresh provenance for comparison.
    """
    import hashlib
    import json

    prov = json.loads(Path(provenance_json).read_text())
    case_yaml = Path(prov["case"]["yaml_path"])
    if not case_yaml.exists():
        console.print(f"[red]✗[/] case yaml missing: {case_yaml}")
        sys.exit(1)

    # Verify YAML SHA
    actual = hashlib.sha256(case_yaml.read_bytes()).hexdigest()
    expected = prov["case"]["yaml_sha256"]
    if actual != expected:
        console.print(f"[red]✗[/] case YAML drift: {expected[:12]} → {actual[:12]}")
    else:
        console.print("[green]✓[/] case YAML SHA matches")

    # Verify input data SHAs
    for label, sha in prov["inputs"].get("input_data_sha256", {}).items():
        # Note: the path is not stored explicitly; we use the case data section
        from openlimno.case import Case

        case = Case.from_yaml(case_yaml)
        data_path = case._resolve(case.config.get("data", {}).get(label, ""))
        if not data_path.exists():
            console.print(f"[yellow]?[/] {label}: data file missing {data_path}")
            continue
        actual_sha = hashlib.sha256(Path(data_path).read_bytes()).hexdigest()
        if actual_sha != sha:
            console.print(f"[red]✗[/] {label} drift: {sha[:12]} → {actual_sha[:12]}")
        else:
            console.print(f"[green]✓[/] {label} SHA matches")

    # v0.3 P0: verify external-source SHAs (auto-fetched datasets)
    external = prov.get("external_sources", [])
    if external:
        console.print(f"\n[bold]External sources ({len(external)}):[/]")
        for rec in external:
            label = rec.get("label", "?")
            stype = rec.get("source_type", "?")
            produced = rec.get("produced_file", "")
            url = rec.get("source_url", "")
            ftime = rec.get("fetch_time", "")
            expected_sha = rec.get("produced_sha256", "")
            file_path = case_yaml.parent / produced
            if not file_path.exists():
                console.print(
                    f"  [yellow]?[/] {label} ({stype}): file missing {produced}"
                )
                continue
            actual_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                console.print(
                    f"  [red]✗[/] {label} ({stype}) drift: "
                    f"{expected_sha[:12]}… → {actual_sha[:12]}…"
                )
            else:
                console.print(
                    f"  [green]✓[/] {label} ({stype}) — {produced} "
                    f"SHA matches  ↳ origin: {url}  ({ftime})"
                )

    if check_only:
        return

    from openlimno.case import Case

    case = Case.from_yaml(case_yaml)
    discharges = prov["inputs"]["discharges_m3s"]
    result = case.run(discharges_m3s=discharges)
    console.print(f"[green]✓[/] re-executed: {result.summary()}")
    console.print(f"  fresh provenance: {result.provenance_path}")


@main.group()
def studyplan() -> None:
    """IFIM study plan helpers (SPEC §4.4)."""


@studyplan.command("init")
@click.argument("output_path", type=click.Path())
@click.option("--problem", default=None, help="One-line problem statement")
@click.option(
    "--species", multiple=True, default=("oncorhynchus_mykiss",), help="Target species (repeatable)"
)
@click.option("--interactive/--non-interactive", default=False)
def studyplan_init(
    output_path: str, problem: str | None, species: tuple[str, ...], interactive: bool
) -> None:
    """Generate a studyplan.yaml.

    Non-interactive (default): writes a templated studyplan with the supplied
    species and problem statement. Use ``--interactive`` to be prompted for
    each field.
    """
    import yaml as _yaml

    out = Path(output_path)
    if out.exists():
        console.print(f"[red]✗[/] {out} already exists")
        sys.exit(1)

    if interactive:
        problem = click.prompt(
            "Problem statement (≥50 chars)",
            default="Establish ecological flow recommendations for ...",
        )

    if problem is None or len(problem) < 50:
        problem = (
            "Establish minimum and suitable ecological flow recommendations "
            "for this reach, supporting native species. EDIT THIS BLOCK."
        )

    plan = {
        "problem_statement": problem,
        "target_species_rationale": [
            {"species": sp, "rationale": "EDIT: why this species"} for sp in species
        ],
        "objective_variables": ["wua-q", "persistent_habitat"],
        "uncertainty_sources_acknowledged": [
            "hsi_uncertainty",
            "transferability",
            "measurement_error",
        ],
    }
    out.write_text(_yaml.safe_dump(plan, sort_keys=False, allow_unicode=True))
    console.print(f"[green]✓[/] {out} created")
    console.print(f"  Validate: openlimno studyplan validate {out}")


@studyplan.command("validate")
@click.argument("yaml_file", type=click.Path(exists=True))
def studyplan_validate(yaml_file: str) -> None:
    """Validate a studyplan.yaml."""
    from openlimno.wedm import validate_studyplan

    errors = validate_studyplan(yaml_file)
    if errors:
        for err in errors:
            console.print(f"[red]✗[/] {err}")
        sys.exit(1)
    console.print(f"[green]✓[/] {yaml_file} validates against studyplan schema")


@studyplan.command("report")
@click.argument("yaml_file", type=click.Path(exists=True))
def studyplan_report(yaml_file: str) -> None:
    """Print a human-readable report from a studyplan.yaml."""
    from openlimno.studyplan import StudyPlan

    sp = StudyPlan.from_yaml(yaml_file)
    console.print(sp.report())


@main.group()
def hsi() -> None:
    """HSI curve management (SPEC §4.2.2)."""


@hsi.command("upgrade")
@click.argument("parquet_file", type=click.Path(exists=True))
@click.option(
    "--out",
    "output_path",
    type=click.Path(),
    required=False,
    help="Output path; defaults to overwriting input",
)
@click.option(
    "--set-grade", type=click.Choice(["A", "B", "C"]), help="Bulk-set quality_grade for all curves"
)
@click.option("--set-origin", help="Bulk-set geographic_origin for all curves")
@click.option(
    "--set-transferability", type=float, help="Bulk-set transferability_score for all curves"
)
@click.option(
    "--mark-independence-tested/--unmark", default=None, help="Set independence_tested true/false"
)
@click.option("--interactive/--non-interactive", default=False)
def hsi_upgrade(
    parquet_file: str,
    output_path: str | None,
    set_grade: str | None,
    set_origin: str | None,
    set_transferability: float | None,
    mark_independence_tested: bool | None,
    interactive: bool,
) -> None:
    """Upgrade HSI metadata in a Parquet file (ADR-0006 / SPEC §4.2.2.3).

    Non-interactive: bulk-applies the --set-* flags. Interactive: prompts per
    curve. The default writes back to the same file (with a `.bak` backup).
    """
    import pandas as pd

    df = pd.read_parquet(parquet_file)
    n_changed = 0

    if interactive:
        for i in df.index:
            curve_id = f"{df.loc[i, 'species']}/{df.loc[i, 'life_stage']}/{df.loc[i, 'variable']}"
            console.print(f"[bold]{curve_id}[/]  current grade={df.loc[i, 'quality_grade']}")
            new_grade = click.prompt(
                "  new grade (A/B/C, blank=keep)",
                default=str(df.loc[i, "quality_grade"]),
                show_default=False,
            )
            if new_grade != df.loc[i, "quality_grade"]:
                df.at[i, "quality_grade"] = new_grade
                n_changed += 1
    else:
        if set_grade:
            df["quality_grade"] = set_grade
            n_changed = len(df)
        if set_origin:
            df["geographic_origin"] = set_origin
        if set_transferability is not None:
            df["transferability_score"] = set_transferability
        if mark_independence_tested is not None:
            df["independence_tested"] = mark_independence_tested

    target = Path(output_path) if output_path else Path(parquet_file)
    if not output_path:
        Path(parquet_file).rename(Path(parquet_file).with_suffix(".parquet.bak"))
    df.to_parquet(target, index=False)
    console.print(f"[green]✓[/] {n_changed} curves modified → {target}")


@main.group()
def preprocess() -> None:
    """Preprocess external data into WEDM (SPEC §4.0)."""


@preprocess.command("xs")
@click.option("--in", "input_path", type=click.Path(exists=True), required=True)
@click.option("--out", "output_path", type=click.Path(), required=True)
@click.option("--campaign-id", default=None, help="Survey campaign UUID (auto if omitted)")
def preprocess_xs(input_path: str, output_path: str, campaign_id: str | None) -> None:
    """Import cross-section CSV/Excel."""
    from openlimno.preprocess import read_cross_sections, write_cross_sections_to_parquet

    df = read_cross_sections(input_path, campaign_id=campaign_id)
    write_cross_sections_to_parquet(df, output_path, source_note=f"imported from {input_path}")
    console.print(
        f"[green]✓[/] {len(df)} rows from {len(df['station_m'].unique())} stations → {output_path}"
    )


@preprocess.command("adcp")
@click.option("--in", "input_path", type=click.Path(exists=True), required=True)
@click.option("--out", "output_path", type=click.Path(), required=True)
@click.option("--campaign-id", default=None)
def preprocess_adcp(input_path: str, output_path: str, campaign_id: str | None) -> None:
    """Import USGS QRev CSV ADCP transect."""
    from openlimno.preprocess import read_adcp_qrev

    df = read_adcp_qrev(input_path, campaign_id=campaign_id)
    df.to_parquet(output_path, index=False)
    console.print(f"[green]✓[/] {len(df)} ensembles → {output_path}")


@preprocess.command("dem-info")
@click.argument("dem_path", type=click.Path(exists=True))
def preprocess_dem_info(dem_path: str) -> None:
    """Print DEM summary (rows, cols, CRS, bounds)."""
    from openlimno.preprocess import read_dem

    dem = read_dem(dem_path)
    console.print(f"DEM {dem_path}")
    console.print(f"  shape: {dem.shape[0]} rows × {dem.shape[1]} cols")
    console.print(f"  CRS:   {dem.crs}")
    if dem.bounds:
        console.print(f"  bounds: {dem.bounds}")
    console.print(f"  elev range: {dem.elevation.min():.2f} – {dem.elevation.max():.2f}")


@preprocess.command("import-model")
@click.option(
    "--source",
    type=click.Choice(
        [
            "auto",
            "hecras-geometry",
            "river2d-cdg",
            "hecras-hdf",
            "telemac-slf",
            "delft3d-netcdf",
            "mike-dfs",
            "mike-1d",
            "habby-csv",
            "instream-netlogo",
        ]
    ),
    default="auto",
    help="External model/source family. Planned entries report roadmap status.",
)
@click.option("--in", "input_path", type=click.Path(exists=True), required=False)
@click.option("--out", "output_path", type=click.Path(), required=False)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["csv", "parquet"]),
    default=None,
    help="Output table format. Defaults from --out suffix.",
)
@click.option("--flow-area", default=None, help="HEC-RAS 2D flow-area name for HDF imports.")
@click.option(
    "--time-index",
    type=int,
    default=None,
    help="Time index for time-varying result imports; default is last time step.",
)
@click.option("--list-supported", is_flag=True, help="List implemented/planned import paths.")
def preprocess_import_model(
    source: str,
    input_path: str | None,
    output_path: str | None,
    output_format: str | None,
    flow_area: str | None,
    time_index: int | None,
    list_supported: bool,
) -> None:
    """Import or inspect external ecohydraulic model files.

    This is the interop entry point for the "OpenLimno as ecological
    post-processing hub" workflow: bring existing HEC-RAS/River2D/etc. model
    assets into WEDM staging tables, then run habitat / passage / reporting.
    """
    from rich.table import Table

    from openlimno.preprocess import list_external_model_support, read_external_model

    if list_supported:
        table = Table(title="OpenLimno external model interoperability")
        table.add_column("key", no_wrap=True)
        table.add_column("model")
        table.add_column("input")
        table.add_column("status")
        table.add_column("extensions")
        for entry in list_external_model_support():
            table.add_row(
                entry.key,
                entry.model,
                entry.input_kind,
                entry.status,
                ", ".join(entry.extensions),
            )
        console.print(table)
        return

    if input_path is None or output_path is None:
        raise click.UsageError("--in and --out are required unless --list-supported is set.")

    result = read_external_model(
        input_path,
        source=source,
        flow_area=flow_area,
        time_index=time_index,
    )
    out = Path(output_path)
    fmt = output_format
    if fmt is None:
        suffix = out.suffix.lower()
        if suffix == ".parquet":
            fmt = "parquet"
        elif suffix == ".csv":
            fmt = "csv"
        else:
            raise click.UsageError("--out must end in .csv/.parquet or pass --format.")

    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "parquet":
        result.table.to_parquet(out, index=False)
    else:
        result.table.to_csv(out, index=False)

    console.print(
        f"[green]✓[/] imported {result.model} {result.input_kind}: "
        f"{len(result.table)} rows → {out}"
    )
    for warning in result.warnings:
        console.print(f"[yellow]⚠[/] {warning}")


@preprocess.command("river2d-ugrid")
@click.option("--in", "input_path", type=click.Path(exists=True), required=True)
@click.option("--out", "output_path", type=click.Path(), required=True)
def preprocess_river2d_ugrid(input_path: str, output_path: str) -> None:
    """Convert a River2D .cdg/.bed mesh to UGRID NetCDF."""
    from openlimno.preprocess import validate_ugrid_mesh, write_river2d_ugrid

    out = write_river2d_ugrid(input_path, output_path)
    report = validate_ugrid_mesh(out)
    if not report.is_valid:
        message = "; ".join(report.errors) or "UGRID validation failed"
        raise click.ClickException(message)
    console.print(
        f"[green]✓[/] wrote River2D UGRID mesh: {report.n_nodes} nodes, "
        f"{report.n_faces} faces → {out}"
    )
    for warning in report.warnings:
        console.print(f"[yellow]⚠[/] {warning}")


@preprocess.command("diagnose-model")
@click.option(
    "--source",
    type=click.Choice(["mike-dfs", "mike-1d"]),
    required=True,
    help="Optional external model reader stack to diagnose.",
)
@click.option("--strict", is_flag=True, help="Exit non-zero when the reader stack is not ready.")
def preprocess_diagnose_model(source: str, strict: bool) -> None:
    """Diagnose optional external-model reader dependencies."""
    from rich.markup import escape
    from rich.table import Table

    from openlimno.preprocess import diagnose_mike_environment

    diagnostic = diagnose_mike_environment(source)
    summary = Table(title="External model dependency diagnostic")
    summary.add_column("field", no_wrap=True)
    summary.add_column("value")
    summary.add_row("source_key", diagnostic.source_key)
    summary.add_row("module", diagnostic.module_name)
    summary.add_row("module_installed", "yes" if diagnostic.module_installed else "no")
    summary.add_row("module_version", diagnostic.module_version or "(unknown)")
    summary.add_row("dotnet_required", "yes" if diagnostic.dotnet_required else "no")
    summary.add_row("dotnet_cli", diagnostic.dotnet_cli or "(not required/found)")
    summary.add_row(
        "dotnet_ok",
        "(not required)" if diagnostic.dotnet_ok is None else ("yes" if diagnostic.dotnet_ok else "no"),
    )
    summary.add_row("ready", "yes" if diagnostic.ready else "no")
    console.print(summary)

    for warning in diagnostic.warnings:
        console.print(f"[yellow]⚠[/] {warning}")
    if not diagnostic.ready:
        console.print(f"[yellow]hint[/] {escape(diagnostic.install_hint)}")
    if strict and not diagnostic.ready:
        raise click.ClickException(f"{source} reader stack is not ready")


@preprocess.command("inspect-model")
@click.option(
    "--source",
    type=click.Choice(
        [
            "auto",
            "river2d-cdg",
            "hecras-hdf",
            "telemac-slf",
            "delft3d-netcdf",
            "mike-dfs",
            "mike-1d",
            "habby-csv",
            "instream-netlogo",
        ]
    ),
    default="auto",
    help="External model/source family to inspect.",
)
@click.option("--in", "input_path", type=click.Path(exists=True), required=True)
@click.option("--flow-area", default=None, help="HEC-RAS 2D flow-area name for HDF inspection.")
@click.option("--max-rows", type=click.IntRange(min=1), default=20, show_default=True)
def preprocess_inspect_model(
    source: str,
    input_path: str,
    flow_area: str | None,
    max_rows: int,
) -> None:
    """Inspect external model files before importing staging tables."""
    from rich.table import Table

    from openlimno.preprocess import (
        infer_external_model,
        inspect_habitat_exchange,
        inspect_hecras_hdf,
        inspect_instream_exchange,
        inspect_mike_file,
        inspect_netcdf_hydraulic,
        inspect_telemac_selafin,
        read_river2d_cdg,
        read_river2d_elements,
    )

    source_key = infer_external_model(input_path) if source == "auto" else source
    if source_key is None:
        raise click.UsageError("Cannot infer external model format; pass --source.")
    if source_key == "hecras-hdf":
        inspection = inspect_hecras_hdf(input_path, flow_area=flow_area)

        summary = Table(title="HEC-RAS HDF inspection")
        summary.add_column("field", no_wrap=True)
        summary.add_column("value")
        summary.add_row("file", inspection.path)
        summary.add_row("flow_areas", ", ".join(inspection.flow_areas) or "(none)")
        summary.add_row("selected_flow_area", inspection.selected_flow_area or "(none)")
        summary.add_row(
            "n_cells",
            str(inspection.n_cells) if inspection.n_cells is not None else "(unknown)",
        )
        summary.add_row("cell_center_path", inspection.cell_center_path or "(not found)")
        console.print(summary)

        for warning in inspection.warnings:
            console.print(f"[yellow]⚠[/] {warning}")

        candidates = [
            ("geometry", inspection.geometry_candidates),
            ("depth", inspection.depth_candidates),
            ("water_surface", inspection.water_surface_candidates),
            ("velocity", inspection.velocity_candidates),
        ]
        table = Table(title="Candidate datasets")
        table.add_column("kind", no_wrap=True)
        table.add_column("path")
        table.add_column("shape", no_wrap=True)
        table.add_column("dtype", no_wrap=True)
        table.add_column("cell_aligned", no_wrap=True)
        n_rows = 0
        for kind, infos in candidates:
            for info in infos[: max_rows - n_rows]:
                table.add_row(
                    kind,
                    info.path,
                    str(info.shape),
                    info.dtype,
                    "yes" if info.cell_aligned else "no",
                )
                n_rows += 1
            if n_rows >= max_rows:
                break
        if n_rows == 0:
            table.add_row("(none)", "(no candidate datasets found)", "", "", "")
        console.print(table)
        return

    if source_key == "river2d-cdg":
        nodes = read_river2d_cdg(input_path)
        try:
            elements = read_river2d_elements(input_path)
            n_elements = len(elements)
        except ValueError:
            n_elements = 0

        summary = Table(title="River2D CDG inspection")
        summary.add_column("field", no_wrap=True)
        summary.add_column("value")
        summary.add_row("file", input_path)
        summary.add_row("n_nodes", str(len(nodes)))
        summary.add_row("n_elements", str(n_elements))
        summary.add_row("output_table", nodes.attrs.get("openlimno_output_table", "mesh_nodes"))
        console.print(summary)

        columns = Table(title="River2D node columns")
        columns.add_column("index", no_wrap=True)
        columns.add_column("column")
        for idx, column in enumerate([str(col) for col in nodes.columns[:max_rows]]):
            columns.add_row(str(idx), column)
        if nodes.empty:
            columns.add_row("-", "(no nodes)")
        console.print(columns)
        return

    if source_key == "delft3d-netcdf":
        inspection = inspect_netcdf_hydraulic(input_path)
        summary = Table(title="CF/UGRID NetCDF inspection")
        summary.add_column("field", no_wrap=True)
        summary.add_column("value")
        summary.add_row("file", inspection.path)
        summary.add_row("n_cells", str(inspection.n_cells) if inspection.n_cells else "(unknown)")
        summary.add_row("depth", inspection.selected_depth or "(not found)")
        summary.add_row("water_surface", inspection.selected_water_surface or "(not found)")
        summary.add_row("velocity", inspection.selected_velocity or "(not found)")
        summary.add_row("u_component", inspection.selected_u or "(not found)")
        summary.add_row("v_component", inspection.selected_v or "(not found)")
        summary.add_row("x", inspection.selected_x or "(not found)")
        summary.add_row("y", inspection.selected_y or "(not found)")
        summary.add_row("area", inspection.selected_area or "(not found)")
        console.print(summary)
        for warning in inspection.warnings:
            console.print(f"[yellow]⚠[/] {warning}")

        variables = Table(title="NetCDF variables")
        variables.add_column("name")
        variables.add_column("role", no_wrap=True)
        variables.add_column("dims")
        variables.add_column("shape", no_wrap=True)
        variables.add_column("dtype", no_wrap=True)
        for info in inspection.variables[:max_rows]:
            variables.add_row(
                info.name,
                info.role or "",
                ", ".join(info.dims),
                str(info.shape),
                info.dtype,
            )
        if not inspection.variables:
            variables.add_row("(none)", "", "", "", "")
        console.print(variables)
        return

    if source_key == "telemac-slf":
        inspection = inspect_telemac_selafin(input_path)
        summary = Table(title="TELEMAC Selafin inspection")
        summary.add_column("field", no_wrap=True)
        summary.add_column("value")
        summary.add_row("file", inspection.path)
        summary.add_row("title", inspection.title or "(none)")
        summary.add_row("n_points", str(inspection.n_points))
        summary.add_row("n_elements", str(inspection.n_elements))
        summary.add_row("points_per_element", str(inspection.points_per_element))
        summary.add_row("n_timesteps", str(inspection.n_timesteps))
        summary.add_row("times_s", ", ".join(f"{t:g}" for t in inspection.times_s[:max_rows]))
        console.print(summary)
        for warning in inspection.warnings:
            console.print(f"[yellow]⚠[/] {warning}")

        variables = Table(title="Selafin variables")
        variables.add_column("index", no_wrap=True)
        variables.add_column("name")
        variables.add_column("unit", no_wrap=True)
        variables.add_column("role", no_wrap=True)
        for info in inspection.variables[:max_rows]:
            variables.add_row(str(info.index), info.name, info.unit, info.role or "")
        if not inspection.variables:
            variables.add_row("-", "(none)", "", "")
        console.print(variables)
        return

    if source_key == "habby-csv":
        inspection = inspect_habitat_exchange(input_path)
        summary = Table(title="Habitat exchange inspection")
        summary.add_column("field", no_wrap=True)
        summary.add_column("value")
        summary.add_row("file", inspection.path)
        summary.add_row("rows", str(inspection.n_rows))
        summary.add_row("table_type", inspection.table_type)
        summary.add_row(
            "roles",
            ", ".join(f"{role}={column}" for role, column in inspection.detected_roles.items())
            or "(none)",
        )
        console.print(summary)
        for warning in inspection.warnings:
            console.print(f"[yellow]⚠[/] {warning}")

        columns = Table(title="Habitat table columns")
        columns.add_column("index", no_wrap=True)
        columns.add_column("column")
        for idx, column in enumerate(inspection.columns[:max_rows]):
            columns.add_row(str(idx), column)
        if not inspection.columns:
            columns.add_row("-", "(no columns)")
        console.print(columns)
        return

    if source_key == "instream-netlogo":
        inspection = inspect_instream_exchange(input_path)
        summary = Table(title="inSTREAM/NetLogo exchange inspection")
        summary.add_column("field", no_wrap=True)
        summary.add_column("value")
        summary.add_row("file", inspection.path)
        summary.add_row("rows", str(inspection.n_rows))
        summary.add_row("table_type", inspection.table_type)
        summary.add_row(
            "roles",
            ", ".join(f"{role}={column}" for role, column in inspection.detected_roles.items())
            or "(none)",
        )
        console.print(summary)
        for warning in inspection.warnings:
            console.print(f"[yellow]⚠[/] {warning}")

        columns = Table(title="IBM exchange columns")
        columns.add_column("index", no_wrap=True)
        columns.add_column("column")
        for idx, column in enumerate(inspection.columns[:max_rows]):
            columns.add_row(str(idx), column)
        if not inspection.columns:
            columns.add_row("-", "(no columns)")
        console.print(columns)
        return

    if source_key not in {"mike-dfs", "mike-1d"}:
        raise click.UsageError(
            "Detailed inspection is implemented for River2D CDG, HEC-RAS HDF, TELEMAC Selafin, "
            "CF/UGRID NetCDF, MIKE, HABBY/CASiMiR, and inSTREAM/NetLogo table sources."
        )

    mike_inspection = inspect_mike_file(input_path)

    summary = Table(title="MIKE inspection")
    summary.add_column("field", no_wrap=True)
    summary.add_column("value")
    summary.add_row("file", mike_inspection.path)
    summary.add_row("source_key", mike_inspection.source_key)
    summary.add_row("file_kind", mike_inspection.file_kind)
    summary.add_row("geometry_type", mike_inspection.geometry_type or "(none)")
    summary.add_row(
        "n_elements",
        str(mike_inspection.n_elements) if mike_inspection.n_elements is not None else "(unknown)",
    )
    summary.add_row(
        "n_nodes",
        str(mike_inspection.n_nodes) if mike_inspection.n_nodes is not None else "(unknown)",
    )
    summary.add_row(
        "n_timesteps",
        str(mike_inspection.n_timesteps)
        if mike_inspection.n_timesteps is not None
        else "(unknown)",
    )
    summary.add_row("output_table", mike_inspection.output_table)
    console.print(summary)

    for warning in mike_inspection.warnings:
        console.print(f"[yellow]⚠[/] {warning}")

    items = Table(title="MIKE items")
    items.add_column("index", no_wrap=True)
    items.add_column("name")
    for idx, name in enumerate(mike_inspection.item_names[:max_rows]):
        items.add_row(str(idx), name)
    if not mike_inspection.item_names:
        items.add_row("-", "(no items)")
    console.print(items)


@main.command("fetch")
@click.argument(
    "case_yaml", type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--fetch-dem", default=None, type=click.Choice(["cop30"]),
    help="Fetch Copernicus GLO-30 DEM for the case bbox.",
)
@click.option(
    "--fetch-watershed", default=None,
    help="Fetch upstream watershed via HydroSHEDS. Format: "
         "'hydrosheds:REGION:LAT:LON[:LEVEL]'.",
)
@click.option(
    "--fetch-soil", default=None,
    help="Fetch ISRIC SoilGrids point. Format: 'soilgrids:LAT:LON'.",
)
@click.option(
    "--fetch-lulc", default=None,
    help="Fetch ESA WorldCover 10 m LULC. Format: "
         "'worldcover:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX[:YEAR]'.",
)
@click.option(
    "--fetch-species", default=None,
    help="Fetch GBIF taxon + occurrences. Format: "
         "'gbif:SCIENTIFIC_NAME:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX'.",
)
@click.option(
    "--fetch-fishbase", default=None,
    help="Lookup FishBase traits for a species (curated starter "
         "table of ~12 species). Format: 'starter:SCIENTIFIC_NAME'.",
)
@click.option(
    "--fetch-climate", default=None,
    help="Fetch daily climate. Format: 'daymet:LAT:LON:SY:EY' or "
         "'open-meteo:LAT:LON:SY:EY'.",
)
def fetch(
    case_yaml: str,
    fetch_dem: str | None, fetch_watershed: str | None,
    fetch_soil: str | None, fetch_lulc: str | None,
    fetch_species: str | None, fetch_fishbase: str | None,
    fetch_climate: str | None,
) -> None:
    """Run fetchers against an EXISTING case.yaml — additive to its
    sidecar + data.* blocks. Use when you already built the case (via
    ``init-from-osm`` or by hand) and want to pull more layers into it
    without rebuilding the mesh / cross-sections.

    The case's `case.bbox` is used for bbox-shaped fetchers (DEM /
    LULC) if no override is given on those flags' own bbox slots.

    Mirrors the ``--fetch-*`` flag surface from ``init-from-osm`` so
    Studio GUI's QProcess driver can launch this command directly
    without re-implementing fetcher parsing.
    """
    import yaml as _yaml

    from openlimno.preprocess.fetch import (
        fetch_copernicus_dem,
        fetch_daymet_daily,
        fetch_esa_worldcover,
        fetch_gbif_occurrences,
        fetch_hydrobasins,
        fetch_open_meteo_daily,
        fetch_soilgrids,
        find_basin_at,
        match_species,
        record_fetch,
        upstream_basin_ids,
        write_watershed_geojson,
    )

    case_yaml_path = Path(case_yaml).resolve()
    output_dir = case_yaml_path.parent
    case_doc = _yaml.safe_load(case_yaml_path.read_text()) or {}
    case_bbox = (case_doc.get("case", {}) or {}).get("bbox")
    if isinstance(case_bbox, list) and len(case_bbox) == 4:
        case_bbox_tuple = tuple(float(x) for x in case_bbox)
    else:
        case_bbox_tuple = None

    _wedm_patches: dict[str, dict] = {"data": {}}
    n_ran = 0

    if fetch_dem == "cop30":
        if not case_bbox_tuple:
            raise click.UsageError(
                "--fetch-dem cop30 needs case.bbox set in the case.yaml"
            )
        console.print(
            f"[bold]Fetching Copernicus GLO-30 for bbox {case_bbox_tuple}…[/]"
        )
        dem = fetch_copernicus_dem(*case_bbox_tuple)
        ce = dem.cache_entries[0]
        record_fetch(
            output_dir, label="cross_section_dem",
            source_type="copernicus_dem",
            source_url=ce.source_url, fetch_time=ce.fetch_time,
            produced_file=Path(dem.path).name,
            params={"bbox": list(case_bbox_tuple), "n_tiles": dem.n_tiles},
            notes=f"CLI `fetch` Copernicus GLO-30 — {dem.n_tiles} tile(s)",
        )
        _wedm_patches["data"]["dem"] = str(dem.path)
        console.print(f"  → {dem.n_tiles} tile(s) merged")
        n_ran += 1

    if fetch_watershed:
        wparts = fetch_watershed.split(":")
        if not (4 <= len(wparts) <= 5) or wparts[0] != "hydrosheds":
            raise click.UsageError(
                "--fetch-watershed must be "
                "'hydrosheds:REGION:LAT:LON[:LEVEL]'"
            )
        try:
            w_region = wparts[1]
            w_lat = float(wparts[2]); w_lon = float(wparts[3])
            w_level = int(wparts[4]) if len(wparts) == 5 else 12
        except ValueError as e:
            raise click.UsageError(
                f"--fetch-watershed parse error: {fetch_watershed!r}"
            ) from e
        console.print(
            f"[bold]Fetching HydroSHEDS lev{w_level:02d} {w_region.upper()} "
            f"@({w_lat:.4f}, {w_lon:.4f})…[/]"
        )
        layer = fetch_hydrobasins(region=w_region, level=w_level)
        pour = find_basin_at(layer.shp_path, w_lat, w_lon)
        if pour is None:
            raise click.ClickException(
                f"(lat={w_lat}, lon={w_lon}) outside HydroSHEDS region "
                f"{w_region.upper()}"
            )
        pour_id = int(pour["HYBAS_ID"])
        ups = upstream_basin_ids(layer.shp_path, pour_id)
        ws_path = output_dir / "data" / "watershed.geojson"
        ws_path.parent.mkdir(parents=True, exist_ok=True)
        summary = write_watershed_geojson(layer.shp_path, ups, ws_path)
        record_fetch(
            output_dir, label="watershed_hydrosheds",
            source_type="hydrosheds_hydrobasins",
            source_url=layer.cache.source_url,
            fetch_time=layer.cache.fetch_time,
            produced_file=ws_path.relative_to(output_dir),
            params={
                "region": w_region, "level": w_level,
                "pour_lat": w_lat, "pour_lon": w_lon,
                "pour_hybas_id": pour_id,
                "n_basins": summary["n_basins"],
                "area_km2": summary["area_km2"],
            },
            notes=f"CLI `fetch` HydroSHEDS — citation: {layer.citation}",
        )
        _wedm_patches["data"]["watershed"] = {
            "uri": str(ws_path.relative_to(output_dir)),
            "pour_lat": w_lat, "pour_lon": w_lon, "pour_hybas_id": pour_id,
            "region": w_region, "level": w_level,
            "n_basins": summary["n_basins"],
            "area_km2": round(summary["area_km2"], 3),
        }
        console.print(
            f"  → {summary['n_basins']} basins, "
            f"{summary['area_km2']:.1f} km²"
        )
        n_ran += 1

    if fetch_soil:
        sparts = fetch_soil.split(":")
        if len(sparts) != 3 or sparts[0] != "soilgrids":
            raise click.UsageError(
                "--fetch-soil must be 'soilgrids:LAT:LON'"
            )
        try:
            s_lat = float(sparts[1]); s_lon = float(sparts[2])
        except ValueError as e:
            raise click.UsageError(
                f"--fetch-soil parse error: {fetch_soil!r}"
            ) from e
        console.print(f"[bold]Fetching SoilGrids @({s_lat:.4f}, {s_lon:.4f})…[/]")
        sg = fetch_soilgrids(s_lat, s_lon)
        soil_path = output_dir / "data" / "soil.csv"
        soil_path.parent.mkdir(parents=True, exist_ok=True)
        sg.df.to_csv(soil_path, index=False)
        record_fetch(
            output_dir, label="soil_soilgrids",
            source_type="isric_soilgrids_v2",
            source_url=sg.cache.source_url,
            fetch_time=sg.cache.fetch_time,
            produced_file=soil_path.relative_to(output_dir),
            params={"lat": s_lat, "lon": s_lon, "n_rows": len(sg.df)},
            notes=f"CLI `fetch` SoilGrids — citation: {sg.citation}",
        )
        _wedm_patches["data"]["soil"] = {
            "uri": str(soil_path.relative_to(output_dir)),
            "lat": s_lat, "lon": s_lon,
            "properties": sorted(sg.df["property"].unique().tolist()),
            "depths": sorted(sg.df["depth"].unique().tolist()),
            "statistic": (
                str(sg.df["statistic"].iloc[0]) if len(sg.df) else "mean"
            ),
        }
        console.print(f"  → {len(sg.df)} rows")
        n_ran += 1

    if fetch_lulc:
        lparts = fetch_lulc.split(":")
        if not (5 <= len(lparts) <= 6) or lparts[0] != "worldcover":
            raise click.UsageError(
                "--fetch-lulc must be "
                "'worldcover:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX[:YEAR]'"
            )
        try:
            l_lon_min = float(lparts[1]); l_lat_min = float(lparts[2])
            l_lon_max = float(lparts[3]); l_lat_max = float(lparts[4])
            l_year = int(lparts[5]) if len(lparts) == 6 else 2021
        except ValueError as e:
            raise click.UsageError(
                f"--fetch-lulc parse error: {fetch_lulc!r}"
            ) from e
        console.print(
            f"[bold]Fetching ESA WorldCover {l_year}…[/]"
        )
        wc = fetch_esa_worldcover(
            l_lon_min, l_lat_min, l_lon_max, l_lat_max, year=l_year,
        )
        lulc_path = output_dir / "data" / f"lulc_{l_year}.tif"
        lulc_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil as _shutil
        if wc.path != lulc_path:
            _shutil.copy(wc.path, lulc_path)
        record_fetch(
            output_dir, label=f"lulc_worldcover_{l_year}",
            source_type="esa_worldcover",
            source_url=wc.cache_entries[0].source_url,
            fetch_time=wc.cache_entries[0].fetch_time,
            produced_file=lulc_path.relative_to(output_dir),
            params={
                "bbox": [l_lon_min, l_lat_min, l_lon_max, l_lat_max],
                "year": l_year, "version": wc.version,
                "n_tiles": wc.n_tiles,
            },
            notes=f"CLI `fetch` WorldCover — citation: {wc.citation}",
        )
        _wedm_patches["data"]["lulc"] = {
            "uri": str(lulc_path.relative_to(output_dir)),
            "year": l_year, "version": wc.version,
            "class_km2": {
                str(k): round(v, 6) for k, v in wc.class_km2.items()
            },
        }
        console.print(
            f"  → {wc.n_tiles} tile(s), "
            f"{sum(wc.class_pixels.values()):,} px"
        )
        n_ran += 1

    if fetch_species:
        spparts = fetch_species.split(":")
        if len(spparts) != 6 or spparts[0] != "gbif":
            raise click.UsageError(
                "--fetch-species must be "
                "'gbif:SCIENTIFIC_NAME:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX'"
            )
        sp_name = spparts[1].strip()
        try:
            sp_bbox = (
                float(spparts[2]), float(spparts[3]),
                float(spparts[4]), float(spparts[5]),
            )
        except ValueError as e:
            raise click.UsageError(
                f"--fetch-species parse error: {fetch_species!r}"
            ) from e
        console.print(f"[bold]Matching GBIF taxon {sp_name!r}…[/]")
        m = match_species(sp_name)
        if m.usage_key is None or m.match_type == "NONE":
            raise click.ClickException(
                f"GBIF could not match {sp_name!r} "
                f"(match_type={m.match_type})"
            )
        occ = fetch_gbif_occurrences(m.usage_key, sp_bbox)
        sp_path = (
            output_dir / "data" / f"species_gbif_{m.usage_key}.csv"
        )
        sp_path.parent.mkdir(parents=True, exist_ok=True)
        occ.df.to_csv(sp_path, index=False)
        primary = occ.cache[0] if occ.cache else None
        record_fetch(
            output_dir,
            label=f"species_gbif_{m.usage_key}",
            source_type="gbif_occurrence",
            source_url=(
                primary.source_url if primary
                else "https://api.gbif.org/v1/occurrence/search"
            ),
            fetch_time=primary.fetch_time if primary else "",
            produced_file=sp_path.relative_to(output_dir),
            params={
                "scientific_name": sp_name,
                "canonical_name": m.canonical_name,
                "usage_key": m.usage_key,
                "family": m.family, "order": m.order,
                "match_type": m.match_type,
                "confidence": int(m.confidence) if m.confidence is not None else 0,
                "occurrence_count_returned": len(occ.df),
                "occurrence_count_total": int(occ.total_matched),
            },
            notes=f"CLI `fetch` GBIF — citation: {m.citation}",
        )
        _wedm_patches["data"]["species_occurrences"] = {
            "uri": str(sp_path.relative_to(output_dir)),
            "scientific_name": sp_name,
            "canonical_name": m.canonical_name,
            "usage_key": int(m.usage_key),
            "family": m.family, "order": m.order,
            "match_type": m.match_type,
            "confidence": int(m.confidence) if m.confidence is not None else 0,
            "occurrence_count_returned": len(occ.df),
            "occurrence_count_total": int(occ.total_matched),
        }
        console.print(
            f"  → {m.canonical_name} ({m.family}), "
            f"{len(occ.df)}/{occ.total_matched:,} records"
        )
        n_ran += 1

    if fetch_fishbase:
        from openlimno.preprocess.fetch import fetch_fishbase_traits
        fbparts = fetch_fishbase.split(":", 1)
        if len(fbparts) != 2 or fbparts[0] != "starter":
            raise click.UsageError(
                "--fetch-fishbase must be 'starter:SCIENTIFIC_NAME' "
                f"(got {fetch_fishbase!r})"
            )
        fb_name = fbparts[1].strip()
        if not fb_name:
            raise click.UsageError(
                "--fetch-fishbase scientific name is empty"
            )
        console.print(f"[bold]Looking up FishBase traits for {fb_name!r}…[/]")
        traits = fetch_fishbase_traits(fb_name)
        if traits is None:
            console.print(
                f"[yellow]⚠[/] {fb_name!r} not in the bundled starter "
                f"table — see openlimno.preprocess.fetch.list_starter_species()"
            )
        else:
            console.print(
                f"  → {traits.common_name} ({traits.iucn_status}); "
                f"T ∈ [{traits.temperature_min_C}, {traits.temperature_max_C}] °C; "
                f"depth ∈ [{traits.depth_min_m}, {traits.depth_max_m}] m; "
                f"max length {traits.length_max_cm} cm"
            )
            _wedm_patches["data"]["fishbase_traits"] = {
                "scientific_name": traits.scientific_name,
                "common_name": traits.common_name,
                "temperature_min_C": traits.temperature_min_C,
                "temperature_max_C": traits.temperature_max_C,
                "depth_min_m": traits.depth_min_m,
                "depth_max_m": traits.depth_max_m,
                "water_type": traits.water_type,
                "length_max_cm": traits.length_max_cm,
                "iucn_status": traits.iucn_status,
                "fishbase_url": traits.fishbase_url,
            }
        n_ran += 1

    if fetch_climate:
        cparts = fetch_climate.split(":")
        valid = {"daymet", "open-meteo"}
        if len(cparts) != 5 or cparts[0] not in valid:
            raise click.UsageError(
                "--fetch-climate must be '<source>:LAT:LON:SY:EY' "
                f"with source ∈ {sorted(valid)}"
            )
        c_source, c_lat_s, c_lon_s, sy_s, ey_s = cparts
        try:
            c_lat = float(c_lat_s); c_lon = float(c_lon_s)
            c_sy = int(sy_s); c_ey = int(ey_s)
        except ValueError as e:
            raise click.UsageError(
                f"--fetch-climate parse error: {fetch_climate!r}"
            ) from e
        if c_sy > c_ey:
            raise click.UsageError(
                f"start_year ({c_sy}) > end_year ({c_ey})"
            )
        console.print(
            f"[bold]Fetching {c_source} ({c_lat:.4f}, {c_lon:.4f}) "
            f"{c_sy}–{c_ey}…[/]"
        )
        if c_source == "daymet":
            res = fetch_daymet_daily(c_lat, c_lon, c_sy, c_ey)
            label = "climate_daymet"
            stype = "daymet_v4"
        else:
            res = fetch_open_meteo_daily(c_lat, c_lon, c_sy, c_ey)
            label = "climate_open_meteo"
            stype = "open_meteo_archive"
        clim_path = output_dir / "data" / f"climate_{c_sy}_{c_ey}.csv"
        clim_path.parent.mkdir(parents=True, exist_ok=True)
        res.df.to_csv(clim_path, index=False)
        record_fetch(
            output_dir, label=label, source_type=stype,
            source_url=res.cache.source_url,
            fetch_time=res.cache.fetch_time,
            produced_file=clim_path.relative_to(output_dir),
            params={
                "lat": c_lat, "lon": c_lon,
                "start_year": c_sy, "end_year": c_ey,
            },
            notes=f"CLI `fetch` {c_source} — citation: {res.citation}",
        )
        _wedm_patches["data"]["climate"] = {
            "uri": str(clim_path.relative_to(output_dir)),
            "source": c_source,
            "lat": c_lat, "lon": c_lon,
            "start_year": c_sy, "end_year": c_ey,
        }
        console.print(
            f"  → {len(res.df)} days, "
            f"peak T_water {res.df['T_water_C_stefan'].max():.1f}°C"
        )
        n_ran += 1

    if n_ran == 0:
        raise click.UsageError(
            "No fetchers selected — pass at least one --fetch-* flag."
        )

    # Patch case.yaml WEDM v0.2 data.* blocks.
    case_doc["openlimno"] = "0.2"
    case_doc.setdefault("data", {}).update(_wedm_patches["data"])
    case_yaml_path.write_text(
        _yaml.safe_dump(case_doc, sort_keys=False, allow_unicode=True)
    )
    console.print(
        f"\n[green]✓[/] ran {n_ran} fetcher(s); case.yaml updated to WEDM 0.2"
    )


@main.command("init-from-osm")
@click.option("--river", default=None, help="Waterway 'name' tag in OSM (optional if --bbox or --polyline given).")
@click.option("--region", default="Idaho", help="Admin area to scope the OSM query (used only without --bbox).")
@click.option("--bbox", default=None,
                help="Spatial bbox 'lon_min,lat_min,lon_max,lat_max' (overrides region).")
@click.option("--polyline", "polyline_path", type=click.Path(exists=True), default=None,
                help="Path to a LineString GeoJSON (skips Overpass entirely).")
@click.option("--output", "output_dir", type=click.Path(), required=True,
                help="Target directory (created if missing).")
@click.option("--n-sections", default=11, type=int, help="Number of mesh nodes / cross-sections.")
@click.option("--reach-km", default=1.0, type=float, help="Length of modelled reach (km).")
@click.option("--valley-width", default=10.0, type=float, help="Cross-section bank-to-bank width (m).")
@click.option("--thalweg-depth", default=1.0, type=float, help="Thalweg depth below banks (m).")
@click.option("--bank-elev", default=1500.0, type=float, help="Upstream bank elevation (m).")
@click.option("--slope", default=0.002, type=float, help="Bed slope along reach.")
@click.option("--species", default="oncorhynchus_mykiss", help="Default target species.")
@click.option("--fetch-dem", type=click.Choice(["none", "cop30"]), default="none",
                help="Auto-fetch real cross-section bathymetry: "
                     "'cop30' streams Copernicus GLO-30 DEM from AWS S3 and "
                     "cuts perpendicular xs along the centerline. Overrides "
                     "--valley-width / --thalweg-depth / --bank-elev synthesis. "
                     "Requires --bbox (no global lookup with --river).")
@click.option("--fetch-discharge", default=None,
                help="Auto-fetch discharge time series. Format: "
                     "'usgs-nwis:SITE_ID:START:END' (US gauges, no auth). "
                     "Example: 'usgs-nwis:13305000:2020-01-01:2024-12-31' "
                     "for Lemhi River at Lemhi, ID.")
@click.option("--fetch-species", default=None,
                help="Auto-fetch GBIF species match + nearby "
                     "georeferenced occurrences. Format: "
                     "'gbif:SCIENTIFIC_NAME:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX'. "
                     "Writes data/species_<key>.csv and records "
                     "taxonomy match in the sidecar. Example: "
                     "'gbif:Salmo trutta:100.10:38.10:100.30:38.30'.")
@click.option("--fetch-soil", default=None,
                help="Auto-fetch SoilGrids 250 m soil properties at a "
                     "point. Format: 'soilgrids:LAT:LON' — pulls the "
                     "default 6 properties (bdod/clay/sand/silt/soc/"
                     "phh2o) × top 3 depths (0-5/5-15/15-30 cm) × mean "
                     "statistic and writes data/soil.csv plus a "
                     "sidecar entry. Example: 'soilgrids:38.20:100.20'.")
@click.option("--fetch-lulc", default=None,
                help="Auto-fetch ESA WorldCover 10 m LULC. Format: "
                     "'worldcover:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX[:YEAR]' "
                     "with YEAR ∈ {2020, 2021}, default 2021. Writes "
                     "data/lulc.tif (uint8 11-class) + a histogram "
                     "snapshot to the sidecar. Example: "
                     "'worldcover:100.10:38.10:100.30:38.30:2021'.")
@click.option("--fetch-watershed", default=None,
                help="Auto-fetch upstream watershed via HydroSHEDS. "
                     "Format: 'hydrosheds:REGION:LAT:LON[:LEVEL]' where "
                     "REGION ∈ {af,ar,as,au,eu,gr,na,sa,si} and LEVEL "
                     "∈ 1-12 (default 12, finest). Writes "
                     "data/watershed.geojson with the contributing-"
                     "area polygon + drainage area in km². Example: "
                     "'hydrosheds:as:31.23:121.47' (Yangtze estuary).")
@click.option("--fetch-climate", default=None,
                help="Auto-fetch daily climate time series. Formats: "
                     "'daymet:LAT:LON:SY:EY' (North America, 1 km, "
                     "Daymet v4 since 1980) or 'open-meteo:LAT:LON:SY:EY' "
                     "(global, ~11 km, ERA5/ERA5-Land reanalysis via "
                     "Open-Meteo since 1940). Both produce the same "
                     "DataFrame schema (tmax/tmin/T_air_mean + Stefan "
                     "1993 T_water) so downstream code is source-"
                     "agnostic. Resolution differs: Daymet is the "
                     "higher-fidelity choice where it covers, "
                     "Open-Meteo fills the rest of the globe. "
                     "Example: 'open-meteo:31.23:121.47:2024:2024' "
                     "(Shanghai).")
def init_from_osm(
    river: str | None, region: str, bbox: str | None, polyline_path: str | None,
    output_dir: str, n_sections: int, reach_km: float, valley_width: float,
    thalweg_depth: float, bank_elev: float, slope: float, species: str,
    fetch_dem: str, fetch_discharge: str | None,
    fetch_watershed: str | None, fetch_species: str | None,
    fetch_soil: str | None, fetch_lulc: str | None,
    fetch_climate: str | None,
) -> None:
    """Build a complete OpenLimno case from OSM data (SPEC §4.0).

    Reach can be located three ways (priority order):
      1. --polyline path/to/line.geojson  (user-drawn LineString, most precise)
      2. --bbox lon_min,lat_min,lon_max,lat_max  (queries all waterways in box)
      3. --river NAME --region AREA  (fallback, may pick wrong segment)
    """
    from openlimno.preprocess.osm_builder import OSMCaseSpec, build_case

    bbox_tuple = None
    if bbox:
        try:
            parts = [float(x.strip()) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            bbox_tuple = tuple(parts)
        except (ValueError, IndexError):
            raise click.BadParameter("--bbox must be 'lon_min,lat_min,lon_max,lat_max'")

    if not (river or bbox_tuple or polyline_path):
        raise click.UsageError("Provide --river, --bbox, or --polyline")

    # WEDM v0.2: collect fetch-system data pointers so we can patch
    # case.yaml at the end of init_from_osm. Each fetcher's branch
    # populates the matching dict key; the final pass writes the v0.2
    # data block + bumps openlimno to '0.2'.
    _wedm_patches: dict[str, dict] = {"data": {}}
    if bbox_tuple:
        _wedm_patches["case_bbox"] = list(bbox_tuple)

    spec = OSMCaseSpec(
        river_name=river, region_name=region,
        bbox=bbox_tuple, polyline_geojson=polyline_path,
        n_sections=n_sections,
        reach_length_m=reach_km * 1000.0,
        valley_width_m=valley_width,
        thalweg_depth_m=thalweg_depth,
        bank_elevation_m=bank_elev,
        slope=slope,
        species_id=species,
    )
    descriptor = (polyline_path if polyline_path
                    else f"bbox {bbox}" if bbox
                    else f"'{river}' in {region}")
    console.print(f"[bold]Fetching geometry from {descriptor}...[/]")
    import time as _time
    osm_fetch_time = _time.strftime("%Y-%m-%dT%H:%M:%S%z")
    paths = build_case(spec, output_dir)

    # Round-4 fix: record OSM as an external source. The OSM Overpass
    # dataset evolves continuously — two users running the same
    # init-from-osm 6 months apart can get different centerlines, and
    # the resulting mesh.ugrid.nc / cross_section.parquet will hash
    # differently. Without an OSM record in the sidecar, ``openlimno
    # reproduce`` would say "all SHAs match" on day-zero but provenance
    # silently loses the centerline-source provenance over time. This
    # is the transparency gap that motivated the sidecar in the first
    # place.
    if not polyline_path:  # only when we actually hit OSM Overpass
        from openlimno.preprocess.fetch import record_fetch as _rf
        from openlimno.preprocess.osm_builder import build_overpass_query
        # Round-5 fix: use osm_builder's canonical query string instead
        # of re-deriving it here — the previous reconstruction
        # diverged (`way["waterway"~"^(river|stream)$"]` vs the actual
        # `way["waterway"]`, different output format), so the recorded
        # query in provenance.json wouldn't actually replay the same
        # Overpass call. Now we read it from the same source the real
        # fetch uses; if osm_builder ever changes the query, this
        # automatically stays in sync.
        overpass_query = build_overpass_query(
            bbox=bbox_tuple, river_name=river, region_name=region,
        )
        if bbox_tuple:
            osm_params = {"bbox": list(bbox_tuple)}
        else:
            osm_params = {"river_name": river, "region_name": region}
        _rf(
            output_dir,
            label="mesh_osm",
            source_type="osm_overpass",
            source_url="https://overpass-api.de/api/interpreter",
            fetch_time=osm_fetch_time,
            produced_file=Path(paths["mesh"]).relative_to(output_dir),
            params={
                **osm_params,
                "n_sections": n_sections,
                "reach_length_m": reach_km * 1000.0,
                "overpass_query": overpass_query,
            },
            notes=(
                f"OSM Overpass query — mesh.ugrid.nc derived from "
                f"waterway polyline ({descriptor}). OSM is mutable; "
                f"this record pins which dataset version produced the "
                f"current mesh SHA."
            ),
        )

    # v0.3 P0: optional online fetches that REPLACE the synthesized
    # V-section cross_section.parquet and the placeholder Q_2024.csv
    # with real-world data.
    if fetch_dem != "none":
        if not bbox_tuple:
            raise click.UsageError(
                "--fetch-dem requires --bbox (DEM tile selection needs an "
                "explicit lat/lon footprint). River-name mode would need "
                "an extra geocoding step we haven't wired."
            )
        from openlimno.preprocess.fetch import (
            clip_centerline_to_bbox,
            cut_cross_sections_from_dem,
            fetch_copernicus_dem,
            record_fetch,
        )
        from openlimno.preprocess.osm_builder import fetch_river_polyline
        console.print("[bold]Fetching Copernicus GLO-30 DEM for bbox...[/]")
        dem = fetch_copernicus_dem(*bbox_tuple)
        console.print(f"  → DEM {dem.n_tiles} tile(s), bounds {dem.bounds}")
        polyline = clip_centerline_to_bbox(
            fetch_river_polyline(bbox=bbox_tuple), *bbox_tuple
        )
        console.print(f"  → centerline clipped to bbox: {len(polyline)} verts")
        xs_df = cut_cross_sections_from_dem(
            dem.path, polyline, n_sections=n_sections,
            section_width_m=valley_width,
            points_per_section=21,
        )
        xs_df.to_parquet(paths["cross_section"], index=False)
        console.print(
            f"  → cross_section.parquet replaced with {xs_df['station_m'].nunique()} "
            f"real DEM-cut sections (z range "
            f"{xs_df['elevation_m'].min():.0f}–{xs_df['elevation_m'].max():.0f} m)"
        )
        # Record into sidecar for provenance.json
        primary_ce = dem.cache_entries[0]
        record_fetch(
            output_dir,
            label="cross_section_dem",
            source_type="copernicus_dem",
            source_url=primary_ce.source_url,
            fetch_time=primary_ce.fetch_time,
            produced_file=Path(paths["cross_section"]).relative_to(output_dir),
            params={
                "bbox": list(bbox_tuple),
                "n_sections": n_sections,
                "section_width_m": valley_width,
                "n_tiles": dem.n_tiles,
            },
            notes=(
                f"Copernicus GLO-30 DEM, {dem.n_tiles} tile(s); "
                f"perpendicular xs cut along OSM centerline "
                f"({len(polyline)} verts after bbox clip)"
            ),
        )
        # WEDM v0.2: record raw DEM path under data.dem. The merged
        # GeoTIFF lives in the cache; we don't copy it into case_dir
        # (it'd duplicate ~50MB), but the path is still resolvable.
        _wedm_patches["data"]["dem"] = str(dem.path)

    if fetch_discharge:
        import re

        import yaml as _yaml

        from openlimno.preprocess.fetch import (
            fetch_nwis_daily_discharge,
            record_fetch,
        )
        parts = fetch_discharge.split(":")
        if len(parts) != 4 or parts[0] != "usgs-nwis":
            raise click.UsageError(
                "--fetch-discharge must be 'usgs-nwis:SITE_ID:START:END' "
                f"(got {fetch_discharge!r})"
            )
        _, site, start, end = parts
        # Validate date format to avoid a silent 400 from NWIS — they
        # require YYYY-MM-DD and we just pass through what the user
        # typed (round-1 review).
        date_pat = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if not (date_pat.match(start) and date_pat.match(end)):
            raise click.UsageError(
                "--fetch-discharge dates must be YYYY-MM-DD "
                f"(got start={start!r} end={end!r})"
            )
        # Round-3 review: also enforce start <= end. NWIS returns
        # a HTTP 400 for inverted ranges which surfaces as a noisy
        # requests traceback; users get a much clearer local error.
        if start > end:  # lexicographic OK for YYYY-MM-DD
            raise click.UsageError(
                f"--fetch-discharge start_date ({start}) must be on or "
                f"before end_date ({end})"
            )
        # Site IDs are USGS station numbers (8–15 digits). Reject
        # anything else upfront so the silent 400 is replaced by a
        # clear local error.
        if not re.match(r"^\d{8,15}$", site):
            raise click.UsageError(
                f"--fetch-discharge site_id must be 8–15 digits "
                f"(got {site!r})"
            )
        console.print(f"[bold]Fetching USGS NWIS site {site}, {start}..{end}...[/]")
        nwis = fetch_nwis_daily_discharge(site, start, end)
        console.print(
            f"  → station: {nwis.station_name} "
            f"({nwis.station_lat:.4f}, {nwis.station_lon:.4f})"
        )
        q_path = Path(output_dir) / "data" / f"Q_{start[:4]}_{end[:4]}.csv"
        nwis.df.to_csv(q_path, index=False)
        console.print(f"  → discharge: {len(nwis.df)} days → {q_path.name}")
        record_fetch(
            output_dir,
            label="discharge_nwis",
            source_type="usgs_nwis",
            source_url=nwis.cache.source_url,
            fetch_time=nwis.cache.fetch_time,
            produced_file=q_path.relative_to(output_dir),
            params={
                "site_id": site, "start_date": start, "end_date": end,
                "parameterCd": "00060",
            },
            notes=(
                f"USGS NWIS station {site} "
                f"({nwis.station_name} {nwis.station_lat:.4f},{nwis.station_lon:.4f}); "
                f"{len(nwis.df)} daily values"
            ),
        )
        # P0 wire-in: edit case.yaml so the fetched CSV is actually
        # consumed by the model run. Two changes:
        #   1. data.rating_curve = data/<fetched>.csv  (matches Lemhi
        #      reference schema; consumed by regulatory_export modules)
        #   2. regulatory_export: [...]  ENABLED  (without this the
        #      rating_curve is silently ignored by Case.run because
        #      the regulatory step is opt-in via this top-level key).
        # Without both edits the user's auto-fetch from NWIS sits
        # dead-cold in data/ and `openlimno run` produces no eco-flow
        # exports.
        case_yaml_path = Path(paths["case_yaml"])
        case_doc = _yaml.safe_load(case_yaml_path.read_text())
        case_doc.setdefault("data", {})["rating_curve"] = (
            f"data/{q_path.name}"
        )
        if "regulatory_export" not in case_doc:
            case_doc["regulatory_export"] = ["US-FERC-4e", "EU-WFD", "CN-SL712"]
        case_yaml_path.write_text(_yaml.safe_dump(case_doc, sort_keys=False))
        console.print(
            "  → wired into case.yaml: data.rating_curve + regulatory_export"
        )

    if fetch_watershed:
        from openlimno.preprocess.fetch import (
            fetch_hydrobasins,
            find_basin_at,
            upstream_basin_ids,
            write_watershed_geojson,
        )
        from openlimno.preprocess.fetch import (
            record_fetch as _rfw,
        )
        wparts = fetch_watershed.split(":")
        if not (4 <= len(wparts) <= 5) or wparts[0] != "hydrosheds":
            raise click.UsageError(
                "--fetch-watershed must be "
                "'hydrosheds:REGION:LAT:LON[:LEVEL]' "
                f"(got {fetch_watershed!r})"
            )
        w_region = wparts[1]
        try:
            w_lat = float(wparts[2])
            w_lon = float(wparts[3])
            w_level = int(wparts[4]) if len(wparts) == 5 else 12
        except ValueError as e:
            raise click.UsageError(
                f"--fetch-watershed lat/lon must be decimal, "
                f"level must be integer; got {fetch_watershed!r}"
            ) from e
        console.print(
            f"[bold]Fetching HydroBASINS lev{w_level:02d} {w_region.upper()} "
            f"@({w_lat:.4f}, {w_lon:.4f})…[/]"
        )
        layer = fetch_hydrobasins(region=w_region, level=w_level)
        console.print(
            f"  → shapefile {layer.shp_path.name} "
            f"({'cache' if layer.cache.cache_hit else 'downloaded'})"
        )
        pour = find_basin_at(layer.shp_path, w_lat, w_lon)
        if pour is None:
            raise click.ClickException(
                f"(lat={w_lat}, lon={w_lon}) falls outside HydroBASINS "
                f"region {w_region.upper()} — check the region code."
            )
        pour_id = int(pour["HYBAS_ID"])
        console.print(
            f"  → pour-point basin HYBAS_ID={pour_id}, "
            f"SUB_AREA={pour.get('SUB_AREA', 'n/a')} km²"
        )
        upstream = upstream_basin_ids(layer.shp_path, pour_id)
        ws_path = Path(output_dir) / "data" / "watershed.geojson"
        summary = write_watershed_geojson(layer.shp_path, upstream, ws_path)
        console.print(
            f"  → watershed: {summary['n_basins']} basins, "
            f"{summary['area_km2']:.1f} km² → {ws_path.name}"
        )
        _rfw(
            output_dir,
            label="watershed_hydrosheds",
            source_type="hydrosheds_hydrobasins",
            source_url=layer.cache.source_url,
            fetch_time=layer.cache.fetch_time,
            produced_file=ws_path.relative_to(output_dir),
            params={
                "region": w_region, "level": w_level,
                "pour_lat": w_lat, "pour_lon": w_lon,
                "pour_hybas_id": pour_id,
                "n_basins": summary["n_basins"],
                "area_km2": summary["area_km2"],
            },
            notes=(
                f"HydroSHEDS HydroBASINS v1c level {w_level} for "
                f"{w_region.upper()}. Upstream catchment derived by "
                f"walking NEXT_DOWN topology from pour-point basin "
                f"HYBAS_ID={pour_id}. Citation: {layer.citation}"
            ),
        )
        _wedm_patches["data"]["watershed"] = {
            "uri": str(ws_path.relative_to(output_dir)),
            "pour_lat": w_lat, "pour_lon": w_lon,
            "pour_hybas_id": pour_id,
            "region": w_region, "level": w_level,
            "n_basins": summary["n_basins"],
            "area_km2": round(summary["area_km2"], 3),
        }

    if fetch_species:
        from openlimno.preprocess.fetch import (
            fetch_gbif_occurrences,
            match_species,
        )
        from openlimno.preprocess.fetch import (
            record_fetch as _rfsp,
        )
        # Format: gbif:SCIENTIFIC_NAME:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX
        # Scientific names contain spaces but never colons, so naive
        # split-by-':' works. We expect exactly 6 parts.
        spparts = fetch_species.split(":")
        if len(spparts) != 6 or spparts[0] != "gbif":
            raise click.UsageError(
                "--fetch-species must be "
                "'gbif:SCIENTIFIC_NAME:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX' "
                f"(got {fetch_species!r})"
            )
        sp_name = spparts[1].strip()
        try:
            sp_bbox = (
                float(spparts[2]), float(spparts[3]),
                float(spparts[4]), float(spparts[5]),
            )
        except ValueError as e:
            raise click.UsageError(
                f"--fetch-species bbox values must be decimal; got "
                f"{fetch_species!r}"
            ) from e
        console.print(f"[bold]Matching GBIF taxon for {sp_name!r}…[/]")
        m = match_species(sp_name)
        if m.usage_key is None or m.match_type == "NONE":
            raise click.ClickException(
                f"GBIF could not match {sp_name!r} "
                f"(match_type={m.match_type}). Check spelling."
            )
        console.print(
            f"  → usageKey={m.usage_key} ({m.canonical_name}, "
            f"{m.match_type}, confidence {m.confidence}); "
            f"family={m.family}, order={m.order}"
        )
        console.print(
            f"[bold]Fetching GBIF occurrences in bbox {sp_bbox}…[/]"
        )
        occ = fetch_gbif_occurrences(m.usage_key, sp_bbox)
        sp_path = (
            Path(output_dir) / "data" /
            f"species_gbif_{m.usage_key}.csv"
        )
        sp_path.parent.mkdir(parents=True, exist_ok=True)
        occ.df.to_csv(sp_path, index=False)
        console.print(
            f"  → {len(occ.df)} occurrences pulled "
            f"(GBIF total in bbox: {occ.total_matched:,} across "
            f"{occ.n_pages_fetched} page(s)) → {sp_path.name}"
        )
        # First page's cache entry stands in as the canonical fetch
        # record; subsequent pages' SHAs go in params for audit.
        primary_cache = occ.cache[0] if occ.cache else None
        _rfsp(
            output_dir,
            label=f"species_gbif_{m.usage_key}",
            source_type="gbif_occurrence",
            source_url=(
                primary_cache.source_url if primary_cache else
                "https://api.gbif.org/v1/occurrence/search"
            ),
            fetch_time=primary_cache.fetch_time if primary_cache else "",
            produced_file=sp_path.relative_to(output_dir),
            params={
                "scientific_name": sp_name,
                "canonical_name": m.canonical_name,
                "usage_key": m.usage_key,
                "match_type": m.match_type,
                "confidence": m.confidence,
                "family": m.family, "order": m.order,
                "bbox": list(sp_bbox),
                "occurrence_count_returned": len(occ.df),
                "occurrence_count_total": occ.total_matched,
                "pages_fetched": occ.n_pages_fetched,
                "page_shas": [c.sha256[:16] for c in occ.cache],
            },
            notes=(
                f"GBIF taxon match + occurrence search inside bbox. "
                f"Per-row license varies by source dataset — see "
                f"data/species_*.csv 'license' column for re-use "
                f"terms. Citation: {m.citation}"
            ),
        )
        _wedm_patches["data"]["species_occurrences"] = {
            "uri": str(sp_path.relative_to(output_dir)),
            "scientific_name": sp_name,
            "canonical_name": m.canonical_name,
            "usage_key": int(m.usage_key),
            "family": m.family, "order": m.order,
            "match_type": m.match_type,
            "confidence": int(m.confidence) if m.confidence is not None else 0,
            "occurrence_count_returned": len(occ.df),
            "occurrence_count_total": int(occ.total_matched),
        }

    if fetch_soil:
        from openlimno.preprocess.fetch import (
            fetch_soilgrids,
        )
        from openlimno.preprocess.fetch import (
            record_fetch as _rfs,
        )
        sparts = fetch_soil.split(":")
        if len(sparts) != 3 or sparts[0] != "soilgrids":
            raise click.UsageError(
                "--fetch-soil must be 'soilgrids:LAT:LON' "
                f"(got {fetch_soil!r})"
            )
        try:
            s_lat = float(sparts[1]); s_lon = float(sparts[2])
        except ValueError as e:
            raise click.UsageError(
                f"--fetch-soil lat/lon must be decimal; got {fetch_soil!r}"
            ) from e
        console.print(
            f"[bold]Fetching SoilGrids @({s_lat:.4f}, {s_lon:.4f})…[/]"
        )
        sg = fetch_soilgrids(s_lat, s_lon)
        soil_path = Path(output_dir) / "data" / "soil.csv"
        soil_path.parent.mkdir(parents=True, exist_ok=True)
        sg.df.to_csv(soil_path, index=False)
        # Console summary: clay/sand/silt at the top depth.
        try:
            clay = sg.get("clay", "0-5cm")
            sand = sg.get("sand", "0-5cm")
            silt = sg.get("silt", "0-5cm")
            ph = sg.get("phh2o", "0-5cm")
            console.print(
                f"  → top 0-5 cm: clay {clay:.0f} g/kg, "
                f"sand {sand:.0f} g/kg, silt {silt:.0f} g/kg, "
                f"pH {ph:.1f}"
            )
        except KeyError:
            console.print(f"  → {len(sg.df)} (property, depth) values")
        _rfs(
            output_dir,
            label="soil_soilgrids",
            source_type="isric_soilgrids_v2",
            source_url=sg.cache.source_url,
            fetch_time=sg.cache.fetch_time,
            produced_file=soil_path.relative_to(output_dir),
            params={
                "lat": s_lat, "lon": s_lon,
                "n_rows": len(sg.df),
                "properties": sorted(sg.df["property"].unique().tolist()),
                "depths": sorted(sg.df["depth"].unique().tolist()),
                "statistic": (
                    sg.df["statistic"].iloc[0] if len(sg.df) else None
                ),
            },
            notes=(
                f"ISRIC SoilGrids 2.0 point query (250 m grid). Top "
                f"0-30 cm layers, posterior mean. Citation: "
                f"{sg.citation}"
            ),
        )
        _wedm_patches["data"]["soil"] = {
            "uri": str(soil_path.relative_to(output_dir)),
            "lat": s_lat, "lon": s_lon,
            "properties": sorted(sg.df["property"].unique().tolist()),
            "depths": sorted(sg.df["depth"].unique().tolist()),
            "statistic": (
                str(sg.df["statistic"].iloc[0]) if len(sg.df) else "mean"
            ),
        }

    if fetch_lulc:
        from openlimno.preprocess.fetch import (
            WORLDCOVER_CLASSES,
            fetch_esa_worldcover,
        )
        from openlimno.preprocess.fetch import (
            record_fetch as _rfl,
        )
        lparts = fetch_lulc.split(":")
        if not (5 <= len(lparts) <= 6) or lparts[0] != "worldcover":
            raise click.UsageError(
                "--fetch-lulc must be "
                "'worldcover:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX[:YEAR]' "
                f"(got {fetch_lulc!r})"
            )
        try:
            l_lon_min = float(lparts[1]); l_lat_min = float(lparts[2])
            l_lon_max = float(lparts[3]); l_lat_max = float(lparts[4])
            l_year = int(lparts[5]) if len(lparts) == 6 else 2021
        except ValueError as e:
            raise click.UsageError(
                f"--fetch-lulc bbox values must be decimal, year integer; "
                f"got {fetch_lulc!r}"
            ) from e
        console.print(
            f"[bold]Fetching ESA WorldCover {l_year} for bbox "
            f"({l_lon_min:.3f}, {l_lat_min:.3f}, {l_lon_max:.3f}, "
            f"{l_lat_max:.3f})…[/]"
        )
        wc = fetch_esa_worldcover(
            l_lon_min, l_lat_min, l_lon_max, l_lat_max, year=l_year,
        )
        console.print(
            f"  → {wc.n_tiles} tile(s), version {wc.version}, "
            f"{sum(wc.class_pixels.values()):,} pixels"
        )
        # Move/rename into case_dir/data/lulc.tif so it lives with the case.
        import shutil as _shutil
        lulc_path = Path(output_dir) / "data" / f"lulc_{l_year}.tif"
        lulc_path.parent.mkdir(parents=True, exist_ok=True)
        if wc.path != lulc_path:
            _shutil.copy(wc.path, lulc_path)
        # Top 3 classes for the console summary.
        top = sorted(
            wc.class_km2.items(), key=lambda kv: kv[1], reverse=True,
        )[:3]
        top_str = ", ".join(
            f"{WORLDCOVER_CLASSES[c]} {km:.1f} km²" for c, km in top
        )
        console.print(f"  → top classes: {top_str}")
        # Sidecar: store the full histogram for downstream stats.
        _rfl(
            output_dir,
            label=f"lulc_worldcover_{l_year}",
            source_type="esa_worldcover",
            source_url=wc.cache_entries[0].source_url if wc.cache_entries
            else f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/"
                 f"{wc.version}/{l_year}/map/",
            fetch_time=wc.cache_entries[0].fetch_time if wc.cache_entries
            else "",
            produced_file=lulc_path.relative_to(output_dir),
            params={
                "bbox": [l_lon_min, l_lat_min, l_lon_max, l_lat_max],
                "year": l_year, "version": wc.version,
                "n_tiles": wc.n_tiles,
                "class_pixels": {str(k): v for k, v in wc.class_pixels.items()},
                "class_km2": {str(k): round(v, 6)
                              for k, v in wc.class_km2.items()},
            },
            notes=(
                f"ESA WorldCover 10 m {l_year} ({wc.version}). 11-class "
                f"LCCS schema (codes 10..100; see WORLDCOVER_CLASSES). "
                f"Pixel area uses cos(lat) shrinkage at bbox centroid — "
                f"adequate for fraction summaries, not equal-area exact. "
                f"Citation: {wc.citation}"
            ),
        )
        _wedm_patches["data"]["lulc"] = {
            "uri": str(lulc_path.relative_to(output_dir)),
            "year": l_year, "version": wc.version,
            "class_km2": {
                str(k): round(v, 6) for k, v in wc.class_km2.items()
            },
        }

    if fetch_climate:
        from openlimno.preprocess.fetch import (
            fetch_daymet_daily,
            fetch_open_meteo_daily,
        )
        from openlimno.preprocess.fetch import (
            record_fetch as _rfc,
        )
        cparts = fetch_climate.split(":")
        valid_sources = {"daymet", "open-meteo"}
        if len(cparts) != 5 or cparts[0] not in valid_sources:
            raise click.UsageError(
                "--fetch-climate must be '<source>:LAT:LON:START_YEAR:END_YEAR' "
                f"with source ∈ {sorted(valid_sources)} (got {fetch_climate!r})"
            )
        source, lat_s, lon_s, sy_s, ey_s = cparts
        try:
            c_lat = float(lat_s); c_lon = float(lon_s)
            c_sy = int(sy_s); c_ey = int(ey_s)
        except ValueError as e:
            raise click.UsageError(
                f"--fetch-climate lat/lon must be decimal, years must be "
                f"integer; got {fetch_climate!r}"
            ) from e
        if c_sy > c_ey:
            raise click.UsageError(
                f"--fetch-climate start_year ({c_sy}) must be ≤ end_year ({c_ey})"
            )

        if source == "daymet":
            console.print(
                f"[bold]Fetching Daymet ({c_lat:.4f}, {c_lon:.4f}) {c_sy}–{c_ey}…[/]"
            )
            res = fetch_daymet_daily(c_lat, c_lon, c_sy, c_ey)
            console.print(
                f"  → snapped to Daymet pixel ({res.lat:.4f}, {res.lon:.4f}), "
                f"tile {res.tile_id}, elev {res.elevation_m:.0f} m"
            )
            label = "climate_daymet"
            source_type = "daymet_v4"
            notes = (
                f"Daymet v4 (Thornton et al. ORNL DAAC, tile {res.tile_id}). "
                f"T_water column = Stefan & Preud'homme 1993 air→water "
                f"linear model (a=5.0, b=0.75) — unshaded mid-latitude "
                f"default; basin-specific calibration recommended."
            )
        else:  # open-meteo
            console.print(
                f"[bold]Fetching Open-Meteo ({c_lat:.4f}, {c_lon:.4f}) "
                f"{c_sy}–{c_ey}…[/]"
            )
            res = fetch_open_meteo_daily(c_lat, c_lon, c_sy, c_ey)
            console.print(
                f"  → snapped to Open-Meteo cell ({res.lat:.4f}, {res.lon:.4f}), "
                f"elev {res.elevation_m:.0f} m, tz {res.timezone}"
            )
            label = "climate_open_meteo"
            source_type = "open_meteo_archive"
            notes = (
                f"Open-Meteo archive (ERA5/ERA5-Land backend, "
                f"Hersbach et al. 2020). T_water column = Stefan & "
                f"Preud'homme 1993 (a=5.0, b=0.75) — unshaded "
                f"mid-latitude default; basin-specific calibration "
                f"recommended. Citation: {res.citation}"
            )

        clim_path = Path(output_dir) / "data" / f"climate_{c_sy}_{c_ey}.csv"
        res.df.to_csv(clim_path, index=False)
        console.print(
            f"  → climate: {len(res.df)} days "
            f"(air mean {res.df['T_air_C_mean'].mean():.1f} °C, "
            f"peak water {res.df['T_water_C_stefan'].max():.1f} °C "
            f"via Stefan 1993) → {clim_path.name}"
        )
        _rfc(
            output_dir,
            label=label,
            source_type=source_type,
            source_url=res.cache.source_url,
            fetch_time=res.cache.fetch_time,
            produced_file=clim_path.relative_to(output_dir),
            params={
                "lat": c_lat, "lon": c_lon,
                "start_year": c_sy, "end_year": c_ey,
            },
            notes=notes,
        )
        _wedm_patches["data"]["climate"] = {
            "uri": str(clim_path.relative_to(output_dir)),
            "source": source,
            "lat": c_lat, "lon": c_lon,
            "start_year": c_sy, "end_year": c_ey,
        }

    # WEDM v0.2 patch pass: fold collected fetch outputs into case.yaml
    # so the case self-describes the data it was built from. v0.1
    # cases that didn't use any fetcher remain on '0.1' (no patch).
    if _wedm_patches["data"] or "case_bbox" in _wedm_patches:
        import yaml as _yaml_v02
        case_yaml_path = Path(paths["case_yaml"])
        case_doc = _yaml_v02.safe_load(case_yaml_path.read_text()) or {}
        case_doc["openlimno"] = "0.2"
        if "case_bbox" in _wedm_patches:
            case_doc.setdefault("case", {})["bbox"] = (
                _wedm_patches["case_bbox"]
            )
        if _wedm_patches["data"]:
            case_doc.setdefault("data", {}).update(_wedm_patches["data"])
        case_yaml_path.write_text(
            _yaml_v02.safe_dump(case_doc, sort_keys=False, allow_unicode=True)
        )
        console.print(
            f"  → case.yaml bumped to WEDM 0.2 with "
            f"{len(_wedm_patches['data'])} fetched data block(s)"
        )

    console.print()
    console.print(f"[green]✓[/] case built in {output_dir}")
    for k, v in paths.items():
        console.print(f"  {k:14s}: {v}")
    console.print()
    console.print(f"Run:  [bold]openlimno run {paths['case_yaml']}[/]")


if __name__ == "__main__":
    main()
