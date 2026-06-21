# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS vscode-launcher.app bundle.

Builds a menu-bar *agent* app (LSUIElement = no Dock icon) following the
clockwork-orange packaging pattern. Build with `scripts/build_macos.sh`,
which regenerates the .icns first.

Notes:
  - `vscl-tmux-lookup` (tmux_lookup.py) is intentionally NOT bundled: it's a
    PATH helper invoked by the zsh hook as a subprocess, installed as a
    symlink by install.sh, not imported by the launcher.
  - QtDBus / QtSvg are added as hidden imports. QtDBus is imported by the
    KDE-only global_shortcut / single_instance modules (present but inert on
    macOS); QtSvg backs SVG icon rendering for the menu-bar template image.
"""

datas = [
    ("vscode-launcher.svg", "."),
    ("vscode-launcher-template.svg", "."),
]
hiddenimports = ["PyQt6.QtDBus", "PyQt6.QtSvg", "macos_global_shortcut"]

a = Analysis(
    ["vscode_launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
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
    name="vscode-launcher",
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
    icon=["vscode-launcher.icns"],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="vscode-launcher",
)
app = BUNDLE(
    coll,
    name="vscode-launcher.app",
    icon="vscode-launcher.icns",
    bundle_identifier="com.vscode-launcher",
    info_plist={
        # Menu-bar agent: present in /Applications + Spotlight, no Dock icon.
        "LSUIElement": True,
        "CFBundleName": "vscode-launcher",
        "CFBundleDisplayName": "VSCode Launcher",
        "NSHighResolutionCapable": True,
    },
)
