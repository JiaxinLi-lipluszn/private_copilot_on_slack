# private_copilot_on_slack

A private Slack copilot for seminar participants.

This repo is for one person to run one personal seminar copilot. The copilot is
not a meeting host. It joins Slack channels, watches messages for local context,
and answers only its configured owner when that owner mentions it or sends it a
DM.

## The Setup Model

Every participant should create their own Slack app:

- one Slack app per person
- one bot display name per person
- one pair of Slack tokens per person
- one `COPILOT_OWNER_USER_ID` per person
- one local `watch/` folder per running copy

For example, Jiaxin might run `JiaxinCopilot`, Alice might run `AliceCopilot`,
and Bob might run `BobCopilot`. These are separate Slack apps, even if they all
use this same GitHub repo.

Do not reuse a claimed bot name. See [CLAIMED_NAMES.md](./CLAIMED_NAMES.md)
before choosing `COPILOT_APP_NAME` and `COPILOT_BOT_DISPLAY_NAME`.

## What It Does

- Watches messages in public/private channels where the bot has been invited.
- Stores watched channel messages locally under `watch/` for context.
- Explains the current thread when the owner mentions it inside a thread.
- Explains recent channel context when the owner mentions it at the channel top level.
- Explains a Slack message permalink or pasted text when the owner DMs it.
- Ignores mentions and DMs from non-owner users.

## Privacy Model

The copilot is owner-bound:

```bash
COPILOT_OWNER_USER_ID=U...
```

It refuses to start without a real Slack member ID. Display names such as
`LiGaZn`, `alice`, or `Bob Smith` are not enough.

The bot still watches channel messages after it is invited, because it needs
seminar context. But it only answers the configured owner. DM content is not
written to `watch/`.

## Prerequisites

- Python 3.10+
- Permission to create/install Slack apps in your workspace
- Local Codex CLI login, because this copilot uses `codex exec` as its local brain

Check Codex first:

```bash
codex exec --skip-git-repo-check "只回复 OK"
```

## 1. Clone And Install

```bash
git clone https://github.com/JiaxinLi-lipluszn/private_copilot_on_slack.git
cd private_copilot_on_slack
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Do not commit `.env`. It contains Slack tokens and your private owner binding.

## 2. Pick Your Bot Name

Choose a name that belongs to your personal copilot, such as:

```text
AliceCopilot
BobCopilot
YourNameCopilot
```

Avoid claimed or reserved names listed in
[CLAIMED_NAMES.md](./CLAIMED_NAMES.md). In particular, `JiaxinCopilot` is
already claimed and should not be reused by another participant.

Add your chosen name to `.env`:

```bash
COPILOT_APP_NAME=YourNameCopilot
COPILOT_BOT_DISPLAY_NAME=YourNameCopilot
```

## 3. Find Your Slack Member ID

In Slack:

1. Open your own profile.
2. Click **More**.
3. Click **Copy member ID**.

The value usually starts with `U` or `W`, for example:

```bash
COPILOT_OWNER_USER_ID=U0B8Q1X1SF8
```

Use the member ID, not your display name.

## 4. Generate A Slack Manifest

Load your local `.env` and generate a personalized manifest:

```bash
set -a && source .env && set +a
python3 generate_manifest.py
```

This writes `generated_manifest.yaml`. It is ignored by git because every user
should generate their own.

## 5. Create Your Slack App

1. Open [api.slack.com/apps](https://api.slack.com/apps).
2. Click **Create New App**.
3. Choose **From a manifest**.
4. Select your workspace.
5. Paste the full contents of `generated_manifest.yaml`.
6. Create the app.

## 6. Create Slack Tokens

Create the app-level Socket Mode token:

1. In the Slack app page, open **Basic Information**.
2. Under **App-Level Tokens**, click **Generate Token and Scopes**.
3. Add scope `connections:write`.
4. Copy the `xapp-...` token into `.env`:

```bash
COPILOT_SLACK_APP_TOKEN=xapp-...
```

Install the app and copy the bot token:

1. Open **Install App**.
2. Click **Install to Workspace**.
3. Copy the **Bot User OAuth Token** into `.env`:

```bash
COPILOT_SLACK_BOT_TOKEN=xoxb-...
```

Your `.env` should now contain at least:

```bash
COPILOT_SLACK_BOT_TOKEN=xoxb-...
COPILOT_SLACK_APP_TOKEN=xapp-...
COPILOT_OWNER_USER_ID=U...
COPILOT_APP_NAME=YourNameCopilot
COPILOT_BOT_DISPLAY_NAME=YourNameCopilot
```

## 7. Run Your Private Copilot

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
/invite @YourNameCopilot
```

## 8. Try It

Mention it at the channel top level:

```text
@YourNameCopilot 解释一下最近这段讨论
```

Mention it inside a thread:

```text
@YourNameCopilot 这条是什么意思?
```

Send it a DM with a Slack message permalink:

```text
https://your-workspace.slack.com/archives/...
```

Or paste text directly:

```text
请解释这段话: ...
```

## Troubleshooting

If startup says `COPILOT_OWNER_USER_ID` is missing, check that `.env` exists and
that you loaded it with:

```bash
set -a && source .env && set +a
```

If startup says the owner value looks like a display name, replace it with the
Slack member ID copied from your profile. The value should look like `U...` or
`W...`, not `LiGaZn`.

If the bot ignores you, the most common cause is that `COPILOT_OWNER_USER_ID`
does not match the Slack account sending the message.

If the bot cannot see a channel or thread, invite it to that channel and confirm
the app was installed with the manifest scopes.

If the Slack bot still shows an old name, regenerate `generated_manifest.yaml`
after editing `COPILOT_APP_NAME` / `COPILOT_BOT_DISPLAY_NAME`, then update the
Slack app manifest.

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
