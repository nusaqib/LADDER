#!/usr/bin/env python3
"""Fetch the verification tools LADDER uses into <repo>/.tools/.

    python tools/fetch_verifiers.py

- nuXmv (binary release, free for non-commercial use, nuxmv.fbk.eu):
  downloaded and unzipped; the script prints the NUXMV_BIN line to set.
- matiec (GPL source, github.com/beremiz/matiec): cloned; it needs a C
  toolchain + autotools to build, so the script clones and prints the
  build commands instead of guessing your compiler.

`ladder doctor` knows about .tools/ and reports what's usable.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / ".tools"

_PLAT = {"Windows": "win64", "Linux": "linux64", "Darwin": "macos64"}
# fbk.eu reorganizes per release: newer builds live under downloads/<ver>/
# as .tar.xz (Windows builds sometimes lag a release), older zips at the
# flat downloads/ path. First URL that answers wins.
_NUXMV_URLS = {
    "win64": [
        "https://nuxmv.fbk.eu/downloads/2.2.0/nuXmv-2.2.0-win64.zip",
        "https://nuxmv.fbk.eu/downloads/2.1.0/nuXmv-2.1.0-win64.zip",
        "https://es-static.fbk.eu/tools/nuxmv/downloads/nuXmv-2.1.0-win64.zip",
        "https://es-static.fbk.eu/tools/nuxmv/downloads/nuXmv-2.0.0-win64.zip",
    ],
    "linux64": [
        "https://nuxmv.fbk.eu/downloads/2.2.0/nuXmv-2.2.0-linux64.tar.xz",
        "https://es-static.fbk.eu/tools/nuxmv/downloads/nuXmv-2.0.0-linux64.tar.gz",
    ],
    "macos64": [
        "https://nuxmv.fbk.eu/downloads/2.2.0/nuXmv-2.2.0-macos64.tar.xz",
    ],
}


def _find_nuxmv() -> Path | None:
    exe = "nuXmv.exe" if platform.system() == "Windows" else "nuXmv"
    hits = sorted(TOOLS.glob(f"nuXmv-*/bin/{exe}"))
    return hits[-1] if hits else None


def fetch_nuxmv() -> Path | None:
    plat = _PLAT.get(platform.system())
    if not plat:
        print(f"nuXmv: unsupported platform {platform.system()}")
        return None
    found = _find_nuxmv()
    if found:
        print(f"nuXmv: already at {found}")
        return found
    TOOLS.mkdir(exist_ok=True)
    for url in _NUXMV_URLS[plat]:
        archive = TOOLS / url.rsplit("/", 1)[-1]
        try:
            print(f"nuXmv: trying {url} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "LADDER fetcher"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                archive.write_bytes(resp.read())
        except Exception as e:  # noqa: BLE001 - try the next mirror
            print(f"  no: {e}")
            continue
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as z:
                z.extractall(TOOLS)
        else:
            import tarfile

            with tarfile.open(archive) as t:
                t.extractall(TOOLS)
        archive.unlink()
        found = _find_nuxmv()
        if found:
            print(f"nuXmv: ready -> {found}")
            print(f'  set NUXMV_BIN, e.g. PowerShell:  $env:NUXMV_BIN = "{found}"')
            return found
    print("nuXmv: no downloadable build for this platform right now - "
          "download manually from https://nuxmv.fbk.eu (free for "
          "non-commercial use), unzip under .tools/, or set NUXMV_BIN")
    return None


def fetch_matiec() -> None:
    dest = TOOLS / "matiec"
    if dest.exists():
        print(f"matiec: already cloned at {dest}")
    else:
        TOOLS.mkdir(exist_ok=True)
        print("matiec: cloning github.com/beremiz/matiec ...")
        rc = subprocess.call(["git", "clone", "--depth", "1",
                              "https://github.com/beremiz/matiec.git", str(dest)])
        if rc != 0:
            print("matiec: clone failed (is git installed?)")
            return
    print("matiec: build it with a C toolchain (Linux/WSL/MSYS2):")
    print(f"  cd {dest} && autoreconf -i && ./configure && make")
    print("  then set MATIEC_BIN to the built iec2c "
          "(CI builds it fresh on every push regardless)")


if __name__ == "__main__":
    fetch_nuxmv()
    fetch_matiec()
    sys.exit(0)
