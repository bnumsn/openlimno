"""R-PHABSIM-REAL test placeholder.

This file documents the test shape that closes unfreeze-gate U3
(CAPABILITY_BOUNDARY D5): the canonical Bovee 1997 cookbook §5.1
case is run through BOTH

  1. the USFWS PHABSIM Fortran binary (containerised; see ../Dockerfile)
  2. OpenLimno's Case.run on the same input deck

and the cell-level outputs are compared. Δ ≤ 1e-3 cell-by-cell on
WUA closes D5.

As of 2026-05-20, the test is **skipped** because:
  - The PHABSIM Fortran binary is not yet built into the container
    (sub-deliverable #2 placeholder)
  - The IFG4-format input deck for Bovee §5.1 is not yet captured
    (sub-deliverable #3)
  - run_phabsim.sh is a placeholder (sub-deliverable #4)

When all three are present, this test:
  - is gated on the ``benchmark`` pytest marker (NOT in default CI;
    runs on tagged ships)
  - is gated on the ``OPENLIMNO_PHABSIM_REAL_IMAGE`` env var pointing
    at the OCI image (so the test can opt-in to a specific build
    rather than rely on ``latest``)
  - mirrors the pattern from ``benchmarks/phabsim_bovee1997/`` —
    same Bovee §5.1 expected-WUA table, but the comparison reference
    is the Fortran-binary output, not the closed-form analytic table
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.benchmark


@pytest.mark.skipif(
    not os.environ.get("OPENLIMNO_PHABSIM_REAL_IMAGE"),
    reason=(
        "R-PHABSIM-REAL scaffold (2026-05-20): set "
        "OPENLIMNO_PHABSIM_REAL_IMAGE=<oci-ref> to opt in. "
        "See benchmarks/phabsim_real/README.md for what still needs "
        "to land before this test exits the scaffold state."
    ),
)
def test_phabsim_real_run_matches_openlimno_bovee_5_1(
    tmp_path: Path,
) -> None:
    """When fully wired:

    1. Mount benchmarks/phabsim_real/inputs/bovee1997_5_1.dat into
       the PHABSIM container, run via run_phabsim.sh, capture the
       normalised CSV (station, Q, depth, velocity, hsi, wua).
    2. Load the same input deck via OpenLimno's PHABSIM-legacy
       importer (openlimno.preprocess.legacy) and run Case.run.
    3. Join on (station, Q) and assert |OpenLimno − PHABSIM| ≤ 1e-3
       on the WUA column. Smaller-than-1e-3 tolerance accepted as a
       bonus; LARGER than 1e-3 fails the test.

    See ADR-0012 for the strategic context (unfreeze-gate U3,
    CAPABILITY_BOUNDARY D5 closure).
    """
    image = os.environ["OPENLIMNO_PHABSIM_REAL_IMAGE"]
    deck = Path(__file__).parent / "inputs" / "bovee1997_5_1.dat"
    assert deck.exists(), (
        f"R-PHABSIM-REAL: input deck not yet captured at {deck}. "
        f"This is sub-deliverable #3 of the R-PHABSIM-REAL track; "
        f"see ADR-0012."
    )
    pytest.fail(
        f"R-PHABSIM-REAL test scaffold: deck exists at {deck} but "
        f"the container-run + comparison logic is still pending "
        f"(sub-deliverables #4 + #5). Image ref: {image}."
    )
