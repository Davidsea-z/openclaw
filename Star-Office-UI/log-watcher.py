#!/usr/bin/env python3
"""
Star Office UI - Gateway 日志监听器

监听 /tmp/openclaw-gateway.log，检测 WhatsApp/iMessage 消息事件，
直接通过 HTTP 更新 Star 办公室的访客状态。

不依赖 OpenClaw 内部 hook 机制，稳定可靠。

用法:
  python3 log-watcher.py
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("缺少 requests，请执行: pip install requests")
    raise SystemExit(1)

GATEWAY_LOG = os.environ.get("GATEWAY_LOG", "/tmp/openclaw-gateway.log")
OFFICE_URL = os.environ.get("OFFICE_URL", "http://127.0.0.1:19000")
JOIN_KEY = os.environ.get("OFFICE_JOIN_KEY", "ocj_example_team_01")
AGENT_PREFIX = os.environ.get("OFFICE_AGENT_PREFIX", "OpenClaw")
# 收到消息后多少秒没有新消息，自动回 idle
IDLE_AFTER = int(os.environ.get("OFFICE_IDLE_AFTER", "60"))

# 匹配 gateway 日志的 channel 事件
# e.g. "[whatsapp] Inbound message" / "[imessage] Inbound message"
INBOUND_RE = re.compile(r"\[(whatsapp|imessage)\].*(?:Inbound message|inbound)", re.IGNORECASE)
SENT_RE = re.compile(r"\[(whatsapp|imessage)\].*(?:Auto-replied|Sent message|delivered reply|Sent reaction)", re.IGNORECASE)

# 每个 channel 的 agent 状态缓存
_agents: dict[str, dict] = {}  # channel -> {"agentId": str, "lastActivity": float}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def agent_name(channel: str) -> str:
    return f"{AGENT_PREFIX}-{channel}"


def ensure_joined(channel: str) -> str | None:
    """确保 agent 已加入办公室，返回 agentId。"""
    entry = _agents.get(channel, {})
    if entry.get("agentId"):
        return entry["agentId"]

    name = agent_name(channel)
    try:
        resp = requests.post(
            f"{OFFICE_URL}/join-agent",
            json={"name": name, "joinKey": JOIN_KEY, "state": "idle", "detail": "待命中"},
            timeout=8,
        )
        data = resp.json()
        if data.get("ok"):
            agent_id = data["agentId"]
            _agents[channel] = {"agentId": agent_id, "lastActivity": time.time()}
            log(f"✅ [{name}] 加入成功 agentId={agent_id}")
            return agent_id
        log(f"⚠️  [{name}] 加入失败: {data}")
    except Exception as e:
        log(f"⚠️  [{name}] 加入异常: {e}")
    return None


def push(channel: str, state: str, detail: str) -> None:
    """推送状态，失败时清除 agentId 以便下次重新 join。"""
    agent_id = ensure_joined(channel)
    if not agent_id:
        return
    name = agent_name(channel)
    try:
        resp = requests.post(
            f"{OFFICE_URL}/agent-push",
            json={"agentId": agent_id, "joinKey": JOIN_KEY, "state": state, "detail": detail, "name": name},
            timeout=8,
        )
        data = resp.json()
        if data.get("ok"):
            log(f"→ [{name}] {state}  {detail}")
            _agents[channel]["lastActivity"] = time.time()
        elif resp.status_code in (403, 404):
            log(f"⚠️  [{name}] 被移出，下次重新 join")
            _agents[channel]["agentId"] = None
    except Exception as e:
        log(f"⚠️  [{name}] push 异常: {e}")


def check_idle_timeout() -> None:
    """超过 IDLE_AFTER 秒没有活动的 channel → 更新为 idle。"""
    now = time.time()
    for channel, entry in list(_agents.items()):
        if not entry.get("agentId"):
            continue
        last = entry.get("lastActivity", now)
        if now - last > IDLE_AFTER:
            push(channel, "idle", f"等待 {channel} 消息")
            entry["lastActivity"] = now  # 重置避免重复推


def follow_log(filepath: str):
    """tail -f 风格跟踪日志文件，处理文件轮转。"""
    inode = None
    fp = None

    while True:
        # 文件不存在时等待
        if not os.path.exists(filepath):
            time.sleep(2)
            continue

        current_inode = os.stat(filepath).st_ino
        if inode != current_inode:
            # 文件新建或轮转
            if fp:
                fp.close()
            fp = open(filepath, "r", encoding="utf-8", errors="replace")
            fp.seek(0, 2)  # 从末尾开始，只看新行
            inode = current_inode
            log(f"📖 监听日志: {filepath}")

        line = fp.readline()  # type: ignore[union-attr]
        if line:
            yield line.rstrip()
        else:
            check_idle_timeout()
            time.sleep(0.3)


def main() -> None:
    log(f"🚀 log-watcher 启动")
    log(f"   监听: {GATEWAY_LOG}")
    log(f"   办公室: {OFFICE_URL}")
    log(f"   前缀: {AGENT_PREFIX}")
    log("")

    for line in follow_log(GATEWAY_LOG):
        m_in = INBOUND_RE.search(line)
        if m_in:
            channel = m_in.group(1).lower()
            # researching = 正在读消息/思考，会移动到 research 区域
            push(channel, "researching", f"收到 {channel} 消息")
            continue

        m_sent = SENT_RE.search(line)
        if m_sent:
            channel = m_sent.group(1).lower()
            # writing = 正在回复，会移动到 writing 桌
            push(channel, "writing", f"正在回复 {channel}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n👋 log-watcher 已停止")
