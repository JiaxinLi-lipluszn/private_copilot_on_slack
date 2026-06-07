"""Generate a per-owner Slack manifest for the private copilot."""
import os
import re
from pathlib import Path


def _clean_name(name: str, fallback: str) -> str:
    name = (name or fallback).strip()
    name = re.sub(r"\s+", " ", name)
    return name[:35] or fallback


def main():
    app_name = _clean_name(os.environ.get("COPILOT_APP_NAME"), "PersonalCopilot")
    bot_name = _clean_name(os.environ.get("COPILOT_BOT_DISPLAY_NAME"), app_name)
    out = Path(os.environ.get("COPILOT_MANIFEST_OUT", "generated_manifest.yaml"))
    manifest = f"""display_information:
  name: {app_name}
  description: 私人研讨参与助手 — 解释 channel/thread 里的内容
features:
  bot_user:
    display_name: {bot_name}
    always_online: true
  app_home:
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false
oauth_config:
  scopes:
    bot:
      - app_mentions:read
      - chat:write
      - channels:read
      - channels:history
      - groups:read
      - groups:history
      - im:history
      - im:write
      - users:read
settings:
  event_subscriptions:
    bot_events:
      - app_mention
      - message.channels
      - message.groups
      - message.im
  socket_mode_enabled: true
  org_deploy_enabled: false
"""
    out.write_text(manifest, encoding="utf-8")
    print(out.resolve())


if __name__ == "__main__":
    main()
