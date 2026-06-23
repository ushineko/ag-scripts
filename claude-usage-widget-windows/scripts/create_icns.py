#!/usr/bin/env python3
"""Render the app SVG into a macOS .icns icon.

Rasterizes `claude-usage-widget.svg` at every size the macOS iconset requires,
then runs `iconutil` to pack them into `claude-usage-widget.icns`. Build-time
only (invoked by scripts/build_macos.sh); not shipped as a loose file inside
the .app — PyInstaller embeds it as the bundle icon.

Uses PySide6 (the project's Qt binding) for SVG rasterization, so no extra
build dependency beyond what the widget already needs.

Usage: python3 scripts/create_icns.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

PROJECT_DIR = Path(__file__).resolve().parent.parent
SVG_SOURCE = PROJECT_DIR / "claude-usage-widget.svg"
ICNS_OUT = PROJECT_DIR / "claude-usage-widget.icns"

# (base point size, scale) -> iconset entry. macOS expects 1x and @2x for
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
        iconset = Path(tmp) / "claude-usage-widget.iconset"
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
