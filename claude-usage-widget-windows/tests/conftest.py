"""Pytest configuration - ensures proper import paths."""

import sys
from pathlib import Path

# Add the project root to path so we can import src as a package
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
