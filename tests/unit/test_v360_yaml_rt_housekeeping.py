"""v3.6.0 — R16-8 + R16-9 housekeeping for _yaml_rt.

R16-8 (claude): dump_round_trip optional ``case`` kwarg routes the
destination through Case._resolve_write_safe.
R16-9 (claude): threading.Lock around the warned-flag protects
against double-print races on first use.
"""

from __future__ import annotations

import textwrap
import threading
from pathlib import Path

import pytest
import yaml

from openlimno.case import Case


def _make_case(case_dir: Path) -> Case:
    case_dir.mkdir(parents=True, exist_ok=True)
    case_yaml = case_dir / "case.yaml"
    case_yaml.write_text(
        textwrap.dedent("""
            openlimno: '0.2'
            case:
              name: v360_yaml_rt_t
              crs: EPSG:4326
            mesh:
              uri: ./mesh.nc
            hydrodynamics:
              backend: builtin-1d
            habitat:
              species: [oncorhynchus_mykiss]
              stages: [spawning]
              metric: wua-q
              composite: min
            output:
              dir: ./out
              formats: [csv]
        """).lstrip(),
        encoding="utf-8",
    )
    return Case(
        config=yaml.safe_load(case_yaml.read_text()),
        case_yaml_path=case_yaml.resolve(),
    )


# ---------------------------------------------------------------------
# R16-8 — optional case kwarg
# ---------------------------------------------------------------------
def test_v360_r168_dump_round_trip_unsandboxed_default(
    tmp_path: Path,
) -> None:
    """v3.6.0 R16-8: when ``case`` is not provided, the helper
    behaves exactly like v3.3.0/v3.4.0 — writes to any path,
    sandbox not enforced. Back-compat for existing callers."""
    from openlimno._yaml_rt import dump_round_trip

    target = tmp_path / "outside_anywhere" / "config.yaml"
    target.parent.mkdir()
    out = dump_round_trip({"key": "value"}, target)
    assert out == target.resolve()
    assert target.read_text().startswith("key:")


def test_v360_r168_dump_round_trip_sandbox_when_case_provided(
    tmp_path: Path,
) -> None:
    """v3.6.0 R16-8: passing ``case`` engages the path-safety
    sandbox via Case._resolve_write_safe. A target outside the
    case dir (with no allowed_data_roots) gets rejected at the
    same gate the user's normal output.dir does."""
    from openlimno._yaml_rt import dump_round_trip

    case = _make_case(tmp_path / "case_dir")
    outside = tmp_path / "elsewhere" / "leak.yaml"
    outside.parent.mkdir()

    with pytest.raises(ValueError, match="path-safety"):
        dump_round_trip({"key": "value"}, outside, case=case)


def test_v360_r168_dump_round_trip_sandbox_allows_in_case_dir(
    tmp_path: Path,
) -> None:
    """v3.6.0 R16-8: when ``case`` is provided AND the path is
    inside the case dir (or any configured allowed_data_root),
    the write succeeds. The whole point of the kwarg is opt-in
    safety; legitimate same-dir writes must still work."""
    from openlimno._yaml_rt import dump_round_trip

    case = _make_case(tmp_path / "case_dir")
    in_case = case.case_dir / "subdir" / "patched.yaml"
    in_case.parent.mkdir(parents=True, exist_ok=True)
    out = dump_round_trip({"key": "value"}, in_case, case=case)
    assert out == in_case.resolve()


# ---------------------------------------------------------------------
# R16-9 — thread-safe warning singleton
# ---------------------------------------------------------------------
def test_v360_r169_warn_missing_ruamel_lock_exists() -> None:
    """v3.6.0 R16-9: the singleton flag MUST be guarded by a
    threading.Lock. Source-inspect to pin the contract.
    Behavioural test (race-condition stress) would be flaky in
    CI; the source pin is the durable contract."""
    import inspect

    from openlimno import _yaml_rt

    src = inspect.getsource(_yaml_rt)
    assert "threading.Lock()" in src, (
        "v3.6.0 R16-9 regression: threading.Lock guard for the "
        "warned-flag singleton is gone. Two concurrent first-use "
        "callers could double-print the stderr warning."
    )
    # And the lock object IS used (not just declared).
    assert "_WARNED_MISSING_RUAMEL_LOCK" in src
    # Acquired in the warn function:
    warn_src = inspect.getsource(_yaml_rt._warn_missing_ruamel_once)
    assert "_WARNED_MISSING_RUAMEL_LOCK" in warn_src, (
        "v3.6.0 R16-9 regression: the lock exists but the warn "
        "function doesn't acquire it. The lock is dead code."
    )


def test_v360_r169_warn_singleton_threadsafe_basic(
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v3.6.0 R16-9: spawn 10 threads that all call the warn
    function simultaneously. Verify at most one stderr line is
    emitted. Sanity-checks the lock actually works."""
    from openlimno import _yaml_rt

    # Reset module state so we observe a fresh first-use race.
    monkeypatch.setattr(_yaml_rt, "_WARNED_MISSING_RUAMEL", False)

    def call_warn() -> None:
        _yaml_rt._warn_missing_ruamel_once()

    threads = [threading.Thread(target=call_warn) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    out, err = capsys.readouterr()
    # 0 or 1 lines on stderr is acceptable (pytest capsys quirks
    # mean we can't guarantee capture for stderr writes from
    # threads). The real contract is "no doubles," which we
    # verify by asserting line count ≤ 1.
    safety_lines = [line for line in err.splitlines() if "openlimno._yaml_rt" in line]
    assert len(safety_lines) <= 1, (
        f"v3.6.0 R16-9 regression: warned-flag race produced "
        f"{len(safety_lines)} stderr lines under 10-thread "
        f"contention. Expected ≤ 1."
    )
