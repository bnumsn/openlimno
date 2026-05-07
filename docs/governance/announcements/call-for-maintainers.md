# Call for Maintainers — OpenLimno (招募维护者)

> **Date**: 2026-05-07 · **Posting channels**: GitHub Discussions, water-resources mailing lists, ECCV / CWRA / IAHR forums, 知乎 / 中国水利学会
>
> **Reference**: SPEC v0.5 §10.1 — 3 named maintainers from ≥ 2 institutions are an M0 exit blocker.

---

## TL;DR (English)

OpenLimno is an open-source desktop platform for **instream-flow habitat
assessment** that replaces the ageing PHABSIM (Fortran, 1995),
River2D (Windows-only, unmaintained), and FishXing (Java, deprecated)
toolchains with a modern stack: a JSON-Schema-defined data model
(WEDM, UGRID-1.0 + CF-1.8 NetCDF), a built-in 1D hydraulic engine
(Manning normal-depth + standard-step backwater, PHABSIM-equivalent),
deep SCHISM v5.11.0 LTS adapter for 2D, multi-scale habitat evaluation
(cell / HMU / reach), and three regulatory export templates
(CN SL/Z 712-2014, US FERC §4(e), EU Water Framework Directive).

The codebase is **functionally complete for a 1.0-rc**: 205 passing tests,
Bovee 1997 PHABSIM closed-form regression at ≤1e-3, SCHISM container ready
to publish, QGIS plugin alpha, CN/US/EU regulatory exports working.

**We are now blocked on governance**: the project needs three named
maintainers (≥ 2 institutional affiliations) before M1 / 1.0 release can
proceed. This post is the open call.

## TL;DR (中文)

OpenLimno 是一个开源桌面级**生态流量评估**平台,目标是替换过时的
PHABSIM (Fortran, 1995)、River2D (仅 Windows, 已停维护)、FishXing
(Java, 已废弃) 等工具链。技术栈:JSON-Schema 数据模型 (WEDM,
UGRID-1.0 + CF-1.8 NetCDF) + 自研 1D 水动力引擎 (Manning 正常水深
+ 标准步法回水, 与 PHABSIM 同精度) + SCHISM v5.11.0 LTS 2D 适配器
+ 多尺度栖息地评估 (cell / HMU / reach) + 三套监管输出模板
(中国 SL/Z 712-2014、美国 FERC §4(e)、欧盟 WFD)。

代码层面**已达 1.0-rc**:205 个测试通过,Bovee 1997 PHABSIM 闭式回归
≤1e-3,SCHISM 容器构建脚本就绪,QGIS 插件 alpha 可用,中美欧监管
输出全部跑通。

现在的瓶颈在**治理结构**:1.0 发布前需要 3 名维护者 (来自 ≥ 2 个机构)。
这是公开招募贴。

---

## What we have (现状)

| | |
|---|---|
| Code | ~5,200 LoC `src/`, ~3,200 LoC `tests/`, Apache-2.0 |
| Data | Lemhi River sample dataset (real USGS 13305000 + Bovee 1978 HSI) |
| Tests | 205 passing, 3 skipped (snakemake/post-1.0 unsteady SWE) |
| Docs | mkdocs-material site (install / quickstart / 7 module pages / API ref) |
| Verification | Bovee 1997 PHABSIM closed-form, MMS 1D, Toro Riemann, all CI-required |
| ADRs | 10 accepted (data formats, SCHISM strategy, 1D engine, BMI, QGIS, HSI rigor, attraction-passage, multi-scale, regulatory exports, scope discipline) |
| Governance | GOVERNANCE.md, CODEOWNERS skeleton, PR/Issue templates, M0 checklist |

## What we need from maintainers (维护者职责)

Each maintainer commits to:

1. ≥ 4 hours/week sustained contribution
2. Code review SLA: 7 working days for non-urgent PRs
3. Quarterly release sign-off
4. Public meetings: ≥ 75% attendance
5. Conflict of interest disclosure

## Ideal background (理想背景)

We want **3 maintainers from ≥ 2 institutions** covering these competencies
(no single person needs all):

- **Hydraulic / hydrodynamic modeling** — comfortable with Manning, standard
  step, SCHISM 2D, calibration. Prior experience with PHABSIM, HEC-RAS,
  River2D, or MIKE21 is a plus.
- **Aquatic ecology / IFIM** — Bovee 1986/1997 method, HSI curve construction,
  WUA interpretation, mesohabitat (Wadeson 1994). Prior fish-passage or
  spawning-suitability work valued.
- **Software engineering** — modern Python (3.12, type hints, pytest, pixi),
  CI/CD, container builds, scientific reproducibility.

**Domain knowledge takes priority over coding experience.** We can pair-program
ecologists with engineers.

## What you get (你能得到什么)

- **Public listing** in `docs/governance/MAINTAINERS.md` and on the
  project README.
- **Release co-authorship credit** on every 1.0+ tagged release.
- **First-author opportunity** on the OpenLimno methods paper
  (target venue: *Environmental Modelling & Software* or *Ecological
  Engineering*, planned 2026-Q3).
- **Conference travel funding** when grant funds become available
  (NSFC / NSF / Horizon Europe applications drafted; see
  `docs/governance/funding/`).
- **Voting rights** on SPEC Change Proposals and PSC composition.

## How to apply (如何申请)

Within 30 days of this post (deadline: 2026-06-07):

1. **Read** [SPEC v0.5](../../../SPEC.md) and the
   [1.0 Capability Boundary Statement](../CAPABILITY_BOUNDARY_1_0.md).
2. **Open a Discussion** at `https://github.com/openlimno/openlimno/discussions`
   with title `[Maintainer Candidate] <your name>` containing:
   - Your name, affiliation, email
   - GPG fingerprint (run `gpg --fingerprint <key>`)
   - 1-2 paragraphs on which competencies above you cover
   - Public CV / Google Scholar / GitHub link
   - Statement that you commit to the 5 obligations above
3. **Sign the boundary statement** by opening a PR adding your row to
   `docs/governance/CAPABILITY_BOUNDARY_1_0.md`.

The first 3 candidates with ≥ 2 distinct affiliations who meet the
competency bar will be confirmed by the project initiator (acrochen@gmail.com)
+ peer review on the Discussion thread.

## What if I want to contribute but not maintain? (我想贡献但不当维护者怎么办)

We absolutely want you. See [CONTRIBUTING.md](../../../CONTRIBUTING.md). The
project also welcomes:

- **Reviewers-of-Record** for the three regulatory frameworks
  (CN SL712 / US FERC / EU WFD)
- **Translators** (the SPEC is bilingual; the docs are English-only)
- **Real-basin case studies** (we have Lemhi US; we want China-domestic
  Yangtze tributary or Yellow River; EU pilot would be welcomed)
- **QGIS plugin testers** on LTS 3.34 / 3.40

## Questions (问)

Open a GitHub Discussion in the **General** category and tag
`@openlimno/initiator`. Or email `acrochen@gmail.com` directly.

---

> *OpenLimno follows the principle in SPEC §0.3: 1.0 is small on purpose.
> If your favorite feature isn't in the [Capability Boundary Statement](../CAPABILITY_BOUNDARY_1_0.md),
> it's intentionally deferred to 1.x or post-1.0. Please don't propose
> adding it during the M0 → M1 transition — file an SCP after 1.0 ships.*
