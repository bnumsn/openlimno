"""UGRID NetCDF mesh validation.

SPEC §3.1.2 mandates UGRID-1.0 as the canonical mesh format. This module provides
a light-weight validator that ``Case.run()`` invokes before handing a mesh to a
hydrodynamic backend.

Supports both topologies:
  * **UGRID-1D** (network of nodes + ``edge_nodes``) — for 1D backends like Builtin1D
  * **UGRID-2D** (nodes + ``face_nodes``) — for 2D backends like SCHISM

The validator is permissive: it enforces the *minimal* shape downstream code needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class MeshValidationReport:
    """Result of validating a UGRID mesh file."""

    path: Path
    is_valid: bool
    topology_dim: int           # 1 or 2; 0 if undetermined
    n_nodes: int
    n_faces: int                # 0 for 1D meshes
    n_edges: int                # 0 if not present
    has_bottom_elevation: bool
    errors: list[str]
    warnings: list[str]

    def summary(self) -> str:
        status = "OK" if self.is_valid else "INVALID"
        if self.topology_dim == 2:
            shape = f"{self.n_nodes} nodes, {self.n_faces} faces"
        elif self.topology_dim == 1:
            shape = f"{self.n_nodes} nodes, {self.n_edges} edges (1D)"
        else:
            shape = f"{self.n_nodes} nodes"
        return f"[{status}] {self.path.name}: {shape}, depth={self.has_bottom_elevation}"


_NODE_X_NAMES = ("mesh2d_node_x", "mesh1d_node_x", "node_x", "x")
_NODE_Y_NAMES = ("mesh2d_node_y", "mesh1d_node_y", "node_y", "y")
_FACE_NODES_NAMES = ("mesh2d_face_nodes", "face_nodes")
_EDGE_NODES_NAMES = ("mesh2d_edge_nodes", "mesh1d_edge_nodes",
                     "edge_nodes", "edge_node_connectivity")
_DEPTH_NAMES = ("bottom_elevation", "depth", "node_z", "elevation")


def validate_ugrid_mesh(path: str | Path) -> MeshValidationReport:
    """Validate a UGRID-2D NetCDF mesh.

    Returns a report with diagnostics; ``is_valid`` is True only when all
    required vars are present and shapes are consistent.
    """
    p = Path(path)
    errors: list[str] = []
    warnings: list[str] = []

    if not p.exists():
        return MeshValidationReport(
            path=p, is_valid=False, topology_dim=0,
            n_nodes=0, n_faces=0, n_edges=0,
            has_bottom_elevation=False,
            errors=[f"Mesh file does not exist: {p}"],
            warnings=[],
        )

    try:
        import xarray as xr
    except ImportError:  # pragma: no cover
        return MeshValidationReport(
            path=p, is_valid=False, topology_dim=0,
            n_nodes=0, n_faces=0, n_edges=0,
            has_bottom_elevation=False,
            errors=["xarray not available — cannot validate UGRID"],
            warnings=[],
        )

    try:
        ds = xr.open_dataset(p)
    except Exception as e:  # noqa: BLE001
        return MeshValidationReport(
            path=p, is_valid=False, topology_dim=0,
            n_nodes=0, n_faces=0, n_edges=0,
            has_bottom_elevation=False,
            errors=[f"Failed to open NetCDF: {e}"],
            warnings=[],
        )
    try:
        x_var = next((n for n in _NODE_X_NAMES if n in ds.variables), None)
        y_var = next((n for n in _NODE_Y_NAMES if n in ds.variables), None)
        face_var = next((n for n in _FACE_NODES_NAMES if n in ds.variables), None)
        edge_var = next((n for n in _EDGE_NODES_NAMES if n in ds.variables), None)
        depth_var = next((n for n in _DEPTH_NAMES if n in ds.variables), None)

        n_nodes = 0
        n_faces = 0
        n_edges = 0
        topology_dim = 0
        if x_var is None:
            errors.append("Missing node-x variable (mesh2d_node_x / node_x / x)")
        else:
            n_nodes = int(ds[x_var].size)
        if y_var is None:
            errors.append("Missing node-y variable (mesh2d_node_y / node_y / y)")
        elif x_var is not None and ds[y_var].size != ds[x_var].size:
            errors.append(
                f"Node x/y length mismatch: "
                f"{ds[x_var].size} vs {ds[y_var].size}"
            )
        if face_var is not None:
            arr = ds[face_var]
            if arr.ndim != 2:
                errors.append(
                    f"face_nodes must be 2D (face × vertex); got ndim={arr.ndim}"
                )
            else:
                n_faces = int(arr.shape[0])
                topology_dim = 2
                if arr.shape[1] not in (3, 4):
                    warnings.append(
                        f"face_nodes vertex dim={arr.shape[1]} (expected 3=tri or 4=quad)"
                    )
        if edge_var is not None:
            arr = ds[edge_var]
            if arr.ndim != 2 or arr.shape[1] != 2:
                warnings.append(
                    f"edge_nodes shape={arr.shape} (expected (n_edges, 2))"
                )
            else:
                n_edges = int(arr.shape[0])
                if topology_dim == 0:
                    topology_dim = 1

        if face_var is None and edge_var is None:
            errors.append(
                "Missing connectivity variable: need face_nodes (2D) "
                "or edge_nodes (1D)"
            )

        if depth_var is None:
            warnings.append(
                "No bottom_elevation/depth variable; "
                "downstream solvers will get z=0 nodes"
            )

        conv = ds.attrs.get("Conventions", "")
        if "UGRID" not in str(conv):
            warnings.append(
                f"Conventions attribute does not declare UGRID (got {conv!r})"
            )
    finally:
        ds.close()

    return MeshValidationReport(
        path=p,
        is_valid=not errors,
        topology_dim=topology_dim,
        n_nodes=n_nodes,
        n_faces=n_faces,
        n_edges=n_edges,
        has_bottom_elevation=depth_var is not None,
        errors=errors,
        warnings=warnings,
    )


__all__ = ["MeshValidationReport", "validate_ugrid_mesh"]
