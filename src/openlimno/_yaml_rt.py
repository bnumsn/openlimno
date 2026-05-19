"""Comment-preserving YAML round-trip helpers (v3.3.0 R13-3 closure).

OpenLimno's case YAML is hand-edited by researchers — it carries
notes, justifications for ``acknowledge_independence``, citation
links, regulatory-context comments. The standard library's
``yaml.safe_load`` + ``yaml.safe_dump`` round-trip strips all
that on rewrite, which made every YAML-patcher (PEST++ calibration
write-back, fetch ``_patch_case_yaml_v02``, future studyplan
patchers) a destructive operation.

This module exposes two helpers that wrap ``ruamel.yaml`` with the
right settings for OpenLimno's case YAML conventions:

* :func:`load_round_trip(path)` returns a ``CommentedMap``-like
  document that preserves comments, key order, blank lines, and
  quote styles.
* :func:`dump_round_trip(data, path)` writes such a document back
  with everything preserved. Routes through ``Case._atomic_write``
  so a process interrupt doesn't truncate the user's case.yaml.

Both functions auto-detect whether ``ruamel.yaml`` is available and
fall back to the lossy ``yaml.safe_load`` / ``yaml.safe_dump`` form
with a one-time stderr warning. This keeps the module importable on
minimal environments while making the comment-preservation a
hard contract for the deps-installed path.

v3.3.0 R13-3 ship: gemini's 13th-round review flagged the comment-
destroying behavior of ``apply_optimised_params_to_case_yaml`` as a
real concern for case.yaml (researcher-curated). The right fix was
deferred at v2.14.1 + v3.0.0 + v3.1.0 + v3.2.0 because it adds a
runtime dependency; v3.3.0 commits.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml  # PyYAML — used as the fallback writer

try:
    from ruamel.yaml import YAML
    _RUAMEL_AVAILABLE = True
except ImportError:  # pragma: no cover — ruamel is now a runtime dep
    _RUAMEL_AVAILABLE = False


# v3.6.0 R16-9 (claude): the "warned once" flag used to be a plain
# module global with no lock — two threads racing on first import
# could double-print the stderr warning. Real-world impact is small
# (cosmetic double-line) but a threading.Lock is one line and
# closes the race cleanly.
_WARNED_MISSING_RUAMEL = False
_WARNED_MISSING_RUAMEL_LOCK = threading.Lock()


def _ruamel() -> YAML:
    """Configured YAML() instance for case YAML conventions.

    * ``preserve_quotes=True`` — keeps the user's `'0.2'` vs `0.2`
      choice intact (the WEDM schema requires the quoted string).
    * default flow style off — case YAML is block-style throughout.
    * ``indent(mapping=2, sequence=4, offset=2)`` — matches the
      shipped examples' indentation.
    * ``width=120`` — researcher-comfortable line width; PyYAML's
      default of 80 reflows long URIs awkwardly.
    """
    y = YAML()
    y.preserve_quotes = True
    y.default_flow_style = False
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 120
    return y


def load_round_trip(path: str | Path) -> Any:
    """Load a YAML file preserving comments + key order + blanks.

    Falls back to ``yaml.safe_load`` (lossy) if ``ruamel.yaml`` isn't
    installed; emits a one-time warning. The fallback's only
    downside is that comments will be lost on the next ``dump_round_trip``
    call — the loaded data structure itself is correct either way.

    Returns the parsed document (a ``CommentedMap`` in the
    ruamel.yaml path, a plain dict in the fallback path; both
    quack the same for dict-like operations).
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if _RUAMEL_AVAILABLE:
        return _ruamel().load(text)
    _warn_missing_ruamel_once()
    return yaml.safe_load(text)


def dump_round_trip(
    data: Any,
    path: str | Path,
    *,
    case: Any = None,
) -> Path:
    """Write a YAML file preserving comments + key order + blanks.

    Atomic via ``Case._atomic_write`` so process interrupts can't
    truncate the user's case.yaml mid-write (the v2.14.1 R13-2
    contract; v3.3.0 keeps it).

    Falls back to ``yaml.safe_dump`` if ``ruamel.yaml`` isn't
    installed. The fallback strips comments.

    v3.6.0 R16-8 (claude): optional ``case`` kwarg routes the
    destination through ``Case._resolve_write_safe`` so the
    sandbox applies to round-trip YAML writes too. The 16th-
    round review flagged the unsandboxed helper as a "tempting
    backdoor for future writers" — v3.6.0 closes that gap WITHOUT
    breaking the current callers (which pass user case.yaml paths
    that are unambiguously the user's own files; they pass
    ``case=None`` and the sandbox is skipped, matching pre-v3.6.0
    behavior). New callers in v3.6+ should pass ``case=<Case
    instance>`` to opt into the sandbox.

    Args:
        data: Document to serialise.
        path: Destination path (str or Path).
        case: Optional ``Case`` instance. When provided, ``path``
            is routed through ``case._resolve_write_safe`` to
            enforce the v3.0 path-safety sandbox. ``None`` (default)
            skips the sandbox — back-compat with v3.3.0/v3.4.0.

    Returns:
        Resolved Path written to.

    Raises:
        ValueError: if ``case`` is provided and the path escapes
            the sandbox.
    """
    from openlimno.case import Case  # avoid circular at module top

    if case is not None:
        dst = case._resolve_write_safe(path)
    else:
        dst = Path(path).resolve()
    if _RUAMEL_AVAILABLE:
        y = _ruamel()
        import io
        buf = io.StringIO()
        y.dump(data, buf)
        rendered = buf.getvalue()
    else:
        _warn_missing_ruamel_once()
        rendered = yaml.safe_dump(
            data, sort_keys=False, default_flow_style=False,
        )
    Case._atomic_write(
        dst, lambda p: p.write_text(rendered, encoding="utf-8"),
    )
    return dst


def _warn_missing_ruamel_once() -> None:
    """v3.6.0 R16-9: thread-safe one-shot stderr warning.

    The lock protects against double-printing if two threads call
    a round-trip API concurrently on first use (e.g., a Studio
    QThread doing a case load while a fetch subprocess writes a
    patch). Without the lock both threads see ``_WARNED_MISSING_RUAMEL
    is False``, both write, and the user sees two identical lines.
    With the lock at most one wins.
    """
    global _WARNED_MISSING_RUAMEL
    with _WARNED_MISSING_RUAMEL_LOCK:
        if _WARNED_MISSING_RUAMEL:
            return
        _WARNED_MISSING_RUAMEL = True
    import sys
    sys.stderr.write(
        "openlimno._yaml_rt: ruamel.yaml not installed; YAML round-trip "
        "fell back to PyYAML safe_dump (loses comments and key order). "
        "Install ruamel.yaml>=0.18 to preserve case.yaml structure.\n"
    )
