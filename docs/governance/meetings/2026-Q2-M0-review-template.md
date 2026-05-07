# M0 Review Meeting Minutes (TEMPLATE)

> Fill in the bracketed sections, rename the file to
> `2026-Q2-M0-review-YYYYMMDD.md`, and merge via PR signed by the chair.
>
> SPEC v0.5 §10.1 / M0 checklist Bonus item 1.

## Meeting metadata

| | |
|---|---|
| **Date / time** | YYYY-MM-DD HH:MM (timezone) |
| **Location** | [Zoom URL / 腾讯会议 / room] |
| **Chair** | [name, affiliation] |
| **Scribe** | [name] |
| **Quorum** | [N attended / N required] — quorum reached: yes / no |

## Attendees

### Maintainer candidates (3)

| Name | Affiliation | Present | Vote (Y/N/abstain) on M0 exit |
|---|---|---|---|
| _TBD_ | _TBD_ | ☐ | _ |
| _TBD_ | _TBD_ | ☐ | _ |
| _TBD_ | _TBD_ | ☐ | _ |

### PSC members (5)

| Role | Name | Present | Vote |
|---|---|---|---|
| Ecologist | _TBD_ | ☐ | _ |
| Water resources engineer | _TBD_ | ☐ | _ |
| Software engineer | _TBD_ | ☐ | _ |
| At-large 1 | _TBD_ | ☐ | _ |
| At-large 2 | _TBD_ | ☐ | _ |

### Observers / community

- _list any non-voting attendees_

---

## Agenda

1. M0 exit checklist walkthrough (`tools/m0_checklist/M0_CHECKLIST.md`)
2. CAPABILITY_BOUNDARY_1_0 review and sign-off
3. CI status across linux/macOS/Windows × Py 3.11/3.12
4. SCHISM container publication readiness
5. Risk register (open issues blocking M1)
6. Vote: M0 → M1 transition (yes / no / hold)
7. Action items + next meeting

---

## 1. Checklist walkthrough

| Item | Status | Owner | Notes |
|---|---|---|---|
| 1. Three named maintainers signed | ☐ ☐ ☐ | _ | |
| 2. WEDM v0.1 schemas + sample data | ✅ | _ | 12 schemas, Lemhi sample, 15 round-trip tests |
| 3. SCHISM integration ADR Accepted | ✅ | _ | ADR-0002 v5.11.0 LTS pin |
| 4. 1D engine ADR Accepted | ✅ | _ | ADR-0003 build (minimal) |
| 5. Capability Boundary signed | ☐ | _ | |
| 6. Three-platform CI green | ☐ | _ | Pending GitHub Actions deployment |
| 7. SCHISM container published | ☐ | _ | Workflow ready, awaits manual trigger |

(Tick boxes after the meeting; exact verification commands in the M0 checklist.)

## 2. Capability Boundary review

- Sections re-read aloud: §A (capabilities IN), §B (non-goals OUT)
- Marketing claims in §E confirmed by all attendees
- _Any objections raised_: [yes / no — list]
- _Amendments proposed_: [list, or "none"]

## 3. CI status

| Platform / Py | Status | Last green run |
|---|---|---|
| ubuntu-latest / 3.11 | ☐ | URL |
| ubuntu-latest / 3.12 | ☐ | URL |
| macos-latest / 3.11 | ☐ | URL |
| macos-latest / 3.12 | ☐ | URL |
| windows-latest / 3.11 | ☐ | URL |
| windows-latest / 3.12 | ☐ | URL |

## 4. SCHISM container

- Build verified locally: ☐ (digest: `sha256:_____`)
- GHCR push attempt: ☐ (URL: `ghcr.io/openlimno/schism:5.11.0`)
- Multi-arch manifest confirmed: ☐ (linux/amd64 + linux/arm64)
- ADR-0002 digest pinned in PR: ☐

## 5. Risk register

| # | Risk | Owner | Severity | Mitigation |
|---|---|---|---|---|
| R1 | _e.g. SCHISM build flake on macOS arm64_ | _ | M | _ |
| R2 | | | | |

## 6. Vote: M0 → M1 transition

**Motion**: "OpenLimno has met all M0 exit criteria; M1 development may begin."

| Voter | Vote |
|---|---|
| Maintainer 1 | _ |
| Maintainer 2 | _ |
| Maintainer 3 | _ |
| PSC × 5 | _ × 5 |

**Result**: PASSED / FAILED / HELD-FOR-FOLLOWUP

If FAILED or HELD: list the specific blocker items below and target resolution date:

- _blocker 1_
- _blocker 2_

## 7. Action items

| # | Action | Owner | Due |
|---|---|---|---|
| A1 | | | |
| A2 | | | |

## Next meeting

- Date: YYYY-MM-DD
- Standing agenda: M1 sprint review, ADR-0011 (TBD), reviewers-of-record progress

---

## Sign-off

| Role | Name | Signature (initials + date) |
|---|---|---|
| Chair | | |
| Scribe | | |
