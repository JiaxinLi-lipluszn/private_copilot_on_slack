# private_copilot_on_slack

A private Slack copilot for seminar participants.

This is not a meeting host. It passively watches channels it has joined, then answers only its configured owner when the owner mentions it in a channel/thread or DMs it. It is meant to help one participant understand seminar messages, threads, and pasted content.

## What It Does

- Watches messages in public/private channels where the bot has been invited.
- Stores watched channel messages locally under `watch/` for context.
- Explains the current thread when the owner mentions it inside a thread.
- Explains recent channel context when the owner mentions it at the channel top level.
- Explains a Slack message permalink or pasted text when the owner DMs it.
- Ignores mentions and DMs from non-owner users.

## Privacy Model

Each copilot is owner-bound:

```bash
COPILOT_OWNER_USER_ID=U...
```

The bot will refuse to start without this value. It still watches channel messages for context, but only answers the configured owner. DM content is not written to `watch/`.

Recommended deployment: one Slack app/token pair per person, with a unique bot display name such as `JiaxinCopilot`, `AliceCopilot`, or `BobCopilot`.

## Prerequisites

- Python 3.10+
- Slack workspace permission to create/install apps
- Local Codex CLI login, because the copilot uses `codex exec` as its local brain

Check Codex:

```bash
codex exec --skip-git-repo-check "只回复 OK"
```

## Install

Clone the repo:

```bash
git clone https://github.com/JiaxinLi-lipluszn/private_copilot_on_slack.git
cd private_copilot_on_slack
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create local config:

```bash
cp .env.example .env
```

Do not commit `.env`; it contains Slack tokens.

## Create Your Slack App

Pick a unique name for this person's bot:

```bash
export COPILOT_APP_NAME=JiaxinCopilot
export COPILOT_BOT_DISPLAY_NAME=JiaxinCopilot
python3 generate_manifest.py
```

This creates `generated_manifest.yaml`.

Then:

1. Open https://api.slack.com/apps.
2. Click **Create New App**.
3. Choose **From a manifest**.
4. Select your workspace.
5. Paste the full contents of `generated_manifest.yaml`.
6. Create the app.

## Slack Tokens

In the Slack app:

1. Go to **Basic Information**.
2. Under **App-Level Tokens**, click **Generate Token and Scopes**.
3. Add scope `connections:write`.
4. Copy the `xapp-...` token into `.env` as:

```bash
COPILOT_SLACK_APP_TOKEN=xapp-...
```

Then:

1. Go to **Install App**.
2. Click **Install to Workspace**.
3. Copy the **Bot User OAuth Token** `xoxb-...` into `.env`:

```bash
COPILOT_SLACK_BOT_TOKEN=xoxb-...
```

## Bind the Owner

In Slack, open the owner's profile, click **More**, then **Copy member ID**.
Use the copied Slack member ID, not the display name. It usually looks like
`U0B8Q1X1SF8` or `W...`; values such as `LiGaZn` are display names and will not
match Slack events.

Add it to `.env`:

```bash
COPILOT_OWNER_USER_ID=U0B8Q1X1SF8
COPILOT_APP_NAME=JiaxinCopilot
COPILOT_BOT_DISPLAY_NAME=JiaxinCopilot
```

## Run

```bash
set -a && source .env && set +a
python app.py
```

You should see:

```text
Private Seminar Copilot 已启动(Socket Mode)。Ctrl-C 退出。
```

Invite it to a Slack channel:

```text
/invite @JiaxinCopilot
```

## Try It

At the channel top level:

```text
@JiaxinCopilot 解释一下最近这段讨论
```

Inside a thread:

```text
@JiaxinCopilot 这条是什么意思?
```

In a DM:

```text
<paste a Slack message permalink>
```

or:

```text
请解释这段话: ...
```

## Notes

- It only sees messages after it has joined a channel; it does not backfill history.
- It can read only channels it has been invited to and has permission to access.
- It answers only `COPILOT_OWNER_USER_ID`.
- It uses local `codex exec`; it does not require an OpenAI/Anthropic API key.
- `watch/`, `.env`, `.venv/`, and generated manifests are ignored by git.

## Files

- `app.py`: Slack Socket Mode app.
- `brain.py`: local `codex exec` explanation brain.
- `store.py`: local watched-channel message log.
- `generate_manifest.py`: per-owner Slack manifest generator.
- `slack_manifest.yaml`: static template/example manifest.
- `prompts/explain.md`: explanation prompt.
