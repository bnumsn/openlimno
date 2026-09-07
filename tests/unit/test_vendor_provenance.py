"""Integrity + provenance pins for the vendored fishtank third-party runtime.

``src/openlimno/fishtank/vendor/`` holds the only third-party binary blob in
the tree: the pre-minified three.js ES-module build the fishtank Studio serves
to the browser for its 3D virtual aquarium (offline teaching — student machines
may have no CDN access).

OpenLimno's whole external-data story is content-addressing: every fetched
dataset gets a SHA-256, a source URL and a fetch time in
``.openlimno_external_sources.json`` (see
``openlimno.preprocess.fetch.sidecar``). This module holds the vendored blob to
the same standard:

* the blob's SHA-256 must equal the one recorded in ``vendor/PROVENANCE.json``
  — so silently swapping, patching or truncating the runtime turns CI red,
  which is the entire point of writing a provenance record down;
* the MIT license file must be present and non-empty (attribution is a
  redistribution condition, and the file ships in the wheel);
* ``PROVENANCE.json`` must itself parse and carry the mandatory fields, so it
  can't rot into a decorative file that nothing depends on.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import openlimno.fishtank as fishtank

VENDOR_DIR = Path(fishtank.__file__).resolve().parent / "vendor"
PROVENANCE = VENDOR_DIR / "PROVENANCE.json"

# Fields every record must carry. Names are deliberately identical to
# ``sidecar.ExternalSourceRecord`` so provenance is one vocabulary across the
# project (fetched data and vendored code), plus the vendor-specific size pin.
REQUIRED_RECORD_FIELDS = (
    "label",
    "source_type",
    "source_url",
    "fetch_time",
    "produced_file",
    "produced_sha256",
    "size_bytes",
    "params",
    "notes",
)

REQUIRED_TOP_LEVEL_FIELDS = (
    "schema",
    "schema_version",
    "upstream",
    "license",
    "why_vendored",
    "verification",
    "records",
)


def _load_provenance() -> dict:
    assert PROVENANCE.is_file(), (
        f"{PROVENANCE} is missing. The vendored three.js runtime must ship "
        f"with a provenance record (upstream URL, version, SHA-256)."
    )
    return json.loads(PROVENANCE.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_provenance_json_parses_and_has_required_top_level_fields() -> None:
    data = _load_provenance()
    assert isinstance(data, dict)
    missing = [f for f in REQUIRED_TOP_LEVEL_FIELDS if f not in data]
    assert not missing, f"PROVENANCE.json missing required field(s): {missing}"
    assert isinstance(data["records"], list) and data["records"], (
        "PROVENANCE.json must record at least one vendored file."
    )


def test_provenance_records_have_required_fields() -> None:
    for rec in _load_provenance()["records"]:
        missing = [f for f in REQUIRED_RECORD_FIELDS if f not in rec]
        assert not missing, (
            f"PROVENANCE.json record {rec.get('label', '<unlabelled>')!r} "
            f"missing field(s): {missing}"
        )
        # A record whose hash is blank/placeholder pins nothing.
        assert len(rec["produced_sha256"]) == 64, (
            f"record {rec['label']!r}: produced_sha256 must be a full "
            f"64-hex-char SHA-256, got {rec['produced_sha256']!r}"
        )
        int(rec["produced_sha256"], 16)  # raises if not hex
        assert rec["source_url"].startswith("https://"), (
            f"record {rec['label']!r}: source_url must be an https upstream URL"
        )


def test_vendored_files_exist_and_match_recorded_sha256() -> None:
    """The pin. Replace/patch the blob without updating the record -> red CI."""
    records = _load_provenance()["records"]
    seen = set()
    for rec in records:
        path = VENDOR_DIR / rec["produced_file"]
        seen.add(rec["produced_file"])
        assert path.is_file(), f"vendored file {path} recorded but missing"
        assert path.stat().st_size == rec["size_bytes"], (
            f"{path.name}: size {path.stat().st_size} != recorded {rec['size_bytes']}"
        )
        assert _sha256(path) == rec["produced_sha256"], (
            f"{path.name}: SHA-256 differs from PROVENANCE.json. Either the "
            f"vendored file was modified (it must be verbatim upstream) or it "
            f"was upgraded without updating vendor/PROVENANCE.json. See that "
            f"file's `verification.refetch_commands`."
        )
    # The runtime the Studio actually serves must be one of the pinned files.
    assert "three.module.min.js" in seen


def test_three_license_present_and_non_empty() -> None:
    license_path = VENDOR_DIR / _load_provenance()["license"]["file"]
    assert license_path.is_file(), (
        f"{license_path} missing — the MIT license text is a redistribution "
        f"condition for the vendored three.js runtime."
    )
    text = license_path.read_text(encoding="utf-8")
    assert text.strip(), "license file is empty"
    assert "MIT" in text
    assert "three.js" in text.lower()


def test_recorded_version_is_either_verified_or_honestly_flagged() -> None:
    """Provenance must not be vague: state a verified version, or say so.

    A record that quietly omits the version is worse than one that admits it
    is unverified, because it reads as authoritative while pinning nothing.
    """
    upstream = _load_provenance()["upstream"]
    assert upstream.get("version"), "upstream.version must be recorded"
    verified = upstream.get("version_verified")
    assert isinstance(verified, bool), "upstream.version_verified must be an explicit true/false"
    evidence = upstream.get("version_evidence") or []
    assert evidence, (
        "upstream.version_evidence must list how the version was determined "
        "(or, when unverified, what was tried and what the constraints are)."
    )
    if not verified:
        assert "unverified" in str(upstream["version"]).lower(), (
            "an unverified version must be labelled 'unverified', never left "
            "looking like a confirmed release number"
        )


@pytest.mark.parametrize(
    "consumer",
    # studio_http.py serves the file; studio_tank3d.mjs is the module that
    # actually imports it. The import used to live inside the studio_assets.py
    # string literal — when the JS moved into a real asset file, this list had
    # to move with it, which is the point of pinning the consumer names here.
    ["studio_http.py", "studio_tank3d.mjs"],
)
def test_provenance_lists_the_modules_that_consume_the_runtime(consumer: str) -> None:
    consumed = _load_provenance().get("consumed_by", [])
    files = [entry.get("file", "") for entry in consumed]
    assert any(f.endswith(consumer) for f in files), (
        f"PROVENANCE.json consumed_by should name {consumer}, so a future "
        f"reader can find who depends on the vendored runtime."
    )


def test_provenance_consumers_actually_reference_the_runtime() -> None:
    """Every consumed_by entry must really mention the vendored file.

    Without this, consumed_by silently rots into a list of plausible-looking
    paths — exactly what happened when the three.js import moved out of
    studio_assets.py into an asset file.
    """
    repo_root = Path(__file__).resolve().parents[2]
    for entry in _load_provenance().get("consumed_by", []):
        path = repo_root / entry["file"]
        assert path.is_file(), f"consumed_by names a missing file: {entry['file']}"
        assert "three.module.min.js" in path.read_text(encoding="utf-8"), (
            f"consumed_by names {entry['file']}, but that file never mentions three.module.min.js"
        )
