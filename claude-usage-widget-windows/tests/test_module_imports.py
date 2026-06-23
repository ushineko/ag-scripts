"""Regression tests for module import-time compatibility.

The macOS .app bundle is built with the system Python (3.9.6 on current
macOS). PEP 604 union annotations (``X | None``) are *evaluated* at import
time in non-future-annotated modules, which raises ``TypeError`` on Python
< 3.10 and made the packaged app crash on launch before drawing the tray.

Importing each pure (non-Qt) module here fails fast under any interpreter
that would also fail inside the PyInstaller bundle, regardless of the
interpreter pytest happens to run under.
"""

import importlib

import pytest

# Modules with no PySide6 dependency — safe to import in any environment.
PURE_MODULES = [
    "src.platform_support",
    "src.display",
    "src.logging_config",
    "src.config",
    "src.oauth",
]


@pytest.mark.parametrize("module_name", PURE_MODULES)
def test_module_imports_without_error(module_name):
    """Each pure module imports cleanly (catches PEP 604 on Python 3.9)."""
    importlib.import_module(module_name)
