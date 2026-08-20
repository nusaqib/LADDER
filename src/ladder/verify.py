"""`ladder verify` - check generated artifacts with whatever tool is available.

Checkers are best-effort by design: a missing tool is a SKIP, a failed check
is a FAIL (nonzero exit). This lets the same command run on a contributor's
laptop (no vendor software -> iec via matiec only), CI (matiec built from
source), and the lab machine (TIA Portal via TiaOpenness).

Environment:
    MATIEC_BIN  path to iec2c (default: iec2c on PATH)
    MATIEC_LIB  matiec standard library dir (default: <bin dir>/lib)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ladder.ir.model import Project


@dataclass
class VerifyResult:
    target: str
    status: str  # 'pass' | 'fail' | 'skip'
    detail: str = ""

    def __str__(self) -> str:
        return f"[{self.target}] {self.status.upper()}" + (f" - {self.detail}" if self.detail else "")


def _run(cmd: list[str], timeout: int = 900) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def verify_iec(project: Project, outdir: Path) -> VerifyResult:
    """Syntax/semantics check of the neutral ST file with matiec's iec2c."""
    st = outdir / "iec" / f"{project.name}.st"
    if not st.exists():
        return VerifyResult("iec", "skip", f"{st} not built (run build with -t iec)")
    bin_ = os.environ.get("MATIEC_BIN") or shutil.which("iec2c")
    if not bin_:
        return VerifyResult("iec", "skip", "iec2c not found (set MATIEC_BIN or install matiec)")
    lib = os.environ.get("MATIEC_LIB") or str(Path(bin_).parent / "lib")
    with tempfile.TemporaryDirectory() as tmp:
        code, output = _run([bin_, "-I", lib, "-T", tmp, str(st)])
    if code == 0:
        return VerifyResult("iec", "pass", f"iec2c accepted {st.name}")
    detail = "\n".join(output.splitlines()[-10:]) if output else f"iec2c exit {code}"
    return VerifyResult("iec", "fail", detail)


def verify_siemens(project: Project, outdir: Path) -> VerifyResult:
    """Run the emitted build.ps1: scratch TIA project, import, compile 0/0.

    Windows + TIA Portal + TiaOpenness only; several minutes of wall clock.
    """
    build = outdir / "siemens" / "build.ps1"
    if not build.exists():
        return VerifyResult("siemens", "skip", f"{build} not built")
    if os.name != "nt":
        return VerifyResult("siemens", "skip", "requires Windows + TIA Portal")
    api = project.vendor.get("siemens", {}).get("tia_api_path", "E:/TIA_Portal/TIA_API")
    if not Path(api).exists():
        return VerifyResult("siemens", "skip", f"TiaOpenness not found at {api}")
    code, output = _run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                         "-File", str(build)], timeout=1800)
    tail = next((line for line in reversed(output.splitlines()) if "BUILD" in line), "")
    if code == 0:
        return VerifyResult("siemens", "pass", tail or "compile 0 errors")
    return VerifyResult("siemens", "fail", tail or f"build.ps1 exit {code} (see build.log)")


def verify_smv(project: Project, outdir: Path) -> VerifyResult:
    """Model-check emitted SMV with nuXmv (env NUXMV_BIN or on PATH)."""
    from ladder.model_check import emit_project

    bin_ = os.environ.get("NUXMV_BIN") or shutil.which("nuxmv") or shutil.which("nuXmv")
    if not bin_:
        return VerifyResult("smv", "skip", "nuXmv not found (set NUXMV_BIN)")
    files, skipped = emit_project(project, outdir / "smv")
    if not files:
        return VerifyResult("smv", "skip", "; ".join(skipped) or "nothing model-checkable")
    failures = []
    for f in files:
        code, output = _run([bin_, "-dcx", str(f)])
        if code != 0:
            return VerifyResult("smv", "fail", f"nuXmv error on {f.name}: "
                                f"{output.splitlines()[-1] if output else code}")
        failures += [line.strip() for line in output.splitlines()
                     if "is false" in line]
    if failures:
        return VerifyResult("smv", "fail", "; ".join(failures[:3]))
    note = f"{len(files)} model(s), all properties proved"
    if skipped:
        note += f" ({len(skipped)} program(s) skipped)"
    return VerifyResult("smv", "pass", note)


CHECKERS = {
    "iec": verify_iec,
    "siemens": verify_siemens,
    "smv": verify_smv,
}


def verify_targets(project: Project, outdir: Path, targets: list[str]) -> list[VerifyResult]:
    results = []
    for t in targets:
        fn = CHECKERS.get(t)
        if fn is None:
            results.append(VerifyResult(t, "skip", "no checker for this backend yet"))
        else:
            results.append(fn(project, outdir))
    return results
