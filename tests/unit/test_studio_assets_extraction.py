"""Structural guards for the extracted Studio browser assets.

The fishtank and IBM Studios are single self-contained HTML pages, but their
CSS/JS live in real files under ``openlimno/<pkg>/assets/`` (so they can be
linted, syntax checked and executed by :mod:`test_studio_browser`) and are
inlined into ``INDEX_HTML`` / ``_INDEX_HTML`` at import time.

These tests are the cheap, always-on half of that contract:

* every asset file exists, is non-empty and is referenced by exactly one marker;
* the rendered page contains each asset *verbatim* — this is the machine-checked
  form of "the extraction was semantics-preserving";
* no marker survives rendering, and the page pulls nothing off the network
  (the Studios are used offline on classroom machines);
* every asset is force-included into the wheel, so an installed copy renders;
* every ``.js``/``.mjs`` asset parses (``node --check``) when node is available.

Behaviour — that the JavaScript actually *runs* — is covered by
``test_studio_browser.py``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from openlimno.fishtank import studio_assets as fishtank_assets
from openlimno.ibm import studio_assets as ibm_assets

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"

# (label, module, rendered page, wheel-relative package prefix)
STUDIOS = [
    ("fishtank", fishtank_assets, fishtank_assets.INDEX_HTML, "openlimno/fishtank"),
    ("ibm", ibm_assets, ibm_assets._INDEX_HTML, "openlimno/ibm"),
]
STUDIO_IDS = [label for label, *_ in STUDIOS]


def _assets(module: object) -> dict[str, str]:
    """Return ``{marker: asset name}`` for one Studio asset module."""

    return dict(module._ASSET_MARKERS)  # type: ignore[attr-defined]


def _asset_dir(module: object) -> Path:
    return Path(module._ASSETS_DIR)  # type: ignore[attr-defined]


def _template(module: object) -> str:
    return str(module._INDEX_TEMPLATE)  # type: ignore[attr-defined]


def _all_asset_paths() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for label, module, _page, _prefix in STUDIOS:
        for name in _assets(module).values():
            out.append((f"{label}/{name}", _asset_dir(module) / name))
    return out


ASSET_PATHS = _all_asset_paths()
ASSET_IDS = [name for name, _path in ASSET_PATHS]


# ---------------------------------------------------------------------------
# The assets themselves
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "path"), ASSET_PATHS, ids=ASSET_IDS)
def test_studio_asset_file_exists_and_is_not_empty(label: str, path: Path) -> None:
    assert path.is_file(), f"{label}: missing asset file {path}"
    assert path.stat().st_size > 0, f"{label}: empty asset file {path}"


@pytest.mark.parametrize(("label", "path"), ASSET_PATHS, ids=ASSET_IDS)
def test_studio_asset_file_is_utf8_text_with_unix_newlines(label: str, path: Path) -> None:
    raw = path.read_bytes()
    raw.decode("utf-8")  # raises on invalid UTF-8
    assert b"\r\n" not in raw, (
        f"{label}: CRLF in a committed asset would change the rendered page on "
        "one platform but not another; keep the files LF-only"
    )


@pytest.mark.parametrize(("label", "module", "page", "prefix"), STUDIOS, ids=STUDIO_IDS)
def test_asset_directory_holds_no_unreferenced_files(
    label: str, module: object, page: str, prefix: str
) -> None:
    """Every file next to the module is actually inlined by it."""

    on_disk = {p.name for p in _asset_dir(module).iterdir() if p.is_file()}
    referenced = set(_assets(module).values())
    assert on_disk == referenced, (
        f"{label}: assets/ holds {sorted(on_disk - referenced)} that nothing inlines, "
        f"and is missing {sorted(referenced - on_disk)}"
    )


# ---------------------------------------------------------------------------
# Extraction is semantics-preserving: each asset appears verbatim in the page
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "module", "page", "prefix"), STUDIOS, ids=STUDIO_IDS)
def test_rendered_page_inlines_every_asset_verbatim(
    label: str, module: object, page: str, prefix: str
) -> None:
    for marker, name in _assets(module).items():
        body = (_asset_dir(module) / name).read_text(encoding="utf-8")
        assert body in page, f"{label}: {name} is not inlined verbatim into the page"
        assert marker not in page, f"{label}: unreplaced marker for {name} left in the page"


@pytest.mark.parametrize(("label", "module", "page", "prefix"), STUDIOS, ids=STUDIO_IDS)
def test_template_holds_exactly_one_marker_per_asset(
    label: str, module: object, page: str, prefix: str
) -> None:
    template = _template(module)
    for marker, name in _assets(module).items():
        assert template.count(marker) == 1, (
            f"{label}: template must hold exactly one marker for {name}"
        )


@pytest.mark.parametrize(("label", "module", "page", "prefix"), STUDIOS, ids=STUDIO_IDS)
def test_render_refuses_a_template_whose_marker_went_missing(
    label: str, module: object, page: str, prefix: str
) -> None:
    """A silently dropped marker must fail loudly, not ship a page missing its JS."""

    template = _template(module)
    marker = next(iter(_assets(module)))
    with pytest.raises(RuntimeError, match="exactly one"):
        module._render(template.replace(marker, ""))  # type: ignore[attr-defined]


@pytest.mark.parametrize(("label", "module", "page", "prefix"), STUDIOS, ids=STUDIO_IDS)
def test_rendered_page_is_a_str_and_a_complete_document(
    label: str, module: object, page: str, prefix: str
) -> None:
    """``studio_http`` imports these names and writes them straight to the socket."""

    assert isinstance(page, str)
    assert page.startswith("<!doctype html>")
    assert page.rstrip().endswith("</html>")


@pytest.mark.parametrize(("label", "module", "page", "prefix"), STUDIOS, ids=STUDIO_IDS)
def test_rendered_page_loads_nothing_from_the_network(
    label: str, module: object, page: str, prefix: str
) -> None:
    """The Studios run offline on classroom machines — no CDN, no remote fonts."""

    assert "<link" not in page.lower(), f"{label}: a <link> tag would fetch a remote asset"
    for scheme in ('src="http', "src='http", 'src="//', "src='//"):
        assert scheme not in page, f"{label}: remote {scheme}… in the page"
    assert "@import url(http" not in page, f"{label}: remote CSS @import in the page"
    # The only module import is the vendored three.js, served by studio_http from
    # openlimno/fishtank/vendor/ — a same-origin path, never a CDN.
    for statement in re.findall(r"""\bfrom\s+['"]([^'"]+)['"]""", page):
        assert statement.startswith("/assets/"), (
            f"{label}: JS imports {statement!r}, which is not a same-origin path"
        )


# ---------------------------------------------------------------------------
# Packaging: an installed wheel must be able to render the page
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "path"), ASSET_PATHS, ids=ASSET_IDS)
def test_every_asset_is_force_included_in_the_wheel(label: str, path: Path) -> None:
    if not PYPROJECT.is_file():  # installed copy, no source tree
        pytest.skip("pyproject.toml not available (running against an installed copy)")
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    force_include = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    source = path.relative_to(REPO_ROOT).as_posix()
    assert source in force_include, (
        f"{source} is inlined at import time but is not force-included into the "
        "wheel; an installed openlimno would raise FileNotFoundError on import"
    )
    assert force_include[source] == source.removeprefix("src/")


# ---------------------------------------------------------------------------
# The JavaScript parses
# ---------------------------------------------------------------------------

JS_ASSETS = [(label, path) for label, path in ASSET_PATHS if path.suffix in {".js", ".mjs"}]
JS_IDS = [label for label, _path in JS_ASSETS]


@pytest.mark.parametrize(("label", "path"), JS_ASSETS, ids=JS_IDS)
def test_javascript_asset_parses(label: str, path: Path) -> None:
    """``node --check`` is the floor: a typo'd brace can never reach a student.

    ``.mjs`` is checked as an ES module (the 3D tank uses ``import``), ``.js``
    as a classic script — which is exactly how the browser loads each one.
    """

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; browser tests cover parsing when it is not")
    result = subprocess.run(  # noqa: S603 - fixed argv, path from this repo
        [node, "--check", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"{label} failed to parse:\n{result.stderr}"
