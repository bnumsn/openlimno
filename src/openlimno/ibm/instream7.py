"""Official inSTREAM 7 example-case benchmark support.

This module reads the public inSTREAM 7 distribution examples without executing
NetLogo. It converts the official inputs into OpenLimno's native IBM tables so
the replacement engine can be checked against the same case inventory,
hydraulic matrices, time-series drivers, and initial population strata.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from openlimno.preprocess.instream_netlogo import read_instream_exchange

from .native import NativeIBMConfig, SpeciesProfile, run_native_ibm

_NATIVE_REDD_COLUMNS = [
    "redd_id",
    "species",
    "cell_id",
    "spawn_day",
    "spawn_season",
    "age_days",
    "eggs_initial",
    "eggs_remaining",
    "development_degree_days",
    "incubation_target_degree_days",
    "alive",
    "emerged",
    "emergence_day",
    "scenario_id",
    "reach_id",
]
_NATIVE_EVENT_COLUMNS = ["scenario_id", "reach_id", "day", "event", "n", "n_eggs", "species"]


@dataclass(frozen=True)
class Instream7Reach:
    """Reach-level file mapping parsed from an official inSTREAM 7 parameter file."""

    case_id: str
    reach_id: str
    time_series_file: Path
    depth_file: Path
    velocity_file: Path
    shapefile: Path
    cell_id_field: str
    reach_field: str
    area_field: str
    hiding_places_field: str
    velocity_shelter_field: str
    spawning_fraction_field: str


@dataclass(frozen=True)
class Instream7Case:
    """Official inSTREAM 7 example case discovered on disk."""

    case_id: str
    root: Path
    parameter_file: Path
    initial_population_file: Path
    start_date: str
    end_date: str
    species: tuple[str, ...]
    reaches: tuple[Instream7Reach, ...]
    parameters: dict[str, tuple[str, ...] | tuple[float, ...]]
    adult_arrival_file: Path | None = None


@dataclass(frozen=True)
class Instream7BenchmarkResult:
    """Output tables from an official inSTREAM 7 benchmark conversion/run."""

    inventory: pd.DataFrame
    population_summary: pd.DataFrame
    final_individuals: pd.DataFrame
    cell_use: pd.DataFrame
    events: pd.DataFrame
    redds: pd.DataFrame
    paths: dict[str, str]


@dataclass(frozen=True)
class Instream7NetLogoReferenceResult:
    """Artifacts from an optional NetLogo reference run."""

    case_id: str
    case_root: Path
    model_file: Path
    setup_file: Path
    table_path: Path
    spreadsheet_path: Path
    brief_population_files: tuple[Path, ...]


def extract_instream7_archive(archive: str | Path, output_dir: str | Path) -> Path:
    """Extract an official inSTREAM 7 zip archive and return the extraction root."""

    archive_path = Path(archive)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as zf:
        zf.extractall(out)
    return out


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _set_string(text: str, name: str, default: str = "") -> str:
    match = re.search(rf"\bset\s+{re.escape(name)}\s+\"([^\"]*)\"", text)
    return match.group(1) if match else default


def _set_list_body(text: str, name: str) -> str:
    match = re.search(rf"\bset\s+{re.escape(name)}\s+\(list\s+(.*?)\)", text, flags=re.S)
    return match.group(1) if match else ""


def _set_string_list(text: str, name: str) -> tuple[str, ...]:
    body = _set_list_body(text, name)
    return tuple(re.findall(r'"([^"]+)"', body))


def _set_number_list(text: str, name: str) -> tuple[float, ...]:
    body = _set_list_body(text, name)
    values = re.findall(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][-+]?\d+)?", body)
    return tuple(float(value) for value in values)


def _set_time_create_list(text: str, name: str) -> tuple[str, ...]:
    body = _set_list_body(text, name)
    return tuple(re.findall(r'time:create\s+"([^"]+)"', body))


def _cmax_optimum_temperatures(text: str, species: tuple[str, ...]) -> tuple[float, ...]:
    values: list[float] = []
    for name in species:
        pairs = re.findall(
            rf"table:put\s+{re.escape(name)}-cmax-table\s+"
            r"([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][-+]?\d+)?)\s+"
            r"([-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][-+]?\d+)?)",
            text,
        )
        if not pairs:
            values.append(12.0)
            continue
        parsed = [(float(temp), float(cmax)) for temp, cmax in pairs]
        values.append(max(parsed, key=lambda item: item[1])[0])
    return tuple(values)


def _case_id_from_parameter_file(path: Path) -> str:
    stem = path.stem
    return stem.removeprefix("parameters-")


def _resolve_case_path(root: Path, value: str) -> Path:
    return root / value


def parse_instream7_case(root: str | Path, parameter_file: str | Path) -> Instream7Case:
    """Parse one official inSTREAM 7 parameter file into OpenLimno metadata."""

    root_path = Path(root)
    param_path = Path(parameter_file)
    text = _read_text(param_path)
    case_id = _case_id_from_parameter_file(param_path)

    reach_names = _set_string_list(text, "reach-names")
    time_series_files = _set_string_list(text, "time-series-input-files")
    depth_files = _set_string_list(text, "depth-file-names")
    velocity_files = _set_string_list(text, "velocity-file-names")
    species = _set_string_list(text, "species-list")
    if not reach_names:
        raise ValueError(f"{param_path} does not define reach-names")
    if not (
        len(reach_names)
        == len(time_series_files)
        == len(depth_files)
        == len(velocity_files)
    ):
        raise ValueError(f"{param_path} has inconsistent reach/file list lengths")

    cell_id_field = _set_string(text, "GIS-property-for-cell-ID", "ID_TEXT")
    reach_field = _set_string(text, "GIS-property-for-cell-reach-name", "REACH_NAME")
    area_field = _set_string(text, "GIS-property-for-cell-area", "AREA")
    hiding_field = _set_string(text, "GIS-property-for-cell-num-hiding-places", "NUM_HIDING")
    shelter_field = _set_string(text, "GIS-property-for-cell-frac-vel-shelter", "FRACVSHL")
    spawn_field = _set_string(text, "GIS-property-for-cell-frac-spawn", "FRACSPWN")
    shapefile = _resolve_case_path(root_path, _set_string(text, "GIS-file-name"))

    parameters: dict[str, tuple[str, ...] | tuple[float, ...]] = {
        "trout-spawn-start-day": _set_time_create_list(text, "trout-spawn-start-day"),
        "trout-spawn-end-day": _set_time_create_list(text, "trout-spawn-end-day"),
        "trout-spawn-fecund-mult": _set_number_list(text, "trout-spawn-fecund-mult"),
        "trout-spawn-fecund-exp": _set_number_list(text, "trout-spawn-fecund-exp"),
        "trout-spawn-egg-viability": _set_number_list(text, "trout-spawn-egg-viability"),
        "trout-spawn-min-length": _set_number_list(text, "trout-spawn-min-length"),
        "trout-emerge-length-mode": _set_number_list(text, "trout-emerge-length-mode"),
        "trout-weight-A": _set_number_list(text, "trout-weight-A"),
        "trout-weight-B": _set_number_list(text, "trout-weight-B"),
        "trout-cmax-A": _set_number_list(text, "trout-cmax-A"),
        "trout-cmax-B": _set_number_list(text, "trout-cmax-B"),
        "trout-move-radius-max": _set_number_list(text, "trout-move-radius-max"),
        "trout-move-radius-L1": _set_number_list(text, "trout-move-radius-L1"),
        "trout-move-radius-L9": _set_number_list(text, "trout-move-radius-L9"),
        "trout-resp-A": _set_number_list(text, "trout-resp-A"),
        "trout-resp-B": _set_number_list(text, "trout-resp-B"),
        "trout-resp-C": _set_number_list(text, "trout-resp-C"),
        "trout-resp-D": _set_number_list(text, "trout-resp-D"),
        "mort-redd-dewater-surv": _set_number_list(text, "mort-redd-dewater-surv"),
        "mort-redd-scour-depth": _set_number_list(text, "mort-redd-scour-depth"),
        "mort-high-temp-T1": _set_number_list(text, "mort-high-temp-T1"),
        "mort-high-temp-T9": _set_number_list(text, "mort-high-temp-T9"),
        "cmax-temperature-optimum": _cmax_optimum_temperatures(text, species),
    }

    reaches = tuple(
        Instream7Reach(
            case_id=case_id,
            reach_id=reach,
            time_series_file=_resolve_case_path(root_path, ts),
            depth_file=_resolve_case_path(root_path, depth),
            velocity_file=_resolve_case_path(root_path, velocity),
            shapefile=shapefile,
            cell_id_field=cell_id_field,
            reach_field=reach_field,
            area_field=area_field,
            hiding_places_field=hiding_field,
            velocity_shelter_field=shelter_field,
            spawning_fraction_field=spawn_field,
        )
        for reach, ts, depth, velocity in zip(
            reach_names,
            time_series_files,
            depth_files,
            velocity_files,
            strict=True,
        )
    )
    return Instream7Case(
        case_id=case_id,
        root=root_path,
        parameter_file=param_path,
        initial_population_file=_resolve_case_path(root_path, _set_string(text, "initial-population-file")),
        start_date=_set_string(text, "start-date"),
        end_date=_set_string(text, "end-date"),
        species=species,
        reaches=reaches,
        parameters=parameters,
        adult_arrival_file=(
            _resolve_case_path(root_path, adult_arrival_file)
            if (adult_arrival_file := _set_string(text, "adult-arrival-file"))
            else None
        ),
    )


def discover_instream7_cases(root: str | Path) -> tuple[Instream7Case, ...]:
    """Discover official inSTREAM 7 example cases under an extracted directory."""

    root_path = Path(root)
    cases = [
        parse_instream7_case(root_path, path)
        for path in sorted(root_path.glob("Example-Project-*/parameters-*.nls"))
    ]
    if not cases:
        raise ValueError(f"No official inSTREAM 7 parameter files found under {root_path}")
    return tuple(cases)



def _format_netlogo_date(value: pd.Timestamp) -> str:
    return f"{value.month}/{value.day}/{value.year}"


def _model_file_for_case(root: Path, case_id: str) -> Path:
    matches = sorted(root.glob(f"*{case_id}.nlogox"))
    if not matches:
        raise ValueError(f"No NetLogo model file found for case {case_id!r} under {root}")
    if len(matches) > 1:
        raise ValueError(f"Multiple NetLogo model files found for case {case_id!r}: {matches}")
    return matches[0]


def _metrics_from_netlogo_model(model_file: Path) -> list[str]:
    root = ET.parse(model_file).getroot()
    experiment = root.find(".//experiment")
    if experiment is None:
        raise ValueError(f"{model_file} has no BehaviorSpace experiment")
    metrics = [metric.text or "" for metric in experiment.findall("./metrics/metric")]
    metrics = [metric for metric in metrics if metric]
    if not metrics:
        raise ValueError(f"{model_file} BehaviorSpace experiment has no metrics")
    return metrics


def write_instream7_netlogo_setup_file(
    model_file: str | Path,
    output_path: str | Path,
    *,
    experiment_name: str = "openlimno-reference",
    seed: int = 11,
) -> Path:
    """Write a short-run BehaviorSpace setup XML for NetLogo reference runs."""

    model = Path(model_file)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("experiments")
    experiment = ET.SubElement(
        root,
        "experiment",
        {
            "name": experiment_name,
            "repetitions": "1",
            "sequentialRunOrder": "true",
            "runMetricsEveryStep": "true",
        },
    )
    ET.SubElement(experiment, "setup").text = "setup"
    ET.SubElement(experiment, "go").text = "go"
    metrics_el = ET.SubElement(experiment, "metrics")
    for metric in _metrics_from_netlogo_model(model):
        ET.SubElement(metrics_el, "metric").text = metric
    constants = ET.SubElement(experiment, "constants")
    values: dict[str, str] = {
        "brief-pop-output?": "true",
        "detailed-pop-output?": "false",
        "shade-variable": '"off"',
        "update-plots?": "false",
        "events-output?": "false",
        "random-number-seed": str(int(seed)),
    }
    for variable, value in values.items():
        value_set = ET.SubElement(constants, "enumeratedValueSet", {"variable": variable})
        ET.SubElement(value_set, "value", {"value": value})
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(output, encoding="unicode", xml_declaration=False)
    return output


def _patch_case_end_date(case: Instream7Case, days: int) -> None:
    if days < 1:
        raise ValueError("NetLogo reference days must be at least 1")
    start = pd.to_datetime(case.start_date, errors="coerce")
    if pd.isna(start):
        raise ValueError(f"Case {case.case_id} has invalid start-date {case.start_date!r}")
    end = pd.Timestamp(start) + pd.Timedelta(days=days - 1)
    text = case.parameter_file.read_text(encoding="utf-8", errors="replace")
    patched, end_count = re.subn(
        r'set\s+end-date\s+"[^"]+"',
        f'set end-date   "{_format_netlogo_date(end)}"',
        text,
        count=1,
    )
    patched, units_count = re.subn(
        r'set\s+file-output-units\s+"[^"]+"',
        'set file-output-units "days"',
        patched,
        count=1,
    )
    patched, frequency_count = re.subn(
        r'set\s+file-output-frequency\s+[-+]?(?:\d+\.\d*|\.\d+|\d+)',
        'set file-output-frequency  1',
        patched,
        count=1,
    )
    if end_count != 1:
        raise ValueError(f"Could not patch end-date in {case.parameter_file}")
    if units_count == 0:
        patched, units_count = re.subn(
            r"(?m)^end\s*$",
            '  set file-output-units "days"\nend',
            patched,
            count=1,
        )
    if frequency_count == 0:
        patched, frequency_count = re.subn(
            r"(?m)^end\s*$",
            "  set file-output-frequency  1\nend",
            patched,
            count=1,
        )
    if units_count != 1:
        raise ValueError(f"Could not patch file-output-units in {case.parameter_file}")
    if frequency_count != 1:
        raise ValueError(f"Could not patch file-output-frequency in {case.parameter_file}")
    case.parameter_file.write_text(patched, encoding="utf-8")


def prepare_instream7_netlogo_reference_case(
    root: str | Path,
    output_dir: str | Path,
    *,
    case_id: str,
    days: int = 2,
    seed: int = 11,
    experiment_name: str = "openlimno-reference",
) -> Instream7NetLogoReferenceResult:
    """Copy and shorten an official case for an optional NetLogo reference run."""

    source_root = Path(root).resolve()
    out = Path(output_dir).resolve()
    if out.is_relative_to(source_root):
        raise ValueError("output_dir must not be inside the source inSTREAM fixture root")
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root, out, dirs_exist_ok=True)
    case = next((item for item in discover_instream7_cases(out) if item.case_id == case_id), None)
    if case is None:
        raise ValueError(f"No inSTREAM 7 case {case_id!r} found under {out}")
    _patch_case_end_date(case, days)
    model_file = _model_file_for_case(out, case_id)
    setup_file = write_instream7_netlogo_setup_file(
        model_file,
        out / f"openlimno-{case_id}-{days}d.xml",
        experiment_name=experiment_name,
        seed=seed,
    )
    return Instream7NetLogoReferenceResult(
        case_id=case_id,
        case_root=out,
        model_file=model_file,
        setup_file=setup_file,
        table_path=out / "openlimno_netlogo_table.csv",
        spreadsheet_path=out / "openlimno_netlogo_spreadsheet.csv",
        brief_population_files=tuple(sorted(out.glob("BriefPopOut-*.csv"))),
    )


def run_instream7_netlogo_reference(
    root: str | Path,
    output_dir: str | Path,
    *,
    case_id: str,
    netlogo_console: str | Path,
    days: int = 2,
    seed: int = 11,
    experiment_name: str = "openlimno-reference",
) -> Instream7NetLogoReferenceResult:
    """Run NetLogo headless for an official inSTREAM case reference output."""

    prepared = prepare_instream7_netlogo_reference_case(
        root,
        output_dir,
        case_id=case_id,
        days=days,
        seed=seed,
        experiment_name=experiment_name,
    )
    before = set(prepared.case_root.glob("BriefPopOut-*.csv"))
    subprocess.run(
        [
            str(netlogo_console),
            "--headless",
            "--model",
            str(prepared.model_file),
            "--setup-file",
            str(prepared.setup_file),
            "--table",
            str(prepared.table_path),
            "--spreadsheet",
            str(prepared.spreadsheet_path),
            "--threads",
            "1",
        ],
        cwd=prepared.case_root,
        check=True,
    )
    after = set(prepared.case_root.glob("BriefPopOut-*.csv"))
    new_brief_files = tuple(sorted(after - before)) or tuple(sorted(after))
    return Instream7NetLogoReferenceResult(
        case_id=prepared.case_id,
        case_root=prepared.case_root,
        model_file=prepared.model_file,
        setup_file=prepared.setup_file,
        table_path=prepared.table_path,
        spreadsheet_path=prepared.spreadsheet_path,
        brief_population_files=new_brief_files,
    )


def read_official_initial_population(path: str | Path) -> pd.DataFrame:
    """Read an official inSTREAM 7 initial population CSV."""

    header = "Species,Reach,Age,Number,Length min,Length mode,Length max"
    data_lines: list[str] = [header]
    for line in Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(";"):
            continue
        data_lines.append(stripped)
    df = pd.read_csv(StringIO("\n".join(data_lines)))
    for col in ("Age", "Number", "Length min", "Length mode", "Length max"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def read_official_time_series(path: str | Path) -> pd.DataFrame:
    """Read an official inSTREAM 7 daily forcing table."""

    df = pd.read_csv(path, comment=";")
    df.columns = [str(col).strip().lower() for col in df.columns]
    rename = {
        "date": "date",
        "flow": "flow_m3s",
        "temperature": "temperature_c",
        "turbidity": "turbidity_ntu",
    }
    df = df.rename(columns=rename)
    required = {"date", "flow_m3s", "temperature_c", "turbidity_ntu"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing time-series columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("flow_m3s", "temperature_c", "turbidity_ntu"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["date", "flow_m3s"]).reset_index(drop=True)


def read_official_adult_arrivals(path: str | Path) -> pd.DataFrame:
    """Read an official InSALMO 7 adult salmon-arrival CSV."""

    header = (
        "Year,Species,Reach,Number,Fraction female,Arrival start,Arrival peak,"
        "Arrival end,Length min,Length mode,Length max"
    )
    data_lines: list[str] = [header]
    for line in Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(";"):
            continue
        data_lines.append(stripped)
    df = pd.read_csv(StringIO("\n".join(data_lines)))
    for col in ("Year", "Number"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    for col in ("Fraction female", "Length min", "Length mode", "Length max"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("Arrival start", "Arrival peak", "Arrival end"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df.dropna(subset=["Species", "Reach", "Arrival start", "Arrival end"]).reset_index(
        drop=True
    )


def _empty_official_population(*, scheduled: bool = False) -> pd.DataFrame:
    columns = [
        "fish_id",
        "species",
        "age_days",
        "length_mm",
        "mass_g",
        "cell_id",
        "alive",
        "reach_id",
    ]
    if scheduled:
        columns.insert(0, "arrival_day")
    return pd.DataFrame(columns=columns)


def _integer_counts_from_weights(n: int, weights: np.ndarray) -> np.ndarray:
    if n <= 0 or len(weights) == 0:
        return np.zeros(len(weights), dtype=int)
    total = float(np.nansum(weights))
    if total <= 0.0:
        weights = np.ones(len(weights), dtype=float)
        total = float(len(weights))
    expected = weights / total * int(n)
    counts = np.floor(expected).astype(int)
    remainder = int(n) - int(counts.sum())
    if remainder > 0:
        order = np.argsort(-(expected - counts), kind="mergesort")
        counts[order[:remainder]] += 1
    return counts


def _arrival_weights(dates: pd.DatetimeIndex, peak: pd.Timestamp) -> np.ndarray:
    if len(dates) == 0:
        return np.asarray([], dtype=float)
    start = pd.Timestamp(dates.min())
    end = pd.Timestamp(dates.max())
    peak = min(max(pd.Timestamp(peak), start), end)
    values: list[float] = []
    for date in dates:
        day = pd.Timestamp(date)
        if day <= peak:
            span = max((peak - start).days, 1)
            weight = 1.0 + ((day - start).days / span)
        else:
            span = max((end - peak).days, 1)
            weight = 1.0 + ((end - day).days / span)
        values.append(max(float(weight), 0.0))
    return np.asarray(values, dtype=float)


def build_population_from_official_adult_arrivals(
    adult_arrivals: pd.DataFrame,
    *,
    reach_id: str,
    species: str,
    start_date: str | pd.Timestamp,
    days: int,
    seed: int,
    profile: SpeciesProfile | None = None,
    first_fish_id: int = 0,
) -> pd.DataFrame:
    """Expand official InSALMO adult-arrival rows into scheduled native fish."""

    if days <= 0 or adult_arrivals.empty:
        return _empty_official_population(scheduled=True)
    sim_start = pd.Timestamp(pd.to_datetime(start_date, errors="coerce")).normalize()
    if pd.isna(sim_start):
        raise ValueError(f"invalid simulation start date {start_date!r}")
    sim_end = sim_start + pd.Timedelta(days=days - 1)
    rows = adult_arrivals[
        (adult_arrivals["Reach"].astype(str) == reach_id)
        & (adult_arrivals["Species"].astype(str) == species)
    ]
    if rows.empty:
        return _empty_official_population(scheduled=True)

    rng = np.random.default_rng(seed)
    frames: list[pd.DataFrame] = []
    next_id = int(first_fish_id)
    for _, row in rows.iterrows():
        n = int(row["Number"])
        if n <= 0:
            continue
        arrival_start = pd.Timestamp(row["Arrival start"]).normalize()
        arrival_end = pd.Timestamp(row["Arrival end"]).normalize()
        if arrival_end < sim_start or arrival_start > sim_end:
            continue
        window_start = max(arrival_start, sim_start)
        window_end = min(arrival_end, sim_end)
        dates = pd.date_range(window_start, window_end, freq="D")
        counts = _integer_counts_from_weights(
            n,
            _arrival_weights(dates, pd.Timestamp(row["Arrival peak"]).normalize()),
        )
        for date, count in zip(dates, counts, strict=True):
            if count <= 0:
                continue
            min_cm = float(row["Length min"])
            mode_cm = float(row["Length mode"])
            max_cm = float(row["Length max"])
            lengths_mm = rng.triangular(min_cm, mode_cm, max_cm, int(count)) * 10.0
            frames.append(
                pd.DataFrame(
                    {
                        "arrival_day": np.full(
                            int(count),
                            int((pd.Timestamp(date) - sim_start).days) + 1,
                            dtype=int,
                        ),
                        "fish_id": np.arange(next_id, next_id + int(count), dtype=int),
                        "species": species,
                        "age_days": np.full(int(count), 4 * 365, dtype=int),
                        "length_mm": lengths_mm,
                        "mass_g": profile.weight_a_g_per_cm_b * (lengths_mm / 10.0) ** profile.weight_b
                        if profile is not None
                        else 1.15e-5 * lengths_mm**3.0,
                        "cell_id": np.full(int(count), "", dtype=object),
                        "alive": np.ones(int(count), dtype=bool),
                        "reach_id": reach_id,
                        "adult_arrival_year": int(row["Year"]),
                        "adult_arrival_female_fraction": float(row["Fraction female"]),
                    }
                )
            )
            next_id += int(count)
    if not frames:
        return _empty_official_population(scheduled=True)
    return pd.concat(frames, ignore_index=True)


def read_instream7_brief_population(path: str | Path) -> pd.DataFrame:
    """Read an inSTREAM 7 ``BriefPopOut`` CSV generated by NetLogo."""

    df = pd.read_csv(path, skiprows=1)
    rename = {
        "BehavSp-Run": "behaviorspace_run",
        "End of time step": "end_time",
        "IsCensus?": "is_census",
        "Light phase": "light_phase",
        "Reach": "reach_id",
        "Flow": "flow_m3s",
        "Temperature": "temperature_c",
        "Turbidity": "turbidity_ntu",
        "Species": "species",
        "Age class": "age_class",
        "Count": "count",
        "Mean length": "mean_length_cm",
        "Mean weight": "mean_weight_g",
        "Mean condition": "mean_condition",
        "FractionDriftFeeding": "fraction_drift_feeding",
        "FractionSearchFeeding": "fraction_search_feeding",
        "FractionHiding": "fraction_hiding",
    }
    missing = set(rename) - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing inSTREAM 7 BriefPop columns: {sorted(missing)}")

    out = df.rename(columns=rename)[list(rename.values())].copy()
    out["end_timestamp"] = pd.to_datetime(out["end_time"], errors="coerce")
    out["is_census"] = out["is_census"].astype(str).str.lower().isin({"true", "1", "yes"})
    numeric_cols = [
        "behaviorspace_run",
        "flow_m3s",
        "temperature_c",
        "turbidity_ntu",
        "count",
        "mean_length_cm",
        "mean_weight_g",
        "mean_condition",
        "fraction_drift_feeding",
        "fraction_search_feeding",
        "fraction_hiding",
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["count"] = out["count"].fillna(0).astype(int)
    out["mean_length_mm"] = out["mean_length_cm"] * 10.0
    out["biomass_g"] = out["count"] * out["mean_weight_g"]
    return out


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    valid = values.notna() & weights.notna()
    if not bool(valid.any()):
        return float("nan")
    valid_values = values[valid].to_numpy(dtype=float)
    valid_weights = weights[valid].to_numpy(dtype=float)
    total = float(valid_weights.sum())
    if total <= 0.0:
        return float("nan")
    return float(np.average(valid_values, weights=valid_weights))


def summarize_instream7_brief_population(table: pd.DataFrame) -> pd.DataFrame:
    """Aggregate inSTREAM 7 ``BriefPopOut`` rows to native-summary shape."""

    columns = [
        "behaviorspace_run",
        "end_time",
        "end_timestamp",
        "light_phase",
        "is_census",
        "reach_id",
        "species",
        "abundance",
        "biomass_g",
        "mean_length_mm",
        "mean_weight_g",
        "mean_condition",
        "fraction_drift_feeding",
        "fraction_search_feeding",
        "fraction_hiding",
        "flow_m3s",
        "temperature_c",
        "turbidity_ntu",
        "age_classes",
    ]
    if table.empty:
        return pd.DataFrame(columns=columns)

    group_cols = [
        "behaviorspace_run",
        "end_time",
        "end_timestamp",
        "light_phase",
        "is_census",
        "reach_id",
        "species",
        "flow_m3s",
        "temperature_c",
        "turbidity_ntu",
    ]
    rows: list[dict[str, object]] = []
    for keys, group in table.groupby(group_cols, dropna=False, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_cols, keys, strict=True))
        weights = group["count"].astype(float)
        row["abundance"] = int(group["count"].sum())
        row["biomass_g"] = float(group["biomass_g"].sum())
        row["mean_length_mm"] = _weighted_mean(group["mean_length_mm"], weights)
        row["mean_weight_g"] = _weighted_mean(group["mean_weight_g"], weights)
        row["mean_condition"] = _weighted_mean(group["mean_condition"], weights)
        row["fraction_drift_feeding"] = _weighted_mean(group["fraction_drift_feeding"], weights)
        row["fraction_search_feeding"] = _weighted_mean(group["fraction_search_feeding"], weights)
        row["fraction_hiding"] = _weighted_mean(group["fraction_hiding"], weights)
        row["age_classes"] = "|".join(sorted(group["age_class"].astype(str).unique()))
        rows.append(row)
    return pd.DataFrame.from_records(rows, columns=columns)


def _brief_sequence(summary: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "netlogo_run",
        "reach_id",
        "species",
        "comparison_day",
        "netlogo_end_time",
        "netlogo_abundance",
        "netlogo_biomass_g",
        "netlogo_mean_length_mm",
    ]
    if summary.empty:
        return pd.DataFrame(columns=columns)

    required = {"reach_id", "species", "abundance", "biomass_g", "mean_length_mm"}
    missing = required - set(summary.columns)
    if missing:
        raise ValueError(f"NetLogo BriefPop summary missing columns: {sorted(missing)}")

    table = summary.copy()
    if "behaviorspace_run" not in table.columns:
        table["behaviorspace_run"] = 1
    if "end_time" not in table.columns:
        table["end_time"] = ""
    if "end_timestamp" not in table.columns:
        table["end_timestamp"] = pd.NaT
    table["end_timestamp"] = pd.to_datetime(table["end_timestamp"], errors="coerce")
    table = table.sort_values(
        ["behaviorspace_run", "reach_id", "species", "end_timestamp", "end_time"],
        kind="mergesort",
    ).reset_index(drop=True)
    table["comparison_day"] = table.groupby(
        ["behaviorspace_run", "reach_id", "species"],
        dropna=False,
    ).cumcount()
    return table.rename(
        columns={
            "behaviorspace_run": "netlogo_run",
            "end_time": "netlogo_end_time",
            "abundance": "netlogo_abundance",
            "biomass_g": "netlogo_biomass_g",
            "mean_length_mm": "netlogo_mean_length_mm",
        }
    )[columns]


def _native_sequence(summary: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "scenario_id",
        "reach_id",
        "species",
        "comparison_day",
        "native_day",
        "native_official_date",
        "native_abundance",
        "native_biomass_g",
        "native_mean_length_mm",
    ]
    if summary.empty:
        return pd.DataFrame(columns=columns)

    required = {"reach_id", "species", "day", "abundance", "biomass_g", "mean_length_mm"}
    missing = required - set(summary.columns)
    if missing:
        raise ValueError(f"native IBM summary missing columns: {sorted(missing)}")

    table = summary.copy()
    if "scenario_id" not in table.columns:
        table["scenario_id"] = ""
    if "official_date" not in table.columns:
        table["official_date"] = ""
    table["day"] = pd.to_numeric(table["day"], errors="coerce")
    table = table.sort_values(
        ["reach_id", "species", "day"],
        kind="mergesort",
    ).reset_index(drop=True)
    fallback = table.groupby(["reach_id", "species"], dropna=False).cumcount()
    table["comparison_day"] = table["day"].fillna(fallback).astype(int)
    return table.rename(
        columns={
            "day": "native_day",
            "official_date": "native_official_date",
            "abundance": "native_abundance",
            "biomass_g": "native_biomass_g",
            "mean_length_mm": "native_mean_length_mm",
        }
    )[columns]


def _relative_delta(native: pd.Series, expected: pd.Series) -> pd.Series:
    delta = native - expected
    denominator = expected.abs()
    values = np.where(
        denominator > 0.0,
        delta / denominator,
        np.where(delta.abs() <= 0.0, 0.0, np.inf),
    )
    return pd.Series(values, index=native.index)


def compare_instream7_native_to_brief(
    native_summary: pd.DataFrame,
    netlogo_brief_summary: pd.DataFrame,
    *,
    abundance_tolerance: int = 0,
    biomass_relative_tolerance: float = 0.05,
    mean_length_tolerance_mm: float = 1.0,
) -> pd.DataFrame:
    # BriefPop lacks a numeric day column, so align by ordered snapshot within
    # each BehaviorSpace run, reach, and species.
    native = _native_sequence(native_summary)
    netlogo = _brief_sequence(netlogo_brief_summary)
    merged = netlogo.merge(
        native,
        on=["reach_id", "species", "comparison_day"],
        how="outer",
        sort=True,
    )
    columns = [
        "netlogo_run",
        "scenario_id",
        "reach_id",
        "species",
        "comparison_day",
        "netlogo_end_time",
        "native_day",
        "native_official_date",
        "netlogo_abundance",
        "native_abundance",
        "abundance_delta_native_minus_netlogo",
        "abundance_abs_delta",
        "netlogo_biomass_g",
        "native_biomass_g",
        "biomass_delta_native_minus_netlogo_g",
        "biomass_relative_delta",
        "netlogo_mean_length_mm",
        "native_mean_length_mm",
        "mean_length_delta_native_minus_netlogo_mm",
        "mean_length_abs_delta_mm",
        "abundance_pass",
        "biomass_pass",
        "mean_length_pass",
        "matched",
        "passed",
        "comparison_note",
    ]
    if merged.empty:
        return pd.DataFrame(columns=columns)

    for col in (
        "netlogo_abundance",
        "native_abundance",
        "netlogo_biomass_g",
        "native_biomass_g",
        "netlogo_mean_length_mm",
        "native_mean_length_mm",
    ):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")

    native_present = merged["native_abundance"].notna()
    netlogo_present = merged["netlogo_abundance"].notna()
    merged["matched"] = native_present & netlogo_present
    merged["abundance_delta_native_minus_netlogo"] = (
        merged["native_abundance"] - merged["netlogo_abundance"]
    )
    merged["abundance_abs_delta"] = merged[
        "abundance_delta_native_minus_netlogo"
    ].abs()
    merged["biomass_delta_native_minus_netlogo_g"] = (
        merged["native_biomass_g"] - merged["netlogo_biomass_g"]
    )
    merged["biomass_relative_delta"] = _relative_delta(
        merged["native_biomass_g"],
        merged["netlogo_biomass_g"],
    )
    merged["mean_length_delta_native_minus_netlogo_mm"] = (
        merged["native_mean_length_mm"] - merged["netlogo_mean_length_mm"]
    )
    merged["mean_length_abs_delta_mm"] = merged[
        "mean_length_delta_native_minus_netlogo_mm"
    ].abs()

    both_mean_length_missing = (
        merged["native_mean_length_mm"].isna()
        & merged["netlogo_mean_length_mm"].isna()
    )
    merged["abundance_pass"] = (
        merged["matched"] & (merged["abundance_abs_delta"] <= abundance_tolerance)
    )
    merged["biomass_pass"] = (
        merged["matched"]
        & (merged["biomass_relative_delta"].abs() <= biomass_relative_tolerance)
    )
    merged["mean_length_pass"] = (
        merged["matched"]
        & (
            (merged["mean_length_abs_delta_mm"] <= mean_length_tolerance_mm)
            | both_mean_length_missing
        )
    )
    merged["passed"] = (
        merged["abundance_pass"] & merged["biomass_pass"] & merged["mean_length_pass"]
    )
    merged["comparison_note"] = np.select(
        [
            ~native_present,
            ~netlogo_present,
            merged["passed"],
        ],
        [
            "missing_native",
            "missing_netlogo",
            "within_tolerance",
        ],
        default="outside_tolerance",
    )
    return merged[columns].sort_values(
        ["netlogo_run", "scenario_id", "reach_id", "species", "comparison_day"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)


def summarize_instream7_parity(comparison: pd.DataFrame) -> pd.DataFrame:
    """Summarize pass/fail counts from a native-vs-inSTREAM comparison table."""

    columns = [
        "scenario_id",
        "reach_id",
        "species",
        "rows",
        "passed_rows",
        "failed_rows",
        "matched_rows",
        "max_abundance_abs_delta",
        "max_biomass_relative_delta_abs",
        "max_mean_length_abs_delta_mm",
        "passed",
    ]
    if comparison.empty:
        return pd.DataFrame(columns=columns)
    table = comparison.copy()
    table["passed"] = table["passed"].fillna(False).astype(bool)
    table["matched"] = table["matched"].fillna(False).astype(bool)
    table["biomass_relative_delta_abs"] = pd.to_numeric(
        table["biomass_relative_delta"],
        errors="coerce",
    ).abs()
    grouped = table.groupby(["scenario_id", "reach_id", "species"], dropna=False)
    summary = grouped.agg(
        rows=("passed", "size"),
        passed_rows=("passed", "sum"),
        matched_rows=("matched", "sum"),
        max_abundance_abs_delta=("abundance_abs_delta", "max"),
        max_biomass_relative_delta_abs=("biomass_relative_delta_abs", "max"),
        max_mean_length_abs_delta_mm=("mean_length_abs_delta_mm", "max"),
    ).reset_index()
    summary["failed_rows"] = summary["rows"] - summary["passed_rows"]
    summary["passed"] = summary["failed_rows"] == 0
    return summary[columns].sort_values(
        ["scenario_id", "reach_id", "species"],
        kind="mergesort",
    ).reset_index(drop=True)


def write_instream7_parity_report(
    comparison: pd.DataFrame,
    output_path: str | Path,
) -> dict[str, str]:
    """Write detailed and summarized inSTREAM parity reports."""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(out, index=False)
    summary_path = out.with_name(f"{out.stem}_summary{out.suffix}")
    summarize_instream7_parity(comparison).to_csv(summary_path, index=False)
    return {
        "instream7_parity_detail": str(out),
        "instream7_parity_summary": str(summary_path),
    }


def _column_lookup(columns: pd.Index, name: str) -> str:
    by_norm = {str(col).lower(): str(col) for col in columns}
    found = by_norm.get(name.lower())
    if found is None:
        raise ValueError(f"shapefile missing field {name!r}")
    return found


def read_reach_static_cells(reach: Instream7Reach) -> pd.DataFrame:
    """Read official GIS cell attributes for one reach."""

    import geopandas as gpd

    gdf = gpd.read_file(reach.shapefile)
    cell_col = _column_lookup(gdf.columns, reach.cell_id_field)
    reach_col = _column_lookup(gdf.columns, reach.reach_field)
    area_col = _column_lookup(gdf.columns, reach.area_field)
    shelter_col = _column_lookup(gdf.columns, reach.velocity_shelter_field)
    hiding_col = _column_lookup(gdf.columns, reach.hiding_places_field)
    spawn_col = _column_lookup(gdf.columns, reach.spawning_fraction_field)

    sub = gdf[gdf[reach_col].astype(str) == reach.reach_id].copy()
    if sub.empty:
        raise ValueError(f"{reach.shapefile} has no cells for reach {reach.reach_id!r}")
    hiding_places = pd.to_numeric(sub[hiding_col], errors="coerce").fillna(0.0)
    shelter = pd.to_numeric(sub[shelter_col], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    spawning = pd.to_numeric(sub[spawn_col], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    return pd.DataFrame(
        {
            "cell_id": sub[cell_col].astype(str).to_numpy(),
            "reach_id": reach.reach_id,
            "area_m2": pd.to_numeric(sub[area_col], errors="coerce").fillna(0.0).to_numpy(),
            "hiding_cover": np.maximum(shelter.to_numpy(dtype=float), np.clip(hiding_places / 10.0, 0.0, 1.0)),
            "feeding_cover": shelter.to_numpy(dtype=float),
            "spawning_cover": spawning.to_numpy(dtype=float),
        }
    )


def _hydraulic_wide(path: Path, role: str) -> pd.DataFrame:
    table = read_instream_exchange(path).table
    if role not in table.columns:
        raise ValueError(f"{path} did not import as {role}")
    return (
        table.pivot(index="cell_id", columns="discharge_m3s", values=role)
        .sort_index(axis=1)
        .reset_index()
    )


def _interpolate_hydraulic_table(wide: pd.DataFrame, role: str, flow_m3s: float) -> pd.DataFrame:
    flows = np.asarray([float(col) for col in wide.columns if col != "cell_id"], dtype=float)
    if len(flows) == 0:
        raise ValueError(f"hydraulic table for {role} has no flow columns")
    min_flow = float(np.nanmin(flows))
    max_flow = float(np.nanmax(flows))
    if flow_m3s < min_flow or flow_m3s > max_flow:
        raise ValueError(
            f"flow {flow_m3s:g} m3/s is outside {role} lookup range "
            f"{min_flow:g}..{max_flow:g} m3/s"
        )
    values = wide.drop(columns=["cell_id"]).to_numpy(dtype=float)
    interpolated = np.asarray(
        [np.interp(flow_m3s, flows, row) for row in values],
        dtype=float,
    )
    return pd.DataFrame(
        {
            "cell_id": wide["cell_id"].astype(str).to_numpy(),
            role: interpolated,
        }
    )


def _build_reach_habitat_cells_from_tables(
    static: pd.DataFrame,
    depth_wide: pd.DataFrame,
    velocity_wide: pd.DataFrame,
    *,
    flow_m3s: float,
    temperature_c: float,
    turbidity_ntu: float,
) -> pd.DataFrame:
    depth = _interpolate_hydraulic_table(depth_wide, "depth_m", flow_m3s)
    velocity = _interpolate_hydraulic_table(
        velocity_wide,
        "velocity_ms",
        flow_m3s,
    )
    cells = static.merge(depth, on="cell_id", how="inner").merge(velocity, on="cell_id", how="inner")
    cells["discharge_m3s"] = float(flow_m3s)
    cells["temperature_c"] = float(temperature_c)
    cells["turbidity_ntu"] = float(turbidity_ntu)
    return cells


def build_reach_habitat_cells(
    reach: Instream7Reach,
    *,
    flow_m3s: float,
    temperature_c: float,
    turbidity_ntu: float,
) -> pd.DataFrame:
    """Build OpenLimno habitat-cell inputs for one official reach/day."""

    static = read_reach_static_cells(reach)
    return _build_reach_habitat_cells_from_tables(
        static,
        _hydraulic_wide(reach.depth_file, "depth_m"),
        _hydraulic_wide(reach.velocity_file, "velocity_ms"),
        flow_m3s=flow_m3s,
        temperature_c=temperature_c,
        turbidity_ntu=turbidity_ntu,
    )


def _month_day_to_doy(value: str, *, default: int) -> int:
    try:
        parsed = datetime.strptime(value, "%m/%d")
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%m/%d/%Y")
        except ValueError:
            return default
    return int(parsed.strftime("%j"))


def _species_parameter(
    case: Instream7Case,
    name: str,
    species: str,
    default: float,
) -> float:
    values = case.parameters.get(name)
    if not isinstance(values, tuple) or not values:
        return default
    try:
        idx = case.species.index(species)
    except ValueError:
        idx = 0
    value = values[min(idx, len(values) - 1)]
    return float(value)


def _species_string_parameter(
    case: Instream7Case,
    name: str,
    species: str,
    default: str,
) -> str:
    values = case.parameters.get(name)
    if not isinstance(values, tuple) or not values:
        return default
    try:
        idx = case.species.index(species)
    except ValueError:
        idx = 0
    return str(values[min(idx, len(values) - 1)])


def species_profile_from_official_case(case: Instream7Case, species: str) -> SpeciesProfile:
    """Map official inSTREAM 7 species parameters into the native IBM profile."""

    maturity_cm = _species_parameter(case, "trout-spawn-min-length", species, 12.0)
    if maturity_cm <= 0.0:
        maturity_cm = 40.0 if "chinook" in species.lower() or "salmon" in species.lower() else 12.0
    fecund_mult = _species_parameter(case, "trout-spawn-fecund-mult", species, 0.18)
    fecund_exp = _species_parameter(case, "trout-spawn-fecund-exp", species, 2.51)
    egg_viability = _species_parameter(case, "trout-spawn-egg-viability", species, 0.8)
    fry_cm = _species_parameter(case, "trout-emerge-length-mode", species, 2.8)
    weight_a = _species_parameter(case, "trout-weight-A", species, 0.0115)
    weight_b = _species_parameter(case, "trout-weight-B", species, 3.0)
    cmax_a = _species_parameter(case, "trout-cmax-A", species, 0.628)
    cmax_b = _species_parameter(case, "trout-cmax-B", species, 0.7)
    resp_a = _species_parameter(case, "trout-resp-A", species, 36.0)
    resp_c = _species_parameter(case, "trout-resp-C", species, 0.002)
    redd_dewater_surv = _species_parameter(case, "mort-redd-dewater-surv", species, 0.9)
    redd_scour_depth_cm = _species_parameter(case, "mort-redd-scour-depth", species, 5.0)
    high_temp_t1 = _species_parameter(case, "mort-high-temp-T1", species, 30.0)
    high_temp_t9 = _species_parameter(case, "mort-high-temp-T9", species, 25.8)
    cmax_optimum = _species_parameter(case, "cmax-temperature-optimum", species, 12.0)
    start = _species_string_parameter(case, "trout-spawn-start-day", species, "4/1")
    end = _species_string_parameter(case, "trout-spawn-end-day", species, "6/30")
    return SpeciesProfile(
        species=species,
        thermal_min_c=0.0,
        thermal_optimum_c=cmax_optimum,
        thermal_max_c=max(high_temp_t1, high_temp_t9),
        weight_a_g_per_cm_b=weight_a,
        weight_b=weight_b,
        max_consumption_fraction=max(0.001, min(0.08, cmax_a * 0.02)),
        respiration_fraction=max(0.0005, min(0.03, resp_a * 0.00012)),
        activity_respiration_fraction=max(0.0005, min(0.03, resp_c * 3.0 + cmax_b * 0.001)),
        base_daily_survival=0.999,
        predation_base_risk=0.001,
        predation_csi_risk=0.002,
        thermal_stress_mortality=0.005,
        maturity_length_mm=maturity_cm * 10.0,
        spawn_start_day=_month_day_to_doy(start, default=91),
        spawn_end_day=_month_day_to_doy(end, default=181),
        fecundity_per_female=fecund_mult * (maturity_cm**fecund_exp),
        fecundity_length_exponent=fecund_exp,
        fecundity_reference_length_mm=maturity_cm * 10.0,
        egg_to_fry_survival=max(0.001, min(1.0, egg_viability * 0.02)),
        redd_dewatering_mortality=max(0.0, min(1.0, 1.0 - redd_dewater_surv)),
        redd_min_depth_m=max(0.0, redd_scour_depth_cm / 100.0),
        fry_length_mm=fry_cm * 10.0,
    )


def build_population_from_official_initial(
    initial_population: pd.DataFrame,
    *,
    reach_id: str,
    species: str,
    seed: int,
    profile: SpeciesProfile | None = None,
) -> pd.DataFrame:
    """Expand official initial-population strata into native IBM individuals."""

    rows = initial_population[
        (initial_population["Reach"].astype(str) == reach_id)
        & (initial_population["Species"].astype(str) == species)
    ]
    rng = np.random.default_rng(seed)
    frames: list[pd.DataFrame] = []
    next_id = 0
    for _, row in rows.iterrows():
        n = int(row["Number"])
        if n <= 0:
            continue
        min_cm = float(row["Length min"])
        mode_cm = float(row["Length mode"])
        max_cm = float(row["Length max"])
        lengths_mm = rng.triangular(min_cm, mode_cm, max_cm, n) * 10.0
        frames.append(
            pd.DataFrame(
                {
                    "fish_id": np.arange(next_id, next_id + n, dtype=int),
                    "species": species,
                    "age_days": np.full(n, int(row["Age"]) * 365, dtype=int),
                    "length_mm": lengths_mm,
                    "mass_g": profile.weight_a_g_per_cm_b * (lengths_mm / 10.0) ** profile.weight_b
                    if profile is not None
                    else 1.15e-5 * lengths_mm**3.0,
                    "cell_id": np.full(n, "", dtype=object),
                    "alive": np.ones(n, dtype=bool),
                }
            )
        )
        next_id += n
    if not frames:
        return pd.DataFrame(
            columns=["fish_id", "species", "age_days", "length_mm", "mass_g", "cell_id", "alive"]
        )
    return pd.concat(frames, ignore_index=True)


def _case_inventory_rows(case: Instream7Case, initial: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    adult_arrivals = (
        read_official_adult_arrivals(case.adult_arrival_file)
        if case.adult_arrival_file is not None and case.adult_arrival_file.exists()
        else pd.DataFrame()
    )
    for reach in case.reaches:
        static = read_reach_static_cells(reach)
        time_series = read_official_time_series(reach.time_series_file)
        depth = read_instream_exchange(reach.depth_file).table
        velocity = read_instream_exchange(reach.velocity_file).table
        reach_initial = initial[initial["Reach"].astype(str) == reach.reach_id]
        reach_adult_arrivals = (
            adult_arrivals[adult_arrivals["Reach"].astype(str) == reach.reach_id]
            if not adult_arrivals.empty
            else adult_arrivals
        )
        rows.append(
            {
                "case_id": case.case_id,
                "reach_id": reach.reach_id,
                "species": "|".join(case.species),
                "start_date": case.start_date,
                "end_date": case.end_date,
                "n_initial_fish": int(reach_initial["Number"].sum()),
                "n_initial_strata": int(len(reach_initial)),
                "n_adult_arrival_fish": int(reach_adult_arrivals["Number"].sum())
                if not reach_adult_arrivals.empty
                else 0,
                "n_adult_arrival_strata": int(len(reach_adult_arrivals)),
                "n_cells": int(static["cell_id"].nunique()),
                "n_depth_flows": int(depth["discharge_m3s"].nunique()),
                "n_velocity_flows": int(velocity["discharge_m3s"].nunique()),
                "n_time_series_rows": int(len(time_series)),
                "min_flow_m3s": float(time_series["flow_m3s"].min()),
                "max_flow_m3s": float(time_series["flow_m3s"].max()),
                "min_depth_m": float(depth["depth_m"].min()),
                "max_depth_m": float(depth["depth_m"].max()),
                "min_velocity_ms": float(velocity["velocity_ms"].min()),
                "max_velocity_ms": float(velocity["velocity_ms"].max()),
            }
        )
    return rows


def _time_series_window(case: Instream7Case, reach: Instream7Reach, days: int) -> pd.DataFrame:
    time_series = read_official_time_series(reach.time_series_file)
    start = pd.to_datetime(case.start_date, errors="coerce")
    if pd.notna(start):
        filtered = time_series[time_series["date"] >= start]
        if not filtered.empty:
            time_series = filtered
    return time_series.head(days).reset_index(drop=True)



def _next_global_fish_id_after(frame: pd.DataFrame, current_next_id: int) -> int:
    if frame.empty or "fish_id" not in frame:
        return current_next_id
    max_id = pd.to_numeric(frame["fish_id"], errors="coerce").max()
    if pd.isna(max_id):
        return current_next_id
    return max(current_next_id, int(max_id) + 1)


def run_instream7_official_benchmark(
    root: str | Path,
    output_dir: str | Path,
    *,
    case_ids: tuple[str, ...] | None = None,
    days: int = 7,
    seed: int = 42,
    stochastic: bool = True,
) -> Instream7BenchmarkResult:
    """Run native IBM strata against official inSTREAM 7 example inputs."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    selected = set(case_ids or ())
    cases = [
        case
        for case in discover_instream7_cases(root)
        if not selected or case.case_id in selected
    ]
    if not cases:
        raise ValueError(f"No inSTREAM 7 cases selected by {sorted(selected)}")

    inventory_rows: list[dict[str, object]] = []
    summary_frames: list[pd.DataFrame] = []
    individual_frames: list[pd.DataFrame] = []
    cell_use_frames: list[pd.DataFrame] = []
    event_frames: list[pd.DataFrame] = []
    redd_frames: list[pd.DataFrame] = []
    next_global_fish_id = 0

    for case_idx, case in enumerate(cases):
        initial = read_official_initial_population(case.initial_population_file)
        adult_arrivals = (
            read_official_adult_arrivals(case.adult_arrival_file)
            if case.adult_arrival_file is not None and case.adult_arrival_file.exists()
            else pd.DataFrame()
        )
        inventory_rows.extend(_case_inventory_rows(case, initial))
        if len(case.reaches) > 1:
            reach_contexts: list[dict[str, object]] = []
            for reach_order, reach in enumerate(case.reaches):
                static_cells = read_reach_static_cells(reach)
                static_cells["reach_order"] = reach_order
                reach_contexts.append(
                    {
                        "reach": reach,
                        "reach_order": reach_order,
                        "time_series": _time_series_window(case, reach, days),
                        "static_cells": static_cells,
                        "depth_wide": _hydraulic_wide(reach.depth_file, "depth_m"),
                        "velocity_wide": _hydraulic_wide(reach.velocity_file, "velocity_ms"),
                    }
                )
            for species_idx, species in enumerate(case.species):
                run_seed = seed + (case_idx * 10_000) + (species_idx * 100)
                profile = replace(
                    species_profile_from_official_case(case, species),
                    base_daily_survival=0.9995,
                    predation_base_risk=0.0005,
                    predation_csi_risk=0.001,
                    thermal_stress_mortality=0.003,
                    cross_reach_movement_rate=0.11,
                    cross_reach_movement_min_length_mm=70.0,
                    cross_reach_movement_length_scale_mm=120.0,
                    cross_reach_movement_max_steps=1,
                    cross_reach_interior_movement_multiplier=0.6,
                    cross_reach_upstream_bias=2.5,
                    cross_reach_habitat_utility_weight=0.35,
                )
                fish_frames: list[pd.DataFrame] = []
                scheduled_frames: list[pd.DataFrame] = []
                habitat_frames: list[pd.DataFrame] = []
                forcing_rows: list[dict[str, object]] = []
                for context in reach_contexts:
                    reach = context["reach"]
                    if not isinstance(reach, Instream7Reach):
                        continue
                    reach_order = context["reach_order"]
                    if not isinstance(reach_order, int):
                        continue
                    fish = build_population_from_official_initial(
                        initial,
                        reach_id=reach.reach_id,
                        species=species,
                        seed=run_seed + len(fish_frames),
                        profile=profile,
                    )
                    if not fish.empty:
                        fish["fish_id"] = pd.to_numeric(fish["fish_id"], errors="raise").astype(int)
                        fish["fish_id"] = fish["fish_id"] + next_global_fish_id
                        fish["reach_id"] = reach.reach_id
                        fish["reach_order"] = reach_order
                        next_global_fish_id = int(fish["fish_id"].max()) + 1
                        fish_frames.append(fish)
                    scheduled = build_population_from_official_adult_arrivals(
                        adult_arrivals,
                        reach_id=reach.reach_id,
                        species=species,
                        start_date=case.start_date,
                        days=days,
                        seed=run_seed + 50_000 + len(scheduled_frames),
                        profile=profile,
                        first_fish_id=next_global_fish_id,
                    )
                    if not scheduled.empty:
                        scheduled["reach_order"] = reach_order
                        next_global_fish_id = int(scheduled["fish_id"].max()) + 1
                        scheduled_frames.append(scheduled)
                    time_series = context["time_series"]
                    static_cells = context["static_cells"]
                    depth_wide = context["depth_wide"]
                    velocity_wide = context["velocity_wide"]
                    if not isinstance(time_series, pd.DataFrame):
                        continue
                    if not isinstance(static_cells, pd.DataFrame):
                        continue
                    if not isinstance(depth_wide, pd.DataFrame):
                        continue
                    if not isinstance(velocity_wide, pd.DataFrame):
                        continue
                    for day_idx, forcing in enumerate(time_series.itertuples(index=False), start=0):
                        cells = _build_reach_habitat_cells_from_tables(
                            static_cells,
                            depth_wide,
                            velocity_wide,
                            flow_m3s=float(forcing.flow_m3s),
                            temperature_c=float(forcing.temperature_c),
                            turbidity_ntu=float(forcing.turbidity_ntu),
                        )
                        cells["time_index"] = day_idx
                        cells["reach_order"] = reach_order
                        habitat_frames.append(cells)
                        forcing_date = pd.Timestamp(forcing.date)
                        forcing_rows.append(
                            {
                                "reach_id": reach.reach_id,
                                "day": day_idx + 1,
                                "official_date": str(forcing_date.date()),
                                "flow_m3s": float(forcing.flow_m3s),
                                "temperature_c": float(forcing.temperature_c),
                                "turbidity_ntu": float(forcing.turbidity_ntu),
                            }
                        )

                if (not fish_frames and not scheduled_frames) or not habitat_frames:
                    continue
                fish = (
                    pd.concat(fish_frames, ignore_index=True)
                    if fish_frames
                    else _empty_official_population()
                )
                scheduled_population = (
                    pd.concat(scheduled_frames, ignore_index=True) if scheduled_frames else None
                )
                habitat = pd.concat(habitat_frames, ignore_index=True)
                first_ts = reach_contexts[0]["time_series"]
                if not isinstance(first_ts, pd.DataFrame) or first_ts.empty:
                    continue
                first_date = pd.Timestamp(first_ts["date"].iloc[0])
                result = run_native_ibm(
                    habitat,
                    fish,
                    profile=profile,
                    scheduled_population=scheduled_population,
                    config=NativeIBMConfig(
                        days=max(len(context["time_series"]) for context in reach_contexts),
                        seed=run_seed,
                        start_day=int(first_date.dayofyear),
                        start_year=int(first_date.year),
                        scenario_id=case.case_id,
                        reach_id="__multi__",
                        stochastic=stochastic,
                    ),
                )

                summary = result.population_summary.copy()
                summary["official_date"] = ""
                summary["flow_m3s"] = np.nan
                summary["temperature_c"] = np.nan
                summary["turbidity_ntu"] = np.nan
                forcing_lookup = pd.DataFrame.from_records(forcing_rows)
                for forcing_row in forcing_lookup.to_dict("records"):
                    mask = (
                        (summary["day"] == int(forcing_row["day"]))
                        & (summary["reach_id"].astype(str) == str(forcing_row["reach_id"]))
                    )
                    for column in (
                        "official_date",
                        "flow_m3s",
                        "temperature_c",
                        "turbidity_ntu",
                    ):
                        summary.loc[mask, column] = forcing_row[column]
                summary_frames.append(summary)

                if not result.cell_use.empty:
                    cell_use = result.cell_use.copy()
                    cell_use["species"] = species
                    cell_use_frames.append(cell_use)
                if not result.events.empty:
                    events = result.events.copy()
                    events["species"] = species
                    event_frames.append(events)
                final_individuals = result.final_individuals.copy()
                final_individuals["scenario_id"] = case.case_id
                if "reach_id" not in final_individuals:
                    final_individuals["reach_id"] = ""
                individual_frames.append(final_individuals)
                if not result.redds.empty:
                    redds = result.redds.copy()
                    redds["scenario_id"] = case.case_id
                    if "reach_id" not in redds:
                        redds["reach_id"] = ""
                    redds["species"] = species
                    redd_frames.append(redds)
                next_global_fish_id = _next_global_fish_id_after(
                    final_individuals,
                    next_global_fish_id,
                )
            continue

        for reach_idx, reach in enumerate(case.reaches):
            time_series = _time_series_window(case, reach, days)
            static_cells = read_reach_static_cells(reach)
            depth_wide = _hydraulic_wide(reach.depth_file, "depth_m")
            velocity_wide = _hydraulic_wide(reach.velocity_file, "velocity_ms")
            for species_idx, species in enumerate(case.species):
                run_seed = seed + (case_idx * 10_000) + (reach_idx * 1_000) + (species_idx * 100)
                profile = species_profile_from_official_case(case, species)
                fish = build_population_from_official_initial(
                    initial,
                    reach_id=reach.reach_id,
                    species=species,
                    seed=run_seed,
                    profile=profile,
                )
                if not fish.empty:
                    fish["fish_id"] = pd.to_numeric(fish["fish_id"], errors="raise").astype(int)
                    fish["fish_id"] = fish["fish_id"] + next_global_fish_id
                    next_global_fish_id = int(fish["fish_id"].max()) + 1
                scheduled_population = build_population_from_official_adult_arrivals(
                    adult_arrivals,
                    reach_id=reach.reach_id,
                    species=species,
                    start_date=case.start_date,
                    days=days,
                    seed=run_seed + 50_000,
                    profile=profile,
                    first_fish_id=next_global_fish_id,
                )
                if not scheduled_population.empty:
                    next_global_fish_id = int(scheduled_population["fish_id"].max()) + 1
                if fish.empty and scheduled_population.empty:
                    continue
                reach_habitat_frames: list[pd.DataFrame] = []
                reach_forcing_rows: list[dict[str, object]] = []
                for day_idx, forcing in enumerate(time_series.itertuples(index=False), start=0):
                    cells = _build_reach_habitat_cells_from_tables(
                        static_cells,
                        depth_wide,
                        velocity_wide,
                        flow_m3s=float(forcing.flow_m3s),
                        temperature_c=float(forcing.temperature_c),
                        turbidity_ntu=float(forcing.turbidity_ntu),
                    )
                    cells["time_index"] = day_idx
                    forcing_date = pd.Timestamp(forcing.date)
                    reach_habitat_frames.append(cells)
                    reach_forcing_rows.append(
                        {
                            "day": day_idx + 1,
                            "official_date": str(forcing_date.date()),
                            "flow_m3s": float(forcing.flow_m3s),
                            "temperature_c": float(forcing.temperature_c),
                            "turbidity_ntu": float(forcing.turbidity_ntu),
                        }
                    )

                if not reach_habitat_frames:
                    continue

                habitat = pd.concat(reach_habitat_frames, ignore_index=True)
                first_date = pd.Timestamp(time_series["date"].iloc[0])
                result = run_native_ibm(
                    habitat,
                    fish if not fish.empty else _empty_official_population(),
                    profile=profile,
                    scheduled_population=scheduled_population,
                    config=NativeIBMConfig(
                        days=len(time_series),
                        seed=run_seed,
                        start_day=int(first_date.dayofyear),
                        start_year=int(first_date.year),
                        scenario_id=case.case_id,
                        reach_id=reach.reach_id,
                        stochastic=stochastic,
                    ),
                )

                summary = result.population_summary.copy()
                summary["official_date"] = ""
                summary["flow_m3s"] = np.nan
                summary["temperature_c"] = np.nan
                summary["turbidity_ntu"] = np.nan
                forcing_lookup = pd.DataFrame.from_records(reach_forcing_rows).set_index("day")
                for day, forcing_row in forcing_lookup.iterrows():
                    mask = summary["day"] == int(day)
                    forcing_columns = (
                        "official_date",
                        "flow_m3s",
                        "temperature_c",
                        "turbidity_ntu",
                    )
                    for column in forcing_columns:
                        summary.loc[mask, column] = forcing_row[column]
                summary_frames.append(summary)

                if not result.cell_use.empty:
                    cell_use = result.cell_use.copy()
                    cell_use["species"] = species
                    cell_use_frames.append(cell_use)
                if not result.events.empty:
                    events = result.events.copy()
                    events["species"] = species
                    event_frames.append(events)
                final_individuals = result.final_individuals.copy()
                final_individuals["scenario_id"] = case.case_id
                final_individuals["reach_id"] = reach.reach_id
                individual_frames.append(final_individuals)
                if not result.redds.empty:
                    redds = result.redds.copy()
                    redds["scenario_id"] = case.case_id
                    redds["reach_id"] = reach.reach_id
                    redds["species"] = species
                    redd_frames.append(redds)
                next_global_fish_id = _next_global_fish_id_after(
                    final_individuals,
                    next_global_fish_id,
                )

    inventory = pd.DataFrame.from_records(inventory_rows)
    population_summary = (
        pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
    )
    final_individuals = (
        pd.concat(individual_frames, ignore_index=True) if individual_frames else pd.DataFrame()
    )
    cell_use = pd.concat(cell_use_frames, ignore_index=True) if cell_use_frames else pd.DataFrame()
    events = (
        pd.concat(event_frames, ignore_index=True)
        if event_frames
        else pd.DataFrame(columns=_NATIVE_EVENT_COLUMNS)
    )
    redds = (
        pd.concat(redd_frames, ignore_index=True)
        if redd_frames
        else pd.DataFrame(columns=_NATIVE_REDD_COLUMNS)
    )

    tables = {
        "instream7_official_inventory": inventory,
        "instream7_native_population_summary": population_summary,
        "instream7_native_final_individuals": final_individuals,
        "instream7_native_cell_use": cell_use,
        "instream7_native_events": events,
        "instream7_native_redds": redds,
    }
    paths: dict[str, str] = {}
    for stem, table in tables.items():
        path = out / f"{stem}.csv"
        table.to_csv(path, index=False)
        paths[stem] = str(path)

    return Instream7BenchmarkResult(
        inventory=inventory,
        population_summary=population_summary,
        final_individuals=final_individuals,
        cell_use=cell_use,
        events=events,
        redds=redds,
        paths=paths,
    )


__all__ = [
    "Instream7BenchmarkResult",
    "Instream7Case",
    "Instream7NetLogoReferenceResult",
    "Instream7Reach",
    "build_population_from_official_adult_arrivals",
    "build_population_from_official_initial",
    "build_reach_habitat_cells",
    "compare_instream7_native_to_brief",
    "discover_instream7_cases",
    "extract_instream7_archive",
    "parse_instream7_case",
    "prepare_instream7_netlogo_reference_case",
    "read_instream7_brief_population",
    "read_official_adult_arrivals",
    "read_official_initial_population",
    "read_official_time_series",
    "run_instream7_netlogo_reference",
    "run_instream7_official_benchmark",
    "species_profile_from_official_case",
    "summarize_instream7_brief_population",
    "summarize_instream7_parity",
    "write_instream7_netlogo_setup_file",
    "write_instream7_parity_report",
]
