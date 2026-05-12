"""External-source provenance sidecar (v0.3 P0).

When ``init-from-osm --fetch-dem`` / ``--fetch-discharge`` etc. pull data
from public APIs, we drop a sidecar JSON next to the case data files
recording:

* the source URL (so the reader can re-run the fetch if needed)
* the fetch_time (when the data was originally pulled — survives
  cache hits, since the cache layer preserves the original time)
* SHA-256 of the produced file (so ``openlimno reproduce`` can verify
  it hasn't been mutated since)
* SHA-256 of the raw fetched payload (different from produced — the
  fetched payload may be post-processed before becoming the case file)
* the API params that uniquely identify the request (bbox / site_id /
  date range / …)
* the case-data file path the fetch produced

The sidecar lives at ``<case_dir>/data/.openlimno_external_sources.json``
so it travels with the case files when users ``git commit`` the case
or ``rsync`` it to a server. ``Case._build_provenance`` reads it and
folds it into the run-time ``provenance.json``.

Format: a JSON list of records. Append-only — multiple fetches in
one ``init-from-osm`` call become multiple records.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


SIDECAR_NAME = ".openlimno_external_sources.json"


@dataclass
class ExternalSourceRecord:
    """One auto-fetched dataset's provenance.

    Attributes:
        label: short ID like ``"cross_section_dem"`` /
            ``"discharge_nwis"`` so reproduce can match records to
            expected case-data files.
        source_type: classifier (``"copernicus_dem"`` / ``"usgs_nwis"``
            / future ``"era5_temp"`` etc.) so downstream tools can
            re-fetch with the right module without parsing the URL.
        source_url: canonical request URL (without query params).
        fetch_time: ISO-8601 of when the upstream server returned the
            payload. For cache hits this is the ORIGINAL fetch time,
            so an ``init-from-osm`` of a re-buit case still references
            the data's true origin.
        produced_file: relative path (from case_dir) of the file the
            fetch ultimately produced. e.g.
            ``"data/cross_section.parquet"``.
        produced_sha256: SHA-256 of the produced file at write time.
            ``openlimno reproduce`` verifies the file still hashes the
            same value.
        params: API params that uniquely identify the request
            (bbox + dates + station_id etc.). Folded into the
            sidecar so anyone can re-fetch with the same arguments.
        notes: free-text human-readable summary (station name, n
            tiles, …). Optional.
    """

    label: str
    source_type: str
    source_url: str
    fetch_time: str
    produced_file: str
    produced_sha256: str
    params: dict = field(default_factory=dict)
    notes: str = ""


def _sidecar_path(case_dir: str | Path) -> Path:
    return Path(case_dir) / "data" / SIDECAR_NAME


class SidecarCorruptedError(RuntimeError):
    """The sidecar file exists but its contents are malformed.

    Distinct subclass so callers (case.py / reproduce) can choose
    whether to fail loudly or warn-and-continue. Default is fail loudly
    — silent "no external sources" would silently break reproducibility
    guarantees the sidecar exists to provide.
    """


def read_sidecar(case_dir: str | Path) -> list[dict]:
    """Load the external-sources sidecar.

    Returns an empty list ONLY if the sidecar doesn't exist (case was
    built without ``--fetch-*`` flags). If the sidecar exists but is
    corrupt (invalid JSON, wrong root type) raises
    ``SidecarCorruptedError`` — silently returning [] would orphan the
    provenance trail without telling the user, which is exactly the
    failure mode this file exists to prevent.
    """
    path = _sidecar_path(case_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SidecarCorruptedError(
            f"External-source sidecar at {path} is not valid JSON: {e}. "
            f"Either restore from version control or delete the file and "
            f"re-run `openlimno init-from-osm --fetch-*` to regenerate "
            f"the provenance trail."
        ) from e
    if not isinstance(data, list):
        raise SidecarCorruptedError(
            f"External-source sidecar at {path} root type must be a JSON "
            f"list, got {type(data).__name__}. Delete the file and re-run "
            f"`openlimno init-from-osm --fetch-*` to regenerate."
        )
    return data


def record_fetch(
    case_dir: str | Path,
    *,
    label: str,
    source_type: str,
    source_url: str,
    fetch_time: str,
    produced_file: str | Path,
    params: dict | None = None,
    notes: str = "",
) -> ExternalSourceRecord:
    """Append a fetch record to the case sidecar.

    Computes ``produced_sha256`` from the current file contents on
    disk. The caller MUST write the produced_file before calling this
    — otherwise reproduce will check against an empty-file hash and
    every later read will look mutated.

    Idempotent: calling twice with the same ``label`` REPLACES the
    earlier record (so re-running ``init-from-osm --fetch-*`` against
    the same case_dir produces an up-to-date sidecar, not a stack of
    stale entries).
    """
    case_dir = Path(case_dir)
    produced_file = Path(produced_file)
    if not produced_file.is_absolute():
        full = case_dir / produced_file
    else:
        full = produced_file
        # Store as case-relative for portability
        try:
            produced_file = full.relative_to(case_dir)
        except ValueError:
            pass  # outside case_dir — keep absolute

    if not full.exists():
        raise FileNotFoundError(
            f"Cannot record fetch: produced_file {full} doesn't exist. "
            f"Write the file first, then call record_fetch."
        )
    sha = hashlib.sha256(full.read_bytes()).hexdigest()
    rec = ExternalSourceRecord(
        label=label,
        source_type=source_type,
        source_url=source_url,
        fetch_time=fetch_time,
        produced_file=str(produced_file),
        produced_sha256=sha,
        params=params or {},
        notes=notes,
    )

    sidecar = _sidecar_path(case_dir)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    existing = read_sidecar(case_dir)
    # Drop any prior record with the same label (idempotent)
    existing = [r for r in existing if r.get("label") != label]
    existing.append(asdict(rec))
    sidecar.write_text(json.dumps(existing, indent=2))
    return rec


def verify_sidecar(case_dir: str | Path) -> list[tuple[str, bool, str]]:
    """Check each record's produced_file SHA against current disk SHA.

    Returns a list of ``(label, ok, reason)`` tuples. ``ok`` is False
    when the file is missing, unreadable, or the SHA differs. ``reason``
    is "" on ok=True.
    """
    out: list[tuple[str, bool, str]] = []
    case_dir = Path(case_dir)
    for rec in read_sidecar(case_dir):
        label = rec.get("label", "?")
        produced = rec.get("produced_file", "")
        expected = rec.get("produced_sha256", "")
        path = case_dir / produced
        if not path.exists():
            out.append((label, False, f"file missing: {produced}"))
            continue
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as e:
            out.append((label, False, f"unreadable: {e}"))
            continue
        if actual != expected:
            out.append((
                label, False,
                f"SHA mismatch: produced_sha={expected[:12]}…, "
                f"current={actual[:12]}… — file has been modified since fetch"
            ))
        else:
            out.append((label, True, ""))
    return out
