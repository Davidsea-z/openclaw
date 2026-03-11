#!/usr/bin/env python3
"""Update Star Office UI state (for testing or agent-driven sync).

For automatic state sync from OpenClaw: add a rule in your agent SOUL.md or AGENTS.md:
  Before starting a task: run `python3 set_state.py writing "doing XYZ"`.
  After finishing: run `python3 set_state.py idle "ready"`.

Multi-session support (each session appears as a separate character in Star Office):
  python3 set_state.py writing "coding" --session discord
  python3 set_state.py idle "done" --session telegram
  → writes state-discord.json / state-telegram.json
  → multi-push.py picks these up and creates one Star Office agent per session

The main session (no --session flag) uses state.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

VALID_STATES = [
    "idle",
    "writing",
    "receiving",
    "replying",
    "researching",
    "executing",
    "syncing",
    "error",
]

# 会话名只允许字母数字和连字符，防止路径注入
_SESSION_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


def resolve_state_file(session: Optional[str]) -> str:
    """根据 session 名称解析状态文件路径。"""
    env_override = os.environ.get("STAR_OFFICE_STATE_FILE")
    if env_override and not session:
        return env_override
    if session:
        return os.path.join(SCRIPT_DIR, f"state-{session}.json")
    return os.path.join(SCRIPT_DIR, "state.json")


def load_state(state_file: str) -> dict:
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "state": "idle",
        "detail": "待命中...",
        "progress": 0,
        "updated_at": datetime.now().isoformat(),
    }


def save_state(state_file: str, data: dict) -> None:
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="更新 Star Office UI 状态（支持多会话）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
状态选项: {', '.join(VALID_STATES)}

用法示例:
  python set_state.py writing "正在写代码"
  python set_state.py idle "任务完成"
  python set_state.py researching "调研中" --session discord
  python set_state.py executing "执行命令" --session telegram
  python set_state.py error "发现问题" --session whatsapp

多会话说明:
  --session 指定会话名时，写入 state-<session>.json
  配合 multi-push.py 使用，每个会话在 Star 办公室显示为独立角色。
""",
    )
    parser.add_argument("state", choices=VALID_STATES, help="状态")
    parser.add_argument("detail", nargs="?", default="", help="状态描述（可选）")
    parser.add_argument(
        "--session", "-s",
        default=None,
        help="会话标识（例如 discord/telegram/main），留空表示主会话",
    )
    args = parser.parse_args()

    if args.session and not _SESSION_RE.match(args.session):
        print(f"错误: --session 只允许字母/数字/连字符，长度 1-32，当前值: {args.session!r}")
        sys.exit(1)

    state_file = resolve_state_file(args.session)
    data = load_state(state_file)
    data["state"] = args.state
    data["detail"] = args.detail
    data["updated_at"] = datetime.now().isoformat()
    if args.session:
        data["session"] = args.session

    save_state(state_file, data)

    label = f"[{args.session}] " if args.session else ""
    print(f"状态已更新: {label}{args.state} - {args.detail}")
    if args.session:
        print(f"  → {state_file}")


if __name__ == "__main__":
    main()
