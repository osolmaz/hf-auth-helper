"""Loader for the vendored questionary stack.

questionary and its dependencies live under ``vendor`` (refresh with
``scripts/vendor.py``). They are imported through ``sys.path`` so the
vendored code keeps its own absolute imports; this module is the only
place that path manipulation happens.
"""

import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType

_VENDOR_DIR = str(Path(__file__).resolve().parent / "vendor")


def load_questionary() -> ModuleType:
    """Import the vendored questionary package."""
    if _VENDOR_DIR not in sys.path:
        sys.path.insert(0, _VENDOR_DIR)
    return import_module("questionary")
