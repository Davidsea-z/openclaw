#!/usr/bin/env bash
# 关闭 OpenClaw gateway、Star-Office-UI 后端、以及 OpenClaw→Star 状态推送。
# 用法：在 Star-Office-UI 目录执行 ./scripts/stop-star-and-openclaw.sh

set -euo pipefail

STAR_PORT="${STAR_BACKEND_PORT:-19000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 1. 停止 OpenClaw → Star 状态推送
if pgrep -f "office-agent-push.py" &>/dev/null; then
  pkill -f "office-agent-push.py" || true
  echo "[连接] 已停止 office-agent-push.py"
else
  echo "[连接] office-agent-push.py 未在运行"
fi

# 2. 停止 Star-Office-UI 后端（端口 19000）
if lsof -i :"$STAR_PORT" -t &>/dev/null; then
  lsof -i :"$STAR_PORT" -t | xargs kill 2>/dev/null || true
  echo "[Star] 已停止端口 $STAR_PORT 上的进程"
else
  echo "[Star] 端口 $STAR_PORT 无进程"
fi

# 3. 停止 OpenClaw gateway
if command -v openclaw &>/dev/null; then
  if openclaw gateway stop 2>/dev/null; then
    echo "[OpenClaw] gateway 已停止"
  else
    echo "[OpenClaw] openclaw gateway stop 未生效（可能由菜单栏应用托管），可手动退出 OpenClaw 应用，或执行: launchctl bootout gui/\$UID/ai.openclaw.gateway"
  fi
else
  echo "[OpenClaw] 未找到 openclaw 命令；若 gateway 由菜单栏应用运行，请从菜单栏退出 OpenClaw"
fi

echo ""
echo "已执行关闭步骤。若 Control UI 仍显示 401，请用带 token 的链接重新打开：openclaw dashboard --no-open"
