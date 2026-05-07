"""StudyPlan loader, validator, and TUF merger. SPEC §4.4.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from openlimno.wedm import validate_studyplan


@dataclass
class TUFOverride:
    """Case-level TUF override entry (SPEC §4.4.1.1)."""

    species: str
    stage: str
    monthly: list[float]
    rationale: str = ""

    def __post_init__(self) -> None:
        if len(self.monthly) != 12:
            raise ValueError("TUF monthly array must have 12 values")
        if any(m < 0 or m > 1 for m in self.monthly):
            raise ValueError("TUF values must be in [0, 1]")


@dataclass
class StudyPlan:
    """A loaded, validated IFIM study plan."""

    config: dict[str, Any]

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StudyPlan":
        path = Path(path)
        errors = validate_studyplan(path)
        if errors:
            raise ValueError(
                "Study plan failed schema validation:\n  - " + "\n  - ".join(errors)
            )
        with path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls(config=config)

    @property
    def problem_statement(self) -> str:
        return self.config["problem_statement"]

    @property
    def target_species(self) -> list[dict[str, Any]]:
        return self.config["target_species_rationale"]

    @property
    def objective_variables(self) -> list[str]:
        return self.config["objective_variables"]

    def tuf_overrides(self) -> dict[tuple[str, str], TUFOverride]:
        out: dict[tuple[str, str], TUFOverride] = {}
        for entry in self.config.get("tuf_override", []):
            ov = TUFOverride(
                species=entry["species"],
                stage=entry["stage"],
                monthly=list(entry["monthly"]),
                rationale=entry.get("rationale", ""),
            )
            out[(ov.species, ov.stage)] = ov
        return out

    def merge_tuf(
        self, species: str, stage: str, library_default_monthly: list[float] | None
    ) -> tuple[list[float], str]:
        """Merge library default with case override (SPEC §4.4.1.1).

        Returns (monthly TUF, source_label) where source ∈ {"library_default",
        "case_override", "fallback_uniform"}.
        """
        overrides = self.tuf_overrides()
        if (species, stage) in overrides:
            return overrides[(species, stage)].monthly, "case_override"
        if library_default_monthly is not None and len(library_default_monthly) == 12:
            return list(library_default_monthly), "library_default"
        return [1.0 / 12] * 12, "fallback_uniform"

    def report(self) -> str:
        """Human-readable report. M2 deliverable per §4.4.2."""
        lines = [
            "OpenLimno Study Plan Report",
            "=" * 60,
            "",
            "Problem statement:",
            f"  {self.problem_statement}",
            "",
            f"Target species ({len(self.target_species)}):",
        ]
        for sp in self.target_species:
            lines.append(f"  - {sp['species']}: {sp['rationale']}")
            if "protection_status" in sp:
                lines.append(f"    Protection: {sp['protection_status']}")

        lines.extend(["", "Objective variables:"])
        for ov in self.objective_variables:
            lines.append(f"  - {ov}")

        if "study_planning" in self.config:
            sp = self.config["study_planning"]
            lines.extend(["", "Study planning (IFIM Step 2):"])
            for k, v in sp.items():
                lines.append(f"  {k}: {v}")

        if "hsi_source_decision" in self.config:
            hsi = self.config["hsi_source_decision"]
            lines.extend(["", "HSI source decision:"])
            lines.append(f"  preference: {hsi.get('preference', 'unspecified')}")
            if "rationale" in hsi:
                lines.append(f"  rationale: {hsi['rationale']}")

        if "uncertainty_sources_acknowledged" in self.config:
            lines.extend(["", "Uncertainty sources acknowledged:"])
            for u in self.config["uncertainty_sources_acknowledged"]:
                lines.append(f"  - {u}")

        overrides = self.tuf_overrides()
        if overrides:
            lines.extend(["", f"TUF overrides ({len(overrides)}):"])
            for (sp_, st_), ov in overrides.items():
                lines.append(f"  - {sp_}/{st_}: {ov.monthly}")
                if ov.rationale:
                    lines.append(f"    rationale: {ov.rationale}")

        return "\n".join(lines)


def merge_tuf(
    studyplan: StudyPlan | None,
    species: str,
    stage: str,
    library_default_monthly: list[float] | None,
) -> tuple[list[float], str]:
    """Module-level helper: equivalent to StudyPlan.merge_tuf but tolerates None."""
    if studyplan is None:
        if library_default_monthly is not None and len(library_default_monthly) == 12:
            return list(library_default_monthly), "library_default"
        return [1.0 / 12] * 12, "fallback_uniform"
    return studyplan.merge_tuf(species, stage, library_default_monthly)


__all__ = ["StudyPlan", "TUFOverride", "merge_tuf"]
