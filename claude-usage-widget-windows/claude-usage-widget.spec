# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS "Claude Usage Widget.app" bundle.

Builds a menu-bar/tray *agent* app (LSUIElement = no Dock icon — the widget is
a floating tray utility). Build with `scripts/build_macos.sh`, which
regenerates the .icns first; install with `install.sh`.

Notes:
  - The entry point is `app_main.py`, a thin wrapper around `src.main.main()`.
    The package modules (`src/*.py`) use relative imports, so PyInstaller
    cannot target `src/main.py` directly.
  - `structlog` is declared as a hidden import. It is imported normally and
    PyInstaller's analysis usually finds it, but declaring it guards against
    its lazy/conditional internals being missed.
  - Qt plugins (platforms, imageformats) are pulled in automatically by
    PyInstaller's bundled PySide6 hook.
"""

hiddenimports = ["structlog"]

a = Analysis(
    ["app_main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="claude-usage-widget",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["claude-usage-widget.icns"],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="claude-usage-widget",
)
app = BUNDLE(
    coll,
    name="Claude Usage Widget.app",
    icon="claude-usage-widget.icns",
    bundle_identifier="com.nverenin.claude-usage-widget",
    info_plist={
        # Tray/menu-bar agent: present in /Applications + Spotlight, no Dock icon.
        "LSUIElement": True,
        "CFBundleName": "Claude Usage Widget",
        "CFBundleDisplayName": "Claude Usage Widget",
        "NSHighResolutionCapable": True,
    },
)
