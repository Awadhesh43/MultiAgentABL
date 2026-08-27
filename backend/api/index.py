from app.main import app
from app.db import init_db

init_db()

__all__ = ["app"]
