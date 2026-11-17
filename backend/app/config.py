"""Backend runtime configuration."""
from pathlib import Path
import os
import sys

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env")

# Reuse the CLI package's math and Chroma-backed knowledge base rather than
# duplicating them -- calculations.py and knowledge_base.py have no
# dependency on the CLI's own file-based deal store.
sys.path.insert(0, str(ROOT_DIR / "src"))

# Defaults to BACKEND_DIR so local dev is unchanged; a container sets ABL_DB_DIR
# to a mounted volume so the SQLite file survives container recreation.
DB_DIR = Path(os.environ.get("ABL_DB_DIR", str(BACKEND_DIR)))
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "abl_platform.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

UPLOAD_DIR = Path(os.environ.get("ABL_UPLOAD_DIR", str(BACKEND_DIR / "uploaded_docs")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Cached "screenshots" of the source chunks a key term was extracted from
# (see evidence_render.py). Regenerable from the original upload at any time.
EVIDENCE_DIR = UPLOAD_DIR / "evidence"

# Same physical directory the CLI's knowledge_base.py (src/abl_agents) uses
# for the curated ABL wiki collection -- semantic_extraction.py stores
# uploaded-document chunks there too, under a separate collection name, so
# both share one Chroma store without mixing their content. ABL_UPLOAD_DIR and
# ABL_CHROMA_DIR exist so a scratch instance (tests, demos) can run without
# touching the real uploads or vector index.
CHROMA_DIR = Path(os.environ.get("ABL_CHROMA_DIR", str(ROOT_DIR / "chroma_db")))

SAMPLE_DOCS_DIR = BACKEND_DIR / "sample_documents"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL = os.environ.get("ABL_AGENT_MODEL", "claude-sonnet-5")

CORS_ORIGINS = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
]
