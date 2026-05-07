"""SPEC §0.3 scope discipline check.

Reads `SPEC.md` §0.3 (1.0 non-goals), extracts forbidden keywords, greps changed
Python files for them. Outputs warnings to stdout. Used in CI (advisory, not blocking).

Per ADR-0010.

Usage:
    python tools/m0_checklist/spec_scope_check.py [path...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "SPEC.md"

# Hand-curated keyword set derived from SPEC §0.3 non-goals.
# Update when SPEC changes (and bump SPEC version).
NON_GOAL_KEYWORDS = {
    "gpu_solver": [r"\bcuda\b", r"\bcupy\b", r"\bcudf\b"],
    "self_2d_solver": [r"\bswe2d_native\b", r"\bself_built_swe\b"],
    "self_3d_solver": [r"\bnh_swe\b", r"\bnon_hydrostatic\b"],
    "uq": [r"\bensemble_kalman\b", r"\bpolynomial_chaos\b", r"\bpce\b", r"\bbayesian_calib"],
    "data_assimilation": [r"\benkf\b", r"\b4dvar\b", r"\bdata_assim"],
    "ml_surrogate": [r"\bfno\b", r"\bdeeponet\b", r"\bneural_operator\b"],
    "ibm": [r"\bagent_based\b", r"\bibm_fish\b", r"\blangevin_fish\b"],
    "population_dynamics": [r"\bleslie_matrix\b", r"\bipm_pop"],
    "thermal": [r"\btemperature_advection\b", r"\bheat_balance\b", r"\briparian_shading\b"],
    "water_quality": [r"\bstreeter_phelps\b", r"\bwasp\b"],
    "sediment": [r"\bmeyer_peter\b", r"\bvan_rijn\b", r"\bexner\b", r"\bhirano\b"],
    "web_gui": [r"\bfastapi\b", r"\bflask\b", r"\bdjango\b", r"\btauri\b"],
    "cloud": [r"\bkubernetes\b", r"\bargo_workflows\b", r"\bhelm\b"],
    "embedded": [r"\bmqtt\b", r"\bruntime_min\b"],
    "bmi": [r"\bbmi\.\b", r"\bibmi_\b"],
}


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv[1:]] if len(argv) > 1 else [REPO_ROOT / "src/openlimno"]
    py_files: list[Path] = []
    for p in paths:
        if p.is_dir():
            py_files.extend(p.rglob("*.py"))
        elif p.is_file() and p.suffix == ".py":
            py_files.append(p)

    findings: list[tuple[Path, int, str, str]] = []
    for f in py_files:
        try:
            text = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for category, patterns in NON_GOAL_KEYWORDS.items():
            for pattern in patterns:
                for lineno, line in enumerate(text, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append((f, lineno, category, line.strip()))

    if findings:
        print("[spec-scope-check] Found references to SPEC §0.3 non-goal keywords:")
        for f, lineno, cat, line in findings:
            print(f"  {f.relative_to(REPO_ROOT)}:{lineno}  [{cat}]")
            print(f"    {line[:120]}")
        print()
        print("If these are §13 research roadmap features:")
        print("  - Move them to a `research-*` branch, not main")
        print("If they should be in 1.0:")
        print("  - File a SPEC change proposal (docs/governance/SPEC_CHANGE_PROPOSAL.md)")
        print()
        print("This check is advisory; CI does not block on it. PSC review required for override.")
        return 0  # advisory: do not fail CI
    print("[spec-scope-check] OK: no §0.3 non-goal keywords detected")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
