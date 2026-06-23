#!/usr/bin/env python3
"""PyInstaller entry point for the packaged macOS .app.

`src/main.py` uses package-relative imports (`from .logging_config import ...`),
so it can't be a PyInstaller entry script directly — running it as `__main__`
breaks those imports. This thin wrapper imports the package properly and hands
off to `src.main.main()`. Equivalent to `python -m src.main`.
"""

from src.main import main

if __name__ == "__main__":
    main()
