"""Backend runtime configuration."""
from pathlib import Path
import os
import shutil
import sys

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env")

# Reuse the CLI package's math and Chroma-backed knowledge base rather than
# duplicating them -- calculations.py and knowledge_base.py have no
# dependency on the CLI's own file-based deal store.
sys.path.insert(0, str(ROOT_DIR / "src"))

RUNTIME_DIR = Path("/tmp/abl-platform") if os.environ.get("VERCEL") else BACKEND_DIR
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = RUNTIME_DIR / "abl_platform.db"
BUNDLED_DB_PATH = BACKEND_DIR / "abl_platform.db"
if RUNTIME_DIR != BACKEND_DIR and not DB_PATH.exists() and BUNDLED_DB_PATH.exists():
    shutil.copyfile(BUNDLED_DB_PATH, DB_PATH)
DATABASE_URL = f"sqlite:///{DB_PATH}"

UPLOAD_DIR = RUNTIME_DIR / "uploaded_docs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Same physical directory the CLI's knowledge_base.py (src/abl_agents) uses
# for the curated ABL wiki collection -- semantic_extraction.py stores
# uploaded-document chunks there too, under a separate collection name, so
# both share one Chroma store without mixing their content.
CHROMA_DIR = RUNTIME_DIR / "chroma_db"
KNOWLEDGE_BASE_DIR = BACKEND_DIR / "data" / "knowledge_base"
KB_COLLECTION_NAME = "abl_knowledge_base"

SAMPLE_DOCS_DIR = BACKEND_DIR / "sample_documents"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL = os.environ.get("ABL_AGENT_MODEL", "claude-sonnet-4-20250514")

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:4200,http://127.0.0.1:4200",
    ).split(",")
    if origin.strip()
]
