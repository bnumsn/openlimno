# Architecture Decision Records (ADRs)

ADRs document significant architectural / technical decisions. Format: [MADR 4.0](https://adr.github.io/madr/).

## Active

| # | Title | Status |
|---|---|---|
| [0001](0001-data-formats-open-only.md) | Data formats: open standards only | Accepted |
| [0002](0002-schism-integration-strategy.md) | SCHISM integration: subprocess wrapper, v5.11.0 pinned, OCI container distribution | **Accepted** |
| [0003](0003-1d-engine-build-vs-buy.md) | 1D engine: build (minimal in-house Manning + standard step) | **Accepted** (build, minimal scope) |
| [0004](0004-no-bmi-in-1.0.md) | No BMI in 1.0; introduce when 3rd backend lands | Accepted |
| [0005](0005-qgis-deployment-strategy.md) | QGIS plugin: subprocess CLI not in-process import | Accepted |
| [0006](0006-hsi-rigor-hard-constraints.md) | HSI rigor as hard constraints (not advisory warnings) | Accepted |
| [0007](0007-attraction-passage-decomposition.md) | Passage analysis: η = η_A × η_P split, not pass/fail | Accepted |
| [0008](0008-multi-scale-habitat-aggregation.md) | Multi-scale WUA: cell / HMU / reach | Accepted |
| [0009](0009-regulatory-output-templates.md) | Regulatory output: CN-SL712 / US-FERC / EU-WFD | Accepted (M2 sign-off needed) |
| [0010](0010-spec-scope-discipline.md) | SPEC §0.3 enforcement via PR template + CI check | Accepted |
| [0011](0011-stable-major-tag-moratorium.md) | Moratorium on stable major-version tags until D1+D2+(D5∨D6∨D7) close | **Accepted (interim)** |
| [0012](0012-phabsim-real-fortran-validation.md) | PHABSIM Fortran real-run validation harness (R-PHABSIM-REAL) | Proposed |
| [0013](0013-gui-dependency-direction.md) | GUI dependency direction: `gui_core` / `studio` / `qgis` cleanup (doc-only, refactor blocked by moratorium) | Proposed |
| [0014](0014-charter-pivot-native-ibm.md) | Charter pivot — native IBM as inSTREAM successor (v4 target) | Merged via ADR-0016; PSC ratification pending |
| [0015](0015-ibm-moratorium-exception.md) | Moratorium relationship for native IBM experiment | Superseded by ADR-0016 |
| [0016](0016-author-override-direct-merge.md) | Author override — direct merge of IBM pivot to main | **Accepted (BDFL decision)** |

## Template

See [`_template.md`](_template.md) for new ADRs.

## Process

- Author proposes ADR via PR
- Status: `Proposed` → `Accepted` (PSC majority) | `Rejected` | `Superseded by ADR-XXXX` | `Deprecated`
- Once Accepted, the ADR is immutable. Changes require a new ADR.
