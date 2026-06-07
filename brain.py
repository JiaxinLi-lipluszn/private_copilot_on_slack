"""Private copilot brain: delegate explanation to local `codex exec`."""
import os
import subprocess
import tempfile
from pathlib import Path

CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
CODEX_EXTRA_ARGS = os.environ.get("CODEX_EXTRA_ARGS", "--skip-git-repo-check")
COPILOT_MODEL = os.environ.get("COPILOT_MODEL", os.environ.get("BRAIN_MODEL", "")).strip()

PROMPTS = Path(__file__).parent / "prompts"


def _load(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def _run(prompt: str, timeout: int = 240) -> str:
    workdir = tempfile.mkdtemp(prefix="seminar-copilot-")
    cmd = [CODEX_BIN, "exec"]
    if CODEX_EXTRA_ARGS:
        cmd += CODEX_EXTRA_ARGS.split()
    if COPILOT_MODEL:
        cmd += ["-m", COPILOT_MODEL]
    cmd += ["-C", workdir, prompt]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return "我这边找不到 codex 可执行文件。请确认 `CODEX_BIN` 配置正确。"
    except subprocess.TimeoutExpired:
        return "我这边解释超时了。可以把目标消息缩短一点再问我。"
    return (res.stdout or "").strip()


def explain(*, user_request: str, target_context: str, recent_context: str = "", source: str = "") -> str:
    prompt = (
        _load("explain.md")
        .replace("{{USER_REQUEST}}", user_request or "请解释这条内容。")
        .replace("{{TARGET_CONTEXT}}", target_context or "(没有明确目标内容)")
        .replace("{{RECENT_CONTEXT}}", recent_context or "(无)")
        .replace("{{SOURCE}}", source or "(未指定)")
    )
    return _run(prompt) or "我没有生成出解释。可以把要解释的消息链接或原文贴给我。"
