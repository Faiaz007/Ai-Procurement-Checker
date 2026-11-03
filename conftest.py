"""
Root conftest.py – ensures the project root is on sys.path so that
`app` is importable regardless of how pytest is invoked.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
