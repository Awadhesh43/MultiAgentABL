"""Mock system-of-record for deals and borrowing base certificates.

Stands in for the LOS / servicing platform integrations described in the
HLD's integration layer. Reads are unrestricted for the demo; writes only
ever happen through `apply_change`, which the orchestrator calls after a
human has approved a proposed change -- agents themselves never call this
module directly.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config

_deal_path_cache: dict[str, Path] = {}


def _index_deals() -> None:
    if _deal_path_cache:
        return
    for path in config.DEALS_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        deal_id = data.get("deal_id")
        if deal_id:
            _deal_path_cache[deal_id] = path


def list_deals() -> list[dict]:
    _index_deals()
    return [json.loads(p.read_text(encoding="utf-8")) for p in _deal_path_cache.values()]


def get_deal(deal_id: str) -> dict:
    _index_deals()
    path = _deal_path_cache.get(deal_id)
    if not path:
        raise KeyError(f"No deal on file with deal_id={deal_id!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_deal(deal_id: str, data: dict) -> None:
    _index_deals()
    path = _deal_path_cache.get(deal_id)
    if not path:
        raise KeyError(f"No deal on file with deal_id={deal_id!r}")
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def apply_change(deal_id: str, field_path: str, new_value: Any) -> dict:
    """Applies a dot-path update, e.g. 'financials.trailing_ebitda' -> 4800000."""
    deal = get_deal(deal_id)
    parts = field_path.split(".")
    cursor = deal
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    old_value = cursor.get(parts[-1])
    cursor[parts[-1]] = new_value
    save_deal(deal_id, deal)
    return {"field_path": field_path, "old_value": old_value, "new_value": new_value}


def _bbc_history_path(deal_id: str) -> Path:
    for path in config.BBC_DIR.glob("*_bbc_history.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("deal_id") == deal_id:
            return path
    raise KeyError(f"No BBC history on file for deal_id={deal_id!r}")


def get_bbc_history(deal_id: str, limit: int = 10) -> list[dict]:
    path = _bbc_history_path(deal_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["history"][-limit:]


def get_pending_bbc_submission(deal_id: str) -> dict | None:
    path = config.BBC_DIR / "new_bbc_submission.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("deal_id") != deal_id:
        return None
    return data


def commit_bbc_submission(deal_id: str, computed_entry: dict) -> None:
    path = _bbc_history_path(deal_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["history"].append(computed_entry)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
