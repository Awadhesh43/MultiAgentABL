from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from abl_agents import knowledge_base

from .. import agent_eval, config, schemas
from ..db import get_db

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
def chat(req: schemas.WikiChatRequest, db: Session = Depends(get_db)):
    use_llm = bool(config.ANTHROPIC_API_KEY)
    with agent_eval.record(
        db, "wiki", "ABL Wiki Agent", mode="llm" if use_llm else "retrieval",
        model=config.DEFAULT_MODEL if use_llm else "", input_summary=req.question,
    ) as call:
        started = perf_counter()
        hits = knowledge_base.search(req.question, n_results=4)
        call.row.retrieval_ms = round((perf_counter() - started) * 1000, 1)
        citations = [{"source": h.source, "title": h.title} for h in hits]
        call.update_details(retrieval=[{"source": h.source, "title": h.title, "distance": round(h.distance, 4)} for h in hits])
        call.eval_input = {
            "query": req.question, "context": [h.text for h in hits], "retrieval_distances": [h.distance for h in hits],
        }

        if not hits:
            call.row.mode = "retrieval"  # nothing to ground an LLM answer on, so none was requested
            answer = "I couldn't find anything in the knowledge base related to that question."
            call.set_output(answer)
            response = schemas.WikiChatResponse(answer=answer, citations=[], grounded=False)
        elif use_llm:
            import anthropic

            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            context_block = "\n\n".join(f"[{h.source} - {h.title}]\n{h.text}" for h in hits)
            started = perf_counter()
            llm_response = client.messages.create(
                model=config.DEFAULT_MODEL,
                max_tokens=600,
                system=_WIKI_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Knowledge base excerpts:\n\n{context_block}\n\nQuestion: {req.question}"}],
            )
            call.row.llm_ms = round((perf_counter() - started) * 1000, 1)
            answer = "".join(b.text for b in llm_response.content if b.type == "text")
            call.set_usage(llm_response.usage)
            call.row.model = getattr(llm_response, "model", config.DEFAULT_MODEL)
            call.update_details(stop_reason=getattr(llm_response, "stop_reason", None))
            call.eval_input["answer"] = answer
            call.set_output(answer)
            response = schemas.WikiChatResponse(answer=answer, citations=citations, grounded=True)
        else:
            # No API key: fall back to showing the retrieved passages directly.
            answer = "No ANTHROPIC_API_KEY is configured, so here are the most relevant knowledge base passages directly:\n\n"
            answer += "\n\n".join(f"**{h.title}** ({h.source}):\n{h.text}" for h in hits[:2])
            call.set_output(answer)
            response = schemas.WikiChatResponse(answer=answer, citations=citations, grounded=True)

    db.commit()
    return response
