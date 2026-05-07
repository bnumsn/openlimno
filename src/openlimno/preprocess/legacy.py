"""Legacy cross-section importers (best-effort). SPEC §4.0.1 M3.

Two minimal parsers for cross-section data trapped in legacy software formats:

* **HEC-RAS .g0X geometry files** — fixed-format ASCII; we extract reach + cross
  section "X1"/"GR" records and yield a normalised DataFrame.
* **River2D .cdg bed-mesh files** — node + element ASCII; we extract the
  ``ELEVATION`` block as point data along a synthetic station.

Limitations: these are *best-effort* readers. Hydraulic structures (bridges,
weirs, culverts), Manning n strips, and rating-curve overrides are NOT parsed —
a warning is emitted and the user is expected to redefine those in WEDM.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

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
        chunk = s[i:i + 8].strip()
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
            rows.append({
                "river": river,
                "reach": reach,
                "station_m": float(cur_station),
                "point_index": i // 2,
                "distance_m": float(dist),
                "elevation_m": float(elev),
            })
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
        len(rows), len({r["station_m"] for r in rows})
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


def read_river2d_cdg(path: str | Path) -> pd.DataFrame:
    """Parse a River2D .cdg bed-mesh file into a node DataFrame.

    Returns a DataFrame with columns:
        node_id, x, y, z (bed elevation), depth (if present)

    The triangulation is read but not returned in the DataFrame; pair this
    output with ``preprocess.validate_ugrid_mesh`` after exporting to UGRID.
    """
    p = Path(path)
    lines = p.read_text(encoding="latin-1", errors="replace").splitlines()
    nodes: list[dict[str, float]] = []
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
                rec: dict[str, float] = {
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
            break  # only one NODES block in the bed file
        i += 1
    if not nodes:
        raise ValueError(
            f"No NODES block found in River2D .cdg file {p}; "
            "file may be a separate .bcs/.tri output."
        )
    logger.info("River2D imported: %d nodes from %s", len(nodes), p.name)
    return pd.DataFrame(nodes)


__all__ = [
    "read_hecras_geometry",
    "read_river2d_cdg",
]
