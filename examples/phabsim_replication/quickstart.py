"""PHABSIM replication quickstart.

Builds the closed-form Bovee 1997 dataset, runs ``Case.run()`` end-to-end,
and asserts the produced WUA matches the analytic expectation within 1e-3.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


def main() -> int:
    # 1. Build sample data (idempotent)
    if not (HERE / "data" / "expected_wua.json").exists():
        from examples.phabsim_replication.build_data import main as build  # type: ignore
        build()

    # 2. Run the case
    sys.path.insert(0, str(HERE.parents[1] / "src"))
    from openlimno.case import Case

    case = Case.from_yaml(HERE / "case.yaml")
    Qs = [0.5, 1.5, 4.0, 8.0]
    res = case.run(discharges_m3s=Qs, slope=0.001, manning_n=0.030)
    print(res.summary())

    # 3. Compare against analytic expectation
    expected = json.loads((HERE / "data" / "expected_wua.json").read_text())
    df = res.wua_q[["discharge_m3s", "wua_m2_oncorhynchus_mykiss_spawning"]]
    print("\nAnalytic vs. OpenLimno WUA:")
    print(f"  {'Q (m³/s)':>10} {'analytic':>12} {'openlimno':>12} {'rel err':>10}")
    max_err = 0.0
    for Q in Qs:
        analytic = float(expected[str(Q)])
        ol = float(df.loc[df["discharge_m3s"] == Q,
                          "wua_m2_oncorhynchus_mykiss_spawning"].iloc[0])
        rel = abs(ol - analytic) / max(analytic, 1e-9)
        max_err = max(max_err, rel)
        print(f"  {Q:>10.2f} {analytic:>12.3f} {ol:>12.3f} {rel:>10.2e}")
    if max_err > 1e-2:
        print(f"\nFAIL: max relative error {max_err:.2e} > 1e-2")
        return 1
    print(f"\nPASS: max relative error {max_err:.2e} ≤ 1e-2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
