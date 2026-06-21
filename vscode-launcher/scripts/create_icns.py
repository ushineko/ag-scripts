#!/usr/bin/env python3
"""Render the colored app SVG into a macOS .icns icon.

Rasterizes `vscode-launcher.svg` (the full-color icon — the monochrome
`vscode-launcher-template.svg` is for the menu bar only) at every size the
macOS iconset requires, then runs `iconutil` to pack them into
`vscode-launcher.icns`. Build-time only; not shipped inside the .app.

Usage: python3 scripts/create_icns.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

PROJECT_DIR = Path(__file__).resolve().parent.parent
SVG_SOURCE = PROJECT_DIR / "vscode-launcher.svg"
ICNS_OUT = PROJECT_DIR / "vscode-launcher.icns"

# (base point size, scale) -> iconset filename. macOS expects 1x and @2x for
# each logical size from 16 to 512.
ICONSET = [
    (16, 1), (16, 2),
    (32, 1), (32, 2),
    (128, 1), (128, 2),
    (256, 1), (256, 2),
    (512, 1), (512, 2),
]


def _render(renderer: QSvgRenderer, px: int) -> QImage:
    img = QImage(px, px, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    return img


def main() -> int:
    if not SVG_SOURCE.is_file():
        print(f"error: {SVG_SOURCE} not found", file=sys.stderr)
        return 1
    # QImage/QPainter need a (headless) Qt application instance.
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    _ = app
    renderer = QSvgRenderer(str(SVG_SOURCE))
    if not renderer.isValid():
        print(f"error: could not parse {SVG_SOURCE}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "vscode-launcher.iconset"
        iconset.mkdir()
        for base, scale in ICONSET:
            px = base * scale
            name = (
                f"icon_{base}x{base}.png"
                if scale == 1
                else f"icon_{base}x{base}@2x.png"
            )
            if not _render(renderer, px).save(str(iconset / name), "PNG"):
                print(f"error: failed to write {name}", file=sys.stderr)
                return 1
        result = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(ICNS_OUT)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"iconutil failed:\n{result.stderr}", file=sys.stderr)
            return 1

    print(f"wrote {ICNS_OUT} ({ICNS_OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
