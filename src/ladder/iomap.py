"""IO mapping: bind IR IO tags to vendor addresses, outside the IR (M3).

The IR stays hardware-free; a separate iomap YAML carries per-vendor
bindings and is applied at build time (`ladder build --iomap ...`):

    io_version: "0.1"
    project: VacuumInterlock          # must match the IR project name
    siemens:
      pressure_ok:         {address: "%I8.0"}
      beam_shutter_permit: {address: "%Q4.0"}
    rockwell:
      pressure_ok:         {alias: "Local:1:I.Data.0"}
      beam_shutter_permit: {alias: "Local:2:O.Data.0"}
    beckhoff:
      pressure_ok:         {address: "%IX0.0"}   # or "%I*" for linked IO
    iec:
      pressure_ok:         {address: "%IX0.0"}   # 61131 located variable

Semantics per vendor: `address` becomes the tag's absolute address
(Siemens PLC tag, TwinCAT `AT %..`, IEC located var, PLCopen `address`
attribute); `alias` (Rockwell) turns the controller tag into an alias tag
for the named IO point. Unmapped IO tags keep today's behavior
(auto-allocated scratch addresses on Siemens, plain tags elsewhere).

Address SYNTAX is each vendor's own - the map is per-vendor by design, so
`%I8.0` (Siemens) and `%IX8.0` (IEC/TwinCAT) never collide.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ladder.ir.model import Project


class IoBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: Optional[str] = None
    alias: Optional[str] = None
    comment: Optional[str] = None

    @model_validator(mode="after")
    def _one_of(self) -> "IoBinding":
        if bool(self.address) == bool(self.alias):
            raise ValueError("binding needs exactly one of address / alias")
        return self


class IoMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    io_version: str = "0.1"
    project: str
    siemens: dict[str, IoBinding] = Field(default_factory=dict)
    rockwell: dict[str, IoBinding] = Field(default_factory=dict)
    beckhoff: dict[str, IoBinding] = Field(default_factory=dict)
    plcopen: dict[str, IoBinding] = Field(default_factory=dict)
    iec: dict[str, IoBinding] = Field(default_factory=dict)

    def section(self, backend: str) -> dict[str, IoBinding]:
        return getattr(self, backend, {}) or {}


def load_iomap(path: str | Path) -> IoMap:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: iomap must be a mapping")
    return IoMap.model_validate(data)


def validate_iomap(project: Project, iomap: IoMap) -> list[str]:
    """Cross-check the map against the IR; returns human/machine-readable
    problem strings (empty = good)."""
    problems: list[str] = []
    if iomap.project != project.name:
        problems.append(f"iomap is for project {iomap.project!r}, "
                        f"IR is {project.name!r}")
    tags = {t.name: t for t in project.tags}
    for backend in ("siemens", "rockwell", "beckhoff", "plcopen", "iec"):
        seen_targets: dict[str, str] = {}
        for name, b in iomap.section(backend).items():
            w = f"{backend}/{name}"
            tag = tags.get(name)
            if tag is None:
                problems.append(f"{w}: unknown tag")
                continue
            if tag.direction == "memory":
                problems.append(f"{w}: {name!r} is a memory tag, not IO")
            if tag.is_complex:
                problems.append(f"{w}: UDT/array tags cannot be mapped")
            if backend == "rockwell" and b.address:
                problems.append(f"{w}: rockwell bindings use alias, not address")
            if backend != "rockwell" and b.alias:
                problems.append(f"{w}: alias bindings are rockwell-only")
            target = b.address or b.alias or ""
            if target.endswith("*"):
                continue  # wildcard 'link later' markers may repeat (%I*)
            if target in seen_targets:
                problems.append(f"{w}: {target!r} already bound to "
                                f"{seen_targets[target]!r}")
            seen_targets[target] = name
    return problems


def apply_addresses(project: Project, iomap: IoMap, backend: str) -> Project:
    """Return a project copy with this backend's addresses stamped onto the
    tags (used by backends whose formats carry the address on the tag)."""
    section = iomap.section(backend)
    if not section:
        return project
    tags = [
        t.model_copy(update={"address": section[t.name].address})
        if t.name in section and section[t.name].address else t
        for t in project.tags
    ]
    return project.model_copy(update={"tags": tags})
