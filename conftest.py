"""Pytest configuration: ensure the project root is on sys.path so that
``import src.retriever`` works without an editable install.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))