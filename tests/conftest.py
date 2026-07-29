"""Test bootstrap for pure, Home-Assistant-independent modules.

`cycle_math.py` and `pill_math.py` deliberately have no Home Assistant
imports (see their own docstrings) - only `custom_components/perioder/const.py`,
via a relative import (`from .const import ...`). Importing them the normal
way (`from custom_components.perioder import cycle_math`) would first run
`custom_components/perioder/__init__.py`, which *does* import Home Assistant
- pulling in the full `homeassistant` package as a test dependency just to
exercise pure arithmetic. This project doesn't use
`pytest-homeassistant-custom-component` (or any other HA test scaffolding),
so instead this loads exactly the three pure modules by file path, registers
them under their real dotted names in `sys.modules` (so their own
`from .const import ...` relative imports resolve correctly), and never
touches `custom_components/perioder/__init__.py` at all.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT_DIR = REPO_ROOT / "custom_components" / "perioder"


def _ensure_namespace_package(name: str, path: Path) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module
    return module


def _load_submodule(parent_name: str, submodule: str, filename: str) -> types.ModuleType:
    full_name = f"{parent_name}.{submodule}"
    if full_name in sys.modules:
        return sys.modules[full_name]

    spec = importlib.util.spec_from_file_location(full_name, COMPONENT_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    setattr(sys.modules[parent_name], submodule, module)
    return module


_ensure_namespace_package("custom_components", REPO_ROOT / "custom_components")
_ensure_namespace_package("custom_components.perioder", COMPONENT_DIR)

_load_submodule("custom_components.perioder", "const", "const.py")
_load_submodule("custom_components.perioder", "cycle_math", "cycle_math.py")
_load_submodule("custom_components.perioder", "pill_math", "pill_math.py")
