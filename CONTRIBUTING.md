# Contributing to OpenLimno

Thanks for your interest. This document explains how to contribute and what we look for.

## Scope discipline (read this first)

OpenLimno 1.0 has a **frozen scope** in [`SPEC.md`](./SPEC.md) §0.3. Before opening a PR or issue, please check:

- Is your feature in **§0.3 (non-goals)**? It will be treated as Research Roadmap (§13) by default, not 1.0. To change this, file a SPEC change proposal (see below).
- Is your feature in **§13**? Welcome to a `feature/research-*` branch; do not target `main` until 1.0 ships.
- Is your feature in **1.0** scope (§4 modules)? Standard PR workflow applies.

Why so strict? PHABSIM, River2D, and FishXing all stalled when scope grew faster than maintainers. We aim to deliver a 1.0 in 18 months and have a chance.

## Quick links

- [Code of Conduct](./CODE_OF_CONDUCT.md)
- [Governance](./docs/governance/GOVERNANCE.md)
- [Architecture Decision Records (ADRs)](./docs/decisions/)
- [SPEC change proposal template](./docs/governance/SPEC_CHANGE_PROPOSAL.md)

## Development setup

```bash
git clone https://github.com/openlimno/openlimno.git
cd openlimno
pixi install
pixi run pytest
pixi run mkdocs serve
```

## What we accept

| Type | Process |
|---|---|
| Bug fix in 1.0 scope | Direct PR |
| Documentation / typo / example | Direct PR |
| Real-world basin case study | PR adding `examples/<basin>/` with data license |
| Regional HSI curve / species data | PR adding entries to `data/species/` with `evidence` and `quality_grade` |
| New 1.0 feature listed in §4 | Issue first, then PR after maintainer approval |
| §13 research feature | Open issue tagged `research-roadmap`; no main-branch PR until 1.0 |
| SPEC change | File `docs/governance/SPEC_CHANGE_PROPOSAL.md` issue first |

## PR checklist

Before submitting:

- [ ] `pixi run pytest` passes locally
- [ ] `pixi run ruff check .` passes
- [ ] `pixi run mypy src/` passes
- [ ] `pixi run mkdocs build --strict` passes (if docs touched)
- [ ] If touching WEDM schemas, JSON-Schema validation example added to `tests/unit/wedm/`
- [ ] If touching habitat / passage / hydro: at least one regression case in `tests/`
- [ ] If touching SPEC: corresponding implementation PR linked
- [ ] PR description states whether this is **in 1.0 scope** or **research roadmap**
- [ ] No new GPL / commercial-incompatible dependency added (Apache-2.0 / MIT / BSD / LGPL only)

## Commit messages

Format: `<scope>: <imperative summary>` where scope is one of: `wedm`, `preprocess`, `hydro`, `habitat`, `passage`, `studyplan`, `qgis`, `cli`, `docs`, `ci`, `test`.

Example: `habitat: add HMU-level WUA aggregation per SPEC §4.2.3.2`

## Code style

- Python: PEP 8 enforced via ruff
- Type hints: full coverage required for public API (`openlimno.*`)
- Docstrings: NumPy style; SPEC section references where applicable

## Maintainers

See [`docs/governance/MAINTAINERS.md`](./docs/governance/MAINTAINERS.md). M0 deliverable: 3 named maintainers from ≥ 2 institutions.

## Reporting security issues

Email security@openlimno.org (placeholder). Do not file public issues.
