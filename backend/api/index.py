from pathlib import Path
import shutil
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import config  # noqa: E402

# Vercel bundles the entrypoint reliably; hydrate the writable runtime database
# from the bundled seed artifact when the function starts.
if config.RUNTIME_DIR != config.BACKEND_DIR and not config.DB_PATH.exists():
    bundled = config.BACKEND_DIR / "abl_platform.db"
    if bundled.exists():
        shutil.copyfile(bundled, config.DB_PATH)

from app.main import app  # noqa: E402

__all__ = ["app"]
