"""SPEC §0.3 scope discipline check.

Greps ``src/openlimno`` (or the paths given on the command line) for
identifiers that denote SPEC §0.3 "1.0 non-goals", classifies every hit as
either **exempted** (an explicitly registered, documented research-route or
cross-reference) or **unexempted**, and exits non-zero on the latter.

Per ADR-0010 (enforcement layers) and ADR-0017 (this rewrite).

Two things changed relative to the original ADR-0010 implementation:

1. **Word boundaries.** The original used ``\\b`` around multi-word snake_case
   phrases (``\\bagent_based\\b``). ``_`` is a *word* character, so ``\\b`` never
   holds where snake_case composition actually puts the phrase:
   ``re.search(r"\\bagent_based\\b", "simulate_agent_based_model")`` is ``None``.
   Every multi-word pattern in the original table was therefore blind to the
   exact case it existed to catch. See ``_snake`` / ``_token`` below for the
   replacement boundary policy and the per-entry rationale in the keyword
   table.

2. **Advisory → blocking, with an explicit exemption register.** ADR-0010
   rejected hard-failing because of false positives ("a comment mentioning GPU
   as future work"). That objection is answered by ``EXEMPTIONS``: a narrow,
   documented allowlist keyed on *path glob + specific keyword*, each entry
   carrying a reason and a citable basis (SPEC section / README section / ADR).
   Exempted hits are **printed, not swallowed**, so the fact that e.g.
   ``src/openlimno/ibm/`` contains agent-based code — deliberately, per
   ADR-0014/0015/0016 — is visible in every CI log. Anything not on the
   register fails the run.

Exit codes:
    0  no findings, or every finding is exempted (or ``--advisory`` was passed)
    1  at least one unexempted §0.3 non-goal hit
    2  bad usage / malformed exemption register

Usage:
    python tools/m0_checklist/spec_scope_check.py [path...]
    python tools/m0_checklist/spec_scope_check.py --advisory src/openlimno/
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "SPEC.md"


# ---------------------------------------------------------------------
# Boundary policy
# ---------------------------------------------------------------------
# Two classes of pattern, because they carry different false-positive risk:
#
#   _snake(...)  multi-word phrase ("agent_based", "meyer_peter"). A two-plus
#                word technical phrase is specific enough that *any* occurrence
#                is signal, so there is no leading anchor at all — that is what
#                lets it fire inside `simulate_agent_based_model` and
#                `AgentBasedModel`. Words are joined with `[_-]?` so snake_case,
#                kebab-case, CamelCase and SCREAMING_SNAKE all match. The
#                trailing guard is `_PHRASE_TAIL` — see below.
#
#   _token(...)  single short word or abbreviation ("pce", "wasp", "enkf").
#                These need a strict boundary or they fire inside unrelated
#                words. `\b` is still wrong (it treats `_` as a word character,
#                so `\bwasp\b` misses `my_wasp_model`), so the guard is
#                "the whole alphanumeric run must be exactly this word":
#                `(?<![0-9A-Za-z])word(?![0-9A-Za-z])`. `_` reads as a
#                separator, `wasps` and `space` do not match.

_SEP = "[_-]?"

# Trailing guard for phrases: "this phrase is not the prefix of a longer word".
#
# The hard part is that a phrase has to keep matching when the identifier
# continues with a *new* word, but stop matching when the identifier continues
# the *same* word — and the two look identical if you only inspect the next
# character:
#
#     AgentBasedModel    -> `AgentBased` + new word `Model`   : must MATCH
#     RUNTIME_MINUTES    -> `RUNTIME_MIN` + rest of `MINUTES`  : must NOT match
#
# Both continue with an uppercase letter. What separates them is the *case style
# of the text just matched*: in CamelCase a new word starts with an uppercase
# letter after a lowercase one, whereas in SCREAMING_SNAKE words are separated
# only by `_`, never by a case transition. So the guard branches on the last
# character consumed by the body (via a lookbehind, which sees through the
# scoped `(?i:...)` group):
#
#   ...ends lowercase  -> CamelCase style: an uppercase letter starts a new
#                         word, so only a lowercase letter is forbidden.
#   ...ends uppercase  -> SCREAMING_SNAKE style: a case transition carries no
#     or a digit          meaning, so any letter is forbidden.
#
# Digits are permitted in both branches: a digit never continues an English
# word, so `TemperatureAdvection1d`, `self_built_swe_v2` and `runtime_min1` are
# the keyword plus a dimension/version/index suffix, not a different word.
#
# A previous revision used a bare `(?![a-z0-9])`, which is the lowercase-only
# half of this rule; it passed `runtime_minutes` but false-positived on
# `RUNTIME_MINUTES`. Both spellings are pinned pairwise in the unit tests.
_PHRASE_TAIL = r"(?:(?<=[a-z])(?![a-z])|(?<=[0-9A-Z])(?![A-Za-z]))"


def _snake(*words: str, prefix: bool = False) -> str:
    """Pattern for a multi-word phrase, matchable inside a longer identifier.

    IGNORECASE is applied only to the phrase body via ``(?i:...)`` so that
    :data:`_PHRASE_TAIL` can still tell the case styles apart; a global
    ``re.IGNORECASE`` would flatten every character class in the guard and
    defeat it.

    ``prefix=True`` drops the trailing guard, for entries that are deliberately
    stems (``data_assim`` must also catch ``data_assimilation``).
    """
    if len(words) < 2:  # pragma: no cover - guards a table authoring mistake
        raise ValueError("_snake is for multi-word phrases; use _token()")
    body = "(?i:" + _SEP.join(re.escape(w) for w in words) + ")"
    return body if prefix else body + _PHRASE_TAIL


def _token(word: str, *, digit_suffix: bool = False) -> str:
    """Pattern for a single short word: the whole alphanumeric run must match.

    ``digit_suffix=True`` also accepts one trailing digit, for product names
    that ship a version number in the token (``WASP7``, ``WASP8``).
    """
    body = "(?i:" + re.escape(word) + (r"[0-9]?" if digit_suffix else "") + ")"
    return r"(?<![0-9A-Za-z])" + body + r"(?![0-9A-Za-z])"


# ---------------------------------------------------------------------
# Keyword register
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class Keyword:
    """One §0.3 non-goal detector.

    ``rationale`` records *why this boundary* was chosen, so a future editor can
    tell a deliberate loose match from an accident.
    """

    id: str
    category: str
    pattern: str
    rationale: str


def _phrase_kw(
    kw_id: str, category: str, *words: str, prefix: bool = False, note: str = ""
) -> Keyword:
    base = (
        "multi-word phrase: unanchored so it fires inside longer snake_case / "
        "SCREAMING_SNAKE / "
        "CamelCase identifiers; false-positive risk is negligible at this specificity"
    )
    if prefix:
        base += "; stem match (no trailing guard) so longer suffixes are caught"
    return Keyword(
        kw_id, category, _snake(*words, prefix=prefix), f"{base}{'; ' + note if note else ''}"
    )


def _token_kw(
    kw_id: str, category: str, word: str, *, digit_suffix: bool = False, note: str = ""
) -> Keyword:
    base = (
        "short token: strict segment boundary kept to avoid firing inside "
        "unrelated words; `_` still reads as a separator (unlike `\\b`)"
    )
    if digit_suffix:
        base += "; one trailing digit allowed for versioned product names"
    return Keyword(
        kw_id,
        category,
        _token(word, digit_suffix=digit_suffix),
        f"{base}{'; ' + note if note else ''}",
    )


# Hand-curated, cross-checked against SPEC.md §0.3 (see `SPEC` above).
# NOTE: despite ADR-0010's implementation note, this table is *not* parsed out
# of SPEC.md at runtime — §0.3 is prose (and Chinese prose at that), not a
# machine-readable list. Update this table by hand when §0.3 changes.
NON_GOAL_KEYWORDS: tuple[Keyword, ...] = (
    # --- 自研 GPU 求解器 ------------------------------------------------
    # Deliberately no bare `gpu`/`mpi` token: those are prose words that appear
    # in unrelated notes (a browser "GPU stall" comment, "MPI processes" for the
    # *external* SCHISM binary). The import-level tokens below are what an
    # actual in-house GPU solver would look like. See ADR-0017 open items.
    _token_kw("cuda", "gpu_solver", "cuda"),
    _token_kw("cupy", "gpu_solver", "cupy"),
    _token_kw("cudf", "gpu_solver", "cudf"),
    # --- 自研 2D/3D 求解器 ----------------------------------------------
    _phrase_kw("swe2d_native", "self_2d_solver", "swe2d", "native"),
    _phrase_kw("self_built_swe", "self_2d_solver", "self", "built", "swe"),
    _phrase_kw("nh_swe", "self_3d_solver", "nh", "swe"),
    _phrase_kw("non_hydrostatic", "self_3d_solver", "non", "hydrostatic"),
    # --- 不确定性量化 / 集合预报 ----------------------------------------
    _phrase_kw("ensemble_kalman", "uq", "ensemble", "kalman"),
    _phrase_kw("polynomial_chaos", "uq", "polynomial", "chaos"),
    _token_kw(
        "pce",
        "uq",
        "pce",
        note="no English word is exactly `pce`, so the strict boundary costs nothing",
    ),
    _phrase_kw("bayesian_calib", "uq", "bayesian", "calib", prefix=True),
    _phrase_kw("bayesian_hsi", "uq", "bayesian", "hsi", note="named in ADR-0010's keyword sketch"),
    # --- 数据同化 -------------------------------------------------------
    _token_kw("enkf", "data_assimilation", "enkf"),
    _token_kw("4dvar", "data_assimilation", "4dvar"),
    _phrase_kw("data_assim", "data_assimilation", "data", "assim", prefix=True),
    # --- ML 代理模型 / 神经算子 -----------------------------------------
    _token_kw("fno", "ml_surrogate", "fno"),
    _token_kw("deeponet", "ml_surrogate", "deeponet"),
    _phrase_kw("neural_operator", "ml_surrogate", "neural", "operator"),
    # --- 个体行为模型 (IBM/ABM) -----------------------------------------
    # SPEC §0.3 names "IBM/ABM" literally, and ADR-0010's own implementation
    # note lists `ibm` as an intended keyword — but the shipped table never had
    # it, which is why 11k LOC of `src/openlimno/ibm/` scanned clean for months.
    _token_kw(
        "ibm", "ibm", "ibm", note="the §0.3 term itself; strict boundary keeps it off `ibmi`/`bimb`"
    ),
    _token_kw("abm", "ibm", "abm", note="the §0.3 term itself"),
    _phrase_kw("individual_based", "ibm", "individual", "based"),
    _phrase_kw("agent_based", "ibm", "agent", "based"),
    _phrase_kw("ibm_fish", "ibm", "ibm", "fish"),
    _phrase_kw("langevin_fish", "ibm", "langevin", "fish"),
    # --- 种群动力学 -----------------------------------------------------
    _phrase_kw("leslie_matrix", "population_dynamics", "leslie", "matrix"),
    _phrase_kw("ipm_pop", "population_dynamics", "ipm", "pop", prefix=True),
    _phrase_kw("population_dynamics", "population_dynamics", "population", "dynamics"),
    # --- 水温 -----------------------------------------------------------
    # Bare `thermal`/`temperature` are NOT keywords: temperature as an HSI input
    # (`habitat/thermal.py`) is in 1.0 scope; what §0.3 excludes is *modelling*
    # the heat budget. These three phrases are that modelling vocabulary.
    _phrase_kw("temperature_advection", "thermal", "temperature", "advection"),
    _phrase_kw("heat_balance", "thermal", "heat", "balance"),
    _phrase_kw("riparian_shading", "thermal", "riparian", "shading"),
    # --- 水质 -----------------------------------------------------------
    _phrase_kw("streeter_phelps", "water_quality", "streeter", "phelps"),
    _token_kw(
        "wasp",
        "water_quality",
        "wasp",
        digit_suffix=True,
        note="`wasps` stays out; `WASP7`/`WASP8` come in",
    ),
    # --- 泥沙 / 河床演变 -------------------------------------------------
    _phrase_kw("meyer_peter", "sediment", "meyer", "peter"),
    _phrase_kw("van_rijn", "sediment", "van", "rijn"),
    _token_kw("exner", "sediment", "exner"),
    _token_kw("hirano", "sediment", "hirano"),
    # --- Web GUI / 云原生 ------------------------------------------------
    _token_kw("fastapi", "web_gui", "fastapi"),
    _token_kw(
        "flask",
        "web_gui",
        "flask",
        note="lab glassware sense is possible; strict boundary + review",
    ),
    _token_kw("django", "web_gui", "django"),
    _token_kw("tauri", "web_gui", "tauri"),
    _token_kw("kubernetes", "cloud", "kubernetes"),
    _phrase_kw("argo_workflows", "cloud", "argo", "workflows"),
    _token_kw("helm", "cloud", "helm"),
    # --- 嵌入式实时调度 --------------------------------------------------
    _token_kw("mqtt", "embedded", "mqtt"),
    _phrase_kw(
        "runtime_min",
        "embedded",
        "runtime",
        "min",
        note="trailing guard keeps `runtime_minutes` AND `RUNTIME_MINUTES` out",
    ),
    # --- 多求解器 BMI 互换 -----------------------------------------------
    # The original table had `\bbmi\.\b` and `\bibmi_\b`. Both were unreachable:
    # `\b` after a `.` needs a following word character, `\b` after `_` needs a
    # following non-word character, and `ibmi` is not a term in SPEC or the
    # codebase (almost certainly a typo for `bmi_`). Replaced with one token.
    _token_kw("bmi", "bmi", "bmi", note="ADR-0004; matches the acronym in any snake_case position"),
)

KEYWORDS_BY_ID: dict[str, Keyword] = {k.id: k for k in NON_GOAL_KEYWORDS}


# ---------------------------------------------------------------------
# Exemption register
# ---------------------------------------------------------------------
class ExemptionError(ValueError):
    """The exemption register is malformed (too broad, stale, or a typo)."""


@dataclass(frozen=True)
class Exemption:
    """One narrow, documented carve-out.

    An exemption is **path glob + specific keywords**. There is deliberately no
    "exempt this whole tree for everything" form — see ``validate_exemptions``.
    """

    path_glob: str
    keywords: tuple[str, ...]
    reason: str
    basis: tuple[str, ...]


EXEMPTIONS: tuple[Exemption, ...] = (
    Exemption(
        path_glob="src/openlimno/ibm/**",
        keywords=("ibm", "individual_based", "agent_based", "ibm_fish", "langevin_fish"),
        reason=(
            "Declared research route: the native IBM prototype targeted at v4, "
            "merged to main by author override. Not part of the 1.0 capability "
            "boundary and not claimed as a calibrated inSTREAM replacement."
        ),
        basis=(
            "SPEC.md §13 (research roadmap)",
            'README.md "What 1.0 does NOT do"',
            "docs/decisions/0014-charter-pivot-native-ibm.md",
            "docs/decisions/0016-author-override-direct-merge.md",
        ),
    ),
    Exemption(
        path_glob="src/openlimno/cli.py",
        keywords=("ibm", "abm", "individual_based"),
        reason=(
            "CLI entry points for the declared research prototypes: "
            "`ibm-run-native`, `ibm-benchmark-instream7`, "
            "`ibm-summarize-instream7-brief`, plus the fishtank ODE/ABM stack."
        ),
        basis=(
            'README.md "What 1.0 does NOT do" (names these subcommands)',
            "docs/decisions/0016-author-override-direct-merge.md",
        ),
    ),
    Exemption(
        path_glob="src/openlimno/fishtank/**",
        keywords=("abm", "agent_based"),
        reason=(
            "Teaching microcosm (closed-aquarium ODE + ABM) used as the worked "
            "example for a 4-hour Master's lab. Its own spec lists the ABM as "
            "in-scope; it is not part of the 1.0 ecological-flow capability "
            "boundary. NOTE: this basis is module-local — the root SPEC §0.3 / "
            "README charter does not yet mention fishtank at all (ADR-0017 open item O1)."
        ),
        basis=(
            "docs/fishtank/SPEC.md §0 (in-scope list names the ABM)",
            "docs/decisions/0017-scope-check-exemption-register.md",
        ),
    ),
    Exemption(
        path_glob="src/openlimno/preprocess/**",
        keywords=("ibm", "individual_based"),
        reason=(
            "The inSTREAM / NetLogo CSV *bridge*. Exchanging tables with an "
            "external IBM is the 1.0 role; §0.3 excludes owning an IBM, not "
            "interoperating with one."
        ),
        basis=(
            "SPEC.md §0.3 (excludes OpenLimno-owned IBM, not exchange formats)",
            "docs/decisions/0014-charter-pivot-native-ibm.md (context: 'OpenLimno's role was the CSV bridge')",
        ),
    ),
    Exemption(
        path_glob="src/openlimno/hydro/**",
        keywords=("ibm",),
        reason=(
            "Docstring cross-references to the R-IBM-* post-merge cleanup tracks, "
            "plus the `ibm_forcing` / IBM-compatible hydraulic-cell CSV export "
            "column names (bridge output, not an IBM implementation)."
        ),
        basis=(
            "docs/decisions/0016-author-override-direct-merge.md (R-IBM-* cleanup track table)",
        ),
    ),
    Exemption(
        path_glob="src/openlimno/hydro/__init__.py",
        keywords=("bmi",),
        reason=(
            "Module docstring that documents the *exclusion* ('SPEC §3.2 rejects "
            "BMI in 1.0'). Exactly the false-positive class ADR-0010 cited when "
            "it chose advisory mode; recorded here instead of disabling the check."
        ),
        basis=(
            "SPEC.md §3.2",
            "docs/decisions/0004-no-bmi-in-1.0.md",
        ),
    ),
)


def validate_exemptions(
    exemptions: tuple[Exemption, ...] = EXEMPTIONS,
    *,
    keywords_by_id: dict[str, Keyword] | None = None,
    doc_root: Path | None = None,
) -> None:
    """Raise :class:`ExemptionError` if the register is not narrow and citable.

    Enforced invariants:

    * every entry names at least one keyword, and no wildcard keyword — a
      "whole tree, all keywords" carve-out is not expressible on purpose;
    * every keyword id exists in :data:`NON_GOAL_KEYWORDS` (catches typos and
      keywords that were renamed out from under the register);
    * every entry carries a non-empty reason and at least one basis;
    * a basis that looks like a repo-relative document path must actually exist.
    """
    known = KEYWORDS_BY_ID if keywords_by_id is None else keywords_by_id
    root = REPO_ROOT if doc_root is None else doc_root
    seen: set[tuple[str, str]] = set()
    for ex in exemptions:
        if not ex.path_glob:
            raise ExemptionError("exemption with empty path_glob")
        if not ex.keywords:
            raise ExemptionError(f"{ex.path_glob}: exemption must name at least one keyword")
        if "*" in ex.keywords:
            raise ExemptionError(
                f"{ex.path_glob}: wildcard keyword exemptions are forbidden — "
                "list the specific keywords so the carve-out stays narrow"
            )
        for kw_id in ex.keywords:
            if kw_id not in known:
                raise ExemptionError(f"{ex.path_glob}: unknown keyword id {kw_id!r}")
            if (ex.path_glob, kw_id) in seen:
                raise ExemptionError(f"duplicate exemption for {ex.path_glob} / {kw_id}")
            seen.add((ex.path_glob, kw_id))
        if not ex.reason.strip():
            raise ExemptionError(f"{ex.path_glob}: exemption must carry a reason")
        if not ex.basis:
            raise ExemptionError(f"{ex.path_glob}: exemption must cite a basis")
        for cite in ex.basis:
            doc = cite.split(" ", 1)[0]
            if "/" in doc and doc.endswith(".md") and not (root / doc).exists():
                raise ExemptionError(f"{ex.path_glob}: basis document not found: {doc}")


# ---------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class Finding:
    path: str  # repo-relative posix path when possible
    lineno: int
    keyword_id: str
    category: str
    line: str


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def iter_python_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.is_file() and p.suffix == ".py":
            files.append(p)
    return files


def scan(
    paths: list[Path],
    *,
    root: Path | None = None,
    keywords: tuple[Keyword, ...] = NON_GOAL_KEYWORDS,
) -> list[Finding]:
    """Return every §0.3 non-goal hit under ``paths``, unclassified."""
    base = REPO_ROOT if root is None else root.resolve()
    compiled = [(k, re.compile(k.pattern)) for k in keywords]
    findings: list[Finding] = []
    for f in iter_python_files(paths):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        rel = _relative(f, base)
        for lineno, line in enumerate(lines, 1):
            for kw, rx in compiled:
                if rx.search(line):
                    findings.append(Finding(rel, lineno, kw.id, kw.category, line.strip()))
    return findings


def path_matches(rel: str, pattern: str) -> bool:
    """Match a repo-relative posix path against an exemption glob.

    ``dir/**`` means "everything under dir"; anything else is fnmatch.
    """
    if pattern.endswith("/**"):
        return rel.startswith(pattern[:-2])
    return fnmatch.fnmatchcase(rel, pattern)


def partition(
    findings: list[Finding],
    exemptions: tuple[Exemption, ...] = EXEMPTIONS,
) -> tuple[dict[Exemption, list[Finding]], list[Finding]]:
    """Split findings into ``{exemption: [findings]}`` and the unexempted rest."""
    exempted: dict[Exemption, list[Finding]] = defaultdict(list)
    unexempted: list[Finding] = []
    for fi in findings:
        for ex in exemptions:
            if fi.keyword_id in ex.keywords and path_matches(fi.path, ex.path_glob):
                exempted[ex].append(fi)
                break
        else:
            unexempted.append(fi)
    return dict(exempted), unexempted


# ---------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------
def report(
    n_files: int,
    exempted: dict[Exemption, list[Finding]],
    unexempted: list[Finding],
    exemptions: tuple[Exemption, ...] = EXEMPTIONS,
) -> None:
    """Print the scan result: exempted hits are listed, never swallowed."""
    print(f"[spec-scope-check] scanned {n_files} Python file(s) against SPEC.md §0.3")
    print("")

    if exempted:
        total = sum(len(v) for v in exempted.values())
        print(f"[spec-scope-check] {total} hit(s) EXEMPTED by the declared-scope register:")
        for ex in exemptions:
            hits = exempted.get(ex)
            if not hits:
                continue
            kws = ", ".join(sorted({h.keyword_id for h in hits}))
            per_file: dict[str, int] = defaultdict(int)
            for h in hits:
                per_file[h.path] += 1
            print(f"  {ex.path_glob}  [{kws}]  {len(hits)} hit(s) in {len(per_file)} file(s)")
            print(f"    reason: {ex.reason}")
            for cite in ex.basis:
                print(f"    basis:  {cite}")
            for path in sorted(per_file):
                print(f"      {path}  ({per_file[path]})")
        print("")

    stale = [ex for ex in exemptions if ex not in exempted]
    if stale:
        print("[spec-scope-check] exemption rules that matched nothing (review for removal):")
        for ex in stale:
            print(f"  {ex.path_glob}  [{', '.join(ex.keywords)}]")
        print("")

    if unexempted:
        print(f"[spec-scope-check] {len(unexempted)} UNEXEMPTED §0.3 non-goal hit(s):")
        for fi in unexempted:
            print(f"  {fi.path}:{fi.lineno}  [{fi.category}/{fi.keyword_id}]")
            print(f"    {fi.line[:120]}")
        print("")
        print("Resolve one of these ways:")
        print("  - §13 research roadmap feature: keep it off the 1.0 line, or register")
        print("    a narrow exemption in EXEMPTIONS with a citable basis")
        print("  - belongs in 1.0: file a SPEC change proposal")
        print("    (docs/governance/SPEC_CHANGE_PROPOSAL.md) and amend SPEC.md §0.3")
        print("  - false positive: tighten the keyword pattern, don't widen the exemption")
    else:
        print("[spec-scope-check] OK: no unexempted §0.3 non-goal keywords detected")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spec_scope_check",
        description="SPEC §0.3 scope discipline check (ADR-0010, ADR-0017).",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="files or directories to scan (default: src/openlimno)",
    )
    parser.add_argument(
        "--advisory",
        action="store_true",
        help="report findings but always exit 0 (local/pre-flight use; CI uses the blocking default)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="root that scanned paths are reported relative to (default: repo root)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args((argv or sys.argv)[1:])
    root = (args.root or REPO_ROOT).resolve()
    paths = args.paths or [REPO_ROOT / "src/openlimno"]

    try:
        validate_exemptions(EXEMPTIONS)
    except ExemptionError as exc:
        print(f"[spec-scope-check] malformed exemption register: {exc}", file=sys.stderr)
        return 2

    files = iter_python_files(paths)
    findings = scan(paths, root=root)
    exempted, unexempted = partition(findings, EXEMPTIONS)
    report(len(files), exempted, unexempted, EXEMPTIONS)

    if unexempted and not args.advisory:
        return 1
    if unexempted:
        print("")
        print("[spec-scope-check] --advisory: exiting 0 despite unexempted hits")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
