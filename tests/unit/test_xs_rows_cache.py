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
