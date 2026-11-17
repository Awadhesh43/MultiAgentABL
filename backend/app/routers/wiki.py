from __future__ import annotations

from fastapi import APIRouter

from abl_agents import knowledge_base

from .. import config, schemas

router = APIRouter(prefix="/api/wiki", tags=["wiki"])

_WIKI_SYSTEM_PROMPT = (
    "You are the ABL Wiki agent, a read-only conversational reference over a bank's curated ABL "
    "knowledge base. Ground your answer strictly in the excerpts provided below. If the excerpts "
    "don't clearly answer the question, say so rather than answering from general knowledge. Keep "
    "answers to 3-6 sentences unless the question needs a list. The calling application displays "
    "source citations separately below your answer -- do not add your own 'Sources:' line or cite "
    "documents by name inside the answer text itself."
)


@router.post("/chat", response_model=schemas.WikiChatResponse)
def chat(req: schemas.WikiChatRequest):
    hits = knowledge_base.search(req.question, n_results=4)
    citations = [{"source": h.source, "title": h.title} for h in hits]

    if not hits:
        return schemas.WikiChatResponse(
            answer="I couldn't find anything in the knowledge base related to that question.",
            citations=[], grounded=False,
        )

    if config.ANTHROPIC_API_KEY:
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        context_block = "\n\n".join(f"[{h.source} - {h.title}]\n{h.text}" for h in hits)
        response = client.messages.create(
            model=config.DEFAULT_MODEL,
            max_tokens=600,
            system=_WIKI_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Knowledge base excerpts:\n\n{context_block}\n\nQuestion: {req.question}"}],
        )
        answer = "".join(b.text for b in response.content if b.type == "text")
        return schemas.WikiChatResponse(answer=answer, citations=citations, grounded=True)

    # No API key: fall back to showing the retrieved passages directly.
    fallback = "No ANTHROPIC_API_KEY is configured, so here are the most relevant knowledge base passages directly:\n\n"
    fallback += "\n\n".join(f"**{h.title}** ({h.source}):\n{h.text}" for h in hits[:2])
    return schemas.WikiChatResponse(answer=fallback, citations=citations, grounded=True)
