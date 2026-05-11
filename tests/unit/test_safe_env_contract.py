"""Contract tests for ``scripts/lib/safe_env.sh``.

Pins that ``safe_env`` strips every auth/routing env var the
subscription CLIs (claude / gemini / codex) honor, including future
vendor-specific variants we don't know about yet. The allowlist
inverts the env-u blocklist burden: only explicitly allowed vars
cross the boundary, so a new ``ANTHROPIC_FANCY_TOKEN`` shipping
tomorrow is excluded by default.

The test invokes ``safe_env env`` from a poisoned environment and
parses the resulting variable list. A regression that adds a forbidden
prefix to the allowlist would fail immediately.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SAFE_ENV_SH = REPO / "scripts" / "lib" / "safe_env.sh"


# Names a subscription CLI would honor that MUST be stripped. The
# list isn't exhaustive (the whole point of the allowlist is that we
# don't have to enumerate every future variant), but covers the
# headline cases each provider documents.
FORBIDDEN_VARS = [
    # Anthropic
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_PROJECT_ID",
    # OpenAI / Codex
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "OPENAI_ORG_ID",
    "OPENAI_ORGANIZATION",
    "OPENAI_PROJECT_ID",
    "OPENAI_API_TYPE",
    "CODEX_API_KEY",
    # Google / Gemini
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_PROJECT_ID",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_GEMINI_BASE_URL",
    "GOOGLE_APPLICATION_CREDENTIALS",
    # Hypothetical future variants — these are the test's real value:
    # they don't exist today, so a blocklist couldn't catch them, but
    # an allowlist excludes them by default.
    "OPENAI_FUTURE_TOKEN",
    "ANTHROPIC_NEW_AUTH",
    "GOOGLE_VENDOR_KEY",
]


def _run_safe_env_dump(extra_env: dict) -> dict:
    """Source ``safe_env.sh`` then invoke ``safe_env env`` from a
    poisoned environment; parse the output back into a dict.
    """
    poisoned_env = dict(os.environ)
    poisoned_env.update(extra_env)
    # Bash-source the snippet then run ``safe_env env``.
    cmd = ["bash", "-c", f". '{SAFE_ENV_SH}' && safe_env env"]
    result = subprocess.run(
        cmd, env=poisoned_env, capture_output=True, text=True, check=True,
    )
    out: dict = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k] = v
    return out


def test_safe_env_strips_all_forbidden_auth_vars():
    """Every known auth/routing env var must be absent inside safe_env,
    even when set to a non-empty value in the parent shell.
    """
    poison = {name: f"poisoned_value_for_{name}" for name in FORBIDDEN_VARS}
    inside = _run_safe_env_dump(poison)
    leaked = [name for name in FORBIDDEN_VARS if name in inside]
    assert not leaked, (
        f"REGRESSION: safe_env let auth vars cross the boundary: {leaked!r}. "
        f"The allowlist in scripts/lib/safe_env.sh must have grown a "
        f"forbidden prefix (or env -i was replaced with env -u)."
    )


def test_safe_env_keeps_essential_runtime_vars():
    """HOME and PATH must survive — without them the CLIs can't find
    their subscription tokens (HOME) or the binary itself (PATH).
    """
    inside = _run_safe_env_dump({})
    assert inside.get("HOME") == os.environ["HOME"]
    assert inside.get("PATH") == os.environ["PATH"], (
        "PATH must pass through unchanged or the CLI binary can't be found"
    )


def test_safe_env_drops_unknown_arbitrary_var():
    """A made-up variable not in the allowlist must not survive —
    this is the allowlist's whole reason for being.
    """
    inside = _run_safe_env_dump({"COMPLETELY_RANDOM_VAR_XYZ": "should_be_dropped"})
    assert "COMPLETELY_RANDOM_VAR_XYZ" not in inside, (
        "REGRESSION: an arbitrary unlisted variable crossed safe_env. "
        "The allowlist must be exhaustive — adding wildcard fallthrough "
        "defeats the whole design."
    )


@pytest.mark.parametrize("prefix_pattern", [
    "OPENAI_", "ANTHROPIC_", "GOOGLE_", "GEMINI_", "CODEX_",
])
def test_safe_env_blocks_provider_prefix_wildcard(prefix_pattern):
    """For each provider prefix, a hypothetical brand-new env var
    must be dropped. Defends against the blocklist-creep failure mode
    where a CLI release ships ``ANTHROPIC_SOME_NEW_THING`` and we
    forget to add it to env -u.
    """
    fake_name = f"{prefix_pattern}TEST_FUTURE_AUTH_VAR_XYZ"
    inside = _run_safe_env_dump({fake_name: "x"})
    assert fake_name not in inside, (
        f"REGRESSION: hypothetical future var {fake_name!r} crossed "
        f"safe_env — the allowlist must not contain {prefix_pattern}* "
        f"or the contract is broken."
    )


def test_triple_review_script_sources_safe_env():
    """``scripts/triple_review.sh`` must actually source the
    extracted ``safe_env`` definition rather than re-inlining its own
    copy — otherwise the contract this file pins doesn't cover the
    real invocation path.
    """
    script = (REPO / "scripts" / "triple_review.sh").read_text()
    assert ". \"$(dirname \"$0\")/lib/safe_env.sh\"" in script or \
           "source \"$(dirname \"$0\")/lib/safe_env.sh\"" in script, (
        "triple_review.sh must source scripts/lib/safe_env.sh so the "
        "contract tested in this file applies to actual reviewer "
        "invocations. If you inlined a copy, the contract diverges."
    )
    # And it must NOT still contain inline env -u patterns that would
    # mask a regression where safe_env got loosened.
    assert "env -u OPENAI_" not in script, (
        "Legacy env -u OPENAI_* blocklist still present in "
        "triple_review.sh — should be using safe_env"
    )
    assert "env -u ANTHROPIC_" not in script, (
        "Legacy env -u ANTHROPIC_* blocklist still present"
    )
    assert "env -u GOOGLE_" not in script, (
        "Legacy env -u GOOGLE_* blocklist still present"
    )
