from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from app import config

if not config.DB_PATH.exists():
    from seed import main as seed_database

    seed_database()
