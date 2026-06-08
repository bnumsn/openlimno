"""Optional MIKE Powered by DHI interoperability adapters.

The MIKE ecosystem is important for ecological-flow studies, but its Python
readers are optional platform dependencies. This module keeps the OpenLimno
core importable without DHI tooling while exposing a stable adapter when
``mikeio`` or ``mikeio1d`` is available.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MIKE_DFS_SUFFIXES = (".dfs0", ".dfs1", ".dfs2", ".dfs3", ".dfsu", ".mesh")
MIKE_1D_SUFFIXES = (".res1d", ".res11", ".xns11", ".prf", ".crf", ".xrf")
MIKE_1D_LINUX_DOTNET_HINT = (
    "MIKE 1D/XNS11 import uses DHI mikeio1d, which needs the OS .NET Runtime "
    "on Linux. Install .NET Runtime 8.0 (for Ubuntu: sudo apt install "
    "dotnet-runtime-8.0), then rerun `openlimno preprocess diagnose-model "
    "--source mike-1d`."
)


@dataclass(frozen=True)
class MIKEInspection:
    """Metadata report for a MIKE file."""

    path: str
    source_key: str
    file_kind: str
    item_names: tuple[str, ...]
    geometry_type: str | None
    n_elements: int | None
    n_nodes: int | None
    n_timesteps: int | None
    start_time: str | None
    end_time: str | None
    output_table: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MIKEImportSummary:
    """Small import report for MIKE adapters."""

    source_key: str
    file_kind: str
    output_table: str
    n_rows: int
    item_names: tuple[str, ...]
    time_index: int | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MIKEImportResult:
    """MIKE staging table plus import summary."""

    table: pd.DataFrame
    summary: MIKEImportSummary


@dataclass(frozen=True)
class MIKERuntimeDiagnostic:
    """Environment diagnostic for optional MIKE readers."""

    source_key: str
    module_name: str
    module_installed: bool
    module_version: str | None
    dotnet_required: bool
    dotnet_cli: str | None
    dotnet_ok: bool | None
    ready: bool
    install_hint: str
    warnings: tuple[str, ...] = ()


def _require_module(module_name: str, install_hint: str) -> Any:
    try:
        return import_module(module_name)
    except ModuleNotFoundError as e:
        raise ImportError(
            f"MIKE import requires optional dependency {module_name!r}. "
            f"Install OpenLimno with the 'mike' extra or install {install_hint}."
        ) from e


def diagnose_mike_environment(source_key: str = "mike-dfs") -> MIKERuntimeDiagnostic:
    """Check whether the optional MIKE reader stack is ready on this machine."""

    if source_key not in {"mike-dfs", "mike-1d"}:
        raise ValueError("source_key must be 'mike-dfs' or 'mike-1d'.")

    module_name = "mikeio1d" if source_key == "mike-1d" else "mikeio"
    install_hint = (
        'Install with `pip install "openlimno[mike]"` or `pip install mikeio1d`. '
        f"{MIKE_1D_LINUX_DOTNET_HINT}"
        if source_key == "mike-1d"
        else 'Install with `pip install "openlimno[mike]"` or `pip install mikeio`.'
    )
    warnings: list[str] = []
    module_installed = False
    module_ready = False
    module_version: str | None = None

    try:
        module = import_module(module_name)
        module_installed = True
        module_ready = True
        version = getattr(module, "__version__", None)
        module_version = None if version is None else str(version)
    except ModuleNotFoundError as exc:
        warnings.append(f"Optional dependency {module_name!r} is not installed: {exc}")
    except RuntimeError as exc:
        module_installed = True
        warnings.append(f"Optional dependency {module_name!r} could not initialize: {exc}")

    dotnet_required = source_key == "mike-1d" and sys.platform.startswith("linux")
    dotnet_cli = shutil.which("dotnet") if dotnet_required else None
    dotnet_ok: bool | None = None
    if dotnet_required:
        if dotnet_cli is None:
            dotnet_ok = False
            warnings.append("Linux .NET Runtime was not found on PATH (`dotnet --info` failed).")
        else:
            try:
                completed = subprocess.run(
                    [dotnet_cli, "--info"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                dotnet_ok = completed.returncode == 0
                if not dotnet_ok:
                    message = (completed.stderr or completed.stdout).strip()
                    warnings.append(f"`dotnet --info` failed: {message}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                dotnet_ok = False
                warnings.append(f"`dotnet --info` could not run: {exc}")

    ready = module_ready and (dotnet_ok is not False)
    return MIKERuntimeDiagnostic(
        source_key=source_key,
        module_name=module_name,
        module_installed=module_installed,
        module_version=module_version,
        dotnet_required=dotnet_required,
        dotnet_cli=dotnet_cli,
        dotnet_ok=dotnet_ok,
        ready=ready,
        install_hint=install_hint,
        warnings=tuple(warnings),
    )


def _norm(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _item_name(item: Any) -> str:
    for attr in ("name", "Name"):
        value = getattr(item, attr, None)
        if value is not None:
            return str(value)
    return str(item)


def _item_names(obj: Any) -> tuple[str, ...]:
    items = getattr(obj, "items", None)
    if callable(items):
        items = items()
    if items is None:
        return ()
    return tuple(_item_name(item) for item in list(items))


def _maybe_len(value: Any) -> int | None:
    try:
        return len(value)
    except TypeError:
        return None


def _n_timesteps(obj: Any) -> int | None:
    for attr in ("n_timesteps", "n_time_steps", "number_of_time_steps"):
        value = getattr(obj, attr, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return _maybe_len(getattr(obj, "time", None))


def _time_endpoint(obj: Any, attr: str) -> str | None:
    value = getattr(obj, attr, None)
    return None if value is None else str(value)


def _open_mikeio(path: Path) -> Any:
    mikeio = _require_module("mikeio", "mikeio")
    if not hasattr(mikeio, "open"):
        raise ImportError("Installed 'mikeio' module does not expose mikeio.open().")
    return mikeio.open(str(path))


def _open_mike1d(path: Path) -> Any:
    try:
        mikeio1d = _require_module("mikeio1d", "mikeio1d")
        if hasattr(mikeio1d, "open"):
            return mikeio1d.open(str(path))
        if path.suffix.lower() == ".xns11" and hasattr(mikeio1d, "Xns11"):
            return mikeio1d.Xns11(str(path))
        if hasattr(mikeio1d, "Res1D"):
            return mikeio1d.Res1D(str(path))
    except RuntimeError as exc:
        raise RuntimeError(f"{MIKE_1D_LINUX_DOTNET_HINT} Original error: {exc}") from exc
    raise ImportError("Installed 'mikeio1d' module does not expose a supported opener.")


def _geometry_n(geometry: Any) -> int | None:
    if geometry is None:
        return None
    for attr in ("n_elements", "n_cells", "n_nodes"):
        value = getattr(geometry, attr, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    for attr in ("element_coordinates", "cell_coordinates"):
        coords = getattr(geometry, attr, None)
        if coords is not None:
            arr = np.asarray(coords)
            if arr.ndim >= 2:
                return int(arr.shape[0])
    x = getattr(geometry, "x", None)
    y = getattr(geometry, "y", None)
    if x is not None and y is not None:
        x_arr = np.asarray(x)
        y_arr = np.asarray(y)
        if x_arr.ndim == 1 and y_arr.ndim == 1:
            return int(x_arr.size * y_arr.size)
        if x_arr.shape == y_arr.shape:
            return int(x_arr.size)
    return None


def _geometry_nodes(geometry: Any) -> int | None:
    if geometry is None:
        return None
    value = getattr(geometry, "n_nodes", None)
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    coords = getattr(geometry, "node_coordinates", None)
    if coords is not None:
        arr = np.asarray(coords)
        if arr.ndim >= 2:
            return int(arr.shape[0])
    return None


def _geometry_type(geometry: Any) -> str | None:
    return None if geometry is None else type(geometry).__name__


def _output_table_for_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".xns11":
        return "cross_section_points"
    if suffix in {".dfs0", ".dfs1", ".res1d", ".res11", ".prf", ".crf", ".xrf"}:
        return "mike_timeseries"
    if suffix == ".mesh":
        return "mesh_cells"
    return "hydraulic_cells"


def _source_key_for_suffix(path: Path) -> str:
    return "mike-1d" if path.suffix.lower() in MIKE_1D_SUFFIXES else "mike-dfs"


def inspect_mike_file(path: str | Path) -> MIKEInspection:
    """Inspect a MIKE DFS/DFSU/1D file using optional DHI Python readers."""

    p = Path(path)
    suffix = p.suffix.lower()
    warnings: list[str] = []
    if suffix in MIKE_1D_SUFFIXES:
        obj = _open_mike1d(p)
        source_key = "mike-1d"
        geometry = None
        item_names = _mike1d_item_names(obj)
        n_elements = _mike1d_location_count(obj)
        n_nodes = _count_collection(getattr(obj, "nodes", None))
    else:
        obj = _open_mikeio(p)
        source_key = "mike-dfs"
        geometry = getattr(obj, "geometry", None)
        item_names = _item_names(obj)
        n_elements = _geometry_n(geometry)
        n_nodes = _geometry_nodes(geometry)

    if not item_names:
        warnings.append("No item/quantity names were exposed by the MIKE reader.")

    return MIKEInspection(
        path=str(p),
        source_key=source_key,
        file_kind=suffix.lstrip(".") or type(obj).__name__,
        item_names=item_names,
        geometry_type=_geometry_type(geometry),
        n_elements=n_elements,
        n_nodes=n_nodes,
        n_timesteps=_n_timesteps(obj),
        start_time=_time_endpoint(obj, "start_time"),
        end_time=_time_endpoint(obj, "end_time"),
        output_table=_output_table_for_suffix(p),
        warnings=tuple(warnings),
    )


def read_mike_file(path: str | Path, *, time_index: int | None = None) -> MIKEImportResult:
    """Read a MIKE file into an OpenLimno staging table."""

    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in MIKE_1D_SUFFIXES:
        result = _read_mike1d_file(p, time_index=time_index)
    elif suffix in {".dfs0", ".dfs1"}:
        result = _read_mikeio_timeseries(p, time_index=time_index)
    elif suffix == ".mesh":
        result = _read_mikeio_mesh(p)
    else:
        result = _read_mikeio_hydraulic_cells(p, time_index=time_index)

    result.table.attrs["openlimno_source_model"] = "MIKE Powered by DHI"
    result.table.attrs["openlimno_source_key"] = result.summary.source_key
    result.table.attrs["openlimno_output_table"] = result.summary.output_table
    return result


def _read_dataset(reader: Any, path: Path, time_index: int | None) -> Any:
    attempts: list[dict[str, Any]] = []
    if time_index is not None:
        attempts.extend([{"time": time_index}, {"time": [time_index]}])
    attempts.append({})
    if hasattr(reader, "read"):
        last_error: TypeError | None = None
        for kwargs in attempts:
            try:
                return reader.read(**kwargs)
            except TypeError as e:
                last_error = e
        if last_error is not None:
            raise last_error

    mikeio = _require_module("mikeio", "mikeio")
    if not hasattr(mikeio, "read"):
        raise ImportError(
            "Installed 'mikeio' module exposes neither reader.read() nor mikeio.read()."
        )
    for kwargs in attempts:
        try:
            return mikeio.read(str(path), **kwargs)
        except TypeError:
            continue
    return mikeio.read(str(path))


def _data_array(dataset: Any, idx: int, name: str) -> Any:
    try:
        return dataset[idx]
    except (KeyError, IndexError, TypeError):
        pass
    try:
        return dataset[name]
    except (KeyError, IndexError, TypeError):
        pass
    data = getattr(dataset, "data", None)
    if data is not None:
        return data[idx]
    raise KeyError(f"Cannot access MIKE dataset item {name!r}.")


def _values(obj: Any) -> np.ndarray:
    if hasattr(obj, "to_numpy") and callable(obj.to_numpy):
        arr = obj.to_numpy()
    elif hasattr(obj, "values"):
        arr = obj.values
    elif hasattr(obj, "data"):
        arr = obj.data
    else:
        arr = obj
    return np.asarray(np.ma.filled(arr, np.nan))


def _resolve_time_index(n_time: int, time_index: int | None) -> int:
    if n_time <= 0:
        raise ValueError("MIKE result dataset has zero time steps.")
    idx = -1 if time_index is None else time_index
    if idx < 0:
        idx = n_time + idx
    if idx < 0 or idx >= n_time:
        raise IndexError(f"time_index out of range: {time_index} for {n_time} time steps.")
    return idx


def _as_spatial_values(
    values: Any,
    n_cells: int | None,
    time_index: int | None,
) -> tuple[np.ndarray, int | None]:
    arr = _values(values).astype(float)
    arr = np.squeeze(arr)
    if arr.ndim == 0:
        raise ValueError("scalar MIKE item cannot be converted to cell values")
    if arr.ndim == 1:
        if n_cells is not None and arr.size != n_cells:
            raise ValueError(f"item length {arr.size} does not match n_cells {n_cells}")
        return arr, None
    if arr.ndim == 2:
        if n_cells is not None and arr.shape[-1] == n_cells:
            idx = _resolve_time_index(arr.shape[0], time_index)
            return arr[idx, :], idx
        if n_cells is not None and arr.shape[0] == n_cells:
            idx = _resolve_time_index(arr.shape[1], time_index)
            return arr[:, idx], idx
        if n_cells is None or arr.size == n_cells:
            return arr.reshape(-1), None
    if arr.ndim == 3:
        if n_cells is not None and arr.shape[1] == n_cells and arr.shape[2] in {2, 3}:
            idx = _resolve_time_index(arr.shape[0], time_index)
            return np.linalg.norm(arr[idx, :, :2], axis=1), idx
        if n_cells is not None and arr.shape[0] == n_cells and arr.shape[2] in {2, 3}:
            idx = _resolve_time_index(arr.shape[1], time_index)
            return np.linalg.norm(arr[:, idx, :2], axis=1), idx
        idx = _resolve_time_index(arr.shape[0], time_index)
        flat = arr[idx].reshape(-1)
        if n_cells is not None and flat.size != n_cells:
            raise ValueError(f"grid item length {flat.size} does not match n_cells {n_cells}")
        return flat, idx
    if arr.ndim == 4:
        idx = _resolve_time_index(arr.shape[0], time_index)
        flat = arr[idx, 0].reshape(-1)
        if n_cells is not None and flat.size != n_cells:
            raise ValueError(
                f"layered grid item length {flat.size} does not match n_cells {n_cells}"
            )
        return flat, idx
    raise ValueError(f"unsupported MIKE item shape {arr.shape}")


def _find_item(
    item_names: tuple[str, ...],
    includes: tuple[str, ...],
    excludes: tuple[str, ...] = (),
) -> str | None:
    include_norm = tuple(_norm(x) for x in includes)
    exclude_norm = tuple(_norm(x) for x in excludes)
    candidates: list[tuple[int, str]] = []
    for name in item_names:
        name_norm = _norm(name)
        if not all(tok in name_norm for tok in include_norm):
            continue
        if any(tok in name_norm for tok in exclude_norm):
            continue
        score = 10 if any(tok == name_norm for tok in include_norm) else 0
        candidates.append((score, name))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _find_velocity_component(
    item_names: tuple[str, ...], components: tuple[str, ...]
) -> str | None:
    for name in item_names:
        name_norm = _norm(name)
        if "velocity" not in name_norm and "vel" not in name_norm:
            continue
        for component in components:
            if (
                name_norm.startswith(f"{component}velocity")
                or name_norm.endswith(f"velocity{component}")
                or name_norm.startswith(f"{component}vel")
                or name_norm.endswith(f"vel{component}")
            ):
                return name
    return None


def _series_for_name(
    dataset: Any,
    item_names: tuple[str, ...],
    name: str,
    n_cells: int | None,
    time_index: int | None,
) -> tuple[np.ndarray, int | None]:
    idx = item_names.index(name)
    return _as_spatial_values(_data_array(dataset, idx, name), n_cells, time_index)


def _infer_n_cells(
    geometry: Any,
    dataset: Any,
    item_names: tuple[str, ...],
    candidate_names: list[str | None],
) -> int:
    n = _geometry_n(geometry)
    if n is not None:
        return n
    for name in candidate_names:
        if name is None:
            continue
        arr = np.squeeze(_values(_data_array(dataset, item_names.index(name), name)))
        if arr.ndim == 1:
            return int(arr.size)
        if arr.ndim == 2:
            return int(arr.shape[-1])
        if arr.ndim >= 3:
            return int(np.prod(arr.shape[1:]))
    raise ValueError("Cannot infer MIKE cell count from geometry or result items.")


def _coordinates_from_geometry(
    geometry: Any, n_cells: int
) -> tuple[np.ndarray | None, np.ndarray | None]:
    if geometry is None:
        return None, None
    for attr in ("element_coordinates", "cell_coordinates"):
        coords = getattr(geometry, attr, None)
        if coords is None:
            continue
        arr = np.asarray(coords, dtype=float)
        if arr.ndim == 2 and arr.shape[0] >= n_cells and arr.shape[1] >= 2:
            return arr[:n_cells, 0], arr[:n_cells, 1]

    x = getattr(geometry, "x", None)
    y = getattr(geometry, "y", None)
    if x is None or y is None:
        return None, None
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    if x_arr.ndim == 1 and y_arr.ndim == 1 and x_arr.size * y_arr.size == n_cells:
        xx, yy = np.meshgrid(x_arr, y_arr)
        return xx.reshape(-1), yy.reshape(-1)
    if x_arr.shape == y_arr.shape and x_arr.size == n_cells:
        return x_arr.reshape(-1), y_arr.reshape(-1)
    return None, None


def _area_from_geometry(geometry: Any, n_cells: int) -> np.ndarray | None:
    if geometry is None:
        return None
    for attr in ("get_element_area", "get_element_areas"):
        method = getattr(geometry, attr, None)
        if callable(method):
            area = np.asarray(method(), dtype=float).reshape(-1)
            if area.size == n_cells:
                return area
    for attr in ("element_area", "element_areas", "cell_area", "cell_areas"):
        value = getattr(geometry, attr, None)
        if value is None:
            continue
        area = np.asarray(value, dtype=float).reshape(-1)
        if area.size == n_cells:
            return area
        if area.size == 1:
            return np.repeat(float(area[0]), n_cells)
    dx = getattr(geometry, "dx", None)
    dy = getattr(geometry, "dy", None)
    if dx is not None and dy is not None:
        return np.repeat(float(dx) * float(dy), n_cells)
    return None


def _cell_frame(geometry: Any, n_cells: int) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    frame = pd.DataFrame({"cell_id": np.arange(n_cells, dtype=int)})
    x, y = _coordinates_from_geometry(geometry, n_cells)
    if x is not None and y is not None:
        frame["x"] = x
        frame["y"] = y
    else:
        warnings.append("MIKE geometry did not expose cell-center coordinates.")
    area = _area_from_geometry(geometry, n_cells)
    if area is not None:
        frame["area_m2"] = area
    else:
        warnings.append("MIKE geometry did not expose cell areas; WUA needs area_m2.")
    return frame, warnings


def _time_label(dataset: Any, reader: Any, resolved_time_index: int | None) -> str | None:
    time_values = getattr(dataset, "time", None)
    if time_values is None:
        time_values = getattr(reader, "time", None)
    n = _maybe_len(time_values)
    if time_values is None or not n:
        return None
    idx = 0 if resolved_time_index is None and n == 1 else resolved_time_index
    if idx is None:
        return None
    if idx < 0:
        idx = n + idx
    if idx < 0 or idx >= n:
        return None
    return str(time_values[idx])


def _read_mikeio_hydraulic_cells(
    path: Path,
    *,
    time_index: int | None,
) -> MIKEImportResult:
    reader = _open_mikeio(path)
    dataset = _read_dataset(reader, path, time_index)
    geometry = getattr(dataset, "geometry", None) or getattr(reader, "geometry", None)
    item_names = _item_names(dataset) or _item_names(reader)
    warnings: list[str] = []
    if not item_names:
        raise ValueError("MIKE dataset exposes no item names.")

    depth_name = _find_item(item_names, ("depth",), excludes=("minimum", "maximum"))
    wse_name = _find_item(
        item_names,
        ("water", "level"),
        excludes=("minimum", "maximum"),
    ) or _find_item(item_names, ("surface", "elevation"), excludes=("minimum", "maximum"))
    velocity_name = _find_item(
        item_names,
        ("velocity",),
        excludes=("u", "v", "x", "y", "minimum", "maximum"),
    ) or _find_item(item_names, ("speed",), excludes=("minimum", "maximum"))
    u_name = _find_velocity_component(item_names, ("u", "x"))
    v_name = _find_velocity_component(item_names, ("v", "y"))

    n_cells = _infer_n_cells(
        geometry,
        dataset,
        item_names,
        [depth_name, wse_name, velocity_name, u_name, v_name],
    )
    table, geometry_warnings = _cell_frame(geometry, n_cells)
    warnings.extend(geometry_warnings)

    resolved_indexes: list[int] = []
    if depth_name is not None:
        depth, idx = _series_for_name(dataset, item_names, depth_name, n_cells, time_index)
        table["depth_m"] = depth
        if idx is not None:
            resolved_indexes.append(idx)
    else:
        warnings.append("No MIKE item matched water depth.")

    if wse_name is not None:
        wse, idx = _series_for_name(dataset, item_names, wse_name, n_cells, time_index)
        table["water_surface_m"] = wse
        if idx is not None:
            resolved_indexes.append(idx)
    else:
        warnings.append("No MIKE item matched water level/surface elevation.")

    if velocity_name is not None:
        velocity, idx = _series_for_name(dataset, item_names, velocity_name, n_cells, time_index)
        table["velocity_ms"] = velocity
        if idx is not None:
            resolved_indexes.append(idx)
    elif u_name is not None and v_name is not None:
        u, idx_u = _series_for_name(dataset, item_names, u_name, n_cells, time_index)
        v, idx_v = _series_for_name(dataset, item_names, v_name, n_cells, time_index)
        table["velocity_ms"] = np.sqrt(u**2 + v**2)
        for idx in (idx_u, idx_v):
            if idx is not None:
                resolved_indexes.append(idx)
    else:
        warnings.append("No MIKE item matched velocity or U/V velocity components.")

    resolved_idx = resolved_indexes[0] if resolved_indexes else None
    if any(idx != resolved_idx for idx in resolved_indexes[1:]):
        warnings.append(f"MIKE items resolved to different time indexes: {resolved_indexes}.")

    table.insert(0, "time", _time_label(dataset, reader, resolved_idx))
    table.insert(0, "time_index", resolved_idx)
    table.insert(0, "flow_area", path.stem)
    table.insert(0, "source_file", str(path))
    table.attrs["openlimno_output_table"] = "hydraulic_cells"
    return MIKEImportResult(
        table=table,
        summary=MIKEImportSummary(
            source_key="mike-dfs",
            file_kind=path.suffix.lower().lstrip("."),
            output_table="hydraulic_cells",
            n_rows=len(table),
            item_names=item_names,
            time_index=resolved_idx,
            warnings=tuple(warnings),
        ),
    )


def _read_mikeio_mesh(path: Path) -> MIKEImportResult:
    reader = _open_mikeio(path)
    geometry = getattr(reader, "geometry", reader)
    n_cells = _geometry_n(geometry)
    if n_cells is None:
        raise ValueError("Cannot infer MIKE mesh cell count.")
    table, warnings = _cell_frame(geometry, n_cells)
    table.insert(0, "flow_area", path.stem)
    table.insert(0, "source_file", str(path))
    table.attrs["openlimno_output_table"] = "mesh_cells"
    return MIKEImportResult(
        table=table,
        summary=MIKEImportSummary(
            source_key="mike-dfs",
            file_kind="mesh",
            output_table="mesh_cells",
            n_rows=len(table),
            item_names=(),
            time_index=None,
            warnings=tuple(warnings),
        ),
    )


def _dataframe_from_dataset(dataset: Any) -> pd.DataFrame:
    if hasattr(dataset, "to_dataframe") and callable(dataset.to_dataframe):
        df = dataset.to_dataframe()
    elif isinstance(dataset, pd.DataFrame):
        df = dataset
    else:
        raise ValueError("MIKE dataset cannot be converted to a DataFrame.")
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    return df.reset_index()


def _stringify_column_label(label: Any) -> str:
    if isinstance(label, tuple):
        parts = [str(part) for part in label if part is not None and str(part) != "nan"]
        return ":".join(parts) if parts else "column"
    text = str(label)
    return text if text else "column"


def _deduplicate_export_columns(table: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    seen: dict[str, int] = {}
    columns: list[str] = []
    renamed_duplicates = False
    for label in table.columns:
        base = _stringify_column_label(label)
        count = seen.get(base, 0) + 1
        seen[base] = count
        if count == 1:
            columns.append(base)
        else:
            columns.append(f"{base}__{count}")
            renamed_duplicates = True
    if list(table.columns) == columns:
        return table, False
    out = table.copy()
    out.columns = columns
    return out, renamed_duplicates


def _read_mikeio_timeseries(path: Path, *, time_index: int | None) -> MIKEImportResult:
    reader = _open_mikeio(path)
    dataset = _read_dataset(reader, path, time_index)
    item_names = _item_names(dataset) or _item_names(reader)
    warnings: list[str] = []
    try:
        table = _dataframe_from_dataset(dataset)
    except ValueError:
        rows = []
        for idx, name in enumerate(item_names):
            values = np.squeeze(_values(_data_array(dataset, idx, name))).reshape(-1)
            for step, value in enumerate(values):
                rows.append({"time_index": step, "item": name, "value": float(value)})
        table = pd.DataFrame(rows)
        warnings.append("MIKE time-series dataset was exported in long item/value form.")
    table.insert(0, "source_file", str(path))
    table, renamed_duplicates = _deduplicate_export_columns(table)
    if renamed_duplicates:
        warnings.append("Duplicate MIKE result column names were suffixed for tabular export.")
    table.attrs["openlimno_output_table"] = "mike_timeseries"
    return MIKEImportResult(
        table=table,
        summary=MIKEImportSummary(
            source_key="mike-dfs",
            file_kind=path.suffix.lower().lstrip("."),
            output_table="mike_timeseries",
            n_rows=len(table),
            item_names=item_names,
            time_index=time_index,
            warnings=tuple(warnings),
        ),
    )


def _count_collection(collection: Any) -> int | None:
    if collection is None:
        return None
    n = _maybe_len(collection)
    if n is not None:
        return n
    try:
        return len(list(collection))
    except TypeError:
        return None


def _mike1d_item_names(obj: Any) -> tuple[str, ...]:
    names: list[str] = []
    for attr in ("quantities", "derived_quantities"):
        values = getattr(obj, attr, None)
        if values is None:
            continue
        try:
            names.extend(str(v) for v in list(values))
        except TypeError:
            names.append(str(values))
    if names:
        return tuple(names)
    return _item_names(obj)


def _mike1d_location_count(obj: Any) -> int | None:
    counts = [
        _count_collection(getattr(obj, "reaches", None)),
        _count_collection(getattr(obj, "nodes", None)),
        _count_collection(getattr(obj, "catchments", None)),
    ]
    present = [count for count in counts if count is not None]
    if present:
        return int(sum(present))
    try:
        return len(obj.to_dataframe())
    except (AttributeError, TypeError):
        return None


def _read_mike1d_file(path: Path, *, time_index: int | None) -> MIKEImportResult:
    obj = _open_mike1d(path)
    if path.suffix.lower() == ".xns11":
        return _read_mike1d_xns11(path, obj)

    if hasattr(obj, "read") and callable(obj.read):
        table = obj.read()
    elif hasattr(obj, "to_dataframe") and callable(obj.to_dataframe):
        table = obj.to_dataframe()
    else:
        raise ValueError("MIKE 1D result object exposes neither read() nor to_dataframe().")
    if not isinstance(table, pd.DataFrame):
        table = pd.DataFrame(table)
    table = table.reset_index()
    table.insert(0, "source_file", str(path))
    table, renamed_duplicates = _deduplicate_export_columns(table)
    table.attrs["openlimno_output_table"] = "mike_timeseries"
    warnings = []
    if renamed_duplicates:
        warnings.append("Duplicate MIKE 1D result column names were suffixed for tabular export.")
    return MIKEImportResult(
        table=table,
        summary=MIKEImportSummary(
            source_key="mike-1d",
            file_kind=path.suffix.lower().lstrip("."),
            output_table="mike_timeseries",
            n_rows=len(table),
            item_names=_mike1d_item_names(obj),
            time_index=time_index,
            warnings=tuple(warnings),
        ),
    )


def _read_mike1d_xns11(path: Path, obj: Any) -> MIKEImportResult:
    if not hasattr(obj, "to_dataframe") or not callable(obj.to_dataframe):
        raise ValueError("MIKE XNS11 object does not expose to_dataframe().")
    overview = obj.to_dataframe()
    if not isinstance(overview, pd.DataFrame):
        overview = pd.DataFrame(overview)
    rows: list[pd.DataFrame] = []
    for key, row in overview.iterrows():
        xs = row.get("cross_section") if isinstance(row, pd.Series) else None
        if xs is None:
            continue
        raw = getattr(xs, "raw", None)
        if raw is None:
            continue
        raw_df = pd.DataFrame(raw).copy()
        if raw_df.empty:
            continue
        if isinstance(key, tuple):
            location_id = key[0] if len(key) > 0 else None
            chainage = key[1] if len(key) > 1 else None
            topo_id = key[2] if len(key) > 2 else None
        else:
            location_id = key
            chainage = getattr(xs, "chainage", None)
            topo_id = getattr(xs, "topo_id", None)
        raw_df.insert(0, "point_index", np.arange(len(raw_df), dtype=int))
        raw_df.insert(0, "topo_id", topo_id)
        raw_df.insert(0, "station_id", chainage)
        raw_df.insert(0, "reach", location_id)
        rows.append(raw_df)

    if not rows:
        raise ValueError("No cross-section point data found in MIKE XNS11 file.")
    table = pd.concat(rows, ignore_index=True)
    rename = {}
    if "x" in table.columns:
        rename["x"] = "station_m"
    if "z" in table.columns:
        rename["z"] = "elevation_m"
    table = table.rename(columns=rename)
    table.insert(0, "source_file", str(path))
    table.attrs["openlimno_output_table"] = "cross_section_points"
    return MIKEImportResult(
        table=table,
        summary=MIKEImportSummary(
            source_key="mike-1d",
            file_kind="xns11",
            output_table="cross_section_points",
            n_rows=len(table),
            item_names=(),
            time_index=None,
            warnings=(),
        ),
    )


__all__ = [
    "MIKE_1D_SUFFIXES",
    "MIKE_DFS_SUFFIXES",
    "MIKEImportResult",
    "MIKEImportSummary",
    "MIKEInspection",
    "MIKERuntimeDiagnostic",
    "diagnose_mike_environment",
    "inspect_mike_file",
    "read_mike_file",
]
