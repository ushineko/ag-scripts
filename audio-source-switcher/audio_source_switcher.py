#!/usr/bin/env python3
"""Audio Source Switcher — thin entry point.

All logic lives in the audio_source_switcher package.
This file exists so existing CLI invocations, hotkeys, and .desktop files
continue to work unchanged.
"""

from audio_source_switcher.cli import main

if __name__ == "__main__":
    main()
