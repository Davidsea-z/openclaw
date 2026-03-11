#!/usr/bin/env python3
"""将 OpenClaw 的 session transcript 日志同步到 Star-Office-UI 的「昨日小记」来源目录。

读取 ~/.openclaw/agents/<agentId>/sessions/*.jsonl 中的对话记录，按日期汇总为
memory/YYYY-MM-DD.md，Star-Office-UI 的 GET /yesterday-memo 会从该目录读取并展示。

用法:
  python3 scripts/sync-openclaw-logs-to-memo.py [--date YYYY-MM-DD] [--dry-run]
  # 默认同步「昨天」的日志；--date 可指定日期；--dry-run 只打印不写入。

环境变量:
  OPENCLAW_HOME     OpenClaw 数据目录，默认 ~/.openclaw
  MEMORY_DIR        输出的 memory 目录，默认 Star-Office-UI 上一级目录下的 memory
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# OpenClaw 默认数据目录（与 office-agent-push 一致）
OPENCLAW_HOME = os.environ.get("OPENCLAW_HOME") or os.path.join(
    os.path.expanduser("~"), ".openclaw"
)
SCRIPT_DIR = Path(__file__).resolve().parent
STAR_OFFICE_ROOT = SCRIPT_DIR.parent
# Star-Office-UI 的「昨日小记」来自上一级目录的 memory/
DEFAULT_MEMORY_DIR = STAR_OFFICE_ROOT.parent / "memory"


def _sanitize(text: str) -> str:
    """简单脱敏，避免隐私出现在小记中。"""
    if not text:
        return ""
    text = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[邮箱]", text)
    text = re.sub(r"1[3-9]\d{9}", "[手机号]", text)
    text = re.sub(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "[IP]", text)
    return text


def _extract_text_from_content(content: object) -> str:
    """从 message content 中取出纯文本（支持 content 为 string 或 list of {type,text}）。"""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t.strip())
        return " ".join(parts).strip()
    return ""


def _parse_ts(ts: object) -> datetime | None:
    """解析时间戳（毫秒或 ISO 字符串）。"""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts / 1000.0 if ts > 1e12 else ts, tz=timezone.utc)
        except Exception:
            return None
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _collect_messages_for_date(
    openclaw_home: str,
    target_date: str,
) -> list[tuple[datetime, str, str, str, str]]:
    """收集 target_date 当天的所有会话消息。(ts, role, text, agent_id, session_id)"""
    agents_dir = Path(openclaw_home) / "agents"
    if not agents_dir.is_dir():
        return []

    out: list[tuple[datetime, str, str, str, str]] = []
    try:
        date_low = datetime.fromisoformat(target_date + "T00:00:00+00:00")
        date_high = date_low + timedelta(days=1)
    except Exception:
        return out

    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue
        agent_id = agent_dir.name
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.is_dir():
            continue
        for jsonl_file in sessions_dir.glob("*.jsonl"):
            session_id = jsonl_file.stem
            try:
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if obj.get("type") == "session":
                            continue
                        role = obj.get("role")
                        if role not in ("user", "assistant"):
                            continue
                        ts = _parse_ts(obj.get("timestamp"))
                        if ts is None:
                            continue
                        if not (date_low <= ts < date_high):
                            continue
                        content = obj.get("content")
                        text = _extract_text_from_content(content)
                        if not text:
                            continue
                        if len(text) > 500:
                            text = text[:500] + "..."
                        out.append((ts, role, text, agent_id, session_id))
            except OSError:
                continue
    out.sort(key=lambda x: x[0])
    return out


def _build_markdown(
    rows: list[tuple[datetime, str, str, str, str]],
    target_date: str,
) -> str:
    """将收集到的消息写成 memo 用的 Markdown（- 要点格式，便于 memo_utils 提取）。"""
    lines = [f"# OpenClaw 日志 {target_date}", ""]
    if not rows:
        lines.extend(["- 当日无会话记录", ""])
        return "\n".join(lines)

    for _ts, role, text, _agent_id, _session_id in rows[:50]:  # 最多 50 条
        text = _sanitize(text)
        if not text:
            continue
        label = "用户" if role == "user" else "助手"
        # 单行过长时截断，保留 - 要点格式
        if len(text) > 80:
            text = text[:77] + "..."
        lines.append(f"- [{label}] {text}")
    if len(rows) > 50:
        lines.append(f"- （共 {len(rows)} 条，仅展示前 50 条）")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="将 OpenClaw transcript 同步到 Star-Office-UI 昨日小记来源目录"
    )
    parser.add_argument(
        "--date",
        default=(datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d"),
        help="目标日期 YYYY-MM-DD，默认昨天",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入文件")
    args = parser.parse_args()

    memory_dir = os.environ.get("MEMORY_DIR", str(DEFAULT_MEMORY_DIR))
    memory_dir = Path(memory_dir)
    target_date = args.date

    rows = _collect_messages_for_date(OPENCLAW_HOME, target_date)
    md = _build_markdown(rows, target_date)

    out_file = memory_dir / f"{target_date}.md"
    if args.dry_run:
        print(f"[dry-run] 会写入 {out_file}，共 {len(rows)} 条消息")
        print(md[:1500] + ("..." if len(md) > 1500 else ""))
        return 0

    memory_dir.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"已同步 {len(rows)} 条消息到 {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
