"""HEC-RAS HDF result importer.

HEC-RAS stores 2D results in HDF5 with paths that vary across versions and
output selections. This reader is intentionally conservative:

* discover 2D flow areas from ``/Geometry/2D Flow Areas``
* prefer canonical cell-center geometry and cell-aligned hydraulic result arrays
* reject face-aligned velocity datasets instead of pretending they are cells

The output is a staging table for ecological post-processing, not a full
round-trip HEC-RAS model representation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HECRASHDFImportSummary:
    """Small import report for diagnostics and provenance."""

    flow_area: str
    n_cells: int
    time_index: int | None
    depth_path: str | None
    velocity_path: str | None
    water_surface_path: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HECRASHDFImportResult:
    """HEC-RAS hydraulic cell staging table plus summary metadata."""

    table: pd.DataFrame
    summary: HECRASHDFImportSummary


@dataclass(frozen=True)
class HDFDatasetInfo:
    """Lightweight HDF dataset metadata used by the inspector."""

    path: str
    shape: tuple[int, ...]
    dtype: str
    cell_aligned: bool


@dataclass(frozen=True)
class HECRASHDFInspection:
    """Diagnostic view of a HEC-RAS HDF file."""

    path: str
    flow_areas: tuple[str, ...]
    selected_flow_area: str | None
    n_cells: int | None
    cell_center_path: str | None
    depth_candidates: tuple[HDFDatasetInfo, ...]
    velocity_candidates: tuple[HDFDatasetInfo, ...]
    water_surface_candidates: tuple[HDFDatasetInfo, ...]
    geometry_candidates: tuple[HDFDatasetInfo, ...]
    warnings: tuple[str, ...] = ()


def _require_h5py() -> Any:
    try:
        import h5py  # type: ignore[import-not-found]
    except ModuleNotFoundError as e:
        raise ImportError(
            "HEC-RAS HDF import requires the optional dependency 'h5py'. "
            "Install OpenLimno with an environment that includes h5py."
        ) from e
    return h5py


def _norm(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum())


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _dataset_paths(h5: Any) -> dict[str, Any]:
    paths: dict[str, Any] = {}

    def visit(name: str, obj: Any) -> None:
        if hasattr(obj, "shape") and hasattr(obj, "dtype"):
            paths["/" + name] = obj

    h5.visititems(visit)
    return paths


def _group_names(group: Any) -> list[str]:
    return [str(k) for k in group if hasattr(group[k], "keys")]


def _area_geom_prefix(area: str) -> str:
    return f"/Geometry/2D Flow Areas/{area}"


def _pick_flow_area(h5: Any, flow_area: str | None) -> str:
    try:
        area_group = h5["/Geometry/2D Flow Areas"]
        areas = _group_names(area_group)
    except KeyError as e:
        raise ValueError("No '/Geometry/2D Flow Areas' group found in HEC-RAS HDF.") from e
    if not areas:
        raise ValueError("HEC-RAS HDF contains no 2D flow areas.")
    if flow_area is None:
        return areas[0]
    if flow_area not in areas:
        raise ValueError(f"Flow area {flow_area!r} not found. Available: {areas}")
    return flow_area


def _topology_datasets(
    h5: Any,
    area: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    prefix = _area_geom_prefix(area)
    required = (
        "Cells Face and Orientation Info",
        "Cells Face and Orientation Values",
        "Faces FacePoint Indexes",
        "FacePoints Coordinate",
    )
    try:
        info = np.asarray(h5[f"{prefix}/{required[0]}"], dtype=int)
        values = np.asarray(h5[f"{prefix}/{required[1]}"], dtype=int)
        face_points = np.asarray(h5[f"{prefix}/{required[2]}"], dtype=int)
        points = np.asarray(h5[f"{prefix}/{required[3]}"], dtype=float)
    except KeyError:
        return None
    if (
        info.ndim != 2
        or info.shape[1] < 2
        or values.ndim != 2
        or face_points.ndim != 2
        or face_points.shape[1] < 2
        or points.ndim != 2
        or points.shape[1] < 2
    ):
        return None
    return info[:, :2], values, face_points[:, :2], points[:, :2]


def _ordered_polygon(points: np.ndarray) -> np.ndarray:
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    return points[np.argsort(angles)]


def _polygon_area(points: np.ndarray) -> float:
    if len(points) < 3:
        return 0.0
    poly = _ordered_polygon(points)
    x = poly[:, 0]
    y = poly[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) * 0.5)


def _centers_and_areas_from_topology(
    h5: Any,
    area: str,
) -> tuple[np.ndarray, np.ndarray, str] | None:
    topology = _topology_datasets(h5, area)
    if topology is None:
        return None
    info, values, face_points, points = topology
    centers = np.full((len(info), 2), np.nan, dtype=float)
    areas = np.full(len(info), np.nan, dtype=float)
    for cell_idx, (start, count) in enumerate(info):
        faces = values[int(start) : int(start) + int(count), 0]
        face_point_ids = face_points[faces.reshape(-1)].reshape(-1)
        unique_ids = np.unique(face_point_ids)
        if unique_ids.size == 0:
            continue
        cell_points = points[unique_ids]
        centers[cell_idx] = cell_points.mean(axis=0)
        areas[cell_idx] = _polygon_area(cell_points)
    if np.isnan(centers).any():
        return None
    return centers, areas, f"{_area_geom_prefix(area)}/<derived cell face topology>"


def _find_dataset(
    paths: dict[str, Any],
    *,
    includes: Iterable[str],
    excludes: Iterable[str] = (),
    under: str | None = None,
) -> tuple[str, Any] | tuple[None, None]:
    include_norm = tuple(_norm(x) for x in includes)
    exclude_norm = tuple(_norm(x) for x in excludes)
    candidates: list[tuple[int, str, Any]] = []
    for path, ds in paths.items():
        if under and not path.startswith(under):
            continue
        path_norm = _norm(path)
        name_norm = _norm(path.rsplit("/", 1)[-1])
        if not all(token in path_norm for token in include_norm):
            continue
        if any(token in path_norm for token in exclude_norm):
            continue
        # Prefer exact-ish leaf-name matches over broad path matches.
        score = 0
        if any(token == name_norm for token in include_norm):
            score += 10
        if "2dflowareas" in path_norm:
            score += 2
        candidates.append((score, path, ds))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    _, path, ds = candidates[0]
    return path, ds


def _cell_centers(h5: Any, paths: dict[str, Any], area: str) -> tuple[np.ndarray, str]:
    geom_prefix = _area_geom_prefix(area)
    path, ds = _find_dataset(
        paths,
        includes=("cells center coordinate",),
        under=geom_prefix,
    )
    if path is None:
        path, ds = _find_dataset(paths, includes=("cell center",), under=geom_prefix)
    if path is None:
        raise ValueError(
            f"No cell-center coordinate dataset found under {geom_prefix!r}. "
            "Expected a dataset such as 'Cells Center Coordinate'."
        )
    arr = np.asarray(ds, dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 2:
        raise ValueError(f"Cell-center dataset {path!r} has unsupported shape {arr.shape}.")
    return arr[:, :2], path


def _cell_centers_any(h5: Any, paths: dict[str, Any], area: str) -> tuple[np.ndarray, str]:
    try:
        return _cell_centers(h5, paths, area)
    except ValueError as first_error:
        derived = _centers_and_areas_from_topology(h5, area)
        if derived is not None:
            centers, _, path = derived
            return centers, path
        raise first_error


def _as_cell_series(ds: Any, n_cells: int, time_index: int | None) -> tuple[np.ndarray, int | None]:
    arr = np.asarray(ds)
    if arr.ndim == 1:
        if arr.shape[0] != n_cells:
            raise ValueError(f"Dataset {ds.name!r} length {arr.shape[0]} != n_cells {n_cells}.")
        return arr.astype(float), None
    if arr.ndim == 2:
        if arr.shape[-1] == n_cells:
            idx = _resolve_time_index(arr.shape[0], time_index)
            return arr[idx, :].astype(float), idx
        if arr.shape[0] == n_cells:
            idx = _resolve_time_index(arr.shape[1], time_index)
            return arr[:, idx].astype(float), idx
    if arr.ndim == 3:
        if arr.shape[1] == n_cells and arr.shape[2] >= 2:
            idx = _resolve_time_index(arr.shape[0], time_index)
            vec = arr[idx, :, :2].astype(float)
            return np.linalg.norm(vec, axis=1), idx
        if arr.shape[0] == n_cells and arr.shape[2] >= 2:
            idx = _resolve_time_index(arr.shape[1], time_index)
            vec = arr[:, idx, :2].astype(float)
            return np.linalg.norm(vec, axis=1), idx
    raise ValueError(f"Dataset {ds.name!r} has unsupported cell/time shape {arr.shape}.")


def _shape_cell_aligned(shape: tuple[int, ...], n_cells: int | None) -> bool:
    if n_cells is None:
        return False
    if len(shape) == 1:
        return shape[0] == n_cells
    if len(shape) == 2:
        return shape[-1] == n_cells or shape[0] == n_cells
    if len(shape) == 3:
        return (shape[1] == n_cells and shape[2] >= 2) or (shape[0] == n_cells and shape[2] >= 2)
    return False


def _resolve_time_index(n_time: int, time_index: int | None) -> int:
    if n_time <= 0:
        raise ValueError("Result dataset has zero time steps.")
    idx = -1 if time_index is None else time_index
    if idx < 0:
        idx = n_time + idx
    if idx < 0 or idx >= n_time:
        raise IndexError(f"time_index out of range: {time_index} for {n_time} time steps.")
    return idx


def _optional_cell_series(
    paths: dict[str, Any],
    *,
    area: str,
    n_cells: int,
    time_index: int | None,
    includes: tuple[str, ...],
    excludes: tuple[str, ...] = (),
) -> tuple[str | None, np.ndarray | None, int | None, str | None]:
    result_prefix = "/Results/Unsteady/Output/Output Blocks"
    area_token = f"2D Flow Areas/{area}"
    candidates: list[tuple[str, Any]] = []
    for path, ds in paths.items():
        if not path.startswith(result_prefix) or area_token not in path:
            continue
        path_norm = _norm(path)
        if not all(_norm(tok) in path_norm for tok in includes):
            continue
        if any(_norm(tok) in path_norm for tok in excludes):
            continue
        candidates.append((path, ds))
    if not candidates:
        return None, None, None, f"No result dataset found for {includes!r}."

    errors: list[str] = []
    for path, ds in sorted(candidates, key=lambda item: item[0]):
        try:
            values, resolved_idx = _as_cell_series(ds, n_cells, time_index)
        except (ValueError, IndexError) as e:
            errors.append(f"{path}: {e}")
            continue
        return path, values, resolved_idx, None
    return None, None, None, "No cell-aligned result dataset usable: " + "; ".join(errors[:3])


def _optional_geometry_series(
    paths: dict[str, Any],
    *,
    area: str,
    n_cells: int,
    includes: tuple[str, ...],
) -> tuple[str | None, np.ndarray | None]:
    geom_prefix = f"/Geometry/2D Flow Areas/{area}"
    path, ds = _find_dataset(paths, includes=includes, under=geom_prefix)
    if path is None:
        return None, None
    arr = np.asarray(ds)
    if arr.ndim == 1 and arr.shape[0] == n_cells:
        return path, arr.astype(float)
    return path, None


def _derived_cell_areas(h5: Any, area: str, n_cells: int) -> tuple[str | None, np.ndarray | None]:
    derived = _centers_and_areas_from_topology(h5, area)
    if derived is None:
        return None, None
    _, areas, path = derived
    if areas.size != n_cells or np.isnan(areas).any():
        return path, None
    return path, areas


def _face_count(h5: Any, area: str) -> int | None:
    topology = _topology_datasets(h5, area)
    if topology is None:
        return None
    _, _, face_points, _ = topology
    return int(face_points.shape[0])


def _optional_face_velocity_series(
    paths: dict[str, Any],
    h5: Any,
    *,
    area: str,
    time_index: int | None,
) -> tuple[str | None, np.ndarray | None, int | None, str | None]:
    n_faces = _face_count(h5, area)
    if n_faces is None:
        return None, None, None, "No HEC-RAS face topology found for face-velocity aggregation."
    result_prefix = "/Results/Unsteady/Output/Output Blocks"
    area_token = f"2D Flow Areas/{area}"
    candidates: list[tuple[int, str, Any]] = []
    for path, ds in paths.items():
        if not path.startswith(result_prefix) or area_token not in path:
            continue
        path_norm = _norm(path)
        leaf_norm = _norm(path.rsplit("/", 1)[-1])
        if "facevelocity" not in path_norm:
            continue
        if any(tok in path_norm for tok in ("boundary", "startingdifferences", "minimum")):
            continue
        priority = 0 if leaf_norm == "facevelocity" else 1 if leaf_norm == "maximumfacevelocity" else 2
        candidates.append((priority, path, ds))
    if not candidates:
        return None, None, None, "No HEC-RAS face velocity dataset found."
    errors: list[str] = []
    for _, path, ds in sorted(candidates, key=lambda item: (item[0], item[1])):
        try:
            values, resolved_idx = _as_cell_series(ds, n_faces, time_index)
        except (ValueError, IndexError) as e:
            errors.append(f"{path}: {e}")
            continue
        return path, values, resolved_idx, None
    return None, None, None, "No face-aligned velocity dataset usable: " + "; ".join(errors[:3])


def _cell_velocity_from_face_velocity(
    h5: Any,
    area: str,
    face_velocity: np.ndarray,
    n_cells: int,
) -> np.ndarray | None:
    topology = _topology_datasets(h5, area)
    if topology is None:
        return None
    info, values, _, _ = topology
    if len(info) != n_cells:
        return None
    out = np.full(n_cells, np.nan, dtype=float)
    abs_face_velocity = np.abs(np.asarray(face_velocity, dtype=float).reshape(-1))
    for cell_idx, (start, count) in enumerate(info):
        faces = values[int(start) : int(start) + int(count), 0].astype(int)
        faces = faces[(faces >= 0) & (faces < abs_face_velocity.size)]
        if faces.size:
            out[cell_idx] = float(np.nanmean(abs_face_velocity[faces]))
    if np.isnan(out).all():
        return None
    return np.nan_to_num(out, nan=0.0)


def _time_label(paths: dict[str, Any], resolved_time_index: int | None) -> str | None:
    if resolved_time_index is None:
        return None
    for label in ("time date stamp", "time", "output times"):
        path, ds = _find_dataset(paths, includes=(label,), under="/Results/")
        if path is None:
            continue
        arr = np.asarray(ds)
        if arr.ndim == 0 or len(arr) <= resolved_time_index:
            continue
        return _decode(arr[resolved_time_index])
    return None


def _dataset_info(path: str, ds: Any, n_cells: int | None) -> HDFDatasetInfo:
    shape = tuple(int(x) for x in getattr(ds, "shape", ()))
    return HDFDatasetInfo(
        path=path,
        shape=shape,
        dtype=str(getattr(ds, "dtype", "")),
        cell_aligned=_shape_cell_aligned(shape, n_cells),
    )


def _candidate_infos(
    paths: dict[str, Any],
    *,
    includes: tuple[str, ...],
    excludes: tuple[str, ...] = (),
    area: str | None = None,
    under: str | None = None,
    n_cells: int | None = None,
) -> tuple[HDFDatasetInfo, ...]:
    include_norm = tuple(_norm(x) for x in includes)
    exclude_norm = tuple(_norm(x) for x in excludes)
    area_token = f"2D Flow Areas/{area}" if area else None
    rows: list[HDFDatasetInfo] = []
    for path, ds in paths.items():
        if under and not path.startswith(under):
            continue
        if area_token and area_token not in path:
            continue
        path_norm = _norm(path)
        if not all(token in path_norm for token in include_norm):
            continue
        if any(token in path_norm for token in exclude_norm):
            continue
        rows.append(_dataset_info(path, ds, n_cells))
    return tuple(sorted(rows, key=lambda item: (not item.cell_aligned, item.path)))


def inspect_hecras_hdf(path: str | Path, *, flow_area: str | None = None) -> HECRASHDFInspection:
    """Inspect a HEC-RAS HDF file without reading full result arrays."""

    h5py = _require_h5py()
    p = Path(path)
    warnings: list[str] = []
    with h5py.File(p, "r") as h5:
        paths = _dataset_paths(h5)
        try:
            flow_areas = tuple(_group_names(h5["/Geometry/2D Flow Areas"]))
        except KeyError:
            flow_areas = ()
            warnings.append("No '/Geometry/2D Flow Areas' group found.")

        selected = None
        n_cells = None
        cell_center_path = None
        if flow_areas:
            try:
                selected = _pick_flow_area(h5, flow_area)
                centers, cell_center_path = _cell_centers_any(h5, paths, selected)
                n_cells = int(centers.shape[0])
            except ValueError as e:
                warnings.append(str(e))

        depth = _candidate_infos(
            paths,
            includes=("depth",),
            excludes=("maximum", "minimum", "face velocity", "facepoint", "faces", "boundary"),
            area=selected,
            under="/Results/Unsteady/Output/Output Blocks",
            n_cells=n_cells,
        )
        velocity = _candidate_infos(
            paths,
            includes=("velocity",),
            excludes=("face velocity", "boundary", "maximum", "minimum", "starting differences"),
            area=selected,
            under="/Results/Unsteady/Output/Output Blocks",
            n_cells=n_cells,
        )
        water_surface = _candidate_infos(
            paths,
            includes=("water surface",),
            excludes=("maximum", "minimum", "boundary", "error"),
            area=selected,
            under="/Results/Unsteady/Output/Output Blocks",
            n_cells=n_cells,
        )
        geometry = tuple(
            sorted(
                [
                    *_candidate_infos(
                        paths,
                        includes=("cells center coordinate",),
                        area=selected,
                        under="/Geometry/2D Flow Areas",
                        n_cells=n_cells,
                    ),
                    *_candidate_infos(
                        paths,
                        includes=("cells surface area",),
                        area=selected,
                        under="/Geometry/2D Flow Areas",
                        n_cells=n_cells,
                    ),
                    *_candidate_infos(
                        paths,
                        includes=("cells minimum elevation",),
                        area=selected,
                        under="/Geometry/2D Flow Areas",
                        n_cells=n_cells,
                    ),
                    *_candidate_infos(
                        paths,
                        includes=("cells face and orientation info",),
                        area=selected,
                        under="/Geometry/2D Flow Areas",
                        n_cells=n_cells,
                    ),
                    *_candidate_infos(
                        paths,
                        includes=("facepoints coordinate",),
                        area=selected,
                        under="/Geometry/2D Flow Areas",
                        n_cells=n_cells,
                    ),
                ],
                key=lambda item: item.path,
            )
        )

    return HECRASHDFInspection(
        path=str(p),
        flow_areas=flow_areas,
        selected_flow_area=selected,
        n_cells=n_cells,
        cell_center_path=cell_center_path,
        depth_candidates=depth,
        velocity_candidates=velocity,
        water_surface_candidates=water_surface,
        geometry_candidates=geometry,
        warnings=tuple(warnings),
    )


def read_hecras_hdf(
    path: str | Path,
    *,
    flow_area: str | None = None,
    time_index: int | None = None,
) -> HECRASHDFImportResult:
    """Read HEC-RAS 2D HDF results into a hydraulic-cell staging table.

    Parameters
    ----------
    path
        HEC-RAS HDF result file.
    flow_area
        Optional 2D flow-area name. Defaults to the first area in geometry.
    time_index
        Time step to import. ``None`` means the last time step. Negative indexes
        follow Python convention.
    """

    h5py = _require_h5py()
    p = Path(path)
    warnings: list[str] = []
    with h5py.File(p, "r") as h5:
        paths = _dataset_paths(h5)
        area = _pick_flow_area(h5, flow_area)
        centers, center_path = _cell_centers_any(h5, paths, area)
        n_cells = centers.shape[0]

        depth_path, depth, idx_depth, depth_warn = _optional_cell_series(
            paths,
            area=area,
            n_cells=n_cells,
            time_index=time_index,
            includes=("depth",),
            excludes=("maximum", "minimum", "face velocity", "facepoint", "faces", "boundary"),
        )

        wse_path, wse, idx_wse, wse_warn = _optional_cell_series(
            paths,
            area=area,
            n_cells=n_cells,
            time_index=time_index,
            includes=("water surface",),
            excludes=("maximum", "minimum", "boundary", "error"),
        )
        if wse is None:
            wse_path, wse, idx_wse, wse_warn = _optional_cell_series(
                paths,
                area=area,
                n_cells=n_cells,
                time_index=0,
                includes=("maximum", "water surface"),
                excludes=("boundary", "error"),
            )
        if wse_warn:
            warnings.append(wse_warn)

        velocity_path, velocity, idx_vel, velocity_warn = _optional_cell_series(
            paths,
            area=area,
            n_cells=n_cells,
            time_index=time_index,
            includes=("velocity",),
            excludes=("face velocity", "boundary", "maximum", "minimum", "starting differences"),
        )
        if velocity is None:
            face_path, face_velocity, idx_face, face_warn = _optional_face_velocity_series(
                paths,
                h5,
                area=area,
                time_index=time_index,
            )
            if face_velocity is not None:
                face_derived_velocity = _cell_velocity_from_face_velocity(
                    h5,
                    area,
                    face_velocity,
                    n_cells,
                )
                if face_derived_velocity is not None:
                    velocity = face_derived_velocity
                    idx_vel = idx_face
                    velocity_path = f"<cell mean absolute face velocity from {face_path}>"
                    warnings.append(
                        "No HEC-RAS cell-center velocity dataset found; approximated "
                        "velocity_ms from mean absolute face velocity per cell."
                    )
            if velocity is None:
                warnings.append(face_warn or velocity_warn)

        area_path, cell_area = _optional_geometry_series(
            paths,
            area=area,
            n_cells=n_cells,
            includes=("cells surface area",),
        )
        if cell_area is None:
            area_path, cell_area = _optional_geometry_series(
                paths,
                area=area,
                n_cells=n_cells,
                includes=("cell area",),
            )
        if area_path is not None and cell_area is None:
            warnings.append(f"Geometry area dataset {area_path} is not cell-aligned; skipped.")
        if cell_area is None:
            area_path, cell_area = _derived_cell_areas(h5, area, n_cells)
            if area_path is not None and cell_area is None:
                warnings.append(f"Could not derive cell areas from {area_path}.")

        bed_path, bed = _optional_geometry_series(
            paths,
            area=area,
            n_cells=n_cells,
            includes=("cells minimum elevation",),
        )
        if bed_path is not None and bed is None:
            warnings.append(f"Geometry elevation dataset {bed_path} is not cell-aligned; skipped.")

        if depth is None and wse is not None and bed is not None:
            depth = np.maximum(wse - bed, 0.0)
            depth_path = f"<derived {wse_path} - {bed_path}>"
            warnings.append(
                "No HEC-RAS cell depth dataset found; derived depth_m from "
                "water_surface_m - bed_elevation_m."
            )
        elif depth_warn:
            warnings.append(depth_warn)

        resolved_indexes = [idx for idx in (idx_depth, idx_wse, idx_vel) if idx is not None]
        resolved_idx = resolved_indexes[0] if resolved_indexes else None
        for idx in resolved_indexes[1:]:
            if idx != resolved_idx:
                warnings.append(
                    "Result datasets resolved to different time indexes "
                    f"({resolved_indexes}); table records the first."
                )
                break
        time_value = _time_label(paths, resolved_idx)

    rows = {
        "source_file": str(p),
        "flow_area": area,
        "time_index": resolved_idx,
        "time": time_value,
        "cell_id": np.arange(n_cells, dtype=int),
        "x": centers[:, 0],
        "y": centers[:, 1],
    }
    if cell_area is not None:
        rows["area_m2"] = cell_area
    if bed is not None:
        rows["bed_elevation_m"] = bed
    if depth is not None:
        rows["depth_m"] = depth
    if wse is not None:
        rows["water_surface_m"] = wse
    if velocity is not None:
        rows["velocity_ms"] = velocity

    table = pd.DataFrame(rows)
    table.attrs["openlimno_source_model"] = "HEC-RAS"
    table.attrs["openlimno_source_key"] = "hecras-hdf"
    table.attrs["openlimno_output_table"] = "hydraulic_cells"
    table.attrs["hecras_cell_center_path"] = center_path
    summary = HECRASHDFImportSummary(
        flow_area=area,
        n_cells=n_cells,
        time_index=resolved_idx,
        depth_path=depth_path,
        velocity_path=velocity_path,
        water_surface_path=wse_path,
        warnings=tuple(warnings),
    )
    return HECRASHDFImportResult(table=table, summary=summary)


__all__ = [
    "HDFDatasetInfo",
    "HECRASHDFImportResult",
    "HECRASHDFImportSummary",
    "HECRASHDFInspection",
    "inspect_hecras_hdf",
    "read_hecras_hdf",
]
