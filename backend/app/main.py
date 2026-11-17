from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .db import init_db
from .routers import agents, audit_router, deals, documents, hitl, wiki

app = FastAPI(title="Agentic ABL Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_configured": bool(config.ANTHROPIC_API_KEY)}


app.include_router(deals.router)
app.include_router(hitl.router)
app.include_router(audit_router.router)
app.include_router(documents.router)
app.include_router(wiki.router)
app.include_router(agents.router)
