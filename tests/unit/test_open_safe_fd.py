"""v3.5.0 R15-4 / R14-11 — TOCTOU mitigation via O_NOFOLLOW.

Pins the contract for ``Case._open_safe_fd``: a low-level helper
that opens a sandbox-resolved URI with the OS's ``O_NOFOLLOW``
flag on POSIX, refusing to traverse a symlink at the final
component. Closes the leaf-component TOCTOU window between
``_resolve_safe`` (which canonicalizes via ``Path.resolve()``)
and the consumer's open call.

Parent-chain TOCTOU is NOT closed here (would need ``openat``-
style descriptor chains; documented in SPEC_v3 as v4-scope work).
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from openlimno.case import Case


def _make_case(case_dir: Path) -> Case:
    """Minimal valid Case object for the open-safe tests."""
    case_dir.mkdir(parents=True, exist_ok=True)
    case_yaml = case_dir / "case.yaml"
    case_yaml.write_text(
        textwrap.dedent("""
            openlimno: '0.2'
            case:
              name: open_safe_t
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


def test_v350_open_safe_fd_reads_normal_file(tmp_path: Path) -> None:
    """v3.5.0: a normal in-sandbox file must open cleanly via the
    safe-fd path. The fd is a real OS handle; caller is responsible
    for closing."""
    case = _make_case(tmp_path / "case_dir")
    target = case.case_dir / "data.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("hello\n")

    fd = case._open_safe_fd(str(target.relative_to(case.case_dir)))
    try:
        assert fd >= 0
        data = os.read(fd, 16)
        assert data == b"hello\n"
    finally:
        os.close(fd)


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"),
    reason="O_NOFOLLOW only exists on POSIX",
)
def test_v350_open_safe_fd_refuses_post_resolve_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v3.5.0 R15-4 (POSIX): the ACTUAL TOCTOU mitigation
    O_NOFOLLOW defends against is a swap of the resolved path
    between ``_resolve_safe`` returning and ``os.open`` running.
    To simulate: monkey-patch ``_resolve_safe`` to return a path
    that exists as a symlink at open time. The os.open call must
    fail with OSError (ELOOP family).

    Note: ``_resolve_safe``'s normal flow chases symlinks via
    ``Path.resolve()`` so the canonical path returned is never a
    symlink. The TOCTOU window is between that canonicalization
    and the consumer's open — that's what this test exercises.
    """
    case = _make_case(tmp_path / "case_dir")
    real_target = case.case_dir / "real_data.txt"
    real_target.write_text("the real data\n")
    symlink_target = case.case_dir / "swapped.txt"
    symlink_target.symlink_to(real_target)

    # Force _resolve_safe to return the symlink's path verbatim
    # (NOT canonicalized). This simulates the TOCTOU window: an
    # attacker replaced the file with a symlink AFTER the sandbox
    # check resolved it as a regular path.
    monkeypatch.setattr(
        case,
        "_resolve_safe",
        lambda uri, **kwargs: symlink_target.absolute(),
    )

    with pytest.raises(OSError, match=r".*") as exc:  # noqa: PT011 — ELOOP/EMLINK varies
        case._open_safe_fd("./swapped.txt")
    # On POSIX, O_NOFOLLOW returns ELOOP (sometimes wrapped as
    # EMLINK on older platforms). Just confirm the system call
    # refused the open.
    assert exc.value.errno is not None


def test_v350_open_safe_fd_propagates_sandbox_rejection(
    tmp_path: Path,
) -> None:
    """v3.5.0: an out-of-sandbox URI must fail with the standard
    v3.0 path-safety ValueError, before any os.open is even
    attempted. The helper delegates to _resolve_safe first."""
    case = _make_case(tmp_path / "case_dir")
    with pytest.raises(ValueError, match="path-safety"):
        case._open_safe_fd("../../escapee.csv")


def test_v350_open_safe_fd_allow_outside_case_kwarg(
    tmp_path: Path,
) -> None:
    """v3.5.0: the per-call escape hatch threads through to
    _resolve_safe — engine code with a legitimate extra-case
    write target can still open via this helper."""
    case = _make_case(tmp_path / "case_dir")
    outside = tmp_path / "outside.txt"
    outside.write_text("legit fetcher output")

    fd = case._open_safe_fd(
        str(outside),
        allow_outside_case=True,
    )
    try:
        data = os.read(fd, 64)
        assert data.startswith(b"legit fetcher")
    finally:
        os.close(fd)


def test_v350_open_safe_fd_supports_write_flag(tmp_path: Path) -> None:
    """v3.5.0: arbitrary OS flags (O_WRONLY, O_CREAT, …) compose
    with the safety O_NOFOLLOW. A new in-sandbox file should
    open for write cleanly (no symlink exists yet → O_NOFOLLOW
    is a no-op at the final component)."""
    case = _make_case(tmp_path / "case_dir")
    fd = case._open_safe_fd(
        "./fresh.txt",
        flags=os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
    )
    try:
        os.write(fd, b"new content\n")
    finally:
        os.close(fd)
    assert (case.case_dir / "fresh.txt").read_text() == "new content\n"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows symlinks gated behind admin; test exercises POSIX path",
)
def test_v350_open_safe_fd_pinned_by_15round_review(tmp_path: Path) -> None:
    """v3.5.0 R15-4 / R14-11 (claude + gemini deferred across
    rounds): pin that the helper exists with the documented
    contract. Source-inspection guard against a future revert."""
    import inspect

    src = inspect.getsource(Case._open_safe_fd)
    # The mitigation depends on O_NOFOLLOW being or'd into flags.
    assert "O_NOFOLLOW" in src, (
        "v3.5.0 R15-4 regression: _open_safe_fd no longer applies "
        "O_NOFOLLOW; TOCTOU mitigation is gone."
    )
    # And delegates to _resolve_safe so the sandbox check still runs.
    assert "_resolve_safe" in src, (
        "v3.5.0 R15-4 regression: _open_safe_fd bypassed the sandbox check."
    )
