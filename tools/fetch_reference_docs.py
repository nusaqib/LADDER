#!/usr/bin/env python3
"""Fetch the real vendor/tool documentation into docs/reference/downloads/.

Driven by docs/reference/downloads/sources.yaml. Downloaded files are
git-ignored (we may download vendor publications freely but not
redistribute them); this script makes the offline library reproducible
on any machine:

    python tools/fetch_reference_docs.py [--force]
"""

from __future__ import annotations

import argparse
import glob
import shutil
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "docs" / "reference" / "downloads"
UA = {"User-Agent": "Mozilla/5.0 (LADDER reference-doc fetcher)"}


def fetch_url(urls: list[str], target: Path) -> str:
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if len(data) < 1024:
                raise OSError(f"suspiciously small ({len(data)} bytes)")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return f"ok      {len(data)//1024:>6} KB  {target.name}"
        except Exception as e:  # noqa: BLE001 - report and try next URL
            last = f"{url}: {e}"
    return f"FAILED  {target.name} - {last}"


def copy_local(pattern: str, rel: str) -> str:
    matches = glob.glob(pattern)
    if not matches:
        return f"SKIP    {rel} - no local match for {pattern}"
    if rel.endswith("/") or len(matches) > 1:
        tdir = DEST / rel.rstrip("/")
        tdir.mkdir(parents=True, exist_ok=True)
        for m in matches:
            shutil.copy2(m, tdir / Path(m).name)
        return f"ok      {len(matches):>3} file(s) -> {rel}"
    target = DEST / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(matches[0], target)
    return f"ok      {target.stat().st_size//1024:>6} KB  {target.name}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="re-fetch files that already exist")
    args = ap.parse_args()

    manifest = yaml.safe_load((DEST / "sources.yaml").read_text(encoding="utf-8"))
    failures = 0
    for src in manifest["sources"]:
        rel = src["path"]
        target = DEST / rel
        if not args.force and (target.is_file() or
                               (rel.endswith("/") and target.is_dir()
                                and any(target.iterdir()))):
            print(f"have    {rel}")
            continue
        if "local" in src:
            line = copy_local(src["local"], rel)
        else:
            line = fetch_url(src["urls"], target)
        print(line)
        failures += line.startswith("FAILED")
    print(f"\ndone -> {DEST}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
