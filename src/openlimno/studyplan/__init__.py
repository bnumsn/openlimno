"""IFIM Study Plan module. SPEC §4.4.

Lightweight, document-driven companion to the computational pipeline:
- Species selection rationale
- Life-stage TUF (Time Use Factor) library defaults vs case overrides
- Objective variable picker
- HSI source decision tree
- Uncertainty acknowledgment

Public API:
    StudyPlan.from_yaml(path)
    StudyPlan.merge_tuf(species, stage, library_default) -> monthly weights
    StudyPlan.report() -> human-readable text
"""

from __future__ import annotations

from .studyplan import StudyPlan, TUFOverride, merge_tuf

__all__ = ["StudyPlan", "TUFOverride", "merge_tuf"]
