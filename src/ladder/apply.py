"""`ladder apply` - land an assistant's intake response into the project.

The intake contract (`ladder prompt --intake`) ends with the model
emitting three fenced blocks: the filled Design Inputs Map (markdown),
the IR (YAML starting with `ir_version:`), and the scenario suite (YAML
starting with `scenarios:`). Save the whole response to a file, then:

    ladder apply response.md .

writes each block to its slot (design/DESIGN.md, the manifest's ir/ and
scenarios/ paths) and runs the full `ladder check` gate. Nothing lands
silently: the diff is yours to review in git before committing.
"""

from __future__ import annotations

import re
from pathlib import Path

_FENCE = re.compile(r"```([^\n`]*)\n(.*?)```", re.S)


class ApplyError(ValueError):
    pass


def extract_blocks(text: str) -> dict[str, str]:
    """Classify fenced blocks into design / ir / scenarios."""
    out: dict[str, str] = {}
    for info, body in _FENCE.findall(text):
        body = body.strip() + "\n"
        head = body.lstrip()[:400]
        if re.search(r"^ir_version\s*:", head, re.M) or (
                re.search(r"^tags\s*:", head, re.M)
                and re.search(r"^programs\s*:", head, re.M)):
            out.setdefault("ir", body)
        elif re.search(r"^scenarios\s*:", head, re.M):
            out.setdefault("scenarios", body)
        elif info.strip().lower() in ("markdown", "md") or head.startswith("#"):
            out.setdefault("design", body)
    missing = [k for k in ("ir", "scenarios") if k not in out]
    if missing:
        raise ApplyError(
            f"response has no recognizable {'/'.join(missing)} block(s) - "
            "the IR block must contain `ir_version:` (or tags:+programs:), "
            "the scenario block `scenarios:`; ask the model to re-emit the "
            "three fenced blocks from the intake contract")
    return out


def apply_response(response_path: str | Path, project_dir: str | Path) -> list[Path]:
    """Write the response's blocks into the project. Returns written paths."""
    from ladder.scaffold import load_manifest

    manifest, root = load_manifest(project_dir)
    blocks = extract_blocks(Path(response_path).read_text(encoding="utf-8"))

    written: list[Path] = []
    ir_target = root / manifest.ir
    if ir_target.is_dir():
        raise ApplyError(
            f"this project uses a modular IR directory ({manifest.ir}/) - "
            "split the model's IR block into project/types/tags/programs "
            "files by hand, or point the manifest at a single file first")
    for key, rel in (("design", Path("design/DESIGN.md")),
                     ("ir", Path(manifest.ir)),
                     ("scenarios", Path(manifest.scenarios or "scenarios/generated.scenarios.yaml"))):
        if key not in blocks:
            continue
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(blocks[key], encoding="utf-8")
        written.append(path)
    return written
