"""Hydraulic parameter calibration.

SPEC §3.5: ``calibrate`` workflow. Provides scipy-based 1-parameter
calibration of Manning's n against an observed rating curve plus PEST++
GLM workspace generation and an external ``pestpp-glm`` runner wrapper.

Use case (Lemhi-typical):
    Given a measured rating curve at a USGS gauge (h, Q pairs) and a built
    cross-section, find the Manning's n that minimises sum-of-squared error
    between observed and Manning-predicted Q for a fixed slope.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from openlimno.hydro.builtin_1d import CrossSection


@dataclass
class CalibrationResult:
    """Outcome of a 1-parameter Manning calibration."""

    parameter: str  # "manning_n"
    calibrated_value: float
    initial_value: float
    rmse_initial: float
    rmse_final: float
    n_iterations: int
    converged: bool
    bounds: tuple[float, float]
    notes: str = ""


@dataclass(frozen=True)
class PestppWorkspace:
    """Files generated for a PEST++ GLM calibration workspace."""

    directory: Path
    control_file: Path
    template_file: Path
    parameter_file: Path
    instruction_file: Path
    model_output_file: Path
    observed_file: Path
    runner_script: Path
    readme_file: Path


@dataclass(frozen=True)
class PestppRunResult:
    """Completed external PEST++ GLM process."""

    command: tuple[str, ...]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str
    record_file: Path | None = None


def _rmse(predicted: np.ndarray, observed: np.ndarray) -> float:
    return float(np.sqrt(np.mean((predicted - observed) ** 2)))


def _predicted_Q_at_h(
    xs: CrossSection, observed: pd.DataFrame, slope: float, n_value: float
) -> np.ndarray:
    """Predict Q at each observed h using Manning with given n."""
    base_n = xs.manning_n
    xs.manning_n = n_value
    try:
        # Translate observed h (depth above thalweg) to absolute WSE
        wse = xs.thalweg_elevation_m + observed["h_m"].to_numpy()
        Q_pred = np.array([xs.manning_discharge(float(w), slope) for w in wse])
    finally:
        xs.manning_n = base_n
    return Q_pred


def calibrate_manning_n(
    cross_section: CrossSection,
    observed_rating: pd.DataFrame,
    slope: float = 0.001,
    initial_n: float = 0.035,
    bounds: tuple[float, float] = (0.012, 0.08),
) -> CalibrationResult:
    """Calibrate Manning's n by minimising RMSE between observed and predicted Q.

    Parameters
    ----------
    cross_section
        A CrossSection (typically the gauge-vicinity section).
    observed_rating
        DataFrame with columns ``h_m`` and ``Q_m3s``.
    slope
        Bed slope assumed during calibration (constant; per-segment slope is M2+).
    initial_n
        Starting Manning's n estimate.
    bounds
        Reasonable physical range for Manning's n.
    """
    if not {"h_m", "Q_m3s"}.issubset(observed_rating.columns):
        raise ValueError("observed_rating must have columns 'h_m' and 'Q_m3s'")
    obs_Q = observed_rating["Q_m3s"].to_numpy()

    Q_pred_init = _predicted_Q_at_h(cross_section, observed_rating, slope, initial_n)
    rmse_init = _rmse(Q_pred_init, obs_Q)

    def objective(n_value: float) -> float:
        if not (bounds[0] <= n_value <= bounds[1]):
            return 1e9
        Q_pred = _predicted_Q_at_h(cross_section, observed_rating, slope, n_value)
        return _rmse(Q_pred, obs_Q)

    result = minimize_scalar(
        objective,
        bounds=bounds,
        method="bounded",
        options={"xatol": 1e-5, "maxiter": 200},
    )

    n_calib = float(result.x)
    rmse_final = float(result.fun)
    return CalibrationResult(
        parameter="manning_n",
        calibrated_value=n_calib,
        initial_value=initial_n,
        rmse_initial=rmse_init,
        rmse_final=rmse_final,
        n_iterations=int(result.nit) if hasattr(result, "nit") else -1,
        converged=bool(result.success),
        bounds=bounds,
        notes=f"slope={slope}, n_obs={len(observed_rating)}",
    )


def _validate_observed_rating(observed_rating: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of the observed rating table with stable observation names."""
    if not {"h_m", "Q_m3s"}.issubset(observed_rating.columns):
        raise ValueError("observed_rating must have columns 'h_m' and 'Q_m3s'")
    obs = observed_rating[["h_m", "Q_m3s"]].copy()
    obs["obs_name"] = [f"q_{i:04d}" for i in range(1, len(obs) + 1)]
    return obs[["obs_name", "h_m", "Q_m3s"]]


def _render_pest_control(
    obs: pd.DataFrame,
    *,
    initial_n: float,
    slope: float,
    n_bounds: tuple[float, float],
    slope_bounds: tuple[float, float],
) -> str:
    obs_lines = "\n".join(
        f"{row.obs_name} {float(row.Q_m3s):.12g} 1.0 rating"
        for row in obs.itertuples(index=False)
    )
    nobs = len(obs)
    return f"""pcf
* control data
restart estimation
2 {nobs} 1 0 1
1 1 single point 1 0 0
10.0 2.0 0.3 0.03 10
3.0 3.0 0.001
0.1
30 0.01 4 3 0.01 3
1 1 1
* parameter groups
hydraulic relative 0.01 0.0 switch 2.0 parabolic
* parameter data
manning_n log factor {initial_n:.12g} {n_bounds[0]:.12g} {n_bounds[1]:.12g} hydraulic 1.0 0.0 1
slope log factor {slope:.12g} {slope_bounds[0]:.12g} {slope_bounds[1]:.12g} hydraulic 1.0 0.0 1
* observation groups
rating
* observation data
{obs_lines}
* model command line
python run_openlimno_calibration.py
* model input/output
params.tpl params.in
model.ins model.out
* prior information
"""


def build_pestpp_glm_workspace(
    case_yaml: str | Path,
    observed_rating: pd.DataFrame,
    out_dir: str | Path,
    *,
    initial_n: float = 0.035,
    slope: float = 0.002,
    n_bounds: tuple[float, float] = (0.012, 0.08),
    slope_bounds: tuple[float, float] = (1e-5, 0.02),
) -> PestppWorkspace:
    """Generate a PEST++ GLM workspace for OpenLimno calibration.

    This does not run ``pestpp-glm``. It writes the control/template/
    instruction files plus a deterministic OpenLimno runner script so an
    external PEST++ binary or container can execute the calibration.
    """
    from openlimno.case import Case

    case = Case.from_yaml(case_yaml)
    # v3.0.0 audit-pass: sandbox-route the PEST++ workspace's
    # cross_section path. With case.allowed_data_roots unset → strict;
    # examples ship with explicit roots so calibration cases keep
    # working under v3.0.
    cross_section_path = case._resolve_safe(case.config["data"]["cross_section"])
    if not cross_section_path.is_file():
        raise FileNotFoundError(f"cross_section parquet missing: {cross_section_path}")
    obs = _validate_observed_rating(observed_rating)

    directory = Path(out_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    control_file = directory / "openlimno_calibration.pst"
    template_file = directory / "params.tpl"
    parameter_file = directory / "params.in"
    instruction_file = directory / "model.ins"
    model_output_file = directory / "model.out"
    observed_file = directory / "observed_rating.csv"
    runner_script = directory / "run_openlimno_calibration.py"
    readme_file = directory / "README.md"

    observed_file.write_text(obs.to_csv(index=False), encoding="utf-8")
    template_file.write_text(
        "ptf ~\n"
        "manning_n ~ manning_n ~\n"
        "slope ~ slope ~\n",
        encoding="utf-8",
    )
    parameter_file.write_text(
        f"manning_n {initial_n:.12g}\n"
        f"slope {slope:.12g}\n",
        encoding="utf-8",
    )
    instruction_lines = ["pif @", "l1"]
    instruction_lines.extend(f"l1 w !{name}!" for name in obs["obs_name"])
    instruction_file.write_text("\n".join(instruction_lines) + "\n", encoding="utf-8")
    control_file.write_text(
        _render_pest_control(
            obs,
            initial_n=initial_n,
            slope=slope,
            n_bounds=n_bounds,
            slope_bounds=slope_bounds,
        ),
        encoding="utf-8",
    )
    runner_script.write_text(
        f'''"""PEST++ model runner generated by OpenLimno."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from openlimno.hydro.builtin_1d import load_sections_from_parquet

WORK_DIR = Path(__file__).resolve().parent
CROSS_SECTION = Path({str(cross_section_path)!r})


def _read_params(path: Path) -> dict[str, float]:
    params: dict[str, float] = {{}}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        params[parts[0]] = float(parts[1])
    return params


def main() -> None:
    params = _read_params(WORK_DIR / "params.in")
    manning_n = params["manning_n"]
    slope = params["slope"]
    observed = pd.read_csv(WORK_DIR / "observed_rating.csv")
    sections = load_sections_from_parquet(CROSS_SECTION, manning_n=manning_n)
    if not sections:
        raise RuntimeError(f"no cross-sections found in {{CROSS_SECTION}}")
    xs = sections[0]
    rows = ["obs_name predicted_Q_m3s"]
    for row in observed.itertuples(index=False):
        wse = xs.thalweg_elevation_m + float(row.h_m)
        predicted = xs.manning_discharge(wse, slope)
        rows.append(f"{{row.obs_name}} {{predicted:.12g}}")
    (WORK_DIR / "model.out").write_text("\\n".join(rows) + "\\n")


if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )
    readme_file.write_text(
        "# OpenLimno PEST++ GLM workspace\n\n"
        "Generated by `openlimno calibrate --algo pestpp-glm`.\n\n"
        "Run from this directory with an external PEST++ binary/container:\n\n"
        "```bash\n"
        "pestpp-glm openlimno_calibration.pst\n"
        "```\n\n"
        "The generated model runner evaluates the first cross-section in the "
        "case against `observed_rating.csv` using `manning_n` and `slope` "
        "from `params.in`.\n",
        encoding="utf-8",
    )

    return PestppWorkspace(
        directory=directory,
        control_file=control_file,
        template_file=template_file,
        parameter_file=parameter_file,
        instruction_file=instruction_file,
        model_output_file=model_output_file,
        observed_file=observed_file,
        runner_script=runner_script,
        readme_file=readme_file,
    )


def _workspace_paths(workspace: PestppWorkspace | str | Path) -> tuple[Path, Path]:
    if isinstance(workspace, PestppWorkspace):
        return workspace.directory, workspace.control_file
    directory = Path(workspace).resolve()
    control_file = directory / "openlimno_calibration.pst"
    return directory, control_file


def run_pestpp_glm_workspace(
    workspace: PestppWorkspace | str | Path,
    *,
    executable: str = "pestpp-glm",
    timeout: float = 600.0,
    check: bool = True,
) -> PestppRunResult:
    """Run an external ``pestpp-glm`` binary against a generated workspace."""
    directory, control_file = _workspace_paths(workspace)
    if not directory.is_dir():
        raise FileNotFoundError(f"PEST++ workspace directory missing: {directory}")
    if not control_file.is_file():
        raise FileNotFoundError(f"PEST++ control file missing: {control_file}")

    exe_path = shutil.which(executable)
    if exe_path is None and Path(executable).is_file():
        exe_path = str(Path(executable).resolve())
    if exe_path is None:
        raise FileNotFoundError(
            f"Could not find {executable!r}. Install PEST++ or pass "
            "executable=/path/to/pestpp-glm."
        )

    command = (exe_path, control_file.name)
    proc = subprocess.run(
        command,
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    result = PestppRunResult(
        command=command,
        cwd=directory,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        record_file=directory / "openlimno_calibration.rec"
        if (directory / "openlimno_calibration.rec").exists()
        else None,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"pestpp-glm failed with exit code {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
        )
    return result


# ---------------------------------------------------------------------
# v2.14.0 — PEST++ GLM ↔ HSI round-trip closure (charter half-promise
# from v2.5.0). Reads the optimised parameters PEST++ wrote, patches
# them back into case.yaml under ``hydrodynamics.builtin_1d`` so a
# subsequent ``Case.run()`` picks them up as defaults.
# ---------------------------------------------------------------------
def read_optimised_params(
    workspace: PestppWorkspace | str | Path,
    *,
    par_filename: str = "openlimno_calibration.par",
) -> dict[str, float]:
    """Read PEST++ GLM's optimised-parameter output.

    After ``pestpp-glm`` finishes a calibration run, it writes the
    final parameter estimates to ``<control>.par`` in the workspace
    directory. The format is:

        single point
        manning_n 0.041234 1.0 0.0
        slope     0.002567 1.0 0.0

    where the first line is the parameter-data header (style + scale
    + offset convention) and each subsequent line carries
    ``name value scale offset``. This function returns ``{name:
    value}`` for every parameter in the file.

    Args:
        workspace: PestppWorkspace dataclass or path to the workspace
            directory.
        par_filename: name of the ``.par`` file (default matches what
            ``build_pestpp_glm_workspace`` writes).

    Returns:
        dict mapping parameter name → optimised numeric value.

    Raises:
        FileNotFoundError: when the ``.par`` file is missing
            (PEST++ didn't finish or never ran).
        ValueError: when the file format is unparseable.
    """
    directory, _ = _workspace_paths(workspace)
    par_path = directory / par_filename
    if not par_path.is_file():
        raise FileNotFoundError(
            f"PEST++ .par file not found: {par_path}. Did pestpp-glm "
            f"finish a successful run? Check the workspace for "
            f"openlimno_calibration.rec / .rmr for diagnostics."
        )
    # v2.14.1 R13-5: PEST++ .par rows are 4 whitespace-separated
    # tokens: `name value scale offset`. Pre-v2.14.1 the parser
    # accepted any 2-token row where token[1] parses as a float —
    # which would misinterpret PEST++ status / iteration / commentary
    # lines as parameters. Require ≥4 tokens AND verify the trailing
    # scale + offset tokens are also numeric (claude R13-5 lower-bound
    # test: a stray comment with 2 stringy tokens would have slipped
    # through).
    params: dict[str, float] = {}
    lines = par_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            value = float(parts[1])
            float(parts[2])  # validate scale is numeric
            float(parts[3])  # validate offset is numeric
        except ValueError:
            continue
        params[parts[0]] = value
    if not params:
        raise ValueError(
            f"PEST++ .par file at {par_path} carried no parseable "
            f"parameter rows (expected `name value scale offset` "
            f"4-token format). First few lines: {lines[:5]!r}"
        )
    return params


def apply_optimised_params_to_case_yaml(
    case_yaml: str | Path,
    params: dict[str, float],
    *,
    out_yaml: str | Path | None = None,
) -> Path:
    """Patch a case YAML with PEST++-optimised parameters.

    Writes the supplied parameters into
    ``hydrodynamics.builtin_1d.{manning_n, slope}`` so a subsequent
    ``Case.from_yaml(out_yaml).run()`` picks them up as the
    effective defaults (without any explicit kwarg). Only
    ``manning_n`` and ``slope`` keys are honored; any other
    parameter names in ``params`` are warned-on and ignored — a
    future ship can extend the mapping to per-segment Manning's-n
    CSV emission, HSI-knot patching, etc.

    Args:
        case_yaml: path to the input case YAML.
        params: ``{name: value}`` dict, typically from
            ``read_optimised_params``.
        out_yaml: where to write the patched YAML. ``None`` means
            write back to the input path (in-place patch); pass an
            explicit path to keep a pre-calibration copy.

    Returns:
        Path to the written YAML.

    Raises:
        ValueError: when ``params`` contains no recognised keys
            (so the user is alerted rather than silently writing
            the file unchanged).
    """
    # v3.3.0 R13-3: use comment-preserving round-trip so the
    # user's case.yaml notes / acknowledge_independence_reason /
    # citations are NOT destroyed when calibrated parameters land.
    # Falls back to safe_dump if ruamel.yaml isn't installed (with
    # a one-time stderr warning), so a minimal-deps env still
    # works — just lossy.
    from openlimno._yaml_rt import dump_round_trip, load_round_trip

    src = Path(case_yaml).resolve()
    dst = Path(out_yaml).resolve() if out_yaml else src
    config = load_round_trip(src)
    # v2.14.1 R13-8: a YAML literal ``hydrodynamics: null`` or
    # ``hydrodynamics:`` (key with empty value) loads as ``None``.
    # ``dict.setdefault("hydrodynamics", {})`` returns the existing
    # None in that case, and the next ``.setdefault("builtin_1d", {})``
    # would raise AttributeError on None. Defensively coalesce.
    if config.get("hydrodynamics") is None:
        config["hydrodynamics"] = {}
    hydro = config["hydrodynamics"]
    if hydro.get("builtin_1d") is None:
        hydro["builtin_1d"] = {}
    b1d = hydro["builtin_1d"]

    recognised = {"manning_n", "slope"}
    patched: list[str] = []
    ignored: list[str] = []
    for name in params:
        if name in recognised:
            b1d[name] = float(params[name])
            patched.append(name)
        else:
            ignored.append(name)

    if not patched:
        raise ValueError(
            f"None of the parameter names {list(params)} are "
            f"currently recognised by the round-trip writer. v2.14.0 "
            f"supports {sorted(recognised)}; extend the mapping in "
            f"calibrate.apply_optimised_params_to_case_yaml for HSI "
            f"knots / per-segment manning."
        )
    # v2.14.1 R13-7: surface dropped parameters via the standard
    # warnings channel so a user calibrating an unsupported param
    # (e.g. an HSI knot in a future PEST++ workspace) is alerted
    # rather than silently losing the result. Default action
    # category UserWarning, not DeprecationWarning — this is a "your
    # data was dropped" notice, not a future-behavior heads-up.
    if ignored:
        import warnings as _w
        _w.warn(
            f"apply_optimised_params_to_case_yaml: dropped "
            f"unrecognised parameter(s) {sorted(ignored)}; only "
            f"{sorted(recognised)} are currently round-tripped. "
            f"These values are NOT written to {dst}.",
            UserWarning,
            stacklevel=2,
        )

    # v2.14.1 R13-2 + v3.3.0 R13-3 combined: atomic write via
    # ``Case._atomic_write`` (truncate-safety) AND ruamel.yaml
    # round-trip dump (comment-preserving). Both contracts live
    # inside ``openlimno._yaml_rt.dump_round_trip``.
    return dump_round_trip(config, dst)


__all__ = [
    "CalibrationResult",
    "PestppRunResult",
    "PestppWorkspace",
    "apply_optimised_params_to_case_yaml",
    "build_pestpp_glm_workspace",
    "calibrate_manning_n",
    "read_optimised_params",
    "run_pestpp_glm_workspace",
]
