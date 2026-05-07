# NSF Application Outline

> Target program: **NSF Pathways to Enable Open-Source Ecosystems (POSE)**
> Phase II (2026 cycle), with NSF Cyberinfrastructure for Sustained
> Scientific Innovation (CSSI) as backup.

## Why POSE

POSE Phase II funds the **transition** of an existing open-source product
to a sustainable governed ecosystem. OpenLimno fits exactly: code is
written, governance is the bottleneck. POSE Phase II awards run up to
$1.5M / 3 years, which lines up with our 3-maintainer × 2-year cost
model plus US case-study field work.

## Program elements

| POSE requirement | OpenLimno status |
|---|---|
| Existing open-source product with users | 1.0-rc, Apache-2.0, ~5,200 LoC, 205 tests |
| Vision document for the ecosystem | `docs/governance/CAPABILITY_BOUNDARY_1_0.md` |
| Governance structure | GOVERNANCE.md, PSC, MAINTAINERS, ADR process |
| Plan for community building | `docs/governance/announcements/call-for-maintainers.md` |
| Diversity / accessibility | Bilingual SPEC (CN/EN), free desktop deployment, no cloud lock-in |
| Sustainability plan | GitHub Sponsors + Open Collective + grant funding mix |

## Project title

**POSE: Sustaining OpenLimno — Open Infrastructure for Instream-Flow
Habitat Assessment Across US, China, and EU Regulatory Frameworks**

## Project description (15 pages, NSF format)

### 1. Vision (1 page)

OpenLimno will be **the** reference open-source implementation for
instream-flow habitat assessment, replacing the unmaintained PHABSIM /
River2D / FishXing toolchain. A single codebase will export
US FERC §4(e), Chinese SL/Z 712-2014, and EU Water Framework Directive
deliverables, enabling cross-jurisdictional reproducibility for the
first time.

### 2. Importance (2 pages)

- 5,000+ FERC-licensed hydropower facilities in the US currently lack a
  maintained open-source toolchain for §4(e)/§10(j) assessments.
- US Geological Survey IFIM training is still based on PHABSIM Fortran
  (1995) — actively interfering with reproducibility audits required by
  recent OSTP open-science memos.
- The methodology paper from this project will be the first peer-reviewed
  open-source PHABSIM-equivalent implementation since 2010.

### 3. Existing product (3 pages)

- Architecture (data model + 1D engine + SCHISM adapter + habitat /
  passage / regulatory exports)
- Code metrics: 205 passing tests, Bovee 1997 closed-form regression
  ≤1e-3, MMS 1D verification
- ADR record (10 accepted), CAPABILITY_BOUNDARY_1_0 signed
- Existing user community (current state: project initiator + early
  evaluators; growth plan in §5)

### 4. Ecosystem plan (4 pages)

- **Maintainer recruitment**: 3 named maintainers from ≥ 2 institutions
  (US partner candidates: PNNL, USGS, USFS Pacific NW Research Station)
- **Reviewers-of-Record**: a US FERC § 4(e) reviewer named at M2
- **Two real US case studies**: one Pacific Northwest salmon reach
  (steelhead spawning) + one Eastern reach (lamprey passage) — each
  with full FERC §4(e) compliance demonstration
- **Annual user workshop**: co-located with American Fisheries Society
  or Instream Flow Council annual meetings
- **Documentation translation**: English ↔ Chinese parity
  (the SPEC is already bilingual)

### 5. Governance (2 pages)

Proven model from successful POSE awardees (e.g. Pangeo, ROpenSci):

- 3-maintainer rotation
- 5-member PSC with explicit conflict-of-interest policy
- ADR process for technical decisions (template in
  `docs/decisions/_template.md`)
- SPEC Change Proposal (SCP) process for scope changes
- Apache-2.0 + CLA (DCO sign-off)

### 6. Sustainability (2 pages)

| Year | Maintenance | Funding source |
|---|---|---|
| Y1 (2026) | NSF POSE | $500k |
| Y2 (2027) | NSF POSE | $500k |
| Y3 (2028) | NSF POSE + NSFC + Horizon Europe | $500k + matched funds |
| Y4+ | NumFOCUS sponsorship + GitHub Sponsors | community-sustained |

By end of Y3, the project must be sustainable on volunteer maintainer
time + corporate sponsorships, with grant funding as supplement only.
This is realistic given our explicit scope discipline (SPEC §0.3 +
Capability Boundary Statement) — we do not commit to an ever-expanding
scope.

### 7. Diversity, equity, accessibility (1 page)

- Bilingual SPEC (CN/EN), enabling participation from non-Anglophone
  scientists (already in production)
- Desktop-first, zero-cloud-cost deployment — no AWS bill required
- Compatible with mid-2010s laptops (4 GB RAM minimum)
- Active recruitment from underrepresented groups in computational
  science (specific outreach to HBCUs, MSIs, women-in-water-resources
  groups)

### 8. Workplan + budget (deliverable schedule)

| Quarter | Milestone | $ |
|---|---|---|
| 2026-Q3 | M0 exit (3 maintainers signed) | $50k |
| 2026-Q4 | CI deployed, container published, US case 1 field campaign | $150k |
| 2027-Q2 | US case 1 published, methods paper submitted | $200k |
| 2027-Q4 | US case 2 + FERC reviewer-of-record signed | $200k |
| 2028-Q2 | 1.0 release tagged | $200k |
| 2028-Q4 | Year-3 user workshop, sustainability handoff | $200k |

Total: $1.0M (matched by $500k from international partners ⇒ NSFC + EU)

## Letters of Support

To collect (target list):

- PNNL SCHISM team (Joseph Zhang or successor)
- USGS Northern Rocky Mountain Science Center (Lemhi data provenance)
- USFS Pacific Northwest Research Station (FishXing legacy stewards)
- Instream Flow Council (industry adoption)
- Yangtze River Institute (international partner — letter feeds into
  the NSFC application)

## Compliance

- NSF Public Access Plan: code (Apache-2.0) + data (CC-BY-4.0) all
  public from day 1
- DMP: data archived at HydroShare or ESS-DIVE; no embargoed datasets
- Postdoc mentoring plan: required if hiring postdoc — template in
  appendix

## Reference: previous POSE Phase I awards

Match grants comparable to **Pangeo** (#1740648), **ROpenSci** (#2434167),
**JOSS** (#1717527) Phase II for narrative tone and funding profile.
