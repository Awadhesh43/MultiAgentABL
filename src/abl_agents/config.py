"""Runtime configuration, resolved once at import time."""
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
KNOWLEDGE_BASE_DIR = DATA_DIR / "knowledge_base"
DEALS_DIR = DATA_DIR / "deals"
BBC_DIR = DATA_DIR / "borrowing_base_certificates"
CHROMA_DIR = ROOT_DIR / "chroma_db"
LOGS_DIR = ROOT_DIR / "logs"
AUDIT_LOG_PATH = LOGS_DIR / "audit_log.jsonl"

LOGS_DIR.mkdir(exist_ok=True)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL = os.environ.get("ABL_AGENT_MODEL", "claude-sonnet-5")
MAX_AGENT_TURNS = int(os.environ.get("ABL_AGENT_MAX_TURNS", "6"))
KB_COLLECTION_NAME = "abl_knowledge_base"


def require_api_key() -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Create a .env file (see .env.example) "
            "or export the variable before running an agent."
        )
    return ANTHROPIC_API_KEY
