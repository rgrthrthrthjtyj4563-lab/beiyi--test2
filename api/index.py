import sys
import os
from pathlib import Path

# Add the project root to sys.path
root_path = Path(__file__).resolve().parent.parent
sys.path.append(str(root_path))

from backend.main import app

# Adjust for Vercel environment
if os.environ.get('VERCEL'):
    app.root_path = "/api"
