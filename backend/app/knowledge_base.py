"""ABL Wiki knowledge base: Markdown source files indexed into ChromaDB.

Chunking is deliberately simple -- each `## ` heading in a source file
becomes one chunk, tagged with its source document and section title, which
is exactly the granularity the glossary and playbook articles were written
at. Embeddings use Chroma's bundled default model (all-MiniLM-L6-v2 via
onnxruntime), so the demo runs fully offline after the model is first
downloaded and needs no separate embeddings API key.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import chromadb

from . import config

_HEADING_RE = re.compile(r"^##\s+(.*)$", re.MULTILINE)


@dataclass
class KBHit:
    text: str
    source: str
    title: str
    distance: float


def _chunk_markdown(path) -> list[tuple[str, str]]:
    """Returns list of (title, body) chunks split on '## ' headings."""
    text = path.read_text(encoding="utf-8")
    matches = list(_HEADING_RE.finditer(text))
    chunks = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        chunks.append((title, body))
    return chunks


def _get_client() -> chromadb.ClientAPI:
    config.CHROMA_DIR.mkdir(exist_ok=True)
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR))


def ingest(rebuild: bool = True) -> int:
    """(Re)indexes every Markdown file in data/knowledge_base. Returns chunk count."""
    client = _get_client()
    if rebuild:
        try:
            client.delete_collection(config.KB_COLLECTION_NAME)
        except Exception:
            pass
    collection = client.get_or_create_collection(config.KB_COLLECTION_NAME)

    ids, documents, metadatas = [], [], []
    for path in sorted(config.KNOWLEDGE_BASE_DIR.glob("*.md")):
        for idx, (title, body) in enumerate(_chunk_markdown(path)):
            if not body:
                continue
            ids.append(f"{path.stem}::{idx}")
            documents.append(f"{title}\n\n{body}")
            metadatas.append({"source": path.name, "title": title})

    if documents:
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
    return len(documents)


def search(query: str, n_results: int = 4) -> list[KBHit]:
    client = _get_client()
    collection = client.get_or_create_collection(config.KB_COLLECTION_NAME)
    if collection.count() == 0:
        ingest()
        collection = client.get_or_create_collection(config.KB_COLLECTION_NAME)

    result = collection.query(query_texts=[query], n_results=n_results)
    hits = []
    for doc, meta, dist in zip(
        result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        hits.append(KBHit(text=doc, source=meta["source"], title=meta["title"], distance=dist))
    return hits
