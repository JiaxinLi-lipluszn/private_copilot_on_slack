"""Local watched-channel log for the private seminar copilot.

This is intentionally not a shared canon. It only gives the private copilot
enough recent Slack context to answer when its owner mentions or DMs it.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("COPILOT_DATA_DIR", "./watch")).resolve()
MAX_SEEN = int(os.environ.get("COPILOT_MAX_SEEN_KEYS", "10000") or "10000")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(s: str) -> str:
    s = (s or "unknown").strip()
    s = re.sub(r"[^A-Za-z0-9_.-]+", "-", s)
    return s.strip("-")[:160] or "unknown"


def _channel_dir(team_id: str, channel_id: str) -> Path:
    return DATA_DIR / "channels" / f"{_slug(team_id)}-{_slug(channel_id)}"


def _messages_path(team_id: str, channel_id: str) -> Path:
    return _channel_dir(team_id, channel_id) / "messages.jsonl"


def _seen_path(team_id: str, channel_id: str) -> Path:
    return _channel_dir(team_id, channel_id) / ".seen.json"


def _append_jsonl(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _load_seen(team_id: str, channel_id: str) -> set:
    try:
        return set(json.loads(_seen_path(team_id, channel_id).read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_seen(team_id: str, channel_id: str, seen: set):
    path = _seen_path(team_id, channel_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen)[-MAX_SEEN:], ensure_ascii=False), encoding="utf-8")


def _ts_float(ts: str) -> float:
    try:
        return float(ts or 0)
    except Exception:
        return 0.0


def record_message(
    *,
    team_id: str,
    channel_id: str,
    channel_type: str = "",
    ts: str,
    thread_ts: str = "",
    user_id: str = "",
    display_name: str = "",
    text: str = "",
    is_bot: bool = False,
    permalink: str = "",
    source: str = "slack_event",
) -> dict:
    """Record one channel message if it has not been recorded before."""
    text = (text or "").strip()
    if not text or not channel_id or not ts:
        return {}
    seen = _load_seen(team_id, channel_id)
    key = f"{channel_id}:{ts}"
    if key in seen:
        return {}
    row = {
        "schema_version": 1,
        "team_id": team_id,
        "channel_id": channel_id,
        "channel_type": channel_type,
        "ts": ts,
        "thread_ts": thread_ts,
        "user_id": user_id,
        "display_name": display_name or user_id,
        "text": text,
        "is_bot": bool(is_bot),
        "permalink": permalink,
        "source": source,
        "created_at": _now(),
    }
    _append_jsonl(_messages_path(team_id, channel_id), row)
    seen.add(key)
    _save_seen(team_id, channel_id, seen)
    return row


def _read_messages(team_id: str, channel_id: str) -> list[dict]:
    path = _messages_path(team_id, channel_id)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def recent_messages(team_id: str, channel_id: str, *, limit: int = 50, before_ts: str = "") -> list[dict]:
    rows = _read_messages(team_id, channel_id)
    if before_ts:
        cutoff = _ts_float(before_ts)
        rows = [r for r in rows if _ts_float(r.get("ts", "")) < cutoff]
    rows = sorted(rows, key=lambda r: _ts_float(r.get("ts", "")))
    return rows[-limit:]


def thread_messages(team_id: str, channel_id: str, thread_ts: str, *, limit: int = 80) -> list[dict]:
    rows = _read_messages(team_id, channel_id)
    rows = [
        r for r in rows
        if r.get("ts") == thread_ts or r.get("thread_ts") == thread_ts
    ]
    rows = sorted(rows, key=lambda r: _ts_float(r.get("ts", "")))
    return rows[-limit:]


def find_message(team_id: str, channel_id: str, ts: str) -> dict:
    for row in _read_messages(team_id, channel_id):
        if row.get("ts") == ts:
            return row
    return {}


def format_messages(rows: list[dict], *, limit_chars: int = 12000) -> str:
    lines = []
    for row in rows:
        who = row.get("display_name") or row.get("user_id") or "?"
        marker = " thread" if row.get("thread_ts") else ""
        text = re.sub(r"\s+", " ", row.get("text", "")).strip()
        if text:
            lines.append(f"[{row.get('ts','')}{marker}] {who}: {text}")
    out = "\n".join(lines)
    if len(out) > limit_chars:
        out = out[-limit_chars:]
    return out
