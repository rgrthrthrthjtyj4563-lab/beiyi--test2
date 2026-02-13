import sys
import os
import shutil
from pathlib import Path

# Add the project root to sys.path
root_path = Path(__file__).resolve().parent.parent
sys.path.append(str(root_path))

# Vercel specific setup
if os.environ.get("VERCEL"):
    # Set DB path to /tmp which is writable
    os.environ["SOA_DB_PATH"] = "/tmp/app.db"
    os.environ["STATEMENTS_JSON_PATH"] = "/tmp/statements_db.json"
    
    # Ensure backend/data exists in /tmp if needed, or just let the app create the DB
    # The config.xlsx is read-only so it can stay in the source tree

from backend.main import app
