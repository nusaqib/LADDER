"""Load and schema-validate a LADDER IR document (YAML/JSON file or
modular directory).

A modular IR is a DIRECTORY instead of one big file - sections live in
files a reviewer can own separately:

    ir/
      project.yaml      root fields: name, description, vendor, ir_version
      types.yaml        `types:` list  (or types/*.yaml, each a list)
      tags.yaml         `tags:` list   (or tags/*.yaml, each a list)
      programs/
        10_intake.yaml  one program mapping per file; files sort by name,
        20_logic.yaml   and that order IS the scan/call order - prefix
                        with numbers to make it explicit

`load_project` accepts either form; everything downstream sees one
Project. Hardware stays in the IO map document, never in the IR.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ladder.ir.model import Project


def _read(p: Path):
    text = p.read_text(encoding="utf-8")
    return json.loads(text) if p.suffix.lower() == ".json" else yaml.safe_load(text)


def _merge_section(root: Path, name: str) -> list:
    """Collect `<name>.yaml` (a list, or a mapping with a `<name>:` key)
    plus `<name>/*.yaml` fragments, in filename order."""
    out: list = []
    single = root / f"{name}.yaml"
    if single.exists():
        data = _read(single)
        if isinstance(data, dict):
            data = data.get(name, [])
        out.extend(data or [])
    frag_dir = root / name
    if frag_dir.is_dir():
        for f in sorted(frag_dir.glob("*.yaml")) + sorted(frag_dir.glob("*.json")):
            data = _read(f)
            if isinstance(data, dict):
                if name == "programs":
                    out.append(data)      # one program per file
                    continue
                data = data.get(name, [])
            out.extend(data or [])
    return out


def load_ir_data(path: str | Path) -> dict:
    """Raw IR mapping from a single file or a modular directory."""
    p = Path(path)
    if p.is_file():
        data = _read(p)
        if not isinstance(data, dict):
            raise ValueError(f"{p}: IR document must be a mapping at top level")
        return data
    if not p.is_dir():
        raise FileNotFoundError(f"{p}: no such IR file or directory")
    root_file = p / "project.yaml"
    if not root_file.exists():
        raise ValueError(f"{p}: a modular IR directory needs a project.yaml "
                         "(name, description, vendor hints)")
    data = _read(root_file)
    if not isinstance(data, dict):
        raise ValueError(f"{root_file}: must be a mapping")
    for section in ("types", "tags", "programs"):
        merged = _merge_section(p, section)
        if section in data and merged:
            raise ValueError(f"{p}: {section!r} defined both in project.yaml "
                             f"and in {section}[.yaml|/]; pick one place")
        if merged:
            data[section] = merged
    return data


class IRLoadError(ValueError):
    """Schema-level failure, reported with file/line context."""


def _yaml_line(text: str, loc: tuple) -> int | None:
    """Line number (1-based) of a pydantic error location in YAML text."""
    try:
        node = yaml.compose(text)
    except yaml.YAMLError:
        return None
    for key in loc:
        if node is None:
            return None
        if isinstance(node, yaml.MappingNode):
            node = next((v for k, v in node.value if k.value == str(key)), None)
        elif isinstance(node, yaml.SequenceNode) and isinstance(key, int):
            node = node.value[key] if key < len(node.value) else None
        else:
            break
    return node.start_mark.line + 1 if node is not None else None


def _friendly_validation_error(e, path: Path) -> str:
    """Pydantic ValidationError -> human-readable, line-numbered report."""
    text = path.read_text(encoding="utf-8") if path.is_file() else None
    lines = [f"{path}: the IR does not match the schema "
             f"({e.error_count()} issue(s)):"]
    seen: set[tuple] = set()
    for err in e.errors():
        loc = tuple(err["loc"])
        # union validators repeat per branch; report each place once
        anchor = loc[:4]
        if anchor in seen:
            continue
        seen.add(anchor)
        where = ".".join(str(x) for x in loc)
        pin = ""
        if text is not None:
            ln = _yaml_line(text, loc)
            if ln:
                pin = f"  ({path.name}:{ln})"
        lines.append(f"  {where}: {err['msg']}{pin}")
        if len(lines) > 9:
            lines.append(f"  ... and more (total {e.error_count()})")
            break
    lines.append("hint: `ladder schema` prints the full contract; element "
                 "docs are in docs/IR-SPEC.md")
    return "\n".join(lines)


def load_project(path: str | Path, expand: bool = True) -> Project:
    """Parse an IR file OR modular directory into a schema-validated
    Project.

    Pattern elements are expanded into real elements by default. Semantic
    validation (name resolution, writability, vendor-portable identifiers)
    is a separate pass: ladder.ir.validate.validate_project.
    """
    from pydantic import ValidationError

    data = load_ir_data(path)
    try:
        project = Project.model_validate(data)
    except ValidationError as e:
        raise IRLoadError(_friendly_validation_error(e, Path(path))) from None
    if expand:
        from ladder.patterns import expand_project  # lazy: avoid import cycle

        project = expand_project(project)
    return project


def json_schema() -> dict:
    """JSON Schema for the IR - the artifact an LLM generation loop
    validates against before anything vendor-specific runs."""
    return Project.model_json_schema()
