"""Guards for the lazy ``openlimno fishtank`` subcommand.

``openlimno.fishtank``'s package ``__init__`` eagerly re-exports the ODE/ABM
stack, so importing its click group costs ~0.75 s of scipy.optimize + pandas.
``openlimno.cli`` therefore registers it through :class:`~openlimno.cli.
LazyGroup` instead of a module-level import. These tests pin both halves of
that trade: start-up stays free of the heavy modules, and the command keeps
behaving exactly as an eagerly registered one.
"""

from __future__ import annotations

import subprocess
import sys

import click
import pytest
from click.testing import CliRunner

import openlimno.cli as cli_module
from openlimno.cli import LAZY_COMMANDS, main

# Pin the formatter width: click otherwise sizes the command list from the
# ambient terminal, which would make the rendering assertions drift.
TERMINAL_WIDTH = 80


def test_importing_cli_does_not_pull_in_heavy_deps() -> None:
    """A bare ``import openlimno.cli`` must not drag in scipy/pandas."""
    probe = (
        "import sys; import openlimno.cli;"
        "roots = {m.split('.')[0] for m in sys.modules};"
        "print(sorted(roots & {'scipy', 'pandas', 'pyarrow'}));"
        "print('openlimno.fishtank' in sys.modules)"
    )
    proc = subprocess.run(
        # ``-s`` keeps a stray user-site install out of the probe's sys.modules.
        [sys.executable, "-s", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
    )
    heavy, fishtank_loaded = proc.stdout.split("\n")[:2]
    assert heavy == "[]", f"openlimno.cli imported heavy modules: {heavy}"
    assert fishtank_loaded == "False"


def test_help_lists_fishtank_without_importing_it() -> None:
    """``openlimno --help`` still advertises the lazy group."""
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "fishtank" in result.output


@pytest.mark.parametrize("limit", [20, 30, 39, 45, 60, 200])
def test_lazy_stub_short_help_matches_real_command(
    limit: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stub must summarise identically at every width, not just wide ones.

    click returns an explicit ``short_help`` verbatim but derives one from
    ``help`` via ``make_default_short_help(help, limit)``, which elides to the
    column width. Pinning the wrong field renders the same text at a generous
    limit yet diverges at the narrower limit ``--help`` actually uses. The stub
    is pulled from ``get_command`` under the listing flag so this exercises the
    object ``format_commands`` really renders, not a look-alike.
    """
    from openlimno.fishtank.cli import main as fishtank_cli

    monkeypatch.setattr(main, "_listing_commands", True)
    ctx = click.Context(main)
    for name in LAZY_COMMANDS:
        stub = main.get_command(ctx, name)
        assert stub is not None
        assert stub.get_short_help_str(limit) == fishtank_cli.get_short_help_str(limit)


def test_help_output_identical_to_eager_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    """``openlimno --help`` must render byte-for-byte as it did before laziness."""
    from openlimno.fishtank.cli import main as fishtank_cli

    runner = CliRunner()
    lazy = runner.invoke(main, ["--help"], terminal_width=TERMINAL_WIDTH)
    assert lazy.exit_code == 0

    # Re-render with the group registered the old way: eagerly, in ``commands``.
    monkeypatch.setattr(cli_module, "LAZY_COMMANDS", {})
    monkeypatch.setitem(main.commands, "fishtank", fishtank_cli)
    eager = runner.invoke(main, ["--help"], terminal_width=TERMINAL_WIDTH)
    assert eager.exit_code == 0

    assert lazy.output == eager.output


def test_help_renders_expected_fishtank_line() -> None:
    """Lock the line the user actually sees, elision included."""
    result = CliRunner().invoke(main, ["--help"], terminal_width=TERMINAL_WIDTH)
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.startswith("  fishtank ")]
    assert lines == ["  fishtank                        Run, validate, calibrate, and launch..."]


def test_get_command_returns_the_real_group() -> None:
    """Resolution yields the very object ``fishtank`` (the entry point) uses."""
    from openlimno.fishtank.cli import main as fishtank_cli

    ctx = click.Context(main)
    assert main.get_command(ctx, "fishtank") is fishtank_cli
    assert "fishtank" in main.list_commands(ctx)


def test_fishtank_subcommand_help_is_unchanged() -> None:
    """``openlimno fishtank ...`` parses args exactly like the direct entry point."""
    runner = CliRunner()
    group_help = runner.invoke(main, ["fishtank", "--help"])
    assert group_help.exit_code == 0
    for subcommand in ("validate", "run", "calibrate", "studio"):
        assert subcommand in group_help.output

    run_help = runner.invoke(main, ["fishtank", "run", "--help"])
    assert run_help.exit_code == 0
    assert "--out-dir" in run_help.output


def test_unknown_lazy_subcommand_still_errors() -> None:
    result = CliRunner().invoke(main, ["fishtank", "no-such-command"])
    assert result.exit_code != 0
    assert "No such command" in result.output
