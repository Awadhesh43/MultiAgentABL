"""ABL Wiki knowledge base: Markdown source files indexed into ChromaDB.

Chunking is deliberately simple -- each `## ` heading in a source file
becomes one chunk, tagged with its source document and section title, which
is exactly the granularity the glossary and playbook articles were written
at. Embeddings use Chroma's bundled default model (all-MiniLM-L6-v2 via
onnxruntime), so the demo runs fully offline after the model is first
downloaded and needs no separate embeddings API key.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

import chromadb

from . import config


class ABLHashEmbeddingFunction:
    """Offline deterministic vector embeddings for serverless Chroma."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def _embed(self, input: list[str]) -> list[list[float]]:
        vectors = []
        for text in input:
            terms = re.findall(r"[a-z0-9]+", text.lower())
            features = terms + [f"{a} {b}" for a, b in zip(terms, terms[1:])]
            vector = [0.0] * self.dimensions
            for feature in features:
                digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self._embed(input)

    def name(self) -> str:
        return "abl-hash-embedding-v1"

    def get_config(self) -> dict:
        return {"dimensions": self.dimensions}


_EMBEDDING_FUNCTION = ABLHashEmbeddingFunction()


def _collection(client):
    return client.get_or_create_collection(
        config.KB_COLLECTION_NAME,
        embedding_function=_EMBEDDING_FUNCTION,
    )

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
    collection = _collection(client)

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
    """Retrieve KB context without requiring writable local Chroma storage."""
    try:
        client = _get_client()
        collection = _collection(client)
        if collection.count() == 0:
            ingest()
            collection = _collection(client)
        result = collection.query(query_texts=[query], n_results=n_results)
        return [KBHit(text=doc, source=meta["source"], title=meta["title"], distance=dist)
                for doc, meta, dist in zip(result["documents"][0], result["metadatas"][0], result["distances"][0])]
    except Exception as exc:
        print(f"[v0] Chroma unavailable; using deterministic KB fallback: {type(exc).__name__}: {exc}")
        query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        candidates = []
        for path in sorted(config.KNOWLEDGE_BASE_DIR.glob("*.md")):
            for title, body in _chunk_markdown(path):
                score = len(query_terms & set(re.findall(r"[a-z0-9]+", (title + " " + body).lower())))
                candidates.append((score, KBHit(text=f"{title}\n\n{body}", source=path.name, title=title, distance=1.0 - min(score, 10) / 10)))
        return [hit for _, hit in sorted(candidates, key=lambda item: item[0], reverse=True)[:n_results]]
