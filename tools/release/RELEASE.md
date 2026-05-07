# OpenLimno — Ship Checklist (you, the human, run this)

> Code is functionally complete (1.0-rc; 205 passing tests). The remaining
> steps require **your account, your signatures, and decisions only you
> can make**. Walk this list top-to-bottom; every step is independent and
> can stop / resume cleanly.
>
> Estimated total wall time: **2-4 weeks** (mostly waiting on humans, not work).

---

## 0. Before you start (5 minutes)

```bash
# Verify the local working tree matches what's in this repo
cd /mnt/data/openlimno
PYTHONPATH=src python3 -m pytest tests/ benchmarks/ -q
# Expected: 205 passed, 3 skipped
```

If anything fails, stop and read the failure — DO NOT push to GitHub
yet.

## 1. Initialise git and push to a private GitHub repo (15 minutes)

```bash
cd /mnt/data/openlimno

# Local git init
git init
git config user.name "<your name>"
git config user.email "acrochen@gmail.com"
# (Optional but recommended: enable GPG signing)
# git config commit.gpgsign true
# git config user.signingkey <your GPG key id>

# Stage everything except generated outputs
git add -A
git rm -r --cached examples/lemhi/out 2>/dev/null || true
git rm -r --cached examples/phabsim_replication/data 2>/dev/null || true
git rm -r --cached examples/phabsim_replication/out 2>/dev/null || true

git commit -m "OpenLimno 1.0-rc: initial public commit

Implements SPEC v0.5 in full:
  - WEDM v0.1 (12 JSON-Schemas, Draft 2020-12)
  - Built-in 1D engine (Manning + standard step)
  - SCHISM v5.11.0 LTS adapter (OCI container)
  - Multi-scale habitat (cell/HMU/reach)
  - Passage (eta_A x eta_P)
  - Regulatory exports (CN-SL712, US-FERC-4e, EU-WFD)
  - StudyPlan IFIM Step 1-2
  - 205 passing tests, Bovee 1997 regression <=1e-3
  - 10 ADRs accepted
  - Capability Boundary 1.0 awaiting signatures

Apache-2.0 (code) + CC-BY-4.0 (data)."

# Create GitHub repo first via web UI:
#   1. https://github.com/new
#   2. Name: openlimno (or your-org/openlimno)
#   3. Visibility: PRIVATE for now (flip to public at step 4)
#   4. DO NOT initialise with README/license/.gitignore
#
# Then push:
git branch -M main
git remote add origin git@github.com:<you>/openlimno.git
git push -u origin main
```

**Verify**: visit the repo URL, confirm CI doesn't run yet (no maintainers
configured), confirm code is intact.

## 2. Wire up CI secrets (10 minutes)

In the GitHub repo settings → Secrets and variables → Actions:

| Secret | Source | Used by |
|---|---|---|
| `CODECOV_TOKEN` | https://app.codecov.io after linking the repo | `.github/workflows/ci.yml` |

(GHCR push uses `GITHUB_TOKEN` automatically — no secret needed.)

In repo settings → Actions → General → Workflow permissions:
- ☑ Read and write permissions
- ☑ Allow GitHub Actions to create and approve pull requests

## 3. First CI run (~15-30 minutes wall clock)

Push any small follow-up commit to trigger CI:

```bash
git commit --allow-empty -m "ci: trigger initial workflow run"
git push
```

Watch `https://github.com/<you>/openlimno/actions`. You should see:

| Job | Expected runtime |
|---|---|
| `lint` | 1-2 min |
| `typecheck` | 2-3 min |
| `schema-validation` | 1 min |
| `test (ubuntu × Py3.11)` | 5-10 min |
| `test (ubuntu × Py3.12)` | 5-10 min |
| `test (macos × Py3.11)` | 8-15 min |
| `test (macos × Py3.12)` | 8-15 min |
| `test (windows × Py3.11)` | 10-20 min |
| `test (windows × Py3.12)` | 10-20 min |
| `benchmark-fast` | 2-5 min |
| `docs` | 1-2 min |
| `spec-scope-check` | < 1 min |

If anything is RED:
- macOS arm64: fortran/openmpi may need `brew install` step in the workflow
- Windows: pyarrow/scipy wheels usually auto-resolve via pixi; if not,
  check `pixi.toml` features
- Don't fix blindly — read the failure first

## 4. Flip the repo to public + announce (30 minutes)

Repo settings → General → Danger zone → Change visibility → Public.

Then post the call-for-maintainers:

1. Open `docs/governance/announcements/call-for-maintainers.md`
2. Copy-paste the body to GitHub Discussions (category: Announcements)
3. Cross-post to:
   - 中国水利学会论坛 / 知乎"水利"话题
   - InstreamFlow Council mailing list
   - WFD-CIS workgroup (via existing contact)
   - Twitter/Mastodon `#openscience #aquaticecology` tags

## 5. Build & publish the SCHISM container (30-60 minutes)

```bash
cd /mnt/data/openlimno

# Local single-arch build first to verify everything works
bash containers/schism/build.sh
# Wait ~30 minutes for the SCHISM Fortran build to complete.
# If it fails, read the Dockerfile comments and fix the build flag.

# Once local build smoke-tests OK, push via the workflow:
#   GitHub → Actions → "SCHISM container" → Run workflow
#   Branch: main, push: true
# Wait ~60 minutes for multi-arch buildx to finish.

# Then verify the public image exists:
docker pull ghcr.io/openlimno/schism:5.11.0
docker run --rm ghcr.io/openlimno/schism:5.11.0 || true   # exits non-zero, that's expected
```

After it lands, **pin the digest** in:
- `docs/decisions/0002-schism-integration-strategy.md` §Implementation
- `SPEC.md` §6.1 SCHISM section

```bash
docker inspect --format='{{index .RepoDigests 0}}' ghcr.io/openlimno/schism:5.11.0
# Take the sha256:... and paste into the two files above.
```

## 6. Recruit the 3 maintainers (~2-4 weeks)

This is the dominant wait. Steps:

1. The call-for-maintainers Discussion stays open 30 days
2. Candidates open `[Maintainer Candidate]` discussions (template in §C
   of the call)
3. You + at least 2 community reviewers (your existing collaborators)
   review each candidate in the public thread
4. Confirmed candidates open a PR adding their row to:
   - `docs/governance/MAINTAINERS.md`
   - `docs/governance/CAPABILITY_BOUNDARY_1_0.md` §F
5. PR is merged with GPG-verified signatures (see `git commit -S`)

**Bus factor**: at least 2 distinct affiliations. Reject candidates if
all three would be from the same lab.

## 7. M0 review meeting (1 hour, after maintainers signed)

Use `docs/governance/meetings/2026-Q2-M0-review-template.md`:

1. Schedule a Zoom + 腾讯会议 dual-listen meeting
2. Walk the M0 checklist (`tools/m0_checklist/M0_CHECKLIST.md`)
3. Vote on M0 → M1 transition
4. Save filled minutes as `docs/governance/meetings/2026-Q2-M0-review-YYYYMMDD.md`
5. Open a PR; once merged, update M0_CHECKLIST.md status to "M0 EXITED"

## 8. Cut the 1.0-rc1 tag

```bash
git tag -s v1.0-rc1 -m "OpenLimno 1.0 release candidate 1"
git push origin v1.0-rc1
```

GitHub Actions has no release-publishing workflow yet (intentional —
1.0-rc is a tag, not a release). After 30 days of stable rc1, repeat
for `v1.0-rc2`, then finally `v1.0` when D1-D8 are all checked
(see `docs/governance/CAPABILITY_BOUNDARY_1_0.md` §D).

## 9. (After 1.0) Sustainability hand-off

Once 1.0 ships:

- Add NumFOCUS sponsorship (apply at https://numfocus.org/projects-overview)
- Open GitHub Sponsors / Open Collective
- Submit funding applications (`docs/governance/funding/`):
  - NSFC: 中国自然科学基金面上项目, 申请代码 E090 / D01
  - NSF POSE Phase II
  - Horizon Europe Cluster 6 BIODIV destination

---

## Things you do NOT have to do

These are out of scope for the 1.0 ship and were intentionally deferred:

- Per-OS native installers (`.dmg`, `.msi`) — pixi is the official install
- Web UI / SaaS — explicitly excluded by SPEC §0.3
- ML surrogate / GPU solver — research roadmap §13
- BMI multi-solver — ADR-0004 rejected for 1.0

Anyone asking for these post-launch should be redirected to the
Capability Boundary Statement and told to file an SCP.

## Emergency contacts

- SCHISM upstream: https://schism-dev.github.io/ → mailing list
- pixi build issues: https://github.com/prefix-dev/pixi/issues
- mkdocs-material: https://github.com/squidfunk/mkdocs-material/issues
- The methods paper: see `docs/governance/funding/00-shared-narrative.md` §"Project metrics"

---

**Last updated**: 2026-05-07 (post final-completion sweep v2 + governance kit)

When something goes wrong during ship, the right answer is almost always:
> "Read the relevant ADR, then ask the maintainers in the public Discussion."

Do not ship around process. The process is the value.
