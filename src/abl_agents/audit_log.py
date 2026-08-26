"""Append-only, hash-chained audit log.

Every agent recommendation and every human gate decision is written here.
Each entry embeds the hash of the entry before it, so the log's integrity
can be verified end to end -- tampering with or deleting a past entry breaks
every hash after it. This is the same pattern described in the tech stack
doc's "audit is structural, not appended" principle, implemented directly
rather than deferred to a managed ledger service.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from . import config

GENESIS_HASH = "0" * 64


def _entry_hash(entry: dict) -> str:
    payload = json.dumps(entry, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _last_hash() -> str:
    if not config.AUDIT_LOG_PATH.exists():
        return GENESIS_HASH
    last_line = None
    with open(config.AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last_line = line
    if last_line is None:
        return GENESIS_HASH
    return json.loads(last_line)["hash"]


def append_entry(
    event_type: str,
    deal_id: str,
    stage: Optional[str] = None,
    actor: str = "system",
    summary: str = "",
    detail: Optional[dict] = None,
) -> dict:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "deal_id": deal_id,
        "stage": stage,
        "actor": actor,
        "summary": summary,
        "detail": detail or {},
        "prev_hash": _last_hash(),
    }
    entry["hash"] = _entry_hash(entry)
    with open(config.AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    return entry


def read_all() -> list[dict]:
    if not config.AUDIT_LOG_PATH.exists():
        return []
    entries = []
    with open(config.AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


def verify_chain() -> tuple[bool, Optional[int]]:
    """Returns (is_valid, index_of_first_break_or_None)."""
    entries = read_all()
    prev = GENESIS_HASH
    for i, entry in enumerate(entries):
        claimed_hash = entry["hash"]
        recomputed = _entry_hash({k: v for k, v in entry.items() if k != "hash"})
        if entry["prev_hash"] != prev or claimed_hash != recomputed:
            return False, i
        prev = claimed_hash
    return True, None
