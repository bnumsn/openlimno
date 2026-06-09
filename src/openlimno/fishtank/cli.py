"""Command-line interface for ``openlimno.fishtank``."""

from __future__ import annotations

import sys

import click
from rich.console import Console

# Teaching-lab machines run a Chinese GBK console (code page 936). rich's
# legacy-windows renderer encodes with that codec directly and aborts with
# UnicodeEncodeError when a message carries a glyph GBK lacks (em-dash in a
# warning, a BOM echoed from a malformed scenario). Harden stdio so such a
# glyph degrades to a placeholder instead of crashing the command, and keep
# rich off the legacy path so its output honours this error handler.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(errors="replace")
        except (ValueError, OSError):
            pass

console = Console(legacy_windows=False)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Run, validate, calibrate, and launch the fishtank model."""


@main.command("validate")
@click.argument("scenario_yaml", type=click.Path(exists=True))
def validate_cmd(scenario_yaml: str) -> None:
    """Validate a fishtank scenario YAML/JSON file."""

    from .io import validate_scenario

    errors = validate_scenario(scenario_yaml)
    if errors:
        for err in errors:
            console.print(f"[red]x[/] {err}")
        raise click.ClickException(f"{scenario_yaml} is not a valid fishtank scenario")
    console.print(f"[green]ok[/] {scenario_yaml} validates")


@main.command("run")
@click.argument("scenario_yaml", type=click.Path(exists=True))
@click.option("--out-dir", type=click.Path(), default="output/fishtank", show_default=True)
def run_cmd(scenario_yaml: str, out_dir: str) -> None:
    """Run a scenario and write reproducible outputs."""

    from .io import load_scenario, write_result

    scenario = load_scenario(scenario_yaml)
    result = scenario.run()
    paths = write_result(result, out_dir)
    final = result.timeseries.iloc[-1]
    console.print(
        "[green]ok[/] fishtank run complete: "
        f"day={final['day']:.1f}, TAN={final['TAN']:.3f}, "
        f"NO2={final['NO2']:.3f}, NO3={final['NO3']:.3f}"
    )
    for name, path in paths.items():
        console.print(f"  {name}: {path}")
    if result.warnings:
        console.print(f"[yellow]{len(result.warnings)} warning(s)[/]")
        for warning in result.warnings:
            console.print(f"  - {warning}")


@main.command("calibrate")
@click.argument("observation", type=click.Path(exists=True))
@click.option(
    "--scenario",
    "scenario_yaml",
    type=click.Path(exists=True),
    default=None,
    help="Optional scenario supplying initial chemistry and base params.",
)
@click.option("--fit", "fit_names", multiple=True, default=("mu_AOB", "mu_NOB"), show_default=True)
def calibrate_cmd(observation: str, scenario_yaml: str | None, fit_names: tuple[str, ...]) -> None:
    """Fit nitrification parameters against an aquarium observation table."""

    from .calibration import fit
    from .io import load_scenario, read_observation
    from .state import Chemistry, Params

    obs = read_observation(observation)
    chemistry = Chemistry()
    params = Params()
    days = None
    schedule = None
    if scenario_yaml:
        scenario = load_scenario(scenario_yaml)
        chemistry = scenario.chemistry
        params = scenario.params
        days = scenario.days
        # Honour the scenario's keeper events (water changes, feeding) during
        # the fit — a real aquarium log was produced under those actions, so
        # the simulated trajectory must replay them or the fit is biased.
        schedule = scenario.schedule
    bounds = tuple((0.1, 1.5) for _ in fit_names)
    result = fit(
        obs,
        chemistry=chemistry,
        base_params=params,
        fit_names=fit_names,
        bounds=bounds,
        days=days,
        schedule=schedule,
    )
    best = ", ".join(f"{name}={value:.4g}" for name, value in result.best_params.items())
    status = "converged" if result.converged else f"not converged: {result.message}"
    console.print(f"[green]ok[/] calibration {status}; RMSE={result.best_rmse:.4g}; {best}")


@main.command("studio")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8768, show_default=True)
@click.option("--open-browser/--no-open-browser", default=True, show_default=True)
def studio_cmd(host: str, port: int, open_browser: bool) -> None:
    """Launch the local browser Studio."""

    from .studio_http import run_fishtank_studio

    run_fishtank_studio(host=host, port=port, open_browser=open_browser)


@main.command("desktop")
def desktop_cmd() -> None:
    """Launch the native desktop app (PySide6) — needs the ``desktop`` extra."""

    try:
        from .desktop import run
    except ImportError as exc:  # PySide6 not installed
        raise click.ClickException(
            f"desktop app needs PySide6: pip install 'openlimno[desktop]'  ({exc})"
        ) from exc
    raise SystemExit(run())


if __name__ == "__main__":
    main()
