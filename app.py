"""Private seminar copilot Slack bot.

This is a separate Slack app from seminar-bot. It passively watches channels it
has joined, then explains a message/thread/content when mentioned or DMed.
"""
import os
import re
from urllib.parse import unquote

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import brain
import store

app = App(token=os.environ["COPILOT_SLACK_BOT_TOKEN"], token_verification_enabled=False)

OWNER_USER_ID = os.environ.get("COPILOT_OWNER_USER_ID", "").strip()
ALLOWED_SEMINAR_BOT_IDS = {
    item.strip()
    for item in os.environ.get("COPILOT_ALLOWED_SEMINAR_BOT_IDS", "").replace(";", ",").split(",")
    if item.strip()
}
RECENT_CONTEXT_LIMIT = int(os.environ.get("COPILOT_RECENT_CONTEXT_MESSAGES", "50") or "50")
THREAD_CONTEXT_LIMIT = int(os.environ.get("COPILOT_THREAD_CONTEXT_MESSAGES", "80") or "80")
CONTEXT_CHAR_LIMIT = int(os.environ.get("COPILOT_CONTEXT_CHARS", "16000") or "16000")

_BOT_USER_ID = ""
_NAME_CACHE = {}
_PERMALINK_RE = re.compile(r"https?://[^>\s]+/archives/([A-Z0-9]+)/p(\d{10})(\d{6})(?:[?][^>\s]*)?")
_GREET = re.compile(r"^\s*(hi|hello|hey|在吗|你在吗|help|帮助|怎么用)\s*$", re.I)
_SLACK_HUMAN_ID = re.compile(r"^[UW][A-Z0-9]+$")
_SLACK_ACTOR_ID = re.compile(r"^[ABUW][A-Z0-9]+$")


def _team_id(event: dict, body: dict = None) -> str:
    body = body or {}
    return (
        event.get("team")
        or event.get("team_id")
        or body.get("team_id")
        or (body.get("team") or {}).get("id")
        or ""
    )


def _bot_user_id(client) -> str:
    global _BOT_USER_ID
    if _BOT_USER_ID:
        return _BOT_USER_ID
    try:
        _BOT_USER_ID = client.auth_test().get("user_id", "") or ""
    except Exception:
        _BOT_USER_ID = ""
    return _BOT_USER_ID


def _display_name(client, user_id: str, event: dict = None) -> str:
    event = event or {}
    if event.get("bot_id"):
        profile = event.get("bot_profile") or {}
        return event.get("username") or profile.get("name") or profile.get("real_name") or event.get("bot_id")
    if not user_id:
        return "?"
    if user_id in _NAME_CACHE:
        return _NAME_CACHE[user_id]
    name = user_id
    try:
        user = client.users_info(user=user_id)["user"]
        profile = user.get("profile", {})
        name = profile.get("display_name") or user.get("real_name") or user.get("name") or user_id
    except Exception:
        pass
    _NAME_CACHE[user_id] = name
    return name


def _clean_slack_text(text: str, client=None) -> str:
    text = text or ""
    if client:
        bid = _bot_user_id(client)
        if bid:
            text = text.replace(f"<@{bid}>", "")
    return re.sub(r"<@[^>]+>", "", text).strip()


def _event_text(event: dict, client=None) -> str:
    parts = [_clean_slack_text(event.get("text", ""), client=client)]
    for attachment in event.get("attachments") or []:
        fallback = (attachment.get("fallback") or attachment.get("text") or "").strip()
        if fallback:
            parts.append(f"[attachment] {fallback}")
    for f in event.get("files") or []:
        title = f.get("title") or f.get("name") or f.get("id") or "file"
        mimetype = f.get("mimetype") or f.get("filetype") or ""
        parts.append(f"[file] {title}" + (f" ({mimetype})" if mimetype else ""))
    return "\n".join(p for p in parts if p).strip()


def _permalink(client, channel: str, ts: str) -> str:
    try:
        return client.chat_getPermalink(channel=channel, message_ts=ts)["permalink"]
    except Exception:
        return ""


def _is_own_message(client, event: dict) -> bool:
    return bool(event.get("user") and event.get("user") == _bot_user_id(client))


def _is_owner(event: dict) -> bool:
    return bool(OWNER_USER_ID and event.get("user") == OWNER_USER_ID)


def _event_actor_ids(event: dict) -> set[str]:
    ids = {
        event.get("user", ""),
        event.get("bot_id", ""),
        event.get("app_id", ""),
    }
    profile = event.get("bot_profile") or {}
    ids.update({
        profile.get("id", ""),
        profile.get("app_id", ""),
    })
    return {item for item in ids if item}


def _is_bot_actor(event: dict) -> bool:
    return bool(event.get("bot_id") or event.get("bot_profile") or event.get("subtype") == "bot_message")


def _is_allowed_seminar_bot(event: dict) -> bool:
    return bool(ALLOWED_SEMINAR_BOT_IDS and _event_actor_ids(event) & ALLOWED_SEMINAR_BOT_IDS)


def _allowed_request_actor(event: dict) -> tuple[bool, str]:
    if _is_owner(event):
        return True, "owner"
    if _is_allowed_seminar_bot(event):
        return True, "seminar_bot"
    if _is_bot_actor(event):
        return False, "untrusted_bot"
    return False, "non_owner"


def _parse_permalink(text: str) -> tuple[str, str]:
    text = unquote(text or "")
    match = _PERMALINK_RE.search(text)
    if not match:
        return "", ""
    return match.group(1), f"{match.group(2)}.{match.group(3)}"


def _format_slack_messages(client, messages: list[dict], *, limit_chars: int = CONTEXT_CHAR_LIMIT) -> str:
    lines = []
    for msg in messages:
        if msg.get("subtype") in {"message_deleted"}:
            continue
        who = _display_name(client, msg.get("user", ""), msg)
        text = _event_text(msg, client=client)
        if text:
            marker = " thread" if msg.get("thread_ts") else ""
            lines.append(f"[{msg.get('ts','')}{marker}] {who}: {text}")
    out = "\n".join(lines)
    if len(out) > limit_chars:
        out = out[-limit_chars:]
    return out


def _fetch_thread_context(client, channel: str, ts: str, logger) -> tuple[str, str]:
    """Return formatted Slack context and the root ts used."""
    root_ts = ts
    try:
        hist = client.conversations_history(channel=channel, latest=ts, inclusive=True, limit=1)
        messages = hist.get("messages") or []
        if messages:
            root_ts = messages[0].get("thread_ts") or messages[0].get("ts") or ts
    except Exception:
        logger.exception("failed to fetch target message history")

    try:
        replies = client.conversations_replies(channel=channel, ts=root_ts, limit=THREAD_CONTEXT_LIMIT)
        return _format_slack_messages(client, replies.get("messages") or []), root_ts
    except Exception:
        logger.exception("failed to fetch thread replies")
        return "", root_ts


def _record_channel_message(event: dict, body: dict, client, logger, *, source: str = "message_event"):
    channel = event.get("channel", "")
    ts = event.get("ts", "")
    if not channel or not ts or _is_own_message(client, event):
        return
    text = _event_text(event, client=client)
    if not text:
        return
    team_id = _team_id(event, body)
    permalink = _permalink(client, channel, ts)
    try:
        store.record_message(
            team_id=team_id,
            channel_id=channel,
            channel_type=event.get("channel_type", ""),
            ts=ts,
            thread_ts=event.get("thread_ts", ""),
            user_id=event.get("user") or event.get("bot_id", ""),
            display_name=_display_name(client, event.get("user", ""), event),
            text=text,
            is_bot=bool(event.get("bot_id")),
            permalink=permalink,
            source=source,
        )
    except Exception:
        logger.exception("failed to record watched channel message")


def _recent_context(team_id: str, channel: str, before_ts: str = "") -> str:
    rows = store.recent_messages(team_id, channel, limit=RECENT_CONTEXT_LIMIT, before_ts=before_ts)
    return store.format_messages(rows, limit_chars=CONTEXT_CHAR_LIMIT)


def _target_context_for_mention(event: dict, body: dict, client, logger) -> tuple[str, str, str]:
    request = _clean_slack_text(event.get("text", ""), client=client)
    channel = event.get("channel", "")
    team_id = _team_id(event, body)

    link_channel, link_ts = _parse_permalink(request)
    if link_channel and link_ts:
        context, _ = _fetch_thread_context(client, link_channel, link_ts, logger)
        if context:
            return request, context, f"Slack permalink {link_channel}/{link_ts}"
        row = store.find_message(team_id, link_channel, link_ts)
        return request, store.format_messages([row]) if row else "", f"local permalink lookup {link_channel}/{link_ts}"

    thread_ts = event.get("thread_ts")
    if thread_ts:
        context, root_ts = _fetch_thread_context(client, channel, thread_ts, logger)
        if not context:
            context = store.format_messages(store.thread_messages(team_id, channel, root_ts, limit=THREAD_CONTEXT_LIMIT))
        return request, context, f"current thread {channel}/{root_ts}"

    recent = _recent_context(team_id, channel, before_ts=event.get("ts", ""))
    return request, recent, f"recent channel context {channel}"


def _post_reply(client, channel: str, text: str, thread_ts: str = ""):
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    client.chat_postMessage(**payload)


def _answer_request(event: dict, body: dict, client, logger, *, is_dm: bool = False):
    text = _clean_slack_text(event.get("text", ""), client=client)
    if _GREET.match(text or ""):
        usage = (
            "我在。把我要解释的 Slack 消息链接发给我,或者在某条消息/thread 里 @我。"
            "你也可以直接把一段内容私信给我。"
        )
        _post_reply(client, event["channel"], usage, thread_ts="" if is_dm else event.get("thread_ts") or event.get("ts"))
        return

    if is_dm:
        link_channel, link_ts = _parse_permalink(text)
        if link_channel and link_ts:
            target, _ = _fetch_thread_context(client, link_channel, link_ts, logger)
            source = f"DM permalink {link_channel}/{link_ts}"
            if not target:
                _post_reply(
                    client,
                    event["channel"],
                    "我读不到这个链接。通常是因为我还没有被加入对应 channel/thread,或没有该 channel 的 history 权限。",
                )
                return
        else:
            target = text
            source = "DM pasted text"
            if len(target.strip()) < 12:
                _post_reply(client, event["channel"], "把要解释的消息链接或原文贴给我就行。")
                return
        answer = brain.explain(user_request=text, target_context=target, recent_context="", source=source)
        _post_reply(client, event["channel"], answer)
        return

    request, target, source = _target_context_for_mention(event, body, client, logger)
    recent = ""
    if not event.get("thread_ts"):
        recent = target
    answer = brain.explain(user_request=request, target_context=target, recent_context=recent, source=source)
    _post_reply(client, event["channel"], answer, thread_ts=event.get("thread_ts") or event.get("ts"))


@app.event("app_mention")
def handle_app_mention(event, body, client, logger):
    subtype = event.get("subtype", "")
    if subtype in {"message_deleted", "message_changed"} or _is_own_message(client, event):
        return
    _record_channel_message(event, body, client, logger, source="app_mention")
    allowed, reason = _allowed_request_actor(event)
    if not allowed:
        logger.info(
            "ignore app mention reason=%s actor_ids=%s",
            reason,
            ",".join(sorted(_event_actor_ids(event))),
        )
        return
    _answer_request(event, body, client, logger)


@app.event("message")
def handle_message(event, body, client, logger):
    subtype = event.get("subtype", "")
    if subtype in {"message_deleted", "message_changed", "channel_join", "channel_leave"}:
        return
    if event.get("channel_type") == "im":
        if _is_own_message(client, event):
            return
        allowed, reason = _allowed_request_actor(event)
        if not allowed:
            logger.info(
                "ignore DM reason=%s actor_ids=%s",
                reason,
                ",".join(sorted(_event_actor_ids(event))),
            )
            return
        _answer_request(event, body, client, logger, is_dm=True)
        return
    _record_channel_message(event, body, client, logger)


if __name__ == "__main__":
    if not OWNER_USER_ID:
        raise RuntimeError("请先设置 COPILOT_OWNER_USER_ID=<你的 Slack member ID>,否则私人 copilot 无法确定服务对象。")
    if not _SLACK_HUMAN_ID.fullmatch(OWNER_USER_ID):
        raise RuntimeError(
            "COPILOT_OWNER_USER_ID 必须是 Slack member ID,不是显示名。"
            "请在 Slack 个人资料里点 More -> Copy member ID,填入类似 U0B8Q1X1SF8 的值。"
        )
    invalid_seminar_bot_ids = [item for item in sorted(ALLOWED_SEMINAR_BOT_IDS) if not _SLACK_ACTOR_ID.fullmatch(item)]
    if invalid_seminar_bot_ids:
        raise RuntimeError(
            "COPILOT_ALLOWED_SEMINAR_BOT_IDS 只能包含 Slack ID,不是显示名。"
            "可填 seminar bot 的 bot user ID(U.../W...),bot ID(B...),或 app ID(A...)。"
            f" 当前无法识别: {', '.join(invalid_seminar_bot_ids)}"
        )
    print("Private Seminar Copilot 已启动(Socket Mode)。Ctrl-C 退出。", flush=True)
    SocketModeHandler(app, os.environ["COPILOT_SLACK_APP_TOKEN"]).start()
