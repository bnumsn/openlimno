"""Lightweight TELEMAC Selafin/Seraphin result reader.

Selafin is a Fortran-unformatted binary format used by TELEMAC and related
models. This adapter intentionally covers the common 2D result surface needed
by OpenLimno: triangular mesh connectivity, node coordinates, node variables,
and selected time-step values averaged onto element/cell rows.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SelafinVariableInfo:
    """Variable metadata from a Selafin header."""

    index: int
    name: str
    unit: str
    role: str | None = None


@dataclass(frozen=True)
class TelemacSelafinInspection:
    """Diagnostic view of a TELEMAC Selafin file."""

    path: str
    title: str
    n_points: int
    n_elements: int
    points_per_element: int
    n_timesteps: int
    times_s: tuple[float, ...]
    variables: tuple[SelafinVariableInfo, ...]
    date: tuple[int, ...] | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TelemacSelafinImportSummary:
    """Small import report for TELEMAC Selafin results."""

    source_key: str
    output_table: str
    n_rows: int
    time_index: int
    time_s: float
    selected_roles: dict[str, str]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TelemacSelafinImportResult:
    """Cell table plus import metadata."""

    table: pd.DataFrame
    summary: TelemacSelafinImportSummary


@dataclass(frozen=True)
class _SelafinHeader:
    path: Path
    title: str
    n_points: int
    n_elements: int
    points_per_element: int
    ikle: np.ndarray
    x: np.ndarray
    y: np.ndarray
    variables: tuple[SelafinVariableInfo, ...]
    endian: str
    float_size: int
    data_offset: int
    record_mark_size: int = 4
    date: tuple[int, ...] | None = None


ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "depth_m": (
        "depth",
        "water depth",
        "waterdepth",
        "hauteur d eau",
        "hauteur d'eau",
        "h",
    ),
    "water_surface_m": (
        "free surface",
        "free surface elevation",
        "surface libre",
        "water surface",
        "water surface elevation",
        "wse",
    ),
    "velocity_ms": (
        "velocity",
        "velocity magnitude",
        "current speed",
        "scalar velocity",
        "speed",
        "norm velocity",
    ),
    "u_ms": (
        "u",
        "u velocity",
        "velocity u",
        "velocity along x",
        "x velocity",
        "current u",
    ),
    "v_ms": (
        "v",
        "v velocity",
        "velocity v",
        "velocity along y",
        "y velocity",
        "current v",
    ),
    "bed_elevation_m": (
        "bottom",
        "bottom elevation",
        "bed elevation",
        "fond",
        "bathymetry",
    ),
}


def _norm(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _role_for_name(name: str) -> str | None:
    normalized = _norm(name)
    for role, aliases in ROLE_ALIASES.items():
        if any(normalized == _norm(alias) for alias in aliases):
            return role
    for role, aliases in ROLE_ALIASES.items():
        if any(len(_norm(alias)) > 2 and _norm(alias) in normalized for alias in aliases):
            return role
    return None


def _detect_endian(f: BinaryIO) -> str:
    start = f.read(4)
    if len(start) != 4:
        raise ValueError("File is too short to be a Selafin file.")
    f.seek(0)
    for endian in (">", "<"):
        if struct.unpack(f"{endian}i", start)[0] == 80:
            return endian
    raise ValueError("Not a Selafin file: first Fortran record is not 80 bytes.")


def _read_record(f: BinaryIO, endian: str) -> bytes | None:
    prefix = f.read(4)
    if prefix == b"":
        return None
    if len(prefix) != 4:
        raise ValueError("Truncated Selafin record marker.")
    n_bytes = struct.unpack(f"{endian}i", prefix)[0]
    if n_bytes < 0:
        raise ValueError(f"Invalid Selafin record length: {n_bytes}")
    payload = f.read(n_bytes)
    suffix = f.read(4)
    if len(payload) != n_bytes or len(suffix) != 4:
        raise ValueError("Truncated Selafin record payload.")
    n_tail = struct.unpack(f"{endian}i", suffix)[0]
    if n_tail != n_bytes:
        raise ValueError(f"Selafin record length mismatch: {n_bytes} != {n_tail}")
    return payload


def _unpack_ints(payload: bytes, endian: str) -> np.ndarray:
    if len(payload) % 4 != 0:
        raise ValueError("Selafin integer record length is not a multiple of 4.")
    return np.frombuffer(payload, dtype=np.dtype(f"{endian}i4")).astype(np.int64)


def _unpack_floats(payload: bytes, endian: str, expected: int | None = None) -> np.ndarray:
    if expected is not None and len(payload) == expected * 8:
        dtype = np.dtype(f"{endian}f8")
    elif expected is not None and len(payload) == expected * 4:
        dtype = np.dtype(f"{endian}f4")
    elif len(payload) % 8 == 0:
        dtype = np.dtype(f"{endian}f8")
    elif len(payload) % 4 == 0:
        dtype = np.dtype(f"{endian}f4")
    else:
        raise ValueError("Selafin float record length is not compatible with 4/8-byte floats.")
    return np.frombuffer(payload, dtype=dtype).astype(float)


def _decode_text(payload: bytes) -> str:
    return payload.decode("latin-1", errors="ignore").strip()


def _read_header(path: str | Path) -> _SelafinHeader:
    p = Path(path)
    with p.open("rb") as f:
        endian = _detect_endian(f)
        title_payload = _read_record(f, endian)
        if title_payload is None or len(title_payload) != 80:
            raise ValueError("Selafin title record must be 80 bytes.")
        title = _decode_text(title_payload)

        nvar_record = _read_record(f, endian)
        if nvar_record is None:
            raise ValueError("Selafin file is missing variable-count record.")
        nvar_info = _unpack_ints(nvar_record, endian)
        if len(nvar_info) < 1:
            raise ValueError("Selafin variable-count record is empty.")
        n_variables = int(nvar_info[0] + (nvar_info[1] if len(nvar_info) > 1 else 0))
        if n_variables <= 0:
            raise ValueError("Selafin file declares no variables.")

        variables: list[SelafinVariableInfo] = []
        for idx in range(n_variables):
            payload = _read_record(f, endian)
            if payload is None:
                raise ValueError("Selafin file ended while reading variable names.")
            text = _decode_text(payload)
            name = _decode_text(payload[:16]) or text
            unit = _decode_text(payload[16:32]) if len(payload) >= 32 else ""
            variables.append(
                SelafinVariableInfo(
                    index=idx,
                    name=name,
                    unit=unit,
                    role=_role_for_name(name),
                )
            )

        iparam_record = _read_record(f, endian)
        if iparam_record is None:
            raise ValueError("Selafin file is missing IPARAM record.")
        iparam = _unpack_ints(iparam_record, endian)
        date: tuple[int, ...] | None = None
        if len(iparam) >= 10 and int(iparam[9]) == 1:
            date_record = _read_record(f, endian)
            if date_record is None:
                raise ValueError("Selafin file declares a date but has no date record.")
            date = tuple(int(v) for v in _unpack_ints(date_record, endian)[:6])

        mesh_record = _read_record(f, endian)
        if mesh_record is None:
            raise ValueError("Selafin file is missing mesh-size record.")
        mesh = _unpack_ints(mesh_record, endian)
        if len(mesh) < 4:
            raise ValueError("Selafin mesh-size record must contain four integers.")
        n_elements = int(mesh[0])
        n_points = int(mesh[1])
        points_per_element = int(mesh[2])
        if n_elements <= 0 or n_points <= 0 or points_per_element <= 0:
            raise ValueError("Selafin mesh has invalid element/point counts.")

        ikle_record = _read_record(f, endian)
        ipobo_record = _read_record(f, endian)
        x_record = _read_record(f, endian)
        y_record = _read_record(f, endian)
        if ikle_record is None or ipobo_record is None or x_record is None or y_record is None:
            raise ValueError("Selafin file ended while reading mesh arrays.")
        ikle = _unpack_ints(ikle_record, endian).reshape(n_elements, points_per_element) - 1
        if len(_unpack_ints(ipobo_record, endian)) != n_points:
            raise ValueError("Selafin IPOBO boundary array length does not match n_points.")
        x = _unpack_floats(x_record, endian, expected=n_points)
        y = _unpack_floats(y_record, endian, expected=n_points)
        if len(x) != n_points or len(y) != n_points:
            raise ValueError("Selafin coordinate arrays do not match n_points.")
        float_size = len(x_record) // n_points

        return _SelafinHeader(
            path=p,
            title=title,
            n_points=n_points,
            n_elements=n_elements,
            points_per_element=points_per_element,
            ikle=ikle,
            x=x,
            y=y,
            variables=tuple(variables),
            endian=endian,
            float_size=float_size,
            data_offset=f.tell(),
            date=date,
        )


def _scan_times(header: _SelafinHeader) -> tuple[float, ...]:
    times: list[float] = []
    with header.path.open("rb") as f:
        f.seek(header.data_offset)
        while True:
            time_payload = _read_record(f, header.endian)
            if time_payload is None:
                break
            time_values = _unpack_floats(time_payload, header.endian, expected=1)
            times.append(float(time_values[0]))
            for _ in header.variables:
                payload = _read_record(f, header.endian)
                if payload is None:
                    raise ValueError("Selafin file ended inside a time-step variable block.")
    return tuple(times)


def _resolve_time_index(n_times: int, time_index: int | None) -> int:
    if n_times <= 0:
        raise ValueError("Selafin file contains no time steps.")
    idx = n_times - 1 if time_index is None else time_index
    if idx < 0:
        idx = n_times + idx
    if idx < 0 or idx >= n_times:
        raise IndexError(f"time_index {time_index} out of range for {n_times} time steps.")
    return idx


def _read_time_step(header: _SelafinHeader, time_index: int) -> tuple[float, dict[str, np.ndarray]]:
    with header.path.open("rb") as f:
        f.seek(header.data_offset)
        for idx in range(time_index + 1):
            time_payload = _read_record(f, header.endian)
            if time_payload is None:
                raise IndexError(f"time_index {time_index} out of range.")
            time_s = float(_unpack_floats(time_payload, header.endian, expected=1)[0])
            values: dict[str, np.ndarray] = {}
            for var in header.variables:
                payload = _read_record(f, header.endian)
                if payload is None:
                    raise ValueError("Selafin file ended inside a variable block.")
                array = _unpack_floats(payload, header.endian, expected=header.n_points)
                if len(array) != header.n_points:
                    raise ValueError(
                        f"Selafin variable {var.name!r} length does not match n_points."
                    )
                if idx == time_index:
                    values[var.name] = array
        return time_s, values


def _element_area(x: np.ndarray, y: np.ndarray, ikle: np.ndarray) -> np.ndarray:
    if ikle.shape[1] < 3:
        return np.full(ikle.shape[0], np.nan)
    x0 = x[ikle[:, 0]]
    y0 = y[ikle[:, 0]]
    area = np.zeros(ikle.shape[0], dtype=float)
    for i in range(1, ikle.shape[1] - 1):
        x1 = x[ikle[:, i]]
        y1 = y[ikle[:, i]]
        x2 = x[ikle[:, i + 1]]
        y2 = y[ikle[:, i + 1]]
        area += 0.5 * np.abs((x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0))
    return area


def _selected_role_variables(header: _SelafinHeader) -> dict[str, str]:
    selected: dict[str, str] = {}
    for var in header.variables:
        if var.role is not None and var.role not in selected:
            selected[var.role] = var.name
    return selected


def inspect_telemac_selafin(path: str | Path) -> TelemacSelafinInspection:
    """Inspect a TELEMAC Selafin/Seraphin file."""

    header = _read_header(path)
    times = _scan_times(header)
    warnings: list[str] = []
    roles = {var.role for var in header.variables if var.role is not None}
    if not {"depth_m", "water_surface_m", "velocity_ms", "u_ms", "v_ms"} & roles:
        warnings.append("No common hydraulic result variables were detected.")
    if header.points_per_element != 3:
        warnings.append(
            f"Expected triangular elements; found {header.points_per_element} points per element."
        )
    return TelemacSelafinInspection(
        path=str(header.path),
        title=header.title,
        n_points=header.n_points,
        n_elements=header.n_elements,
        points_per_element=header.points_per_element,
        n_timesteps=len(times),
        times_s=times,
        variables=header.variables,
        date=header.date,
        warnings=tuple(warnings),
    )


def read_telemac_selafin(
    path: str | Path,
    *,
    source_key: str = "telemac-slf",
    time_index: int | None = None,
) -> TelemacSelafinImportResult:
    """Read a TELEMAC Selafin result file into hydraulic-cell staging rows."""

    header = _read_header(path)
    times = _scan_times(header)
    idx = _resolve_time_index(len(times), time_index)
    time_s, node_values = _read_time_step(header, idx)
    selected = _selected_role_variables(header)
    if not {"depth_m", "water_surface_m", "velocity_ms", "u_ms", "v_ms"} & selected.keys():
        raise ValueError("No common TELEMAC hydraulic variables detected in Selafin file.")

    ikle = header.ikle
    table = pd.DataFrame(
        {
            "source_file": str(header.path),
            "flow_area": header.title or header.path.stem,
            "time_index": idx,
            "time_s": time_s,
            "cell_id": np.arange(header.n_elements, dtype=int),
            "x": header.x[ikle].mean(axis=1),
            "y": header.y[ikle].mean(axis=1),
            "area_m2": _element_area(header.x, header.y, ikle),
            "node_count": header.points_per_element,
        }
    )
    for role, variable_name in selected.items():
        values = node_values[variable_name][ikle].mean(axis=1)
        if role in {"u_ms", "v_ms"}:
            table[role] = values
        elif role == "velocity_ms":
            table["velocity_ms"] = values
        else:
            table[role] = values

    if "velocity_ms" not in table and {"u_ms", "v_ms"}.issubset(table.columns):
        table["velocity_ms"] = np.sqrt(table["u_ms"] ** 2 + table["v_ms"] ** 2)

    warnings: list[str] = []
    if "depth_m" not in table:
        warnings.append("No depth variable detected; downstream WUA needs depth_m.")
    if "velocity_ms" not in table:
        warnings.append("No velocity magnitude or U/V pair detected; downstream WUA needs velocity_ms.")
    if header.points_per_element != 3:
        warnings.append(
            f"Element area was computed for {header.points_per_element}-node polygons."
        )

    table.attrs["openlimno_source_model"] = "TELEMAC-MASCARET Selafin"
    table.attrs["openlimno_source_key"] = source_key
    table.attrs["openlimno_output_table"] = "hydraulic_cells"
    return TelemacSelafinImportResult(
        table=table,
        summary=TelemacSelafinImportSummary(
            source_key=source_key,
            output_table="hydraulic_cells",
            n_rows=len(table),
            time_index=idx,
            time_s=time_s,
            selected_roles=selected,
            warnings=tuple(warnings),
        ),
    )


__all__ = [
    "SelafinVariableInfo",
    "TelemacSelafinImportResult",
    "TelemacSelafinImportSummary",
    "TelemacSelafinInspection",
    "inspect_telemac_selafin",
    "read_telemac_selafin",
]
