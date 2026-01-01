"""Pytest configuration for scripts tests."""

import sys
from pathlib import Path

# Add repo root to sys.path so `from scripts.bump_version import ...` works
# regardless of where pytest is invoked from
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))
