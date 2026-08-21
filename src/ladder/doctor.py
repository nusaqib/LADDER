"""`ladder doctor` - what can THIS machine do, and what is missing?

Converts the classic mystery failure ("deploy didn't work") into a
checklist. Purely informational: exit 0 unless the manifest itself is
broken. Every MISSING row comes with the fix.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool | None  # None = not applicable here
    detail: str
    hint: str = ""

    def line(self) -> str:
        mark = {True: "OK  ", False: "MISS", None: "n/a "}[self.ok]
        s = f"  [{mark}] {self.name}: {self.detail}"
        if self.ok is False and self.hint:
            s += f"\n         fix: {self.hint}"
        return s


def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _first_dir(*candidates: str) -> str | None:
    return next((c for c in candidates if Path(c).is_dir()), None)


def run_doctor(project_dir: str | Path | None = None) -> list[Check]:
    checks: list[Check] = []

    # --- core toolchain -------------------------------------------------
    checks.append(Check("python", sys.version_info >= (3, 11),
                        f"{sys.version.split()[0]} ({sys.executable})",
                        "install Python 3.11+"))
    import ladder as _l
    checks.append(Check("ladder", True, f"v{_l.__version__} at "
                        f"{Path(_l.__file__).parent}"))
    git = _which("git")
    checks.append(Check("git", bool(git), git or "not on PATH",
                        "install git (submodule pinning + review flow need it)"))

    # --- manifest / project ----------------------------------------------
    deploy: list[str] = []
    manifest = None
    if project_dir is not None:
        from ladder.scaffold import ManifestError, load_manifest

        try:
            manifest, root = load_manifest(project_dir)
            deploy = list(manifest.deploy)
            checks.append(Check("manifest", True,
                                f"{manifest.project} (requires "
                                f"{manifest.requires or 'any version'})"))
            vendored = root / "vendor" / "LADDER" / "pyproject.toml"
            checks.append(Check(
                "vendored toolchain", vendored.exists(),
                str(vendored.parent) if vendored.exists()
                else "no vendor/LADDER submodule",
                "run tools/bootstrap.ps1 (or .sh) to pin + install it"))
            if manifest.deploy_script:
                script = root / manifest.deploy_script
                checks.append(Check("deploy_script", script.exists(),
                                    str(script), "path in ladder.yaml is wrong"))
        except ManifestError as e:
            checks.append(Check("manifest", False, str(e),
                                "fix ladder.yaml (or run from the project root)"))

    # --- verification tools ----------------------------------------------
    nux = os.environ.get("NUXMV_BIN")
    nux = nux if nux and Path(nux).exists() else _which("nuXmv", "nuxmv")
    if not nux:  # tools/fetch_verifiers.py drops it under <repo>/.tools
        repo = Path(_l.__file__).parents[2]
        hit = sorted(repo.glob(".tools/nuXmv-*/bin/nuXmv*"))
        nux = str(hit[0]) if hit else None
    checks.append(Check("nuXmv (formal proofs)", bool(nux), nux or "not found",
                        "python tools/fetch_verifiers.py, or download from "
                        "nuxmv.fbk.eu and set NUXMV_BIN"))
    matiec = os.environ.get("MATIEC_BIN")
    matiec = matiec if matiec and Path(matiec).exists() else _which("iec2c")
    checks.append(Check("matiec (IEC compile checks)", bool(matiec),
                        matiec or "not found",
                        "clone github.com/beremiz/matiec and build; CI runs "
                        "it anyway on every push"))
    xsd = os.environ.get("TC6_XSD")
    if not xsd:
        cand = (Path(_l.__file__).parents[2] / "docs" / "reference" /
                "downloads" / "plcopen" / "tc6_xml_v201.xsd")
        xsd = str(cand) if cand.exists() else None
    checks.append(Check("tc6 XSD (PLCopen validation)", bool(xsd),
                        xsd or "not found",
                        "python tools/fetch_reference_docs.py, then set "
                        "TC6_XSD to the downloaded schema"))

    # --- vendor tools (deploy targets) -------------------------------------
    win = os.name == "nt"
    tia = _first_dir(r"C:\Program Files\Siemens\Automation\Portal V21",
                     r"C:\Program Files\Siemens\Automation\Portal V20",
                     r"C:\Program Files\Siemens\Automation\Portal V19") if win else None
    tia_api = os.environ.get("TIA_API_DIR", r"E:\TIA_Portal\TIA_API")
    want_siemens = any(d.startswith("siemens") for d in deploy) or not deploy
    checks.append(Check(
        "TIA Portal (siemens deploy)",
        (bool(tia) if win else None) if want_siemens else None,
        tia or ("not installed" if win else "Windows only"),
        "install TIA Portal + STEP 7 Professional license; artifact "
        "builds (`ladder check`) never need it"))
    if win and any(d.startswith("siemens") for d in deploy) and manifest \
            and manifest.deploy_script:
        ok = Path(tia_api, "src", "TiaOpenness", "TiaOpenness.psd1").exists()
        checks.append(Check("TiaOpenness engine", ok, tia_api,
                            "clone the tia-autocode repo and set TIA_API_DIR"))
    studio = _first_dir(r"C:\Program Files (x86)\Rockwell Software",
                        r"C:\Program Files\Rockwell Software") if win else None
    checks.append(Check(
        "Studio 5000 (rockwell deploy)",
        (bool(studio) if win else None) if any(
            d.startswith("rockwell") for d in deploy) else None,
        studio or ("not installed" if win else "Windows only"),
        "manual L5X import always works; SDK 2.x automates it"))
    twincat = _first_dir(r"C:\TwinCAT", r"C:\Program Files (x86)\Beckhoff") \
        if win else None
    checks.append(Check(
        "TwinCAT (beckhoff deploy)",
        (bool(twincat) if win else None) if any(
            d.startswith("beckhoff") for d in deploy) else None,
        twincat or ("not installed" if win else "engineering mode is a free "
                    "download"), "install TwinCAT XAE (free engineering mode)"))
    return checks


def format_report(checks: list[Check]) -> str:
    lines = ["ladder doctor - what this machine can run", ""]
    lines += [c.line() for c in checks]
    missing = [c for c in checks if c.ok is False]
    lines.append("")
    if missing:
        lines.append(f"{len(missing)} item(s) missing - everything marked OK "
                     "works today; MISSING items only block the step named.")
    else:
        lines.append("everything applicable is available on this machine.")
    return "\n".join(lines)
