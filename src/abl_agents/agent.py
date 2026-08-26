"""Generic tool-calling agent wrapper around the Anthropic Messages API.

Every domain agent in registry.py is an instance of this one class,
parameterized by a system prompt and a subset of the shared tool catalog --
there is deliberately no per-agent subclassing. The loop below is the same
"call model, execute any tool calls, feed results back" pattern regardless
of which lifecycle stage the agent represents.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

import anthropic

from . import config, tools


@dataclass
class AgentResult:
    agent_name: str
    text: str
    pending_changes: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    turns_used: int = 0


class Agent:
    def __init__(self, agent_id: str, name: str, system_prompt: str, tool_names: list[str], model: Optional[str] = None):
        self.agent_id = agent_id
        self.name = name
        self.system_prompt = system_prompt
        unknown = set(tool_names) - set(tools.TOOL_NAMES)
        if unknown:
            raise ValueError(f"{agent_id}: unknown tool names {unknown}")
        self.tool_schemas = [t for t in tools.TOOL_SCHEMAS if t["name"] in tool_names]
        self.model = model or config.DEFAULT_MODEL

    def run(
        self,
        user_message: str,
        max_turns: Optional[int] = None,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
    ) -> AgentResult:
        config.require_api_key()
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        max_turns = max_turns or config.MAX_AGENT_TURNS

        messages = [{"role": "user", "content": user_message}]
        pending_changes: list[dict] = []
        citations: list[dict] = []
        tool_call_log: list[dict] = []

        for turn in range(1, max_turns + 1):
            response = client.messages.create(
                model=self.model,
                max_tokens=1800,
                system=self.system_prompt,
                tools=self.tool_schemas,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": _blocks_to_dicts(response.content)})

            if response.stop_reason != "tool_use":
                final_text = "".join(b.text for b in response.content if b.type == "text")
                return AgentResult(
                    agent_name=self.name,
                    text=final_text,
                    pending_changes=pending_changes,
                    citations=_dedupe_citations(citations),
                    tool_calls=tool_call_log,
                    turns_used=turn,
                )

            tool_result_blocks = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if on_tool_call:
                    on_tool_call(block.name, block.input)
                try:
                    result, staged, cites = tools.dispatch(block.name, block.input)
                    is_error = False
                except Exception as exc:  # noqa: BLE001 - surfaced to the model, not swallowed
                    result = {"error": str(exc)}
                    staged, cites = None, []
                    is_error = True

                tool_call_log.append({"name": block.name, "input": block.input, "result": result})
                if staged:
                    pending_changes.append(staged)
                citations.extend(cites)

                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                    "is_error": is_error,
                })

            messages.append({"role": "user", "content": tool_result_blocks})

        return AgentResult(
            agent_name=self.name,
            text="[Reached max tool-call turns without a final answer.]",
            pending_changes=pending_changes,
            citations=_dedupe_citations(citations),
            tool_calls=tool_call_log,
            turns_used=max_turns,
        )


def _blocks_to_dicts(content_blocks) -> list[dict]:
    out = []
    for b in content_blocks:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


def _dedupe_citations(citations: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for c in citations:
        key = (c["source"], c["title"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique
