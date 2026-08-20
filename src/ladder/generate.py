"""Model-agnostic generation loop (M5).

    ladder generate spec.md --cmd "llm -m gpt-5" --accept scenarios.yaml -o gen.yaml

The LLM is any shell command that reads the prompt on stdin and writes its
answer to stdout - a hosted CLI (`claude -p`, `llm`, `ollama run ...`), a
curl script, or a local model wrapper. LADDER never binds to a provider;
the contract is stdin/stdout text (set LADDER_LLM_CMD to avoid repeating
--cmd).

The loop: build prompt -> model emits YAML -> schema + semantic validation
-> (optional) acceptance scenarios in the simulator -> on any failure, the
full issue list goes back to the model and it re-emits. Every artifact of
the loop (prompt, raw replies, feedback) is kept in a history for audit.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ladder.ir.model import Project
from ladder.ir.validate import lint_project, validate_project
from ladder.promptgen import build_prompt
from ladder.scenario import run_suite


@dataclass
class Attempt:
    reply: str
    problems: list[str] = field(default_factory=list)


@dataclass
class GenResult:
    ok: bool
    project: Project | None
    yaml_text: str | None
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def iterations(self) -> int:
        return len(self.attempts)


_FENCE_RE = re.compile(r"```(?:yaml|yml)?\s*\n(.*?)```", re.DOTALL)


def extract_yaml(reply: str) -> str:
    """Model replies often wrap the document in a code fence - unwrap it."""
    matches = _FENCE_RE.findall(reply)
    if matches:
        return max(matches, key=len).strip()
    return reply.strip()


def _check(yaml_text: str, accept: str | Path | None) -> tuple[Project | None, list[str]]:
    """Validate a candidate document; return (project, problems)."""
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return None, [f"not parseable as YAML: {e}"]
    if not isinstance(data, dict):
        return None, ["document must be a YAML mapping"]
    try:
        project = Project.model_validate(data)
    except Exception as e:  # pydantic ValidationError - report compactly
        return None, [f"schema validation failed: {e}"]
    from ladder.patterns import PatternError, expand_project

    try:
        project = expand_project(project)
    except PatternError as e:
        return None, [str(e)]
    res = validate_project(project)
    if not res.ok:
        return project, [str(i) for i in res.issues]
    problems = []
    if accept:
        for r in run_suite(project, accept):
            if not r.passed:
                problems.append(f"acceptance scenario failed: {r}")
    return project, problems


_FEEDBACK = """

## Your previous attempt

```yaml
{previous}
```

## Problems found (fix ALL of them)

{problems}

Re-emit the COMPLETE corrected YAML document - not a diff, not commentary.
"""


def generate(requirement: str, cmd: str, accept: str | Path | None = None,
             max_iters: int = 3, timeout: int = 600) -> GenResult:
    result = GenResult(ok=False, project=None, yaml_text=None)
    feedback = ""
    previous = ""
    for _ in range(max_iters):
        prompt = build_prompt(requirement) + feedback
        proc = subprocess.run(cmd, shell=True, input=prompt,
                              capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"LLM command failed (exit {proc.returncode}): "
                               f"{proc.stderr.strip()[:500]}")
        yaml_text = extract_yaml(proc.stdout)
        project, problems = _check(yaml_text, accept)
        result.attempts.append(Attempt(reply=yaml_text, problems=problems))
        if not problems:
            result.ok, result.project, result.yaml_text = True, project, yaml_text
            return result
        previous = yaml_text
        feedback = _FEEDBACK.format(
            previous=previous,
            problems="\n".join(f"- {p}" for p in problems))
    return result


def lint_report(project: Project) -> list[str]:
    """Non-fatal warnings worth showing after a successful generation."""
    return [str(w) for w in lint_project(project)]
