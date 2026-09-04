"""Pins for the SPEC §0.3 scope-discipline checker (ADR-0010, ADR-0017).

The checker shipped for months reporting ``OK`` while ``src/openlimno/ibm/``
(11k LOC) and ``src/openlimno/fishtank/agent.py`` sat on ``main``. Two defects:

1. Multi-word keywords were wrapped in ``\\b``. ``_`` is a word character, so
   ``re.search(r"\\bagent_based\\b", "simulate_agent_based_model")`` is ``None``
   — the pattern was blind to the exact shape it existed to catch.
2. ``ibm`` / ``abm`` — the acronyms SPEC §0.3 actually uses — were not in the
   keyword table at all.

These tests pin both fixes, plus the exemption register that lets the check be
blocking without going red over the *declared* research route (ADR-0014/0016).

The tool is a standalone script under ``tools/``, not an installed package, so
it is loaded by path the same way the fishtank teaching-asset tests load theirs.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "m0_checklist" / "spec_scope_check.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("spec_scope_check_under_test", TOOL_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ssc = _load_tool()


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _run(tmp_path: Path, *extra: str) -> int:
    """Run the tool over ``tmp_path/src`` with ``tmp_path`` as the report root."""
    return ssc.main(["spec_scope_check", "--root", str(tmp_path), *extra, str(tmp_path / "src")])


def _pattern(keyword_id: str) -> re.Pattern[str]:
    return re.compile(ssc.KEYWORDS_BY_ID[keyword_id].pattern)


# ---------------------------------------------------------------------
# 1. The regression: multi-word keywords must match inside longer identifiers
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "def simulate_agent_based_model(scenario):",  # the actual fishtank symbol
        "    simulate_agent_based_model,",
        "result = AgentBasedModel().run()",  # CamelCase composition
        "# agent-based model, see docs",  # kebab-case prose
        "AGENT_BASED_STEPS = 100",  # SCREAMING_SNAKE
        "AGENT_BASED_MODEL = 1",  # SCREAMING_SNAKE, word continues after `_`
    ],
)
def test_agent_based_matches_embedded_identifiers(text: str) -> None:
    """ADR-0017 D1 regression pin.

    ``\\bagent_based\\b`` matched none of these; every one is the shape the
    keyword existed to detect.
    """
    assert re.search(r"\bagent_based\b", text) is None, (
        "premise check: the old \\b-anchored pattern is supposed to miss this"
    )
    assert _pattern("agent_based").search(text) is not None


# Every multi-word keyword, in all four spellings a real identifier can take.
# The `\b` defect was table-wide, not specific to ``agent_based``.
@pytest.mark.parametrize(
    ("keyword_id", "text"),
    [
        ("data_assim", "run_data_assimilation_step()"),
        ("data_assim", "runDataAssimilationStep()"),
        ("data_assim", "RUN_DATA_ASSIMILATION_STEP()"),
        ("ibm_fish", "class IbmFishState:"),
        ("ibm_fish", "ibm_fish_state = 1"),
        ("ibm_fish", "IBM_FISH_STATE = 1"),
        ("langevin_fish", "def step_langevin_fish_motion(...):"),
        ("langevin_fish", "class StepLangevinFishMotion:"),
        ("langevin_fish", "STEP_LANGEVIN_FISH_MOTION = 1"),
        ("temperature_advection", "solve_temperature_advection_1d(mesh)"),
        ("temperature_advection", "solveTemperatureAdvection1d(mesh)"),
        ("temperature_advection", "SOLVE_TEMPERATURE_ADVECTION_1D(mesh)"),
        ("self_built_swe", "from .self_built_swe_core import solve"),
        ("self_built_swe", "from .SelfBuiltSweCore import solve"),
        ("self_built_swe", "SELF_BUILT_SWE_CORE = 1"),
        ("meyer_peter", "qb = meyer_peter_mueller(tau)"),
        ("meyer_peter", "qb = MeyerPeterMueller(tau)"),
        ("meyer_peter", "QB = MEYER_PETER_MUELLER(tau)"),
        ("non_hydrostatic", "cfg.non_hydrostatic_pressure = True"),
        ("non_hydrostatic", "cfg.nonHydrostaticPressure = True"),
        ("non_hydrostatic", "NON_HYDROSTATIC_PRESSURE = True"),
    ],
)
def test_every_multiword_keyword_survives_identifier_embedding(keyword_id: str, text: str) -> None:
    assert _pattern(keyword_id).search(text) is not None


@pytest.mark.parametrize(
    ("keyword_id", "text"),
    [
        ("pce", "polynomial_chaos_pce"),
        ("pce", "POLYNOMIAL_CHAOS_PCE"),
        ("wasp", "run_wasp_model(x)"),
        ("wasp", "RUN_WASP_MODEL(x)"),
        ("ibm", "from openlimno.ibm import native"),
        ("ibm", "IBM_RUN_MANIFEST = 'ibm_run_manifest.json'"),
    ],
)
def test_underscore_reads_as_separator_for_short_tokens(keyword_id: str, text: str) -> None:
    """``\\bwasp\\b`` also missed ``my_wasp_model`` — `_` is a word character.

    The replacement guard is "the whole alphanumeric run must be this word",
    which treats `_` as the separator it actually is.
    """
    assert _pattern(keyword_id).search(text) is not None


def test_old_word_boundary_missed_underscore_adjacent_tokens() -> None:
    """Premise check for the test above: `\\b` could not do this."""
    assert re.search(r"\bpce\b", "polynomial_chaos_pce") is None
    assert re.search(r"\bwasp\b", "run_wasp_model(x)") is None


# ---------------------------------------------------------------------
# 2. ...without over-matching
# ---------------------------------------------------------------------
# Case variants are paired deliberately: the first revision of the phrase tail
# guard was `(?![a-z0-9])`, which is case-sensitive and therefore only blocked
# the lowercase spellings. `RUNTIME_MINUTES` and `HEAT_BALANCER_ID` slipped
# through because the guard cannot tell a SCREAMING_SNAKE continuation from a
# CamelCase one by looking at the next character alone. Never add a row here
# without its opposite-case twin.
@pytest.mark.parametrize(
    ("keyword_id", "text"),
    [
        # Short tokens must not fire inside a longer alphanumeric run.
        ("wasp", "wasps = count_insects()"),
        ("wasp", "WASPS = count_insects()"),
        ("helm", "helmholtz_free_energy(x)"),
        ("helm", "HELMHOLTZ_FREE_ENERGY(x)"),
        ("flask", "flasks_used = 3"),
        ("flask", "FLASKS_USED = 3"),
        ("ibm", "ibmi_legacy_adapter()"),
        ("ibm", "IBMI_LEGACY_ADAPTER()"),
        ("abm", "abmodulus = 1.0"),
        ("abm", "ABMODULUS = 1.0"),
        ("exner", "exnerlike = False"),
        ("exner", "EXNERLIKE = False"),
        # Phrase tail guard: the phrase must not eat a longer word, in any case
        # style. These are the rows the case-insensitive guard bug slipped past.
        ("runtime_min", "runtime_minutes = 12.0"),
        ("runtime_min", "RUNTIME_MINUTES = 12.0"),
        ("runtime_min", "Runtime_Minutes = 12.0"),
        ("runtime_min", "runtimeMinutes = 12.0"),
        ("runtime_min", "RuntimeMinutes = 12.0"),
        ("heat_balance", "heat_balancer_id = 3"),
        ("heat_balance", "HEAT_BALANCER_ID = 3"),
        ("heat_balance", "heatBalancerId = 3"),
        ("heat_balance", "HeatBalancerId = 3"),
        ("agent_based", "AGENT_BASEDX = 1"),
        ("agent_based", "agent_basedx = 1"),
    ],
)
def test_boundaries_do_not_over_match(keyword_id: str, text: str) -> None:
    assert _pattern(keyword_id).search(text) is None


# The coordinator's adversarial table, row by row. Each row is the contract for
# how the phrase tail guard must read one case style.
@pytest.mark.parametrize(
    ("keyword_id", "text", "should_match"),
    [
        ("agent_based", "simulate_agent_based_model", True),  # snake_case
        ("agent_based", "AgentBasedModel", True),  # CamelCase
        ("agent_based", "AGENT_BASED_MODEL", True),  # SCREAMING_SNAKE
        ("agent_based", "agent-based", True),  # kebab prose
        ("runtime_min", "runtime_minutes", False),
        ("runtime_min", "RUNTIME_MINUTES", False),
        ("heat_balance", "heat_balancer_id", False),
        ("heat_balance", "HEAT_BALANCER_ID", False),
        ("self_built_swe", "self_built_swe_v2", True),  # version suffix after `_`
        ("self_built_swe", "SELF_BUILT_SWE_V2", True),
        # A digit never continues an English word, so an attached dimension /
        # version / index suffix must not let the keyword escape either.
        ("temperature_advection", "solveTemperatureAdvection1d", True),
        ("temperature_advection", "solve_temperature_advection_1d", True),
        ("runtime_min", "runtime_min1", True),
        ("runtime_min", "RUNTIME_MIN1", True),
    ],
)
def test_phrase_tail_guard_is_case_style_aware(
    keyword_id: str, text: str, should_match: bool
) -> None:
    """A CamelCase continuation is a new word; a SCREAMING_SNAKE one is not.

    Both continue with an uppercase letter, so the guard has to branch on the
    case style of the text it just matched, not on the next character alone.
    """
    assert (_pattern(keyword_id).search(text) is not None) is should_match


def test_wasp_still_catches_the_versioned_product_name() -> None:
    """``WASP7``/``WASP8`` are the real EPA model names; ``wasps`` is an insect."""
    assert _pattern("wasp").search("port_of_WASP7_kinetics()") is not None
    assert _pattern("wasp").search("wasp8_kinetics") is not None
    assert _pattern("wasp").search("wasps") is None
    assert _pattern("wasp").search("WASPS") is None


def test_clean_module_produces_no_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A normal 1.0-scope module must not trip anything.

    Both case styles of every near-miss identifier appear here: the
    lowercase-only version of this fixture passed while the guard was still
    blind to ``RUNTIME_MINUTES``.
    """
    _write(
        tmp_path,
        "src/openlimno/habitat/wua.py",
        '"""Weighted usable area over habitat cells."""\n'
        "from __future__ import annotations\n\n"
        "RUNTIME_MINUTES_DEFAULT = 12.0\n"
        "HEAT_BALANCER_ID = 3\n\n\n"
        "def weighted_usable_area(depth, velocity, substrate):\n"
        "    runtime_minutes = 0.0\n"
        "    heat_balancer_id = HEAT_BALANCER_ID\n"
        "    wasps = 0  # unrelated\n"
        "    WASPS = 0\n"
        "    return depth * velocity * substrate + runtime_minutes + wasps\n",
    )
    assert _run(tmp_path) == 0
    assert "OK: no unexempted" in capsys.readouterr().out


# ---------------------------------------------------------------------
# 3. Exemption register behaviour
# ---------------------------------------------------------------------
def test_exempted_hits_are_listed_but_do_not_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Declared research-route code must be *visible* in the log, not swallowed."""
    _write(
        tmp_path,
        "src/openlimno/ibm/native.py",
        '"""Native individual-based model prototype."""\n'
        "def run_ibm_native(scenario):\n"
        "    return scenario\n",
    )
    assert _run(tmp_path) == 0
    out = capsys.readouterr().out
    assert "EXEMPTED" in out
    assert "src/openlimno/ibm/**" in out
    assert "src/openlimno/ibm/native.py" in out
    assert "0016-author-override-direct-merge.md" in out, "the basis must be cited in the log"
    assert "OK: no unexempted" in out


@pytest.mark.parametrize(
    "source",
    [
        "def simulate_agent_based_model(scenario):\n    return scenario\n",
        "AGENT_BASED_MODEL = 'sneaky'\n",
        "class AgentBasedModel:\n    pass\n",
    ],
)
def test_unexempted_hit_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], source: str
) -> None:
    """Same keyword, undeclared location -> non-zero exit, in every case style."""
    _write(tmp_path, "src/openlimno/habitat/sneaky.py", source)
    assert _run(tmp_path) == 1
    out = capsys.readouterr().out
    assert "UNEXEMPTED" in out
    assert "src/openlimno/habitat/sneaky.py:1" in out
    assert "[ibm/agent_based]" in out


def test_advisory_flag_reports_but_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "src/openlimno/habitat/sneaky.py", "enkf_update(state)\n")
    assert _run(tmp_path, "--advisory") == 0
    out = capsys.readouterr().out
    assert "UNEXEMPTED" in out
    assert "--advisory" in out


def test_exemption_is_keyword_scoped_not_a_whole_tree_blackhole(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``src/openlimno/ibm/**`` is exempt for IBM keywords only.

    A GPU solver hidden in the same tree still fails the run.
    """
    _write(tmp_path, "src/openlimno/ibm/native.py", "def run_ibm_native():\n    pass\n")
    _write(tmp_path, "src/openlimno/ibm/fast.py", "import cupy  # gpu solver\n")
    assert _run(tmp_path) == 1
    out = capsys.readouterr().out
    assert "src/openlimno/ibm/fast.py:1" in out
    assert "[gpu_solver/cupy]" in out


def test_stale_exemption_rules_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A rule that matches nothing is surfaced so the register can be pruned."""
    _write(tmp_path, "src/openlimno/habitat/wua.py", "X = 1\n")
    assert _run(tmp_path) == 0
    assert "matched nothing" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"keywords": ()}, "at least one keyword"),
        ({"keywords": ("*",)}, "wildcard keyword"),
        ({"keywords": ("no_such_keyword",)}, "unknown keyword"),
        ({"reason": "   "}, "must carry a reason"),
        ({"basis": ()}, "must cite a basis"),
        ({"basis": ("docs/decisions/9999-nope.md",)}, "basis document not found"),
    ],
)
def test_register_rejects_broad_or_uncitable_exemptions(kwargs: dict, message: str) -> None:
    """The register cannot degrade into a blanket carve-out or a stale citation."""
    fields = {
        "path_glob": "src/openlimno/ibm/**",
        "keywords": ("ibm",),
        "reason": "declared research route",
        "basis": ("docs/decisions/0016-author-override-direct-merge.md",),
    }
    fields.update(kwargs)
    with pytest.raises(ssc.ExemptionError, match=message):
        ssc.validate_exemptions((ssc.Exemption(**fields),))


def test_shipped_register_is_valid() -> None:
    """Every shipped exemption is narrow, keyword-scoped and citable."""
    ssc.validate_exemptions(ssc.EXEMPTIONS)
    all_ids = set(ssc.KEYWORDS_BY_ID)
    for ex in ssc.EXEMPTIONS:
        assert set(ex.keywords) < all_ids, (
            f"{ex.path_glob} exempts every known keyword — that is a blackhole, not a carve-out"
        )


def test_keyword_table_is_well_formed() -> None:
    ids = [k.id for k in ssc.NON_GOAL_KEYWORDS]
    assert len(ids) == len(set(ids)), "duplicate keyword id"
    for kw in ssc.NON_GOAL_KEYWORDS:
        re.compile(kw.pattern)  # raises on a malformed entry
        assert kw.rationale.strip(), f"{kw.id} must record why its boundary was chosen"


@pytest.mark.parametrize(
    ("rel", "glob", "expected"),
    [
        ("src/openlimno/ibm/native.py", "src/openlimno/ibm/**", True),
        ("src/openlimno/ibm/schemas/x.py", "src/openlimno/ibm/**", True),
        ("src/openlimno/ibm_helper.py", "src/openlimno/ibm/**", False),
        ("src/openlimno/cli.py", "src/openlimno/cli.py", True),
        ("src/openlimno/clix.py", "src/openlimno/cli.py", False),
    ],
)
def test_path_matches(rel: str, glob: str, expected: bool) -> None:
    assert ssc.path_matches(rel, glob) is expected


# ---------------------------------------------------------------------
# 4. Live scan of the real tree
# ---------------------------------------------------------------------
def test_real_src_tree_is_detected_and_fully_accounted_for() -> None:
    """The two known §0.3 modules must show up, and everything must be classified.

    Before ADR-0017 both scanned clean: ``ibm/`` because ``ibm``/``abm`` were
    missing from the table, ``fishtank/agent.py`` because of the ``\\b`` defect.
    """
    src = REPO_ROOT / "src" / "openlimno"
    if not src.is_dir():  # pragma: no cover - source checkout is expected
        pytest.skip("src/openlimno not present in this checkout")

    findings = ssc.scan([src])
    paths = {f.path for f in findings}
    assert any(p.startswith("src/openlimno/ibm/") for p in paths), (
        "src/openlimno/ibm/ must not scan clean — that was the original defect"
    )
    assert "src/openlimno/fishtank/agent.py" in paths, "simulate_agent_based_model must be detected"

    _exempted, unexempted = ssc.partition(findings, ssc.EXEMPTIONS)
    assert not unexempted, "unexempted §0.3 non-goal code on the 1.0 line:\n" + "\n".join(
        f"  {f.path}:{f.lineno} [{f.category}/{f.keyword_id}]" for f in unexempted[:20]
    )
