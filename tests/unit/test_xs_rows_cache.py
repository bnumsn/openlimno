"""Unit tests for ``Controller._read_xs_rows_cached``.

The third review round (codex + gemini + claude) found that the previous
cache implementation cemented torn rows when the parquet was rewritten
during the read. Claude's verdict was unambiguous: 'the only behaviorally
new code path is untested'. This file fixes that.

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
    """Round-6 fix (Codex P0): a vanished file on attempt 0 should
    re-enter the retry loop (a transient ``mv -f`` may complete
    before retries exhaust). Only when ALL retries fail do we raise.
    Previously we raised immediately, defeating the backoff design."""
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
    """Round-6 fix (Gemini P0): if `_read_wua_parquet` raises (e.g.,
    pyarrow's ArrowInvalid on a torn footer, or OSError on a locked
    file), the retry loop must catch and retry instead of propagating
    immediately."""
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
    """Round-6 fix (Claude P1): an empty parquet (legitimate WUA
    with no observations yet) must produce a cacheable empty list.
    Previous ``cache.get("rows")`` truthy-check treated [] as
    no-cache, forcing re-read every click."""
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
    """Round-5 fix (Gemini P0): if a prior good cache exists and the
    file vanishes mid-read on a subsequent call, serve the prior
    cached rows (which were read from a quiescent file) rather than
    the torn read."""
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
    """Round-5 fix (Claude P1): the `time.sleep` calls in the retry
    loop must use linear backoff. A regression that drops the sleep
    or uses a fixed duration must fail."""
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
    """Round-4 fix: a writer rewriting on every read attempt must
    eventually trigger a clear error rather than silently returning
    the last torn read (Claude P1 + Gemini P1)."""
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
    """Round-7 fix (all 3 reviewers): narrow ``except`` so programmer
    bugs (TypeError, AttributeError) propagate immediately rather than
    being misdiagnosed as transient I/O issues that burn the retry
    budget."""
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
    """v0.1.0-final residual #3 (post-alpha.13 Claude): the cache
    wrapper's ``except MissingParquetBackend: raise`` clause must
    precede the broader ``except (..., RuntimeError)`` so a stripped
    install (no pyarrow + no GDAL) does not burn the retry budget on
    a permanent install problem.

    A tooling-driven reorder of the except clauses (ruff sort, etc.)
    would silently regress this. This test pins the behaviour: zero
    retries, zero sleep, error propagates immediately.
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
    """Post-v0.1.0 round-3 review (Claude #1): the except-clause order
    in ``_read_wua_parquet`` is load-bearing — ``_ARROW_PERMANENT``
    contains the ``ArrowException`` parent (forward-compat fallback),
    which is also a superclass of ``ArrowInvalid`` listed in
    ``_ARROW_TRANSIENT``. Python's except-matching tries clauses in
    source order; if a refactor swaps TRANSIENT and PERMANENT blocks,
    every transient ArrowInvalid would silently get re-classified as
    permanent — killing retry semantics for torn reads.

    This test pins the order: a real ``ArrowInvalid`` raised by
    ``pq.read_table`` MUST surface as ``OSError`` (transient path),
    NOT ``ParquetSchemaError`` (permanent path). A swap regression
    would fail this immediately.
    """
    pytest.importorskip("pyarrow")
    pa_lib = pytest.importorskip("pyarrow.lib")
    if not hasattr(pa_lib, "ArrowInvalid"):
        pytest.skip("pyarrow.lib lacks ArrowInvalid on this build")

    from openlimno.gui_core import controller as ctl
    import pyarrow.parquet as pq

    def fake_read_arrow_invalid(path, **kwargs):
        raise pa_lib.ArrowInvalid("simulated torn parquet footer")

    with patch.object(pq, "read_table", side_effect=fake_read_arrow_invalid):
        with pytest.raises(OSError) as exc_info:
            ctl._read_wua_parquet("/nonexistent/path.parquet")
    # Crucial: must be OSError, NOT ParquetSchemaError (which would
    # mean except-clause order regressed and transient was caught by
    # the permanent ArrowException-parent fallback).
    assert not isinstance(exc_info.value, ctl.ParquetSchemaError), (
        "REGRESSION: ArrowInvalid (transient) was caught by the "
        "_ARROW_PERMANENT clause via its ArrowException parent — the "
        "except blocks were probably reordered. Transient retry "
        "semantics are now broken for torn parquet reads."
    )


def test_real_arrow_keyerror_routes_to_parquet_schema_error():
    """Post-v0.1.0 round-3 review (Claude #4): the round-2 fix split
    ``_ARROW_PERMANENT`` to short-circuit retry on schema errors, but
    no integration test verified that an actual ``ArrowKeyError``
    raised by ``pq.read_table`` traverses the normalisation correctly.

    The existing ``test_parquet_schema_error_short_circuits_retry``
    mocks ``_read_wua_parquet`` itself, bypassing the helper's
    classification logic. This test mocks one level lower
    (``pq.read_table``) so the actual ``except _ARROW_PERMANENT``
    branch fires and re-raises as ``ParquetSchemaError``.
    """
    pytest.importorskip("pyarrow")
    pa_lib = pytest.importorskip("pyarrow.lib")
    if not hasattr(pa_lib, "ArrowKeyError"):
        pytest.skip("pyarrow.lib lacks ArrowKeyError on this build")

    from openlimno.gui_core import controller as ctl
    import pyarrow.parquet as pq

    def fake_read_arrow_keyerror(path, **kwargs):
        raise pa_lib.ArrowKeyError("simulated missing column 'station_m'")

    with patch.object(pq, "read_table", side_effect=fake_read_arrow_keyerror):
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
        "to burn 150ms × 3 attempts on a permanent missing-column "
        "failure"
    )


def test_parquet_schema_error_short_circuits_retry(subject, parquet_file):
    """Post-v0.1.0 round-1 review (Claude #1): the round-3 ArrowException
    normalisation re-raised the WHOLE Arrow* family as ``OSError``,
    which made the cache retry burn 150ms × 3 attempts on permanent
    schema failures (``ArrowKeyError`` = missing column,
    ``ArrowNotImplementedError`` = unsupported encoding, etc).

    Same fix pattern as ``MissingParquetBackend``: a dedicated
    ``ParquetSchemaError(RuntimeError)`` subclass that the cache loop
    short-circuits explicitly. This test pins the load-bearing
    behaviour.
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
    """v0.1.0-final residual #3: the subclass relationship is
    load-bearing. ``MissingParquetBackend`` must subclass
    ``RuntimeError`` so the GUI direct-call sites'
    ``except (..., RuntimeError)`` continues to surface a friendly
    QMessageBox without per-site changes when both backends are
    missing.
    """
    from openlimno.gui_core.controller import MissingParquetBackend
    assert issubclass(MissingParquetBackend, RuntimeError), (
        "MissingParquetBackend must subclass RuntimeError so GUI "
        "handlers' existing except tuple catches it; changing the "
        "parent class would silently break the friendly-error UX"
    )


def test_arrow_exception_normalised_to_oserror(tmp_path):
    """v0.1.0-final residual (post-alpha.13 round-3 codex MRO probe):
    pyarrow's exception MRO is asymmetric — ``ArrowInvalid`` is a
    ``ValueError`` and ``ArrowIOError`` is an ``OSError``, but
    ``ArrowCapacityError``, ``ArrowKeyError``,
    ``ArrowNotImplementedError``, ``ArrowTypeError`` inherit only
    from ``ArrowException`` → ``Exception``. Without normalization
    in ``_read_wua_parquet``, those four would escape the cache
    wrapper's ``except (OSError, EOFError, ValueError, RuntimeError)``
    tuple and crash the GUI thread.

    The fix: catch ``ArrowException`` inside ``_read_wua_parquet``
    and re-raise as ``OSError``. This integration test verifies the
    real (non-mocked) code path: garbage bytes that pyarrow's reader
    rejects must surface as ``OSError``, NOT as an Arrow* class.
    """
    pytest.importorskip("pyarrow")
    from openlimno.gui_core.controller import _read_wua_parquet

    bad_parquet = tmp_path / "garbage.parquet"
    bad_parquet.write_bytes(b"not a parquet file at all")

    with pytest.raises(OSError) as exc_info:
        _read_wua_parquet(str(bad_parquet))
    # v0.1.0 RC round-3 review (Claude #4): the previous assertion was
    # tautological — ``pytest.raises(OSError)`` already enforces
    # ``isinstance(exc, OSError)``. The actual invariant we want to
    # pin: the raised exception is NOT one of the pyarrow Arrow*
    # classes leaking through unwrapped. A regression where the
    # normalization is removed would let ``ArrowInvalid`` (a
    # ValueError + OSError-via-Arrow-MRO?) pass through and the old
    # test would silently green.
    # Post-v0.1.0 round-4 review (Claude #7): tighten this from
    # "if-branch on ArrowException availability" to "skip if absent."
    # The previous form silently degraded the assertion to a vacuous
    # "OSError raised somewhere" check on builds without ArrowException
    # — which was much weaker than the test name promised. Skipping
    # surfaces the under-coverage explicitly.
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
    """v0.1.0 RC round-3 review (Claude #8) + post-v0.1.0 round-1
    (Claude #1): positive test for the module-level
    ``_ARROW_TRANSIENT`` and ``_ARROW_PERMANENT`` tuples, so a
    vendor-pyarrow regression that drops e.g. ``ArrowInvalid`` from
    transient or ``ArrowKeyError`` from permanent would actually fail
    CI instead of silently degrading retry classification.

    Transient (retry-eligible): ``ArrowInvalid``, ``ArrowIOError``.
    Permanent (short-circuit): ``ArrowKeyError``, ``ArrowTypeError``,
    ``ArrowNotImplementedError``, ``ArrowCapacityError``.
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

    # Transient family: ArrowInvalid / ArrowIOError.
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

    # Permanent family: post-v0.1.0 round-2 (Codex P2) widened this
    # from 4 classes to 8 + the ArrowException parent as forward-
    # compat fallback. ALL of these must short-circuit retry; missing
    # any one means a regression where (e.g.) ArrowMemoryError on
    # allocation failure would burn 150 ms × 3 of GUI freeze.
    for name in ("ArrowKeyError", "ArrowTypeError",
                 "ArrowNotImplementedError", "ArrowCapacityError",
                 "ArrowMemoryError", "ArrowSerializationError",
                 "ArrowCancelled", "ArrowIndexError",
                 "ArrowException"):  # parent as fallback
        cls = getattr(pa_lib, name, None)
        if cls is not None:
            assert cls in _ARROW_PERMANENT, (
                f"_ARROW_PERMANENT must include pyarrow.lib.{name} so "
                f"the cache retry SHORT-CIRCUITS instead of burning "
                f"150ms × 3 attempts on a permanent failure (or, for "
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


def test_no_arrow_exception_sentinel_never_matches():
    """v0.1.0-final residual #4 (post-alpha.13 Claude): some vendor
    pyarrow builds don't expose ``ArrowException`` on ``pyarrow.lib``.
    The fix introduced a ``_NoArrowExceptionAvailable`` sentinel so
    ``except ArrowException`` is always a syntactically valid clause.
    The sentinel must never match any real exception that
    ``pq.read_table`` would raise, so the absence of ``ArrowException``
    silently downgrades to the cache wrapper's broader ``except``
    tuple (OSError/ValueError/EOFError/RuntimeError) instead of
    swallowing a real failure.
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
