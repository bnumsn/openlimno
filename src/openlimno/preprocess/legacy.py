"""Legacy cross-section importers (best-effort). SPEC §4.0.1 M3.

Two minimal parsers for cross-section data trapped in legacy software formats:

* **HEC-RAS .g0X geometry files** — fixed-format ASCII; we extract reach + cross
  section "X1"/"GR" records and yield a normalised DataFrame.
* **River2D .cdg bed-mesh files** — node + element ASCII; we extract mesh nodes,
  official 2002 solved node fields when present, and triangular topology.

Limitations: these are *best-effort* readers. Hydraulic structures (bridges,
weirs, culverts), Manning n strips, and rating-curve overrides are NOT parsed —
a warning is emitted and the user is expected to redefine those in WEDM.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HEC-RAS .g0X
# ---------------------------------------------------------------------------
# Per HEC-RAS reference manual, geometry record formats (fixed-width 8 cols):
#   X1  Cross-section header line:
#         River Sta, num station-elev pts, ...
#   GR  Cross-section ground points (paired elev,station):
#         elev1, sta1, elev2, sta2, ...  (8 fields per line, continuation OK)
#   #Mann  Manning n breakpoints (skipped here)
#
# We only extract X1 + GR for each XS, and assume reach/river name from
# preceding "River Reach=" / "River Station=" lines.

_X1_RE = re.compile(r"^X1\s*=\s*(.*)")
_GR_RE = re.compile(r"^GR\s*=\s*(.*)")
_RIVER_RE = re.compile(r"^River Reach=([^,]+),\s*([^\n]+)")
_TYPE_RE = re.compile(r"^Type RM Length L Ch R\s*=\s*1\s*,\s*([0-9.\-]+)")


def _parse_numeric_body(line: str) -> list[float]:
    """HEC-RAS GR / X1 body: comma-separated *or* 8-char fixed.

    Strategy:
      1. If the line contains a comma, split on commas (any whitespace stripped).
      2. Otherwise, parse 8-char fixed-width chunks.

    Empty / non-numeric tokens are silently skipped.
    """
    out: list[float] = []
    s = line.rstrip()
    if "," in s:
        for tok in s.split(","):
            tok = tok.strip()
            if tok:
                try:
                    out.append(float(tok))
                except ValueError:
                    pass
        return out
    for i in range(0, len(s), 8):
        chunk = s[i : i + 8].strip()
        if chunk:
            try:
                out.append(float(chunk))
            except ValueError:
                pass
    return out


def read_hecras_geometry(path: str | Path) -> pd.DataFrame:
    """Parse a HEC-RAS .g0X geometry file into WEDM cross-section rows.

    Returns columns:
        river, reach, station_m, point_index, distance_m, elevation_m

    Stations are taken from the X1 record's "River Station" field; the
    station-along-reach is *not* converted (HEC-RAS uses river miles by
    convention) — caller maps to metres if needed.
    """
    p = Path(path)
    text = p.read_text(encoding="latin-1", errors="replace")
    lines = text.splitlines()

    rows: list[dict[str, object]] = []
    river = ""
    reach = ""
    cur_station = None
    cur_npts = 0
    cur_pts: list[float] = []
    in_gr = False

    def flush() -> None:
        nonlocal cur_pts, cur_station
        if cur_station is None or not cur_pts:
            cur_pts = []
            cur_station = None
            return
        # Pairs are (elev, dist) per HEC-RAS convention
        for i in range(0, len(cur_pts), 2):
            if i + 1 >= len(cur_pts):
                break
            elev, dist = cur_pts[i], cur_pts[i + 1]
            rows.append(
                {
                    "river": river,
                    "reach": reach,
                    "station_m": float(cur_station),
                    "point_index": i // 2,
                    "distance_m": float(dist),
                    "elevation_m": float(elev),
                }
            )
        cur_pts = []
        cur_station = None

    for raw in lines:
        m = _RIVER_RE.match(raw)
        if m:
            river, reach = m.group(1).strip(), m.group(2).strip()
            in_gr = False
            continue
        m = _X1_RE.match(raw)
        if m:
            flush()
            body = _parse_numeric_body(m.group(1))
            if body:
                cur_station = body[0]
                cur_npts = int(body[1]) if len(body) > 1 else 0
            in_gr = False
            continue
        m = _GR_RE.match(raw)
        if m:
            cur_pts.extend(_parse_numeric_body(m.group(1)))
            in_gr = True
            continue
        if in_gr and raw.startswith(" ") and not raw.lstrip().startswith(("#", "X", "M")):
            # GR continuation line
            cur_pts.extend(_parse_numeric_body(raw))
            continue
        in_gr = False

    flush()

    if not rows:
        raise ValueError(
            f"No cross-sections found in HEC-RAS file {p}. "
            "File may be empty or use an unsupported format."
        )
    logger.info(
        "HEC-RAS imported: %d points across %d cross-sections",
        len(rows),
        len({r["station_m"] for r in rows}),
    )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# River2D .cdg
# ---------------------------------------------------------------------------
# River2D bed/depth files use a simple ASCII layout:
#   line "NODES n"  -> n followed by n lines: id x y z [bed_elev]
#   line "ELEMENTS m" -> m followed by m lines: id n1 n2 n3 [n4]
# Plus optional "BCMODE" / "INFLOW" blocks we skip.

_CDG_NODES_RE = re.compile(r"^\s*NODES\s+(\d+)", re.IGNORECASE)
_CDG_ELEMS_RE = re.compile(r"^\s*ELEMENTS\s+(\d+)", re.IGNORECASE)


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _river2d_int_value(lines: list[str], label: str) -> int | None:
    pattern = re.compile(
        r"^\s*" + r"\s+".join(re.escape(part) for part in label.split()) + r"\s*=\s*(\d+)",
        re.IGNORECASE,
    )
    for line in lines:
        match = pattern.search(line)
        if match:
            return int(match.group(1))
    return None


def _line_after_header(lines: list[str], text: str) -> int | None:
    text_norm = text.lower()
    for idx, line in enumerate(lines):
        if text_norm in line.lower():
            return idx + 1
    return None


def _parse_legacy_river2d_nodes(lines: list[str]) -> list[dict[str, float | int]]:
    nodes: list[dict[str, float | int]] = []
    i = 0
    while i < len(lines):
        m = _CDG_NODES_RE.match(lines[i])
        if m:
            n = int(m.group(1))
            for j in range(1, n + 1):
                if i + j >= len(lines):
                    break
                parts = lines[i + j].split()
                if len(parts) < 4:
                    continue
                rec: dict[str, float | int] = {
                    "node_id": int(float(parts[0])),
                    "x": float(parts[1]),
                    "y": float(parts[2]),
                    "z": float(parts[3]),
                }
                if len(parts) >= 5:
                    try:
                        rec["depth"] = float(parts[4])
                    except ValueError:
                        pass
                nodes.append(rec)
            break
        i += 1
    return nodes


def _parse_official_river2d_nodes(lines: list[str]) -> list[dict[str, float | int | str]]:
    n_nodes = _river2d_int_value(lines, "Number of Nodes")
    if n_nodes is None:
        return []
    n_params = _river2d_int_value(lines, "Number of Parameters") or 0
    n_vars = _river2d_int_value(lines, "Number of Variables") or 0
    start = _line_after_header(lines, "Node #, Coordinates")
    if start is None:
        return []

    rows: list[dict[str, float | int | str]] = []
    for raw in lines[start:]:
        if len(rows) >= n_nodes:
            break
        parts = raw.split()
        if not parts or not _is_number(parts[0]):
            continue
        idx = 1
        node_type: str | None = None
        if idx < len(parts) and not _is_number(parts[idx]):
            node_type = parts[idx]
            idx += 1
        if len(parts) < idx + 2:
            continue
        node_id = int(float(parts[0]))
        x = float(parts[idx])
        y = float(parts[idx + 1])
        idx += 2
        numeric = [float(token) for token in parts[idx:] if _is_number(token)]
        if len(numeric) < n_params + n_vars:
            continue
        params = numeric[:n_params]
        variables = numeric[n_params : n_params + n_vars]
        rec: dict[str, float | int | str] = {"node_id": node_id, "x": x, "y": y}
        if node_type is not None:
            rec["node_type"] = node_type
        if params:
            rec["bed_elevation_m"] = params[0]
            rec["z"] = params[0]
        if len(params) >= 2:
            rec["roughness_m"] = params[1]
        for pos, value in enumerate(params[2:], start=3):
            rec[f"parameter_{pos}"] = value
        if variables:
            rec["depth_m"] = variables[0]
        if len(variables) >= 2:
            rec["unit_discharge_x"] = variables[1]
        if len(variables) >= 3:
            rec["unit_discharge_y"] = variables[2]
        for pos, value in enumerate(variables[3:], start=4):
            rec[f"variable_{pos}"] = value
        rows.append(rec)

    return rows


def _parse_legacy_river2d_elements(lines: list[str]) -> list[dict[str, int]]:
    elements: list[dict[str, int]] = []
    i = 0
    while i < len(lines):
        m = _CDG_ELEMS_RE.match(lines[i])
        if m:
            n = int(m.group(1))
            for j in range(1, n + 1):
                if i + j >= len(lines):
                    break
                parts = lines[i + j].split()
                if len(parts) < 4:
                    continue
                elements.append(
                    {
                        "element_id": int(float(parts[0])),
                        "node_1": int(float(parts[1])),
                        "node_2": int(float(parts[2])),
                        "node_3": int(float(parts[3])),
                    }
                )
            break
        i += 1
    return elements


def _parse_official_river2d_elements(lines: list[str]) -> list[dict[str, int]]:
    n_elements = _river2d_int_value(lines, "Number of Elements")
    if n_elements is None:
        return []
    start = _line_after_header(lines, "Element #, vtype")
    if start is None:
        return []

    rows: list[dict[str, int]] = []
    for raw in lines[start:]:
        if len(rows) >= n_elements:
            break
        parts = raw.split()
        if len(parts) < 6 or not _is_number(parts[0]):
            continue
        node_ids: list[int] = []
        for token in parts[3:]:
            if not _is_number(token):
                continue
            value = int(float(token))
            if value <= 0:
                break
            node_ids.append(value)
            if len(node_ids) == 3:
                break
        if len(node_ids) < 3:
            continue
        rows.append(
            {
                "element_id": int(float(parts[0])),
                "vtype": int(float(parts[1])),
                "gtype": int(float(parts[2])),
                "node_1": node_ids[0],
                "node_2": node_ids[1],
                "node_3": node_ids[2],
            }
        )
    return rows


def read_river2d_cdg(path: str | Path) -> pd.DataFrame:
    """Parse a River2D .cdg bed-mesh file into a node DataFrame.

    Returns a DataFrame with columns:
        node_id, x, y, z (bed elevation), depth (if present)

    Use :func:`read_river2d_elements` when triangular topology is needed
    alongside the node table.
    """
    p = Path(path)
    lines = p.read_text(encoding="latin-1", errors="replace").splitlines()
    nodes = _parse_legacy_river2d_nodes(lines) or _parse_official_river2d_nodes(lines)
    if not nodes:
        raise ValueError(
            f"No NODES block found in River2D .cdg file {p}; "
            "file may be a separate .bcs/.tri output or an unsupported variant."
        )
    table = pd.DataFrame(nodes)
    if {"depth_m", "unit_discharge_x", "unit_discharge_y"}.issubset(table.columns):
        depth = pd.to_numeric(table["depth_m"], errors="coerce")
        qx = pd.to_numeric(table["unit_discharge_x"], errors="coerce")
        qy = pd.to_numeric(table["unit_discharge_y"], errors="coerce")
        q_mag = np.sqrt(qx**2 + qy**2)
        table["velocity_ms"] = np.where(depth > 0.0, q_mag / depth, 0.0)
    elements = _parse_legacy_river2d_elements(lines) or _parse_official_river2d_elements(lines)
    if elements:
        table.attrs["river2d_n_elements"] = len(elements)
    table.attrs["openlimno_output_table"] = "mesh_nodes"
    logger.info("River2D imported: %d nodes from %s", len(nodes), p.name)
    return table


def read_river2d_elements(path: str | Path) -> pd.DataFrame:
    """Parse River2D triangular element topology from a .cdg/.bed file."""

    p = Path(path)
    lines = p.read_text(encoding="latin-1", errors="replace").splitlines()
    elements = _parse_legacy_river2d_elements(lines) or _parse_official_river2d_elements(lines)
    if not elements:
        raise ValueError(f"No River2D element topology found in {p}.")
    table = pd.DataFrame(elements)
    table.attrs["openlimno_output_table"] = "mesh_elements"
    return table


def write_river2d_ugrid(path: str | Path, out_path: str | Path) -> Path:
    """Convert a River2D .cdg/.bed mesh to a minimal UGRID-1.0 NetCDF file."""

    try:
        import xarray as xr
    except ImportError as exc:  # pragma: no cover
        raise ImportError("write_river2d_ugrid requires optional dependency 'xarray'.") from exc

    nodes = read_river2d_cdg(path)
    elements = read_river2d_elements(path)
    node_ids = [int(value) for value in nodes["node_id"]]
    node_index = {node_id: idx for idx, node_id in enumerate(node_ids)}
    face_nodes = elements[["node_1", "node_2", "node_3"]].to_numpy(dtype=int)
    try:
        face_nodes_zero_based = np.vectorize(node_index.__getitem__)(face_nodes)
    except KeyError as exc:
        raise ValueError(f"River2D element references unknown node id {exc.args[0]}.") from exc

    data_vars = {
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
        "mesh2d_node_x": ("nMesh2d_node", nodes["x"].to_numpy(dtype=float)),
        "mesh2d_node_y": ("nMesh2d_node", nodes["y"].to_numpy(dtype=float)),
        "mesh2d_face_nodes": (
            ("nMesh2d_face", "nMaxMesh2d_face_nodes"),
            face_nodes_zero_based.astype("int32"),
            {"cf_role": "face_node_connectivity", "start_index": 0},
        ),
    }
    if "z" in nodes:
        data_vars["bottom_elevation"] = ("nMesh2d_node", nodes["z"].to_numpy(dtype=float))
    if "depth_m" in nodes:
        data_vars["river2d_depth_m"] = ("nMesh2d_node", nodes["depth_m"].to_numpy(dtype=float))
    if "velocity_ms" in nodes:
        data_vars["river2d_velocity_ms"] = (
            "nMesh2d_node",
            nodes["velocity_ms"].to_numpy(dtype=float),
        )

    ds = xr.Dataset(
        data_vars=data_vars,
        attrs={
            "Conventions": "UGRID-1.0",
            "title": f"OpenLimno River2D mesh export from {Path(path).name}",
        },
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(out)
    return out


__all__ = [
    "read_hecras_geometry",
    "read_river2d_cdg",
    "read_river2d_elements",
    "write_river2d_ugrid",
]
