# OpenLimno — Shared Funding Narrative

> Common reusable text for all three target funders. Each agency's
> companion document (NSFC / NSF / Horizon Europe) reuses these
> paragraphs and adds the agency-specific framing.

## Problem statement

Instream-flow assessment — quantifying how much water aquatic ecosystems
need to remain viable — is a regulatory requirement in most major
jurisdictions:

- **China**: SL/Z 712-2014 generalised ecological flow standard
- **United States**: FERC §4(e) and §10(j) for hydropower licensing
- **European Union**: Water Framework Directive (2000/60/EC) ecological
  status assessment

The toolchains practitioners actually use are 25-40 years old:
**PHABSIM** (USFWS, Fortran 77, last release 1995),
**River2D** (University of Alberta, Windows-only, unmaintained since 2010),
**FishXing** (USFS, Java applet, deprecated 2017).
None are maintained, none accept modern data formats (UGRID NetCDF,
Parquet, Apache Arrow), none have reproducibility guarantees, and none
support modern desktop or container deployment.

This is a **research-infrastructure gap**, not a research-novelty gap:
the algorithms (Manning, Bovee HSI, IFIM) are well-understood; the
problem is no maintained open-source vehicle exists.

## What we have built

OpenLimno is a 1.0-rc open-source platform that consolidates the proven
1D/2D habitat-assessment toolchain into a modern, reproducible Python
codebase. As of 2026-05-07:

| Pillar | Deliverable |
|---|---|
| Data model | WEDM v0.1 — 12 JSON-Schemas (Draft 2020-12), UGRID-1.0 + CF-1.8 NetCDF, Parquet biological tables |
| 1D hydraulics | In-house Manning normal-depth + standard-step backwater (PHABSIM/IFG4-equivalent) |
| 2D hydraulics | SCHISM v5.11.0 LTS adapter with OCI container distribution |
| Habitat | Cell / HMU / reach scales; HSI Bovee Category I/II/III rigor with hard `acknowledge_independence` guard |
| Passage | η = η_A × η_P decomposition (Castro-Santos 2005), Monte-Carlo |
| Regulatory | CN SL712 four-tuple, US FERC §4(e), EU WFD ecological status |
| IFIM | Step 1-2 study-plan module |
| Verification | Bovee 1997 PHABSIM closed-form regression ≤1e-3, MMS 1D, 205 passing tests |
| Reproducibility | SHA-256 chain over case yaml + input data + pixi.lock + parameter fingerprint |
| GIS | QGIS plugin alpha (LTS 3.34/3.40 target) |

Code: ~5,200 LoC Python, Apache-2.0; data: CC-BY-4.0.
Repository: `https://github.com/openlimno/openlimno` (to be public at M0 exit).

## What we will deliver with funding

The work that **funding unblocks** falls in three categories:

### 1. Real-basin case studies (largest cost item)

We have a synthetic + Lemhi River (USA) sample dataset. We need at least
one **domestic** case study per jurisdiction:

- **CN**: Yangtze tributary or Yellow River reach, with on-site ADCP
  campaigns, fish sampling, redd counts, and SL712 sign-off
- **US**: FERC-licensed hydropower reach with §4(e) regulatory review
- **EU**: WFD-classified water body with ecological-status assessment

Each case requires field work, data licensing, expert review, and travel.

### 2. Continuous-integration + container infrastructure

GitHub Actions matrix CI (linux × macOS × Windows × Py 3.11+3.12),
GHCR-hosted SCHISM v5.11.0 container, mkdocs site at docs.openlimno.org.
Modest cost (~10k USD/year for hosted services + occasional Apple
Silicon runner credits).

### 3. Maintainer time

Three core maintainers, each at ~4 hr/week × 2 years through 1.x release.
This is the dominant cost: ~120k USD/maintainer/year × 3 × 2 = ~720k USD
total, scalable down with volunteer fraction.

## Why this matters

**Regulatory science depends on reproducible tools**. PHABSIM-era results
cannot be re-run today on modern hardware; FERC and SL712 filings are
assessed against frozen Fortran binaries that nobody can audit. When
those tools die — and they are dying — *every* historical regulatory
record loses its computational provenance.

OpenLimno is the open replacement: data formats are documented, code is
auditable, results are byte-reproducible (SHA-256-chained provenance),
and the boundary between OpenLimno-owned code and SCHISM-owned solver is
explicit.

## Why now

- PHABSIM / River2D / FishXing have all hit terminal maintenance.
- SCHISM matured to a stable LTS line in 2024-2025.
- Modern Python scientific stack (xarray, pyarrow, pixi, mkdocstrings)
  finally makes reproducibility achievable.
- Three regulatory frameworks (CN SL712, US FERC §4(e), EU WFD) are
  simultaneously updating their methodology guidance in 2026-2028.

A 2-year funding window (2026-2028) places OpenLimno as the reference
implementation across all three frameworks before the next regulatory
update cycles.

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| SCHISM upstream breaks LTS API | M | LTS pin v5.11.0 (ADR-0002), regression suite, 18-month upgrade lead time |
| Maintainer churn | M | 3 maintainers across 2 institutions (bus factor ≥ 2), CODEOWNERS bus-factor rule |
| Scope creep | H | SPEC §0.3 explicit non-goals + ADR-0010 + Capability Boundary Statement signed at M0 |
| Regulatory framework changes | L | Reviewers-of-record per framework; provenance chain enables back-classification |
| Funding gap | M | Phased deliverables: M0 → M1 → M2 → 1.0 each independently shippable |

## License + sustainability

- Code: **Apache-2.0** (commercial-friendly, Apache compatible with FSF)
- Data: **CC-BY-4.0** (attribution-required)
- Trademark: "OpenLimno" reserved by the project; non-fork derivatives must rebrand
- Sustainability: GitHub Sponsors + Open Collective + grant funding;
  zero-dollar deployment remains supported in perpetuity.

## Project metrics (committed)

| Metric | M0 (now) | 1.0 target | 1.x target |
|---|---|---|---|
| Maintainers | 0 named | 3 | 5 |
| CI platforms | local | 3 OS × 2 Py | 3 OS × 2 Py + arm64 |
| Test count | 205 | ≥ 250 | ≥ 350 |
| Real-basin cases | 0 (synthetic + Lemhi) | 3 (CN/US/EU) | 6+ |
| Citations | 0 | ≥ 5 (methods paper out) | ≥ 50 |
| Regulatory reviewers | 0 signed | 3 signed | 6+ |
