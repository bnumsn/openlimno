"""WEDM (Water Ecology Data Model) — SPEC §3.1.

Public API:
    validate_case(path)        : validate a case YAML against case.schema.json
    validate_studyplan(path)   : validate a studyplan YAML
    load_schema(name)          : load a named schema by basename (no .schema.json)
    SCHEMA_VERSION             : current WEDM version string
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_VERSION = "0.1"


def _schema_dir() -> Path:
    return Path(resources.files(__package__).joinpath("schemas"))


def load_schema(name: str) -> dict[str, Any]:
    """Load a schema by basename (without ``.schema.json``)."""
    p = _schema_dir() / f"{name}.schema.json"
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


@cache
def _registry() -> Registry:
    """Build a registry of all WEDM schemas so $ref resolves locally (no network)."""
    registry = Registry()
    for schema_path in _schema_dir().glob("*.schema.json"):
        with schema_path.open("r", encoding="utf-8") as f:
            schema = json.load(f)
        resource = Resource(contents=schema, specification=DRAFT202012)
        # Register under both the absolute $id and the local relative filename
        if "$id" in schema:
            registry = registry.with_resource(uri=schema["$id"], resource=resource)
        registry = registry.with_resource(
            uri=f"./{schema_path.name}", resource=resource
        )
    return registry


def _validate_yaml_against(path: str | Path, schema_name: str) -> list[str]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    schema = load_schema(schema_name)
    validator = Draft202012Validator(schema, registry=_registry())
    return [
        f"{'/'.join(str(x) for x in err.absolute_path) or '<root>'}: {err.message}"
        for err in validator.iter_errors(data)
    ]


def validate_case(path: str | Path) -> list[str]:
    """Validate a case YAML. Returns empty list if valid."""
    return _validate_yaml_against(path, "case")


def validate_studyplan(path: str | Path) -> list[str]:
    """Validate a studyplan YAML."""
    return _validate_yaml_against(path, "studyplan")


__all__ = [
    "SCHEMA_VERSION",
    "load_schema",
    "validate_case",
    "validate_studyplan",
]
