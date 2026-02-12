import sys
from pathlib import Path

# Add the project root to sys.path
root_path = Path(__file__).resolve().parent.parent
sys.path.append(str(root_path))

from backend.main import app
