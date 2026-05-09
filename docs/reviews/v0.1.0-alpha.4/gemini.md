# Gemini review — `v0.1.0-alpha.3..v0.1.0-alpha.4`

_Generated 2026-05-09 by `gemini -p` on the alpha.4 diff._

### 1. Performance and GUI Responsiveness
**Blocking I/O on Main Thread:**
In `src/openlimno/gui_core/controller.py:831`, `_read_wua_parquet(cache_key)` is called directly within the controller logic, likely on the main GUI thread (given the `QMessageBox` interaction at line 813). Parquet files for "typical" reaches of 10k–200k rows can take several seconds to parse and load into Python objects. This will freeze the UI every time a new file is selected or an existing one is modified.

**Memory Overhead:**
The cache (`self._xs_rows_cache`) stores the raw results of `_read_wua_parquet`. If this returns a list of dictionaries for 200,000 rows, the memory footprint will be significant (hundreds of megabytes). There is no mechanism to clear this cache or limit its size if the user switches between multiple large reach files in one session.

### 2. Bug Risk and Robustness
**Incomplete Error Handling:**
In `src/openlimno/gui_core/controller.py:821`, if `os.path.getmtime` raises an `OSError` (e.g., file deleted, permission denied), `mtime` is set to `None`. However, the code proceeds to call `_read_wua_parquet(cache_key)` immediately after. If the file was missing, this second call will likely raise an unhandled exception, crashing the controller logic.

**Cache Invalidation Race Condition:**
The mtime check (line 825) protects against stale data, but it does not protect against partial reads. If an external process (like a `preprocess` shell command mentioned in the comments) is currently writing to the parquet file when the GUI triggers a read, `_read_wua_parquet` may encounter a locked file or, worse, read a corrupted/incomplete footer.

**Path Handling:**
The `cache_key` is assigned directly from `self._xs_parquet`. If this path is not normalized (e.g., `./data.parquet` vs `data.parquet`), the cache check `cache.get("path") != cache_key` might fail unnecessarily, leading to redundant I/O.

### 3. Test Adequacy
**Regression in Coverage:**
The update to `tests/integration/test_appimage_run_smoke.py` replaces the dynamic `build_case` (using `osm_builder`) with a static fixture `lemhi-tiny`. While this improves CI stability against network flakiness, it effectively removes the integration test coverage for the OSM-to-Case pipeline. Errors in `osm_builder` will no longer be caught by the smoke test.

**Silent Failure in CI:**
`test_appimage_run_smoke.py:34` uses `pytest.skip` if the fixture is missing. If a regression in the build process or a misconfiguration causes the fixture directory to be omitted from the test runner, the integration tests will silently skip rather than fail, potentially allowing broken builds to pass CI.

### 4. Packaging and Portability
**Build Environment Fragility:**
The documentation added to `packaging/openlimno-studio.spec` (lines 14–26) describes a very specific, manual build environment requirement regarding `jsonschema` versions and `pathex` exclusion. Relying on a human to "deliberately keep" system paths off `pathex` is brittle. This exclusion should be enforced programmatically within the `.spec` file's `Analysis` object to ensure reproducibility across different developer machines and CI runners.

**Dependency Conflicts:**
The comment notes that `jsonschema` 4.10 and 4.26 have incompatible internal APIs. If the PyInstaller analysis transitively pulls in the system version despite the warning, the resulting bundle will fail at runtime. This indicates a need for stricter `hiddenimports` or `excludedimports` definitions in the spec rather than just documentation.

### 5. Architecture
**State Persistence:**
Using `getattr(self, "_xs_rows_cache", {})` (line 824) to initialize a private attribute suggests the controller state is being managed dynamically rather than through explicit `__init__` declarations. This makes the state of the `Controller` harder to track and test.
