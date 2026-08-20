"""Load and schema-validate a LADDER IR document (YAML or JSON)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ladder.ir.model import Project


def load_project(path: str | Path) -> Project:
    """Parse an IR file into a schema-validated Project.

    Semantic validation (name resolution, writability, vendor-portable
    identifiers) is a separate pass: ladder.ir.validate.validate_project.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    data = json.loads(text) if p.suffix.lower() == ".json" else yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{p}: IR document must be a mapping at top level")
    return Project.model_validate(data)


def json_schema() -> dict:
    """JSON Schema for the IR - the artifact an LLM generation loop
    validates against before anything vendor-specific runs."""
    return Project.model_json_schema()
