"""ADR-0018 fence 4: fishtank course material never enters the public repo.

SPEC.md §0.5 and ADR-0018 declare fishtank a teaching product line on four
conditions, the fourth being that the course material itself stays local and
only ``docs/fishtank/{README,SPEC}.md`` ship. That fence was asserted in prose
and delegated to ``.gitignore`` with nothing checking either half held.

Both halves had already drifted when this file was written: the rules are all
path-specific to ``docs/fishtank/``, so a 172 MB ``fishtank_course_materials.zip``
bundling those same directories sat unignored at the repo root — above GitHub's
100 MB per-file limit, so ``git add -A`` would have produced a commit that could
not be pushed and would need history rewriting to undo.

These tests pin the fence in the form it actually has to hold: material is
ignored *and* untracked, in loose form and bundled.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Loose course-material paths .gitignore must cover. Taken from the block it
#: declares, so deleting a rule there fails here rather than silently widening
#: what a future `git add -A` would sweep in.
LOOSE_MATERIAL = [
    "docs/fishtank/slides/fishtank_course.pdf",
    "docs/fishtank/notebooks/build_along_solution.py",
    "docs/fishtank/abm_minicourse/lesson.md",
    "docs/fishtank/exercises/lab1_dimension_check.py",
    "docs/fishtank/student_bundle/setup.md",
    "docs/fishtank/dist_cli/fishtank.pyz",
    "docs/fishtank/COURSE_PLAN.md",
    "docs/fishtank/TEACHING_RUNSHEET.md",
    "docs/fishtank/INSTRUCTOR_GUIDE.md",
    "docs/fishtank/CLASS_SIMULATION.md",
    "docs/fishtank/QUICKSTART.md",
    "docs/fishtank/USAGE_WALKTHROUGH.md",
    "docs/fishtank/OPENSOURCE_GUIDE.md",
    "docs/fishtank/CHANGELOG_LOCAL.md",
    "docs/fishtank/REHEARSAL_LOG_2026-06-08.md",
]

#: Bundled forms. Packaging the material is exactly what defeats path-specific
#: rules, and it is the normal thing to do before handing a course to someone.
BUNDLED_MATERIAL = [
    "fishtank_course_materials.zip",
    "fishtank_course_materials.tar.gz",
    "fishtank_course.zip",
    "course_material_backup.tar.gz",
    "student_bundle.zip",
    "build/fishtank_course_materials.zip",
    "docs/fishtank/student_bundle.zip",
]

#: The only fishtank docs allowed to ship, per SPEC §0.5 / ADR-0018.
SHIPPABLE_FISHTANK_DOCS = {"docs/fishtank/README.md", "docs/fishtank/SPEC.md"}


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )


@pytest.fixture(scope="module", autouse=True)
def _requires_git_checkout() -> None:
    """Skip in an sdist/wheel install, where there is no repo to inspect."""
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git checkout; the exclusion is a repo-level property")


@pytest.mark.parametrize("path", LOOSE_MATERIAL)
def test_loose_course_material_is_ignored(path: str) -> None:
    proc = _git("check-ignore", "-q", path)
    assert proc.returncode == 0, (
        f"{path} is no longer ignored. SPEC §0.5 / ADR-0018 fence 4 keeps course "
        "material out of the public repo; a deleted .gitignore rule means the "
        "next `git add -A` commits it."
    )


@pytest.mark.parametrize("path", BUNDLED_MATERIAL)
def test_bundled_course_material_is_ignored(path: str) -> None:
    """The loose rules are path-specific; an archive of them must be caught too."""
    proc = _git("check-ignore", "-q", path)
    assert proc.returncode == 0, (
        f"{path} is not ignored. The docs/fishtank/ rules do not cover a bundle "
        "of that same material staged elsewhere — which is how a 172 MB zip once "
        "reached the repo root untracked, above GitHub's 100 MB file limit."
    )


def test_no_course_material_is_actually_tracked() -> None:
    """Ignoring is not the same as absent: assert nothing slipped in earlier.

    A file committed before its rule existed stays tracked forever, and
    .gitignore has no effect on it. Only `git ls-files` can tell us.
    """
    tracked = set(_git("ls-files").stdout.split())
    fishtank_docs = {p for p in tracked if p.startswith("docs/fishtank/")}
    assert fishtank_docs <= SHIPPABLE_FISHTANK_DOCS, (
        "course material is tracked despite being gitignored: "
        f"{sorted(fishtank_docs - SHIPPABLE_FISHTANK_DOCS)}. "
        "Ignoring a path does not untrack it — use `git rm --cached`."
    )


def test_the_pinning_test_is_not_ignored_by_its_own_rule() -> None:
    """The broad patterns match this file's own name — guard against that.

    ``*course_material*`` matches ``test_course_material_exclusion.py``, so on
    first write this file was ignored by the very rule it exists to pin. That
    fails silently and in the worst possible direction: the rule ships, the
    check that proves the rule works does not, and ``git status`` looks clean.
    """
    tracked = set(_git("ls-files").stdout.split())
    own_path = str(Path(__file__).resolve().relative_to(REPO_ROOT))
    assert own_path in tracked, (
        f"{own_path} is not tracked — most likely .gitignore's course-material "
        "patterns are swallowing it. Keep the `!` negation next to them."
    )


def test_no_tracked_file_exceeds_the_github_blob_limit() -> None:
    """The failure mode that made this concrete, generalised past fishtank.

    GitHub hard-rejects a push containing a blob over 100 MB, and by then the
    commit exists locally, so recovery means rewriting history.
    """
    limit = 100 * 1024 * 1024
    oversized = []
    for name in _git("ls-files", "-z").stdout.split("\0"):
        path = REPO_ROOT / name
        if not name or not path.is_file():
            continue  # a deleted-but-tracked path, or a submodule entry
        size = path.stat().st_size
        if size > limit:
            oversized.append((name, size))
    assert not oversized, (
        f"tracked files exceed GitHub's 100 MB per-file limit and cannot be pushed: {oversized}"
    )
