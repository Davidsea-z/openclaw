#!/usr/bin/env python3
"""
Star Office UI - 多会话状态推送器

扫描 state.json 和 state-<session>.json，为每个活跃会话在 Star 办公室
维护一个独立角色（join + 持续 push）。适合 OpenClaw 同时处理多个会话
（Discord、Telegram、WhatsApp、主窗口等）的场景。

用法:
  python3 multi-push.py

环境变量:
  OFFICE_URL          Star 办公室地址，默认 http://127.0.0.1:19000
  OFFICE_JOIN_KEY     join key（所有会话共用，或在 state-*.json 内用 joinKey 字段单独指定）
  OFFICE_AGENT_PREFIX 角色名前缀，默认 "OpenClaw"
                      → 主会话显示为 "OpenClaw"，其他会话显示为 "OpenClaw-discord" 等
  OFFICE_PUSH_INTERVAL  推送间隔秒数，默认 15
  OFFICE_STALE_TTL    状态过期秒数，超过此时间自动切 idle，默认 600
  OFFICE_VERBOSE      设为 1 开启详细日志

多会话 state 文件命名规则:
  state.json              → 主会话（角色名: <PREFIX>）
  state-discord.json      → Discord 会话（角色名: <PREFIX>-discord）
  state-telegram.json     → Telegram 会话
  state-whatsapp.json     → WhatsApp 会话
  state-<任意名>.json     → 自定义会话
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("缺少 requests，请执行: pip install requests")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OFFICE_URL = os.environ.get("OFFICE_URL", "http://127.0.0.1:19000")
DEFAULT_JOIN_KEY = os.environ.get("OFFICE_JOIN_KEY", "ocj_example_team_01")
AGENT_PREFIX = os.environ.get("OFFICE_AGENT_PREFIX", "OpenClaw")
PUSH_INTERVAL = int(os.environ.get("OFFICE_PUSH_INTERVAL", "15"))
STALE_TTL = int(os.environ.get("OFFICE_STALE_TTL", "600"))
VERBOSE = os.environ.get("OFFICE_VERBOSE", "0").strip().lower() in {"1", "true", "yes"}

JOIN_ENDPOINT = "/join-agent"
PUSH_ENDPOINT = "/agent-push"

VALID_STATES = frozenset({"idle", "writing", "receiving", "replying", "researching", "executing", "syncing", "error"})
WORKING_STATES = frozenset({"writing", "receiving", "replying", "researching", "executing", "syncing"})

# 每个会话的 join 状态缓存（内存，重启后重新 join）
# key: session_key (""=main, "discord"=discord session, ...)
# value: {"agentId": str, "joined": bool}
_session_registry: dict[str, dict] = {}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None


def _state_age_seconds(data: dict) -> float | None:
    dt = _parse_ts(data.get("updated_at"))
    if dt is None:
        return None
    if dt.tzinfo is None:
        now = datetime.now()
    else:
        now = datetime.now(timezone.utc).astimezone(dt.tzinfo)
    return (now - dt).total_seconds()


def discover_state_files() -> list[tuple[str, str]]:
    """发现所有 channel 会话的 state-*.json 文件，返回 [(session_key, filepath), ...]。

    注意：state.json（主会话）故意跳过。
    Star-Office-UI 后端直接通过 /status 读取 state.json 来驱动 Star 角色，
    不需要通过 join-agent 推送——否则 Star 和访客 "OpenClaw" 会显示同一份状态。

    只有 state-<channel>.json（如 state-whatsapp.json / state-imessage.json）
    才作为访客 agent 出现在办公室。
    """
    result: list[tuple[str, str]] = []
    for fp in sorted(glob.glob(os.path.join(SCRIPT_DIR, "state-*.json"))):
        fname = os.path.basename(fp)
        m = re.match(r"^state-(.+)\.json$", fname)
        if m:
            session_key = m.group(1)
            # 跳过内部缓存文件
            if session_key in ("sessions", "sample"):
                continue
            result.append((session_key, fp))
    return result


def agent_name(session_key: str) -> str:
    if not session_key:
        return AGENT_PREFIX
    return f"{AGENT_PREFIX}-{session_key}"


def read_state(filepath: str, session_key: str) -> dict:
    """读取状态文件，做校验和过期处理。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"state": "idle", "detail": "状态文件读取失败"}

    state = str(data.get("state", "idle")).strip().lower()
    if state not in VALID_STATES:
        state = "idle"
    detail = str(data.get("detail", "")).strip()

    # 状态文件长时间未更新 → 自动 idle（避免"假工作中"）
    age = _state_age_seconds(data)
    if age is not None and age > STALE_TTL and state in WORKING_STATES:
        state = "idle"
        detail = f"超过 {STALE_TTL}s 未更新，自动回待命"

    return {"state": state, "detail": detail, "joinKey": data.get("joinKey")}


def do_join(session_key: str, join_key: str) -> str | None:
    """加入办公室，返回 agentId，失败返回 None。"""
    name = agent_name(session_key)
    try:
        resp = requests.post(
            f"{OFFICE_URL}{JOIN_ENDPOINT}",
            json={"name": name, "joinKey": join_key, "state": "idle", "detail": "刚加入"},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            agent_id = data["agentId"]
            log(f"✅ [{name}] 加入成功，agentId={agent_id}")
            return agent_id
        log(f"❌ [{name}] 加入失败: {data}")
    except Exception as e:
        log(f"⚠️  [{name}] 加入异常: {e}")
    return None


def do_push(session_key: str, agent_id: str, join_key: str, state: str, detail: str) -> bool:
    """推送状态，返回是否成功。403/404 表示已被移出（调用方应清除 agentId）。"""
    name = agent_name(session_key)
    try:
        resp = requests.post(
            f"{OFFICE_URL}{PUSH_ENDPOINT}",
            json={"agentId": agent_id, "joinKey": join_key, "state": state, "detail": detail, "name": name},
            timeout=10,
        )
        if resp.status_code in (403, 404):
            log(f"⚠️  [{name}] 已被移出房间（{resp.status_code}），下次循环重新加入")
            return False
        data = resp.json()
        if data.get("ok"):
            if VERBOSE:
                log(f"  [{name}] 推送 {state} → area={data.get('area')}")
            return True
        log(f"⚠️  [{name}] 推送失败: {data}")
    except Exception as e:
        log(f"⚠️  [{name}] 推送异常: {e}")
    return False


def sync_session(session_key: str, filepath: str) -> None:
    """单次同步一个会话：读状态 → join（如需）→ push。"""
    state_data = read_state(filepath, session_key)
    join_key = state_data.get("joinKey") or DEFAULT_JOIN_KEY
    state = state_data["state"]
    detail = state_data["detail"]

    reg = _session_registry.setdefault(session_key, {"agentId": None, "joined": False})

    # 若未 join 或 agentId 丢失，先 join
    if not reg.get("agentId"):
        agent_id = do_join(session_key, join_key)
        if not agent_id:
            return
        reg["agentId"] = agent_id
        reg["joined"] = True

    ok = do_push(session_key, reg["agentId"], join_key, state, detail)
    if not ok:
        # push 失败（被移出等），清除 agentId，下次重新 join
        reg["agentId"] = None
        reg["joined"] = False


def do_leave(session_key: str, agent_id: str, join_key: str) -> None:
    """state 文件消失时主动离开，避免访客残留在看板上。"""
    name = agent_name(session_key)
    try:
        resp = requests.post(
            f"{OFFICE_URL}/leave-agent",
            json={"agentId": agent_id, "joinKey": join_key},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            log(f"🚪 [{name}] state 文件消失，已自动离开")
        # 404 = 已不在房间，也算正常
    except Exception as e:
        log(f"⚠️  [{name}] 自动离开失败: {e}")


def main() -> None:
    log(f"🚀 multi-push 启动，前缀={AGENT_PREFIX}，间隔={PUSH_INTERVAL}s，TTL={STALE_TTL}s")
    log(f"   办公室地址: {OFFICE_URL}")
    log(f"   状态文件目录: {SCRIPT_DIR}")
    log(f"   扫描规则: state-<channel>.json（state.json 由 Star 直接读取，不作访客）")
    log("")

    if not DEFAULT_JOIN_KEY:
        log("❌ 请设置环境变量 OFFICE_JOIN_KEY（或在 state-*.json 中填 joinKey 字段）")
        sys.exit(1)

    try:
        while True:
            sessions = discover_state_files()
            active_keys = {s[0] for s in sessions}

            # state 文件消失的会话 → 主动 leave，避免访客残留在看板上
            stale = [k for k in list(_session_registry.keys()) if k not in active_keys]
            for sk in stale:
                reg = _session_registry.pop(sk)
                if reg.get("agentId") and reg.get("joined"):
                    do_leave(sk, reg["agentId"], reg.get("joinKey") or DEFAULT_JOIN_KEY)

            if not sessions:
                log("⚠️  未找到任何 state-*.json 文件，等待中...")
            else:
                if VERBOSE:
                    log(f"发现 {len(sessions)} 个会话: {[s[0] for s in sessions]}")
                for session_key, filepath in sessions:
                    sync_session(session_key, filepath)

            time.sleep(PUSH_INTERVAL)
    except KeyboardInterrupt:
        log("\n👋 multi-push 已停止")
        sys.exit(0)


if __name__ == "__main__":
    main()
