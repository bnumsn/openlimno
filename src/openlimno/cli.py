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
    """OpenLimno: open-source water ecology modeling platform.

    Replaces PHABSIM/River2D/FishXing with modern data formats, multi-scale
    habitat assessment, and explicit IFIM workflow support.
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
@click.option("--executor", type=click.Choice(["local"]), default="local",
              help="1.0 supports only local; HPC/cloud in §13")
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
    from openlimno.case import Case
    import numpy as np

    case = Case.from_yaml(case_yaml)
    Qs = list(np.logspace(0, np.log10(30), n_q))
    result = case.run(discharges_m3s=Qs)
    col = f"wua_m2_{species}_{stage}"
    if col not in result.wua_q.columns:
        console.print(f"[red]✗[/] no WUA column for ({species}, {stage}); "
                      f"available: {[c for c in result.wua_q.columns if c.startswith('wua_m2_')]}")
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
        fig.savefig(png, dpi=120)
        console.print(f"[green]✓[/] plot saved: {png}")


@main.command()
@click.option("--culvert", type=click.Path(exists=True), required=True,
              help="Culvert YAML config (geometry + material)")
@click.option("--swim", "swim_path", type=click.Path(exists=True), required=True,
              help="swimming_performance.parquet")
@click.option("--species", required=True)
@click.option("--stage", default="adult")
@click.option("--discharge", "Q", type=float, required=True,
              help="Discharge through culvert (m³/s)")
@click.option("--temp", "T", type=float, default=12.0)
@click.option("--monte-carlo", "n_mc", type=int, default=0,
              help="Number of Monte Carlo samples (0 = deterministic)")
@click.option("--attraction-eta", type=float, default=1.0,
              help="η_A user input (ADR-0007); 1.0 = no attraction effect")
def passage(culvert: str, swim_path: str, species: str, stage: str,
            Q: float, T: float, n_mc: int, attraction_eta: float) -> None:
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
    res = passage_success_rate(cv, swim, discharge_m3s=Q, temp_C=T,
                                monte_carlo=n_mc, seed=42)

    eta_total = attraction_eta * res.eta_P
    console.print(res.summary())
    console.print(
        f"  η_A (user input): {attraction_eta:.2f}  "
        f"→ η = η_A × η_P = {eta_total:.3f}"
    )


@main.command()
@click.argument("case_yaml", type=click.Path(exists=True))
@click.option("--observed", type=click.Path(exists=True), required=True,
              help="Rating curve Parquet/CSV with columns h_m, Q_m3s")
@click.option("--algo", default="scipy", type=click.Choice(["scipy", "pestpp-glm"]),
              help="scipy = M2 1-parameter; pestpp-glm = 1.x multi-parameter")
@click.option("--initial-n", default=0.035, type=float)
@click.option("--slope", default=0.002, type=float)
def calibrate(case_yaml: str, observed: str, algo: str,
              initial_n: float, slope: float) -> None:
    """Calibrate Manning's n against an observed rating curve.

    M2: scipy-based 1-parameter; PEST++ multi-parameter in 1.x.
    """
    import pandas as pd

    if algo == "pestpp-glm":
        raise NotImplementedError("PEST++ multi-parameter calibration is 1.x")

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
@click.option("--check-only/--rerun", default=True,
              help="check-only verifies SHA-256 fingerprints; rerun re-executes")
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
        console.print(f"[green]✓[/] case YAML SHA matches")

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
@click.option("--species", multiple=True, default=("oncorhynchus_mykiss",),
              help="Target species (repeatable)")
@click.option("--interactive/--non-interactive", default=False)
def studyplan_init(output_path: str, problem: str | None,
                   species: tuple[str, ...], interactive: bool) -> None:
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
            {"species": sp, "rationale": "EDIT: why this species"}
            for sp in species
        ],
        "objective_variables": ["wua-q", "persistent_habitat"],
        "uncertainty_sources_acknowledged": [
            "hsi_uncertainty", "transferability", "measurement_error",
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
@click.option("--out", "output_path", type=click.Path(), required=False,
              help="Output path; defaults to overwriting input")
@click.option("--set-grade", type=click.Choice(["A", "B", "C"]),
              help="Bulk-set quality_grade for all curves")
@click.option("--set-origin", help="Bulk-set geographic_origin for all curves")
@click.option("--set-transferability", type=float,
              help="Bulk-set transferability_score for all curves")
@click.option("--mark-independence-tested/--unmark", default=None,
              help="Set independence_tested true/false")
@click.option("--interactive/--non-interactive", default=False)
def hsi_upgrade(parquet_file: str, output_path: str | None,
                set_grade: str | None, set_origin: str | None,
                set_transferability: float | None,
                mark_independence_tested: bool | None,
                interactive: bool) -> None:
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
    write_cross_sections_to_parquet(df, output_path,
                                     source_note=f"imported from {input_path}")
    console.print(
        f"[green]✓[/] {len(df)} rows from {len(df['station_m'].unique())} stations "
        f"→ {output_path}"
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


if __name__ == "__main__":
    main()
