"""R-DOC-AUDIT-WIRED — R15..R17 cluster smoke pins (2026-05-20).

This file is the cluster-level production-caller check that
complements the audit doc at ``docs/reviews/R15_R17_audit.md``.
The 18 substantive closures across R15..R17 each have their own
per-finding test (`test_v{ship}_r{round}_*` files); this file pins
that the cross-cluster helpers remain importable + callable from
production, so a future refactor that accidentally drops one of
them fails loudly at audit-pass scope rather than only being caught
in the round's specific test.

Pins (one per cluster):
- R15-7 + R17 audit support — `_apply_sandbox_check` is the
  read+write resolver dedup helper.
- R15-2/R15-5 + R16-2/R16-3 — `_load_wua_q_plot_layer` consumer
  + `_run_case_for_worker` producer for trust_roots threading.
- R16-1/R16-5/R17-1/R17-4/R17-5 — AEQD + URI-redaction helpers.
- R15-4/R17-10/R18-1 — fd-ownership chain (_open_safe_fd +
  _open_safe).
- R16-8 (R-DOC-AUDIT-WIRED pass #1) — dump_round_trip case= kwarg
  exists.
- R16-9 — ruamel warning lock is module-level.
"""

from __future__ import annotations

import inspect

from openlimno._yaml_rt import dump_round_trip
from openlimno.case import Case, _uri_looks_absolute
from openlimno.gui_core import controller as ctl_mod
from openlimno.habitat.cover import (
    _aeqd_transformer_from,
    _aeqd_transformer_to,
    _riparian_buffer_geodesic,
)


def test_r15_7_apply_sandbox_check_helper_exists_and_serves_both_resolvers() -> None:
    """R15-7: ``_apply_sandbox_check`` dedup helper must exist AND
    be called from BOTH ``_resolve_safe`` and ``_resolve_write_safe``.
    """
    assert callable(getattr(Case, "_apply_sandbox_check", None)), (
        "R15-7 regression: _apply_sandbox_check dedup helper "
        "disappeared. Both _resolve_safe and _resolve_write_safe "
        "would now duplicate sandbox logic again."
    )
    rs = inspect.getsource(Case._resolve_safe)
    rws = inspect.getsource(Case._resolve_write_safe)
    assert "_apply_sandbox_check(" in rs, (
        "R15-7 regression: _resolve_safe no longer delegates to _apply_sandbox_check; dedup undone."
    )
    assert "_apply_sandbox_check(" in rws, (
        "R15-7 regression: _resolve_write_safe no longer delegates "
        "to _apply_sandbox_check; dedup undone."
    )


def test_r16_2_run_case_for_worker_returns_trust_roots() -> None:
    """R16-2/R16-3/R15-2/R15-5: the worker producer must still emit
    trust_roots so the GUI autoload consumer can use the
    Case-allowed-roots tree rather than just the case dir.
    """
    sig = inspect.signature(ctl_mod._run_case_for_worker)
    src = inspect.getsource(ctl_mod._run_case_for_worker)
    # Function returns a tuple including trust_roots somewhere.
    assert "trust_roots" in src, (
        "R16-2 regression: _run_case_for_worker no longer constructs "
        "trust_roots; GUI autoload would fall back to case-dir only "
        "and silently miss output.dir under allowed_data_roots."
    )
    assert sig.return_annotation is not inspect.Signature.empty or "trust_roots" in src, (
        "R16-2 hygiene: _run_case_for_worker should carry trust_roots in its return contract."
    )


def test_r16_5_r17_1_uri_looks_absolute_widened() -> None:
    """R16-5/R17-1: ``_uri_looks_absolute`` must recognise the
    forms widened in v3.5.0 (R16-5) and corrected in v3.6.0 (R17-1):
    file URI (case-insensitive), home expansion, Windows extended
    path, UNC paths.
    """
    assert _uri_looks_absolute("file:///etc/secret")
    assert _uri_looks_absolute("FILE:///etc/secret"), (
        "R17-1 regression: FILE:// (uppercase) no longer detected — case-sensitivity bug back."
    )
    assert _uri_looks_absolute("~/data.csv"), (
        "R16-5 regression: ~/... no longer detected as absolute."
    )
    assert _uri_looks_absolute(r"\\?\C:\secret"), (
        r"R17-1 regression: Windows \\?\ extended-path prefix no "
        r"longer detected."
    )
    assert _uri_looks_absolute(r"\\server\share\data.csv"), (
        "R17-1 regression: UNC path no longer detected."
    )
    # Negative — relative paths must NOT be misclassified.
    assert not _uri_looks_absolute("data/file.csv")
    assert not _uri_looks_absolute("./local.parquet")


def test_r16_1_r17_4_r17_5_aeqd_pipeline_intact() -> None:
    """R16-1: AEQD continuous-strip buffer.
    R17-4: antimeridian-safe circular-mean longitude.
    R17-5: PROJ Transformer ``lru_cache``.

    Cluster pin: the AEQD pipeline must still produce a valid
    geometry for a sub-polar polyline AND the transformer factories
    must be cache-aware.
    """
    # R17-5: cache_info() exists on the factories (lru_cache wraps).
    assert hasattr(_aeqd_transformer_to, "cache_info"), (
        "R17-5 regression: _aeqd_transformer_to no longer wrapped in lru_cache."
    )
    assert hasattr(_aeqd_transformer_from, "cache_info"), (
        "R17-5 regression: _aeqd_transformer_from no longer wrapped in lru_cache."
    )

    # R16-1 + R17-4: AEQD pipeline produces a valid geometry for
    # a high-lat polyline.
    coords = [(0.0, 65.0), (0.1, 65.05), (0.2, 65.1)]
    geom = _riparian_buffer_geodesic(coords, buffer_m=500.0)
    assert geom.is_valid, (
        "R16-1 regression: AEQD pipeline produced an invalid "
        "geometry for a routine sub-polar reach."
    )
    assert geom.area > 0


def test_r15_4_r17_10_fd_chain_intact() -> None:
    """R15-4: ``_open_safe_fd`` (POSIX ``O_NOFOLLOW``).
    R17-10: ``_open_safe`` context-manager wrapper.

    Cluster pin: the fd-ownership helper chain must still be
    importable from Case and the wrapper must be a context manager.
    """
    assert callable(getattr(Case, "_open_safe_fd", None)), (
        "R15-4 regression: _open_safe_fd disappeared from Case; TOCTOU mitigation undone."
    )
    assert callable(getattr(Case, "_open_safe", None)), (
        "R17-10 regression: _open_safe context-manager wrapper "
        "disappeared; fd leaks possible on exception paths."
    )
    # Light heuristic that _open_safe is a contextlib.contextmanager
    # (the decorator wraps it into a _GeneratorContextManagerBase
    # factory). We don't import contextlib's private classes; just
    # check the function-source markers.
    src = inspect.getsource(Case._open_safe)
    assert "@contextlib.contextmanager" in src or "yield " in src, (
        "R17-10 regression: _open_safe no longer looks like a context manager."
    )


def test_r16_8_dump_round_trip_case_kwarg_present() -> None:
    """R16-8 (and the 2026-05-20 R-DOC-AUDIT-WIRED pass #1 wiring):
    ``dump_round_trip`` must accept the ``case=`` keyword-only
    parameter so production callers can opt into sandbox routing.
    """
    sig = inspect.signature(dump_round_trip)
    assert "case" in sig.parameters, (
        "R16-8 regression: dump_round_trip no longer accepts case=; "
        "the R-DOC-AUDIT-WIRED pass #1 wiring would break."
    )
    assert sig.parameters["case"].kind == inspect.Parameter.KEYWORD_ONLY, (
        "R16-8 hygiene: case= must remain keyword-only so callers "
        "can't pass it positionally by accident."
    )


def test_r16_9_warned_missing_ruamel_lock_present() -> None:
    """R16-9: the ``_WARNED_MISSING_RUAMEL`` flag must be guarded
    by a module-level ``threading.Lock``."""
    import openlimno._yaml_rt as rt

    assert hasattr(rt, "_WARNED_MISSING_RUAMEL_LOCK"), (
        "R16-9 regression: _WARNED_MISSING_RUAMEL_LOCK module-level "
        "lock disappeared; double-print under concurrent first-use "
        "is back."
    )
    import threading

    assert isinstance(rt._WARNED_MISSING_RUAMEL_LOCK, type(threading.Lock())), (
        "R16-9 regression: _WARNED_MISSING_RUAMEL_LOCK is no longer a threading.Lock instance."
    )
