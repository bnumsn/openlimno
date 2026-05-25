"""HEC-RAS GIS cross-section mesh exporters."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr


@dataclass(frozen=True)
class HECRASMeshExportResult:
    """Summary of a HEC-RAS GIS cross-section UGRID export."""

    path: Path
    n_sections: int
    n_nodes: int
    n_faces: int
    transverse_nodes: int
    n_open_boundaries: int
    n_land_boundaries: int
    n_open_boundary_nodes: int
    n_land_boundary_nodes: int


def _resample_section(
    section: pd.DataFrame, transverse_nodes: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ordered = section.sort_values("distance_m")
    distances = pd.to_numeric(ordered["distance_m"], errors="coerce").to_numpy(dtype=float)
    x = pd.to_numeric(ordered["x_m"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(ordered["y_m"], errors="coerce").to_numpy(dtype=float)
    z = pd.to_numeric(ordered["elevation_m"], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(distances) & np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    distances, x, y, z = distances[valid], x[valid], y[valid], z[valid]
    if len(distances) < 2:
        raise ValueError("each cross-section needs at least two georeferenced points")
    unique_distances, unique_index = np.unique(distances, return_index=True)
    distances, x, y, z = (
        unique_distances,
        x[unique_index],
        y[unique_index],
        z[unique_index],
    )
    if len(distances) < 2 or float(distances[-1] - distances[0]) <= 0.0:
        raise ValueError("cross-section distances must span a positive width")
    target = np.linspace(float(distances[0]), float(distances[-1]), transverse_nodes)
    return (
        np.interp(target, distances, x),
        np.interp(target, distances, y),
        np.interp(target, distances, z),
    )


def write_hecras_gis_ugrid(
    cross_sections: pd.DataFrame,
    path: str | Path,
    *,
    river: str | None = None,
    reaches: list[str] | tuple[str, ...] | None = None,
    transverse_nodes: int = 9,
    crs: str | None = None,
    depth_reference_m: float | None = None,
) -> HECRASMeshExportResult:
    """Export HEC-RAS GIS cutline cross-sections as a 2D UGRID NetCDF mesh.

    The exporter resamples every cross-section to a fixed number of transverse
    nodes, then connects adjacent sections within each reach as quadrilateral
    faces. It is a handoff mesh for external 2D solvers, not a substitute for a
    modeler-reviewed production mesh.
    """

    if transverse_nodes < 2:
        raise ValueError("transverse_nodes must be >= 2")
    required = {"river", "reach", "station_m", "distance_m", "elevation_m", "x_m", "y_m"}
    missing = required - set(cross_sections.columns)
    if missing:
        raise ValueError(f"cross_sections missing columns: {sorted(missing)}")

    frame = cross_sections.copy()
    if river is not None:
        frame = frame[frame["river"].astype(str).eq(river)]
    reach_order: list[str] | None = None
    if reaches is not None:
        reach_order = [str(v) for v in reaches]
        frame = frame[frame["reach"].astype(str).isin(reach_order)]
    frame = frame.dropna(subset=["x_m", "y_m", "distance_m", "elevation_m"])
    if frame.empty:
        raise ValueError("no georeferenced HEC-RAS cross-section points available")
    if reach_order is None:
        reach_order = list(dict.fromkeys(frame["reach"].astype(str)))

    node_x: list[float] = []
    node_y: list[float] = []
    node_z: list[float] = []
    node_station: list[float] = []
    faces: list[list[int]] = []
    open_boundaries: list[list[int]] = []
    land_boundaries: list[list[int]] = []
    section_count = 0

    for reach in reach_order:
        reach_frame = frame[frame["reach"].astype(str).eq(reach)]
        if reach_frame.empty:
            continue
        section_nodes: list[list[int]] = []
        stations = sorted(
            (float(v) for v in reach_frame["station_m"].dropna().unique()),
            reverse=True,
        )
        for station in stations:
            section = reach_frame[reach_frame["station_m"].eq(station)]
            try:
                xs, ys, zs = _resample_section(section, transverse_nodes)
            except ValueError:
                continue
            ids: list[int] = []
            for x, y, z in zip(xs, ys, zs, strict=True):
                ids.append(len(node_x))
                node_x.append(float(x))
                node_y.append(float(y))
                node_z.append(float(z))
                node_station.append(float(station))
            section_nodes.append(ids)
            section_count += 1
        for upstream, downstream in pairwise(section_nodes):
            for j in range(transverse_nodes - 1):
                faces.append([upstream[j], upstream[j + 1], downstream[j + 1], downstream[j]])
        if len(section_nodes) >= 2:
            open_boundaries.extend([section_nodes[0], section_nodes[-1]])
            land_boundaries.extend(
                [
                    [nodes[0] for nodes in section_nodes],
                    [nodes[-1] for nodes in section_nodes],
                ]
            )

    if not node_x or not faces:
        raise ValueError("not enough georeferenced cross-sections to build a 2D mesh")

    face_nodes = np.asarray(faces, dtype=np.int32)
    max_open_nodes = max((len(nodes) for nodes in open_boundaries), default=0)
    max_land_nodes = max((len(nodes) for nodes in land_boundaries), default=0)
    open_boundary_nodes = np.full((len(open_boundaries), max_open_nodes), -1, dtype=np.int32)
    for i, nodes in enumerate(open_boundaries):
        open_boundary_nodes[i, : len(nodes)] = nodes
    land_boundary_nodes = np.full((len(land_boundaries), max_land_nodes), -1, dtype=np.int32)
    for i, nodes in enumerate(land_boundaries):
        land_boundary_nodes[i, : len(nodes)] = nodes
    data_vars: dict[str, object] = {
        "mesh2d": (
            (),
            0,
            {
                "cf_role": "mesh_topology",
                "topology_dimension": 2,
                "node_coordinates": "mesh2d_node_x mesh2d_node_y",
                "face_node_connectivity": "mesh2d_face_nodes",
            },
        ),
        "mesh2d_node_x": (("node",), np.asarray(node_x, dtype=float)),
        "mesh2d_node_y": (("node",), np.asarray(node_y, dtype=float)),
        "mesh2d_face_nodes": (
            ("face", "vertex"),
            face_nodes,
            {"_FillValue": -1, "start_index": 0},
        ),
        "bottom_elevation": (("node",), np.asarray(node_z, dtype=float), {"units": "m"}),
        "hecras_station_m": (("node",), np.asarray(node_station, dtype=float)),
        "open_boundary_node_connectivity": (
            ("open_boundary", "open_boundary_node"),
            open_boundary_nodes,
            {"_FillValue": -1, "start_index": 0},
        ),
        "land_boundary_node_connectivity": (
            ("land_boundary", "land_boundary_node"),
            land_boundary_nodes,
            {"_FillValue": -1, "start_index": 0},
        ),
    }
    if depth_reference_m is not None:
        reference = float(depth_reference_m)
        bathymetric_depth = np.maximum(reference - np.asarray(node_z, dtype=float), 0.0)
        data_vars["schism_bathymetric_depth"] = (
            ("node",),
            bathymetric_depth,
            {
                "units": "m",
                "positive": "down",
                "long_name": "SCHISM bathymetric depth relative to depth_reference_m",
                "depth_reference_m": reference,
            },
        )
    attrs = {
        "Conventions": "UGRID-1.0",
        "title": "OpenLimno HEC-RAS GIS cutline-derived mesh",
        "source": "HEC-RAS geometry XS GIS Cut Line + #Sta/Elev",
        "crs": crs or "unknown",
    }
    if depth_reference_m is not None:
        attrs["schism_depth_reference_m"] = float(depth_reference_m)
    ds = xr.Dataset(data_vars=data_vars, attrs=attrs)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(out)
    ds.close()
    return HECRASMeshExportResult(
        path=out,
        n_sections=section_count,
        n_nodes=len(node_x),
        n_faces=len(faces),
        transverse_nodes=transverse_nodes,
        n_open_boundaries=len(open_boundaries),
        n_land_boundaries=len(land_boundaries),
        n_open_boundary_nodes=sum(len(nodes) for nodes in open_boundaries),
        n_land_boundary_nodes=sum(len(nodes) for nodes in land_boundaries),
    )


__all__ = ["HECRASMeshExportResult", "write_hecras_gis_ugrid"]
