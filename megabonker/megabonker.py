#!/usr/bin/env python3
"""Megabonker - thin entry point.

All logic lives in the megabonker package. This file exists so .desktop files,
shell aliases and CLI invocations have a stable path to call.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from megabonker.cli import main

if __name__ == "__main__":
    sys.exit(main())
