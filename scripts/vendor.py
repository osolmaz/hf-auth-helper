#!/usr/bin/env python3
"""Refresh the vendored questionary stack in src/hf_auth_helper/_vendor.

The interactive prompts come from questionary, vendored (with its two pure
Python dependencies) so the published package stays dependency-free. Bump a
pin below and rerun:

    python scripts/vendor.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PINS = {
    "questionary": "2.1.1",
    "prompt_toolkit": "3.0.52",
    "wcwidth": "0.8.2",
}

VENDOR_DIR = Path(__file__).resolve().parent.parent / "src" / "hf_auth_helper" / "vendor"

VENDOR_README = """Vendored dependencies. Do not edit by hand.

Refresh with: python scripts/vendor.py
Pinned versions are recorded in VENDORED.txt.
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--no-deps",
                "--target",
                tmp,
                *[f"{name}=={version}" for name, version in PINS.items()],
            ],
            check=True,
        )
        if VENDOR_DIR.exists():
            shutil.rmtree(VENDOR_DIR)
        VENDOR_DIR.mkdir(parents=True)
        (VENDOR_DIR / "README.txt").write_text(VENDOR_README, encoding="utf-8")
        (VENDOR_DIR / "VENDORED.txt").write_text(
            "".join(f"{name}=={version}\n" for name, version in PINS.items()),
            encoding="utf-8",
        )
        for name in PINS:
            shutil.copytree(Path(tmp) / name, VENDOR_DIR / name)
        # dist-info comes along so importlib.metadata can resolve versions
        # (prompt_toolkit looks its own version up at import time).
        for dist_info in Path(tmp).glob("*.dist-info"):
            shutil.copytree(dist_info, VENDOR_DIR / dist_info.name)
    print(f"vendored {', '.join(f'{n}=={v}' for n, v in PINS.items())} into {VENDOR_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
