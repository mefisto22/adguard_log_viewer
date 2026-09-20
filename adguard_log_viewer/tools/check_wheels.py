#!/usr/bin/env python3
"""Check that every pinned dependency has a wheel for both target platforms.

The Docker build uses ``pip install --only-binary :all:`` so that a missing
wheel is a loud build failure rather than an attempt to compile Rust or C on a
Raspberry Pi. This script asks pip the same question up front, for both
architectures the app supports:

    python tools/check_wheels.py

Run it after changing ``requirements.txt`` or bumping the base image's Python
version. It needs network access; it downloads nothing into the project.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"

#: Alpine's musl matches the musllinux_1_1 tag, which is what the binary wheels
#: in this dependency set are published under.
PLATFORMS = ("musllinux_1_1_aarch64", "musllinux_1_1_x86_64")

#: Must match the Python in the base image named by build.yaml.
PYTHON_VERSION = "3.13"
ABI = "cp313"


def check(platform: str, python_version: str, abi: str) -> tuple[bool, list[str], str]:
    with tempfile.TemporaryDirectory(prefix="wheel-check-") as destination:
        # Fixed argv, no shell.
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--quiet",
                "--only-binary",
                ":all:",
                "--platform",
                platform,
                "--python-version",
                python_version,
                "--implementation",
                "cp",
                "--abi",
                abi,
                "--requirement",
                str(REQUIREMENTS),
                "--dest",
                destination,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        names = sorted(path.name for path in Path(destination).iterdir())
    return process.returncode == 0, names, process.stderr.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-version", default=PYTHON_VERSION)
    parser.add_argument("--abi", default=ABI)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not REQUIREMENTS.is_file():
        print(f"error: {REQUIREMENTS} not found", file=sys.stderr)
        return 2

    failures = 0
    for platform in PLATFORMS:
        ok, names, stderr = check(platform, args.python_version, args.abi)
        label = f"{platform} / cp{args.python_version.replace('.', '')}"
        if ok:
            binary = [name for name in names if not name.endswith("-none-any.whl")]
            print(f"OK   {label}: {len(names)} wheels ({len(binary)} platform specific)")
            if args.verbose:
                for name in names:
                    print(f"       {name}")
            elif binary:
                for name in binary:
                    print(f"       {name}")
        else:
            failures += 1
            print(f"FAIL {label}")
            for line in stderr.splitlines():
                print(f"       {line}")

    if failures:
        print(
            f"\n{failures} platform(s) cannot be installed from wheels. "
            "The Docker build would fail there.",
            file=sys.stderr,
        )
        return 1

    print("\nAll dependencies install from wheels on every supported architecture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
