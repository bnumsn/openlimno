"""Self-validate every schema in src/openlimno/wedm/schemas/ as Draft 2020-12.

Run as: ``python -m openlimno.wedm.validate_schemas``
Used in CI (``pixi run validate-schemas``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from openlimno.wedm import _schema_dir


def main() -> int:
    schema_dir = _schema_dir()
    failures: list[tuple[Path, str]] = []
    schemas = sorted(schema_dir.glob("*.schema.json"))
    if not schemas:
        print(f"No schemas found in {schema_dir}", file=sys.stderr)
        return 1
    for schema_path in schemas:
        try:
            with schema_path.open("r", encoding="utf-8") as f:
                schema = json.load(f)
            Draft202012Validator.check_schema(schema)
            print(f"  ok  {schema_path.name}")
        except Exception as e:  # noqa: BLE001
            failures.append((schema_path, str(e)))
            print(f"  FAIL {schema_path.name}: {e}", file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} schema(s) failed validation", file=sys.stderr)
        return 1
    print(f"\nAll {len(schemas)} schemas valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
