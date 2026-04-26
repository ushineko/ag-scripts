"""Pytest path setup so tests can import the launcher modules from the parent dir."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
