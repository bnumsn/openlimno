"""Unit tests for ``Controller._read_xs_rows_cached`` + the
``_read_wua_parquet`` helper it wraps.

The cache wrapper detects mid-read rewrites by comparing pre/post stat,
retries with linear backoff on transient I/O, and short-circuits on
``MissingParquetBackend`` / ``ParquetSchemaError`` (permanent). The
helper normalises pyarrow's asymmetric exception MRO into the canonical
transient/permanent classes the wrapper expects.

These tests exercise the caching logic in pure Python without instantiating
a Host. ``Controller.__init__`` only needs an attribute access (host),
which we satisfy with a sentinel.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from openlimno.gui_core.controller import Controller


@pytest.fixture
def subject():
    """A Controller instance whose ``_xs_parquet`` we set per-test.
    We pass None for the host since these tests don't touch any host
    methods.
    """
    ctl = Controller(host=None)  # type: ignore[arg-type]
    return ctl


@pytest.fixture
def parquet_file(tmp_path):
    p = tmp_path / "xs.parquet"
    p.write_text("v1")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_first_read_caches_rows(subject, parquet_file):
    calls = []

    def fake_read(p):
        calls.append(p)
        return [{"row": 1}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read):
        rows = subject._read_xs_rows_cached(str(parquet_file))
    assert rows == [{"row": 1}]
    assert len(calls) == 1


def test_cache_hit_skips_re_read(subject, parquet_file):
    calls = []

    def fake_read(p):
        calls.append(p)
        return [{"row": 1}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read):
        subject._read_xs_rows_cached(str(parquet_file))
        subject._read_xs_rows_cached(str(parquet_file))
    assert len(calls) == 1, "cache should have served the second call"


def test_mtime_change_invalidates(subject, parquet_file):
    calls = []

    def fake_read(p):
        calls.append(p)
        return [{"v": len(calls)}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read):
        rows1 = subject._read_xs_rows_cached(str(parquet_file))
        future = time.time() + 100
        os.utime(parquet_file, (future, future))
        rows2 = subject._read_xs_rows_cached(str(parquet_file))
    assert rows1 != rows2, "mtime change should invalidate cache"
    assert len(calls) == 2


def test_size_change_invalidates_at_same_mtime(subject, parquet_file):
    """The FAT/SMB scenario the cache claims to protect against: mtime
    granularity is 1-2 s, so a same-second rewrite ties on mtime. Size
    differing must still trigger an invalidation."""
    calls = []

    def fake_read(p):
        calls.append(p)
        return [{"v": Path(p).read_text()}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read):
        subject._read_xs_rows_cached(str(parquet_file))
        original_mtime = os.path.getmtime(parquet_file)
        parquet_file.write_text("v2_extended_payload")
        os.utime(parquet_file, (original_mtime, original_mtime))
        subject._read_xs_rows_cached(str(parquet_file))
    assert len(calls) == 2, "size change must invalidate even at same mtime"


def test_mid_read_rewrite_does_not_cache_torn_rows(subject, parquet_file):
    """The bug all three reviewers caught. Simulate a rewrite DURING the
    read: pre-stat (T1, S1), read produces torn rows, post-stat (T2, S2).
    The cache MUST NOT store (T2, S2, torn_rows) — that would cement
    corrupt data forever."""
    state = {"call_count": 0}

    def fake_read_with_concurrent_rewrite(p):
        state["call_count"] += 1
        if state["call_count"] == 1:
            # First call: simulate writer touching file mid-read
            future = time.time() + 50
            Path(p).write_text("post-read-content-different-size-XX")
            os.utime(p, (future, future))
            return [{"row": "TORN"}]
        # Subsequent retry: file quiescent
        return [{"row": "CLEAN"}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read_with_concurrent_rewrite):
        rows = subject._read_xs_rows_cached(str(parquet_file))
    assert rows == [{"row": "CLEAN"}], (
        "After mid-read rewrite, the retry must serve clean rows, "
        "not the original torn read"
    )
    assert state["call_count"] >= 2, "expected at least one retry"


def test_stat_failure_serves_stale_cache(subject, parquet_file):
    """If the file is moved/unmounted between clicks, the user shouldn't
    see a crash — they should get the previously-cached rows. The next
    legitimate read can surface the real error."""
    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 return_value=[{"row": "ok"}]):
        subject._read_xs_rows_cached(str(parquet_file))
    parquet_file.unlink()
    with patch("openlimno.gui_core.controller._read_wua_parquet") as mock:
        rows = subject._read_xs_rows_cached(str(parquet_file))
    assert rows == [{"row": "ok"}]
    mock.assert_not_called()


def test_vanished_during_read_retries_then_raises(subject, parquet_file):
    """A vanished file on attempt 0 must re-enter the retry loop —
    a transient ``mv -f`` may complete before retries exhaust. Only
    when ALL retries fail do we raise. Raising immediately on the
    first vanish would defeat the backoff design."""
    def fake_read_then_delete(p):
        Path(p).unlink()
        return [{"row": "TORN"}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read_then_delete), \
         patch("openlimno.gui_core.controller.time.sleep") as mock_sleep:
        # Either FileNotFoundError (post-stat None) or its parent OSError
        # (subsequent pre-stat None) is acceptable — both signal the same
        # condition.
        with pytest.raises(OSError):
            subject._read_xs_rows_cached(str(parquet_file), max_retries=3)
    # Backoff must have run for retries 1 and 2.
    assert mock_sleep.call_count == 2, (
        f"vanished-during-read must retry, got {mock_sleep.call_count} sleeps"
    )


def test_parquet_read_exception_triggers_retry(subject, parquet_file):
    """If ``_read_wua_parquet`` raises (e.g., pyarrow's ArrowInvalid
    on a torn footer, or OSError on a locked file), the retry loop
    must catch and retry instead of propagating immediately."""
    state = {"calls": 0}

    def flaky_read(p):
        state["calls"] += 1
        if state["calls"] < 3:
            raise OSError("torn read - file locked by writer")
        return [{"row": "OK_AT_ATTEMPT_3"}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=flaky_read), \
         patch("openlimno.gui_core.controller.time.sleep"):
        rows = subject._read_xs_rows_cached(str(parquet_file), max_retries=3)
    assert rows == [{"row": "OK_AT_ATTEMPT_3"}]
    assert state["calls"] == 3


def test_empty_rows_treated_as_valid_cache(subject, parquet_file):
    """An empty parquet (legitimate WUA with no observations yet)
    must produce a cacheable empty list. A truthy-check on
    ``cache.get("rows")`` would treat ``[]`` as no-cache and force
    re-read on every click."""
    calls = []

    def fake_read(p):
        calls.append(p)
        return []

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read):
        rows1 = subject._read_xs_rows_cached(str(parquet_file))
        rows2 = subject._read_xs_rows_cached(str(parquet_file))
    assert rows1 == [] and rows2 == []
    assert len(calls) == 1, "empty rows must still be cached"


def test_vanished_during_read_serves_prior_cache(subject, parquet_file):
    """If a prior good cache exists and the file vanishes mid-read
    on a subsequent call, serve the prior cached rows (which were
    read from a quiescent file) rather than the torn read."""
    state = {"reads": 0, "should_delete": False}

    def fake_read(p):
        state["reads"] += 1
        if state["should_delete"]:
            Path(p).unlink()
            return [{"row": "TORN"}]
        return [{"row": "GOOD"}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read):
        # First call: clean read, populates cache.
        rows1 = subject._read_xs_rows_cached(str(parquet_file))
        assert rows1 == [{"row": "GOOD"}]

        # Force cache miss by making the cache see a different stat.
        future = time.time() + 100
        os.utime(parquet_file, (future, future))
        # Second call: rewrite triggers cache miss; mid-read file vanishes.
        state["should_delete"] = True
        rows2 = subject._read_xs_rows_cached(str(parquet_file))
    # Must serve the prior good cache, NOT the torn read.
    assert rows2 == [{"row": "GOOD"}], (
        "must prefer prior cache over torn rows when file vanishes mid-read"
    )


def test_backoff_called_with_correct_durations(subject, parquet_file):
    """The ``time.sleep`` calls in the retry loop must use linear
    backoff (0.05 s × attempt). A regression that drops the sleep or
    uses a fixed duration must fail this test."""
    state = {"call_count": 0}

    def always_rewrite(p):
        state["call_count"] += 1
        future = time.time() + 100 + state["call_count"]
        Path(p).write_text("x" * (10 + state["call_count"]))
        os.utime(p, (future, future))
        return [{"row": f"torn_{state['call_count']}"}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=always_rewrite), \
         patch("openlimno.gui_core.controller.time.sleep") as mock_sleep:
        with pytest.raises((RuntimeError, OSError)):
            subject._read_xs_rows_cached(str(parquet_file), max_retries=3)
    # First attempt: no sleep. Subsequent attempts: 0.05*1, 0.05*2.
    assert mock_sleep.call_count == 2, (
        f"expected 2 backoff sleeps for max_retries=3, got {mock_sleep.call_count}"
    )
    durations = [c.args[0] for c in mock_sleep.call_args_list]
    assert durations == [0.05, 0.10], (
        f"expected linear backoff [0.05, 0.10], got {durations}"
    )


def test_retry_exhaustion_raises(subject, parquet_file):
    """A writer rewriting on every read attempt must eventually
    trigger a clear error rather than silently returning the last
    torn read."""
    state = {"call_count": 0}

    def always_rewrite(p):
        state["call_count"] += 1
        # Bump mtime forward by a different amount each time so pre/post
        # stats always disagree
        future = time.time() + 100 + state["call_count"]
        Path(p).write_text("x" * (10 + state["call_count"]))
        os.utime(p, (future, future))
        return [{"row": f"torn_{state['call_count']}"}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=always_rewrite):
        with pytest.raises((RuntimeError, OSError)):
            subject._read_xs_rows_cached(str(parquet_file), max_retries=3)
    assert state["call_count"] >= 2, "should have retried at least once"


def test_typeerror_propagates_does_not_retry(subject, parquet_file):
    """The cache wrapper's ``except`` must be narrow enough that
    programmer bugs (TypeError, AttributeError) propagate immediately
    rather than being misdiagnosed as transient I/O issues that burn
    the retry budget."""
    state = {"calls": 0}

    def fake_read_typeerror(p):
        state["calls"] += 1
        raise TypeError("simulated programmer bug in parquet reader")

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read_typeerror), \
         patch("openlimno.gui_core.controller.time.sleep") as mock_sleep:
        with pytest.raises(TypeError):
            subject._read_xs_rows_cached(str(parquet_file), max_retries=3)
    # Should NOT retry on TypeError.
    assert state["calls"] == 1, (
        f"TypeError should not trigger retry, but read was called {state['calls']}×"
    )
    assert mock_sleep.call_count == 0


def test_missing_backend_short_circuits_retry(subject, parquet_file):
    """The cache wrapper's ``except MissingParquetBackend: raise``
    clause must precede the broader ``except (..., RuntimeError)`` so
    a stripped install (no pyarrow + no GDAL) does not burn the retry
    budget on a permanent install problem.

    A tooling-driven reorder of the except clauses (ruff sort, etc.)
    would silently regress this. Pins the behaviour: zero retries,
    zero sleep, error propagates immediately.
    """
    from openlimno.gui_core.controller import MissingParquetBackend

    state = {"calls": 0}

    def fake_no_backend(p):
        state["calls"] += 1
        raise MissingParquetBackend("neither pyarrow nor GDAL")

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_no_backend), \
         patch("openlimno.gui_core.controller.time.sleep") as mock_sleep:
        with pytest.raises(MissingParquetBackend):
            subject._read_xs_rows_cached(str(parquet_file), max_retries=3)
    assert state["calls"] == 1, (
        f"MissingParquetBackend should short-circuit, but read was called "
        f"{state['calls']}× (retry budget burned on a permanent failure)"
    )
    assert mock_sleep.call_count == 0


def test_except_clause_order_real_arrow_invalid_routes_to_oserror():
    """The isinstance-check order in ``_normalize_parquet_exception``
    is load-bearing — ``_ARROW_PERMANENT`` contains the
    ``ArrowException`` parent (forward-compat fallback), which is
    also a superclass of ``ArrowInvalid`` listed in
    ``_ARROW_TRANSIENT``. If the helper swaps the TRANSIENT/PERMANENT
    isinstance checks, every transient ``ArrowInvalid`` would silently
    get re-classified as permanent — killing retry semantics for torn
    reads.

    Pins the order: a real ``ArrowInvalid`` raised by ``pq.read_table``
    MUST surface as ``OSError`` (transient path), NOT
    ``ParquetSchemaError`` (permanent path). A swap regression fails
    immediately.
    """
    pytest.importorskip("pyarrow")
    pa_lib = pytest.importorskip("pyarrow.lib")
    if not hasattr(pa_lib, "ArrowInvalid"):
        pytest.skip("pyarrow.lib lacks ArrowInvalid on this build")

    from openlimno.gui_core import controller as ctl
    import pyarrow.parquet as pq

    def fake_parquet_file_arrow_invalid(path, **kwargs):
        raise pa_lib.ArrowInvalid("simulated torn parquet footer")

    with patch.object(pq, "ParquetFile", side_effect=fake_parquet_file_arrow_invalid):
        with pytest.raises(OSError) as exc_info:
            ctl._read_wua_parquet("/nonexistent/path.parquet")
    # Crucial: must be OSError, NOT ParquetSchemaError (which would
    # mean except-clause order regressed and transient was caught by
    # the permanent ArrowException-parent fallback).
    assert not isinstance(exc_info.value, ctl.ParquetSchemaError), (
        "REGRESSION: ArrowInvalid (transient) was caught by the "
        "_ARROW_PERMANENT branch via its ArrowException parent — the "
        "isinstance-check order in _normalize_parquet_exception was "
        "probably swapped. Transient retry semantics are now broken "
        "for torn parquet reads."
    )


def test_real_arrow_keyerror_routes_to_parquet_schema_error():
    """Integration-level check that an actual ``ArrowKeyError`` raised
    by ``pq.read_table`` traverses the normalisation correctly.

    The existing ``test_parquet_schema_error_short_circuits_retry``
    mocks ``_read_wua_parquet`` itself, bypassing the helper's
    classification logic. This test mocks one level lower
    (``pq.read_table``) so the actual ``_ARROW_PERMANENT`` branch
    fires and re-raises as ``ParquetSchemaError``.
    """
    pytest.importorskip("pyarrow")
    pa_lib = pytest.importorskip("pyarrow.lib")
    if not hasattr(pa_lib, "ArrowKeyError"):
        pytest.skip("pyarrow.lib lacks ArrowKeyError on this build")

    from openlimno.gui_core import controller as ctl
    import pyarrow.parquet as pq

    def fake_parquet_file_arrow_keyerror(path, **kwargs):
        raise pa_lib.ArrowKeyError("simulated missing column 'station_m'")

    with patch.object(pq, "ParquetFile", side_effect=fake_parquet_file_arrow_keyerror):
        with pytest.raises(ctl.ParquetSchemaError) as exc_info:
            ctl._read_wua_parquet("/nonexistent/path.parquet")
    # Cause chain must preserve the original ArrowKeyError for
    # debugging.
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, pa_lib.ArrowKeyError)
    # Must NOT be re-raised as OSError (which would mean it got
    # mis-classified as transient and would burn retry budget).
    assert not isinstance(exc_info.value, OSError), (
        "REGRESSION: ArrowKeyError was caught by the _ARROW_TRANSIENT "
        "clause (classified as transient) — would cause cache retry "
        "to burn ~150ms total backoff (50+100ms across 3 attempts) on a permanent missing-column "
        "failure"
    )


def test_cache_loop_except_clause_order_pins_short_circuit(subject, parquet_file):
    """The cache wrapper's except clauses are load-bearing in source
    order.

    ``_read_xs_rows_cached`` has:
        except (MissingParquetBackend, ParquetSchemaError): raise
        except (OSError, EOFError, RuntimeError) as e: ... continue

    Both ``MissingParquetBackend`` and ``ParquetSchemaError`` inherit
    from ``RuntimeError``. If someone reorders the broader RuntimeError
    clause BEFORE the explicit short-circuit clause, both permanent
    classes get caught by the broader tuple and retried 3× with
    backoff — silently breaking the short-circuit contract.

    The helper's isinstance order is pinned by
    ``test_except_clause_order_real_arrow_invalid_routes_to_oserror``;
    this test pins the cache wrapper's order by counting actual calls
    + sleeps. A reorder regression shows calls=3 instead of 1.
    """
    from openlimno.gui_core.controller import (
        MissingParquetBackend, ParquetSchemaError,
    )

    for exc_cls in (MissingParquetBackend, ParquetSchemaError):
        state = {"calls": 0, "raised": None}

        def fake_raise(p, _e=exc_cls):
            state["calls"] += 1
            instance = _e(f"simulated {_e.__name__}")
            state["raised"] = instance
            raise instance

        with patch("openlimno.gui_core.controller._read_wua_parquet",
                     side_effect=fake_raise), \
             patch("openlimno.gui_core.controller.time.sleep") as mock_sleep:
            with pytest.raises(exc_cls) as exc_info:
                subject._read_xs_rows_cached(
                    str(parquet_file), max_retries=3
                )
        # Reset cache between iterations.
        subject._xs_rows_cache = {}

        assert state["calls"] == 1, (
            f"REGRESSION: {exc_cls.__name__} was caught by the broader "
            f"(OSError, EOFError, RuntimeError) clause and RETRIED — "
            f"the cache-loop except clauses must have been reordered. "
            f"Got {state['calls']} calls, expected 1 (short-circuit)."
        )
        assert mock_sleep.call_count == 0, (
            f"REGRESSION: {exc_cls.__name__} triggered backoff sleep — "
            f"the short-circuit clause is not running first."
        )
        # Pin EXCEPTION IDENTITY, not just type. A regression that
        # converted bare ``raise`` to ``raise OSError(str(e))`` in the
        # broader clause would still raise the right type-name (because
        # the test type IS the original) but lose the original
        # exception object — the bare ``raise`` short-circuit MUST
        # propagate the same instance.
        assert exc_info.value is state["raised"], (
            f"REGRESSION: {exc_cls.__name__} was caught and re-raised "
            f"as a NEW instance (not propagated via bare ``raise``). "
            f"This means the broader clause caught it and either "
            f"converted to OSError or re-wrapped — short-circuit is "
            f"broken even though the type happens to match."
        )


def test_parquet_schema_error_short_circuits_retry(subject, parquet_file):
    """``ParquetSchemaError`` is a dedicated ``RuntimeError`` subclass
    so the cache loop can short-circuit permanent schema failures
    (``ArrowKeyError`` = missing column,
    ``ArrowNotImplementedError`` = unsupported encoding, etc.)
    instead of burning ~150 ms total backoff (50+100 ms across 3
    attempts).

    Pins that the short-circuit clause runs: a ParquetSchemaError raised
    on the first attempt must propagate without retry or sleep.
    """
    from openlimno.gui_core.controller import ParquetSchemaError

    state = {"calls": 0}

    def fake_schema_error(p):
        state["calls"] += 1
        raise ParquetSchemaError("missing required column 'station_m'")

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_schema_error), \
         patch("openlimno.gui_core.controller.time.sleep") as mock_sleep:
        with pytest.raises(ParquetSchemaError):
            subject._read_xs_rows_cached(str(parquet_file), max_retries=3)
    assert state["calls"] == 1, (
        f"ParquetSchemaError must short-circuit, but read was called "
        f"{state['calls']}× (retry budget burned on a permanent "
        f"schema/capacity failure)"
    )
    assert mock_sleep.call_count == 0


def test_parquet_schema_error_subclasses_runtime_error():
    """Symmetric to test_missing_parquet_backend_subclasses_runtime_error.
    GUI direct-call sites' ``except (..., RuntimeError)`` must continue
    to surface a friendly QMessageBox when a corrupt parquet hits a
    permanent schema failure path.
    """
    from openlimno.gui_core.controller import ParquetSchemaError
    assert issubclass(ParquetSchemaError, RuntimeError), (
        "ParquetSchemaError must subclass RuntimeError so GUI handlers' "
        "existing except tuple catches it"
    )


def test_missing_parquet_backend_subclasses_runtime_error():
    """``MissingParquetBackend`` must subclass ``RuntimeError`` so
    the GUI direct-call sites' ``except (..., RuntimeError)``
    continues to surface a friendly QMessageBox without per-site
    changes when both backends are missing.
    """
    from openlimno.gui_core.controller import MissingParquetBackend
    assert issubclass(MissingParquetBackend, RuntimeError), (
        "MissingParquetBackend must subclass RuntimeError so GUI "
        "handlers' existing except tuple catches it; changing the "
        "parent class would silently break the friendly-error UX"
    )


def test_arrow_exception_normalised_to_oserror(tmp_path):
    """pyarrow's exception MRO is asymmetric — ``ArrowInvalid`` is
    a ``ValueError`` and ``ArrowIOError`` is an ``OSError``, but
    ``ArrowCapacityError``, ``ArrowKeyError``,
    ``ArrowNotImplementedError``, ``ArrowTypeError`` inherit only
    from ``ArrowException`` → ``Exception``. Without normalisation
    in ``_read_wua_parquet``, those four would escape the cache
    wrapper's ``except (OSError, EOFError, ValueError, RuntimeError)``
    tuple and crash the GUI thread.

    The fix: ``_normalize_parquet_exception`` catches the whole
    ``ArrowException`` family and re-raises as ``OSError``
    (transient) or ``ParquetSchemaError`` (permanent). Integration
    check that garbage bytes pyarrow's reader rejects surface as
    ``OSError``, NOT as an Arrow* class.
    """
    pytest.importorskip("pyarrow")
    from openlimno.gui_core.controller import _read_wua_parquet

    bad_parquet = tmp_path / "garbage.parquet"
    bad_parquet.write_bytes(b"not a parquet file at all")

    with pytest.raises(OSError) as exc_info:
        _read_wua_parquet(str(bad_parquet))
    # The invariant: the raised exception is NOT one of the pyarrow
    # Arrow* classes leaking through unwrapped. Asserting plain
    # ``isinstance(exc, OSError)`` would be tautological after
    # ``pytest.raises(OSError)``; the meaningful check is the
    # negative. ``pytest.skip`` (rather than if-branching) when
    # ``ArrowException`` is absent so vendor builds surface the
    # under-coverage explicitly instead of degrading to a vacuous
    # assertion.
    import pyarrow.lib as pa_lib
    arrow_exc = getattr(pa_lib, "ArrowException", None)
    if arrow_exc is None:
        pytest.skip(
            "pyarrow.lib lacks ArrowException — vendor build, can't "
            "verify the normalisation invariant on this platform"
        )
    assert not isinstance(exc_info.value, arrow_exc), (
        f"normalisation regressed: exception is still an "
        f"ArrowException ({type(exc_info.value).__name__}) — "
        f"the cache wrapper would still see Arrow-typed errors "
        f"and the asymmetric-MRO classes would escape."
    )
    # Also verify the normalisation message is informative (cause
    # chain preserves the original Arrow exception for debugging).
    assert exc_info.value.__cause__ is not None, (
        "OSError should chain from the underlying ArrowException via "
        "``raise ... from e`` so debugging the original cause stays "
        "possible"
    )


def test_arrow_catch_tuples_include_known_pyarrow_classes():
    """Positive test for the module-level ``_ARROW_TRANSIENT`` and
    ``_ARROW_PERMANENT`` tuples, so a vendor-pyarrow regression that
    drops e.g. ``ArrowInvalid`` from transient or ``ArrowKeyError``
    from permanent would actually fail CI instead of silently
    degrading retry classification.

    Transient (retry-eligible): ``ArrowInvalid``, ``ArrowIOError``.
    Permanent (short-circuit): ``ArrowKeyError``, ``ArrowTypeError``,
    ``ArrowNotImplementedError``, ``ArrowCapacityError``,
    ``ArrowMemoryError`` (50/100 ms backoff won't free RAM).
    """
    pytest.importorskip("pyarrow")
    pa_lib = pytest.importorskip("pyarrow.lib")

    from openlimno.gui_core.controller import (
        _ARROW_TRANSIENT, _ARROW_PERMANENT, _NoArrowExceptionAvailable,
    )

    assert _ARROW_TRANSIENT != (_NoArrowExceptionAvailable,), (
        "with pyarrow installed, _ARROW_TRANSIENT must NOT be the "
        "sentinel fallback — that would mean transient parquet read "
        "failures bypass OSError normalization and the cache retry"
    )
    assert _ARROW_PERMANENT != (_NoArrowExceptionAvailable,), (
        "with pyarrow installed, _ARROW_PERMANENT must NOT be the "
        "sentinel fallback — that would mean permanent schema errors "
        "still get retried, burning the retry budget"
    )

    # Transient family: ArrowInvalid / ArrowIOError. ArrowMemoryError
    # is intentionally PERMANENT — 50/100 ms backoff won't help the
    # OS reclaim RAM, so retrying allocation failures just burns the
    # budget.
    for name in ("ArrowInvalid", "ArrowIOError"):
        cls = getattr(pa_lib, name, None)
        if cls is not None:
            assert cls in _ARROW_TRANSIENT, (
                f"_ARROW_TRANSIENT must include pyarrow.lib.{name} so "
                f"the cache retry treats it as a transient I/O issue"
            )
            assert cls not in _ARROW_PERMANENT, (
                f"pyarrow.lib.{name} is transient — it must NOT be "
                f"in _ARROW_PERMANENT or it would short-circuit retry "
                f"on what's actually a torn read"
            )

    # Permanent family: 8 specific + ArrowException parent fallback.
    for name in ("ArrowKeyError", "ArrowTypeError",
                 "ArrowNotImplementedError", "ArrowCapacityError",
                 "ArrowMemoryError",
                 "ArrowSerializationError",
                 "ArrowCancelled", "ArrowIndexError",
                 "ArrowException"):  # parent as fallback
        cls = getattr(pa_lib, name, None)
        if cls is not None:
            assert cls in _ARROW_PERMANENT, (
                f"_ARROW_PERMANENT must include pyarrow.lib.{name} so "
                f"the cache retry SHORT-CIRCUITS instead of burning "
                f"~150ms total backoff (50+100ms across 3 attempts) on a permanent failure (or, for "
                f"ArrowException, escaping uncaught into the GUI)"
            )
            if name != "ArrowException":
                # ArrowException (parent) intentionally NOT in transient
                # — it's the catch-all for forward compat.
                assert cls not in _ARROW_TRANSIENT, (
                    f"pyarrow.lib.{name} is a permanent failure — it "
                    f"must NOT be in _ARROW_TRANSIENT or torn-read "
                    f"retry semantics would apply to a guaranteed-"
                    f"permanent error"
                )


def test_forward_compat_unknown_arrow_subclass_routes_to_permanent():
    """Forward-compat invariant: the ``ArrowException`` parent at
    the end of ``_ARROW_PERMANENT`` catches any future pyarrow
    exception subclass we haven't classified explicitly. Unknown
    Arrow* subclasses MUST route to ``ParquetSchemaError``
    (default-permanent — don't waste retry budget on unknowns).

    Verify by raising a synthetic ``ArrowException`` subclass that
    couldn't possibly be in our explicit list, and asserting it gets
    permanent classification rather than escaping uncaught.
    """
    pytest.importorskip("pyarrow")
    pa_lib = pytest.importorskip("pyarrow.lib")
    arrow_exception = getattr(pa_lib, "ArrowException", None)
    if arrow_exception is None:
        pytest.skip("pyarrow.lib lacks ArrowException — vendor build")

    class _FakeArrowSubclass(arrow_exception):  # type: ignore[valid-type, misc]
        """Synthetic Arrow* subclass to test forward-compat fallback."""

    from openlimno.gui_core import controller as ctl
    import pyarrow.parquet as pq

    def fake_parquet_file_unknown(path, **kwargs):
        raise _FakeArrowSubclass("simulated future pyarrow error")

    with patch.object(pq, "ParquetFile", side_effect=fake_parquet_file_unknown):
        with pytest.raises(ctl.ParquetSchemaError) as exc_info:
            ctl._read_wua_parquet("/nonexistent/path.parquet")
    assert isinstance(exc_info.value.__cause__, _FakeArrowSubclass), (
        "forward-compat fallback regressed: synthetic ArrowException "
        "subclass was not caught by the parent class in _ARROW_PERMANENT"
    )


class _FakeBatch:
    """Mock pyarrow RecordBatch whose ``to_pylist`` behavior we
    control. ``_read_wua_parquet`` calls ``batch.to_pylist()`` once
    per batch; ``raise_exc`` lets us inject classification-test
    exceptions at that exact site.
    """
    def __init__(self, rows, raise_exc=None):
        self._rows = rows
        self._raise_exc = raise_exc

    def to_pylist(self):
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._rows


class _FakeParquetFile:
    """Mock pyarrow.parquet.ParquetFile that yields preset batches
    from ``iter_batches()``. ``_read_wua_parquet`` only depends on
    ``iter_batches()`` so we don't need to fake the full surface.
    """
    def __init__(self, batches):
        self._batches = batches

    def iter_batches(self, **kwargs):
        yield from self._batches


class _FakeOGRFeature:
    def __init__(self, values):
        self._values = values

    def GetField(self, name):
        return self._values[name]


class _FakeOGRFieldDefn:
    def __init__(self, name):
        self._name = name

    def GetName(self):
        return self._name


class _FakeOGRLayerDefn:
    def __init__(self, field_names):
        self._fields = [_FakeOGRFieldDefn(n) for n in field_names]

    def GetFieldCount(self):
        return len(self._fields)

    def GetFieldDefn(self, i):
        return self._fields[i]


class _FakeOGRLayer:
    def __init__(self, field_names, features):
        self._defn = _FakeOGRLayerDefn(field_names)
        self._features = features

    def GetLayerDefn(self):
        return self._defn

    def __iter__(self):
        return iter(self._features)


class _FakeOGRDataset:
    def __init__(self, layer):
        self._layer = layer

    def GetLayer(self, idx):
        return self._layer


def test_read_phase_memoryerror_routes_to_parquet_schema_error():
    """Plain ``MemoryError`` from ``pq.ParquetFile`` itself (large-file
    footer OOM) is in none of the Arrow tuples and none of the cache
    wrapper's ``(OSError, EOFError, RuntimeError)`` tuple — without
    explicit handling it would crash the GUI thread.
    ``_normalize_parquet_exception`` re-raises it as a permanent
    ``ParquetSchemaError`` (50/100 ms backoff won't reclaim RAM).
    """
    pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")

    from openlimno.gui_core import controller as ctl

    def raise_read_memoryerror(path, **kwargs):
        raise MemoryError("simulated large-file read OOM")

    with patch.object(pq, "ParquetFile", side_effect=raise_read_memoryerror):
        with pytest.raises(ctl.ParquetSchemaError) as exc_info:
            ctl._read_wua_parquet("/nonexistent/path.parquet")
    assert isinstance(exc_info.value.__cause__, MemoryError)
    assert "read OOM" in str(exc_info.value)


def test_pyarrow_permanent_failure_falls_back_to_ogr_success():
    """OGR fallback path: when pyarrow rejects a file permanently
    (``ParquetSchemaError``) but OGR can read it (e.g., parquet
    variant / vendor encoding pyarrow doesn't support), the helper
    must return OGR's rows rather than surfacing pyarrow's error.

    Previously the OGR fallback only fired when pyarrow itself
    failed to IMPORT, leaving it orphaned on every other failure
    mode. Pins the fix.
    """
    pytest.importorskip("pyarrow")
    pa_lib = pytest.importorskip("pyarrow.lib")
    pq = pytest.importorskip("pyarrow.parquet")
    osgeo = pytest.importorskip("osgeo")
    if not hasattr(pa_lib, "ArrowKeyError"):
        pytest.skip("pyarrow.lib lacks ArrowKeyError on this build")

    from openlimno.gui_core import controller as ctl

    def fake_parquet_file_keyerror(path, **kwargs):
        raise pa_lib.ArrowKeyError("simulated unsupported column encoding")

    fake_ds = _FakeOGRDataset(
        _FakeOGRLayer(["station_m"], [_FakeOGRFeature({"station_m": 12.5})]),
    )

    with patch.object(pq, "ParquetFile", side_effect=fake_parquet_file_keyerror), \
         patch.object(osgeo.ogr, "Open", return_value=fake_ds):
        rows = ctl._read_wua_parquet("/nonexistent/path.parquet")
    assert rows == [{"station_m": 12.5}], (
        "OGR fallback must return its rows when pyarrow rejects the "
        "file permanently — that's the whole point of the secondary "
        "backend."
    )


def test_materialization_phase_plain_valueerror_falls_through_to_retry():
    """Symmetric to ``test_read_phase_plain_valueerror_falls_through_to_retry``.
    Plain ``ValueError`` from ``batch.to_pylist()`` (Cython-backed
    chunked arrays on bad UTF-8 / decimal overflow / torn dict pages)
    must propagate to the cache wrapper for transient retry, NOT be
    reclassified as permanent ``ParquetSchemaError``.

    The READ phase opens the file; the MATERIALIZE phase iterates
    batches. Plain ValueError from a batch must fall through.
    """
    pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")

    from openlimno.gui_core import controller as ctl

    fake_pf = _FakeParquetFile([
        _FakeBatch(None, raise_exc=ValueError("simulated bad UTF-8 in chunked array")),
    ])
    with patch.object(pq, "ParquetFile", return_value=fake_pf):
        # Must propagate as plain ValueError, NOT ParquetSchemaError.
        with pytest.raises(ValueError) as exc_info:
            ctl._read_wua_parquet("/nonexistent/path.parquet")
    assert not isinstance(exc_info.value, ctl.ParquetSchemaError), (
        "REGRESSION: plain ValueError from batch.to_pylist() was wrongly "
        "reclassified as ParquetSchemaError (permanent), losing the "
        "cache wrapper's transient retry path."
    )


def test_convert_phase_arrow_transient_triggers_cache_retry(subject, parquet_file):
    """End-to-end check that a CONVERT-phase transient Arrow error
    actually triggers cache retry. ``test_convert_phase_arrow_transient_routes_to_oserror``
    verifies the helper-level OSError mapping but doesn't verify the
    cache wrapper actually retries on receipt. A regression breaking
    the OSError → cache OSError handoff (e.g., changing the message
    format) would slip past unit-level mocks.

    Pins the full path: pq.read_table returns a fake_table whose
    column raises ``ArrowInvalid`` during materialization →
    ``_read_wua_parquet`` re-raises as ``OSError`` → cache wrapper
    catches OSError → retries 3× with backoff.
    """
    pytest.importorskip("pyarrow")
    pa_lib = pytest.importorskip("pyarrow.lib")
    pq = pytest.importorskip("pyarrow.parquet")
    if not hasattr(pa_lib, "ArrowInvalid"):
        pytest.skip("pyarrow.lib lacks ArrowInvalid on this build")

    state = {"calls": 0}

    def fake_parquet_file_with_bad_batch(path, **kwargs):
        state["calls"] += 1
        return _FakeParquetFile([
            _FakeBatch(None, raise_exc=pa_lib.ArrowInvalid("mid-mat torn buffer")),
        ])

    with patch.object(pq, "ParquetFile", side_effect=fake_parquet_file_with_bad_batch), \
         patch("openlimno.gui_core.controller.time.sleep") as mock_sleep:
        with pytest.raises(Exception):
            subject._read_xs_rows_cached(str(parquet_file), max_retries=3)
    # MATERIALIZE-phase ArrowInvalid → OSError → cache retries 3×.
    assert state["calls"] == 3, (
        f"REGRESSION: MATERIALIZE-phase ArrowInvalid did not trigger "
        f"cache retry. Got {state['calls']} calls, expected 3."
    )
    assert mock_sleep.call_count == 2  # No sleep on first attempt


def test_convert_phase_arrow_transient_routes_to_oserror():
    """The CONVERT (materialize) phase normalises Arrow exceptions
    through ``_normalize_parquet_exception`` just like the READ phase.
    Without that, ArrowInvalid raised by ``c.to_pylist()`` would
    escape uncaught (it inherits from ValueError but the cache
    wrapper relies on ``OSError`` for retry-with-backoff and
    ``ParquetSchemaError`` for short-circuit).

    Mocks a ``_FakeColumn`` whose ``to_pylist()`` raises a real
    ``ArrowInvalid`` (transient); verifies the helper re-raises as
    ``OSError``.
    """
    pytest.importorskip("pyarrow")
    pa_lib = pytest.importorskip("pyarrow.lib")
    pq = pytest.importorskip("pyarrow.parquet")
    if not hasattr(pa_lib, "ArrowInvalid"):
        pytest.skip("pyarrow.lib lacks ArrowInvalid on this build")

    from openlimno.gui_core import controller as ctl

    fake_pf = _FakeParquetFile([
        _FakeBatch(None, raise_exc=pa_lib.ArrowInvalid("simulated mid-materialization")),
    ])
    with patch.object(pq, "ParquetFile", return_value=fake_pf):
        with pytest.raises(OSError) as exc_info:
            ctl._read_wua_parquet("/nonexistent/path.parquet")
    # Must be OSError (transient), NOT ParquetSchemaError (permanent).
    assert not isinstance(exc_info.value, ctl.ParquetSchemaError), (
        "MATERIALIZE-phase ArrowInvalid must route to OSError (transient), "
        "not ParquetSchemaError (permanent)"
    )
    assert isinstance(exc_info.value.__cause__, pa_lib.ArrowInvalid)


def test_convert_phase_arrow_permanent_routes_to_parquet_schema_error():
    """Symmetric to the transient test —  CONVERT-phase ``ArrowKeyError``
    (in ``_ARROW_PERMANENT``) raised during materialization must
    route to ``ParquetSchemaError``, not bypass classification.
    """
    pytest.importorskip("pyarrow")
    pa_lib = pytest.importorskip("pyarrow.lib")
    pq = pytest.importorskip("pyarrow.parquet")
    if not hasattr(pa_lib, "ArrowKeyError"):
        pytest.skip("pyarrow.lib lacks ArrowKeyError on this build")

    from openlimno.gui_core import controller as ctl

    fake_pf = _FakeParquetFile([
        _FakeBatch(None, raise_exc=pa_lib.ArrowKeyError("simulated bad column ref")),
    ])
    with patch.object(pq, "ParquetFile", return_value=fake_pf):
        with pytest.raises(ctl.ParquetSchemaError) as exc_info:
            ctl._read_wua_parquet("/nonexistent/path.parquet")
    assert isinstance(exc_info.value.__cause__, pa_lib.ArrowKeyError)
    # The materialization-phase message should distinguish from the
    # read phase so users can tell where a corrupt parquet failed.
    assert "materialization" in str(exc_info.value).lower(), (
        "materialization-phase exceptions should produce a message "
        "mentioning materialization, not read — for debuggability"
    )


def test_success_path_after_transient_retries(subject, parquet_file):
    """Success-after-retry coverage: every other retry test exhausts
    attempts, so a regression that turned ``continue`` into ``break``
    after the first transient catch would silently pass them. This
    test fails 2 times then succeeds on attempt 3; asserts rows are
    returned correctly AND cached. A break-instead-of-continue
    regression would fail this immediately because attempt 2's
    failure would prematurely abort the loop.
    """
    state = {"calls": 0}

    def fake_read_transient_then_success(p):
        state["calls"] += 1
        if state["calls"] < 3:
            raise OSError(f"simulated transient on attempt {state['calls']}")
        return [{"row": 1, "ok": True}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read_transient_then_success), \
         patch("openlimno.gui_core.controller.time.sleep") as mock_sleep:
        rows = subject._read_xs_rows_cached(
            str(parquet_file), max_retries=3
        )
    assert state["calls"] == 3, (
        f"REGRESSION: cache loop did not retry through 3 attempts. "
        f"Got {state['calls']} calls — a break-instead-of-continue "
        f"in the broader exception clauses would silently abort the "
        f"loop on first failure."
    )
    assert mock_sleep.call_count == 2  # backoff sleeps before retries 2, 3
    assert rows == [{"row": 1, "ok": True}], (
        "rows from successful retry attempt must be returned"
    )
    # And the success result must be cached for subsequent calls.
    assert subject._xs_rows_cache.get("rows") == [{"row": 1, "ok": True}]


def test_read_phase_plain_valueerror_falls_through_to_retry():
    """Plain ``ValueError`` from ``pq.ParquetFile`` (older/vendor
    pyarrow paths reporting torn footer as plain ValueError,
    bad-parameter errors, etc.) must propagate raw to the cache
    wrapper's transient-retry clause — NOT be reclassified as
    permanent ``ParquetSchemaError``.

    The READ phase only catches Arrow exceptions (via
    ``_normalize_parquet_exception``) and ``MemoryError``; plain
    ValueError falls through to the cache wrapper.

    Pins the contract: plain ValueError from ``pq.ParquetFile`` must
    NOT become ``ParquetSchemaError``; it must propagate as plain
    ValueError so the cache wrapper sees it.
    """
    pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")

    from openlimno.gui_core import controller as ctl

    def raise_plain_valueerror(path, **kwargs):
        raise ValueError("simulated older-pyarrow torn-footer report")

    with patch.object(pq, "ParquetFile", side_effect=raise_plain_valueerror):
        # Must raise ValueError, NOT ParquetSchemaError.
        with pytest.raises(ValueError) as exc_info:
            ctl._read_wua_parquet("/nonexistent/path.parquet")
    # Critical: NOT a ParquetSchemaError — the cache wrapper's
    # transient retry path depends on plain ValueError propagating.
    assert not isinstance(exc_info.value, ctl.ParquetSchemaError), (
        "REGRESSION: plain ValueError from pq.ParquetFile was "
        "reclassified as ParquetSchemaError (permanent), losing "
        "the cache wrapper's transient retry path"
    )


def test_cache_wrapper_retries_on_plain_valueerror(subject, parquet_file):
    """Integration-level check that the cache wrapper actually
    retries on plain ValueError. The sibling
    ``test_read_phase_plain_valueerror_falls_through_to_retry`` only
    verifies that ``_read_wua_parquet`` PROPAGATES plain ValueError;
    a regression that removed the ``except ValueError`` clause in
    ``_read_xs_rows_cached`` would silently lose the transient retry
    contract.

    Pins the full path: pq.read_table raises ValueError →
    ``_read_wua_parquet`` propagates → ``_read_xs_rows_cached``'s
    ``except ValueError`` catches and retries with backoff. Verifies
    ``call_count == max_retries``.
    """
    pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")

    state = {"calls": 0}

    def always_raise_valueerror(path, **kwargs):
        state["calls"] += 1
        raise ValueError("simulated transient torn-footer")

    with patch.object(pq, "ParquetFile", side_effect=always_raise_valueerror), \
         patch("openlimno.gui_core.controller.time.sleep") as mock_sleep:
        # Will exhaust retries; final raise is the last ValueError.
        with pytest.raises(Exception):
            subject._read_xs_rows_cached(str(parquet_file), max_retries=3)
    # 3 read attempts (cache wrapper retried, not short-circuited).
    assert state["calls"] == 3, (
        f"REGRESSION: cache wrapper didn't retry on plain ValueError. "
        f"Got {state['calls']} calls, expected 3 (max_retries). "
        f"The except ValueError clause in _read_xs_rows_cached may "
        f"have been removed — transient retry contract broken."
    )
    # 2 sleeps for 3 attempts (no sleep on first).
    assert mock_sleep.call_count == 2


def test_plain_memoryerror_routes_to_parquet_schema_error():
    """Plain ``MemoryError`` (not ``ArrowMemoryError``) can fire
    during ``to_pylist()`` on a multi-GB column. Without explicit
    handling it would escape both Arrow tuples AND the cache
    wrapper's ``(OSError, EOFError, RuntimeError)`` tuple and crash
    the GUI.

    Returns a fake table whose column raises plain ``MemoryError``
    on ``to_pylist()``; asserts ``_read_wua_parquet`` re-raises as
    ``ParquetSchemaError`` (permanent — 50/100 ms backoff won't
    reclaim RAM).
    """
    pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")

    from openlimno.gui_core import controller as ctl

    fake_pf = _FakeParquetFile([
        _FakeBatch(None, raise_exc=MemoryError("alloc failed")),
    ])
    with patch.object(pq, "ParquetFile", return_value=fake_pf):
        with pytest.raises(ctl.ParquetSchemaError) as exc_info:
            ctl._read_wua_parquet("/nonexistent/path.parquet")
    assert isinstance(exc_info.value.__cause__, MemoryError)
    assert "MemoryError" in str(exc_info.value)


def test_no_arrow_exception_sentinel_never_matches():
    """Some vendor pyarrow builds don't expose ``ArrowException`` on
    ``pyarrow.lib``. ``_NoArrowExceptionAvailable`` is the sentinel
    that keeps ``isinstance(exc, _ARROW_*)`` checks syntactically
    valid in that case. The sentinel must never match any real
    exception ``pq.read_table`` would raise, so the absence of
    ``ArrowException`` silently downgrades to the cache wrapper's
    broader ``except`` tuple (OSError/ValueError/EOFError/RuntimeError)
    instead of swallowing a real failure.
    """
    from openlimno.gui_core.controller import _NoArrowExceptionAvailable

    # The sentinel inherits from Exception (it must, to be valid in
    # an ``except`` clause) but should not match any common error.
    for real_exc in (
        OSError("io"), ValueError("bad"), RuntimeError("runtime"),
        EOFError("eof"), TypeError("type"), KeyError("key"),
    ):
        assert not isinstance(real_exc, _NoArrowExceptionAvailable), (
            f"{type(real_exc).__name__} matched the sentinel — vendor "
            f"pyarrow without ArrowException would silently swallow it"
        )


def test_realpath_normalises_cache_key(subject, parquet_file, tmp_path):
    """Qt file dialogs sometimes change cwd; cache keys must not be
    sensitive to relative-vs-absolute spelling."""
    calls = []

    def fake_read(p):
        calls.append(p)
        return [{"row": "ok"}]

    with patch("openlimno.gui_core.controller._read_wua_parquet",
                 side_effect=fake_read):
        subject._read_xs_rows_cached(str(parquet_file))
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            subject._read_xs_rows_cached(parquet_file.name)
        finally:
            os.chdir(cwd)
    assert len(calls) == 1, (
        "realpath should make both spellings hit the same cache"
    )
