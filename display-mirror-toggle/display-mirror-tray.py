#!/usr/bin/env python3
"""Display Mirror Tray — thin entry point.

All logic lives in the display_mirror_tray package. This file exists so
the .desktop file and any user-bound shortcuts can invoke a stable path.
"""

import os
import sys

# Allow running from a checkout without setting PYTHONPATH: prepend the
# directory containing this script so `display_mirror_tray` resolves.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from display_mirror_tray.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
