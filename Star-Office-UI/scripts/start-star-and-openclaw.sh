#!/usr/bin/env bash
# 同步启动 Star-Office-UI 与 OpenClaw，并连接两者（OpenClaw 作为访客出现在 Star 办公室）。
# 用法：在项目根目录执行 ./scripts/start-star-and-openclaw.sh
# 若端口已被占用，会跳过对应服务并提示。

set -euo pipefail

STAR_PORT="${STAR_BACKEND_PORT:-19000}"
OPENCLAW_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_REPO="${OPENCLAW_REPO:-$(dirname "$ROOT")}"
OFFICE_JOIN_KEY="${OFFICE_JOIN_KEY:-ocj_example_team_01}"
OFFICE_AGENT_NAME="${OFFICE_AGENT_NAME:-OpenClaw}"

# 若 join-keys.json 无可用 key，从 sample 恢复一条便于连接
ensure_join_key() {
  local jk="$ROOT/join-keys.json"
  local sample="$ROOT/join-keys.sample.json"
  if [[ ! -f "$jk" ]] || ! grep -q '"key"' "$jk" 2>/dev/null; then
    if [[ -f "$sample" ]]; then
      cp "$sample" "$jk"
      echo "[Star] 已从 join-keys.sample.json 恢复 join key，便于 OpenClaw 连接"
    fi
  fi
}

start_star() {
  if lsof -i :"$STAR_PORT" -t &>/dev/null; then
    echo "[Star] 端口 $STAR_PORT 已被占用，跳过启动（已在运行）"
    return 0
  fi
  echo "[Star] 启动 Star-Office-UI 后端 (port $STAR_PORT)..."
  (cd "$ROOT/backend" && "../.venv/bin/python" app.py) &
  sleep 2
}

start_openclaw() {
  if lsof -i :"$OPENCLAW_PORT" -t &>/dev/null; then
    echo "[OpenClaw] 端口 $OPENCLAW_PORT 已被占用，跳过启动（已在运行）"
    return 0
  fi
  echo "[OpenClaw] 启动 gateway (port $OPENCLAW_PORT)..."
  if [[ -d "$OPENCLAW_REPO" && -f "$OPENCLAW_REPO/package.json" ]]; then
    (cd "$OPENCLAW_REPO" && nohup pnpm openclaw gateway run --bind loopback --port "$OPENCLAW_PORT" > /tmp/openclaw-gateway.log 2>&1 &)
  else
    nohup openclaw gateway run --bind loopback --port "$OPENCLAW_PORT" > /tmp/openclaw-gateway.log 2>&1 &
  fi
  sleep 2
}

# 连接：让 OpenClaw 以访客身份加入 Star 办公室并持续推送状态
connect_star_openclaw() {
  if ! lsof -i :"$STAR_PORT" -t &>/dev/null; then
    echo "[连接] Star 未运行，跳过连接（先启动 Star 后再运行本脚本即可连接）"
    return 0
  fi
  if ! curl -sf -o /dev/null "http://127.0.0.1:$STAR_PORT/health" 2>/dev/null; then
    echo "[连接] Star 未就绪，跳过连接"
    return 0
  fi
  if pgrep -f "office-agent-push.py" &>/dev/null; then
    echo "[连接] OpenClaw 已连接 Star（office-agent-push 已在运行）"
    return 0
  fi
  local name="${OFFICE_AGENT_NAME:-OpenClaw}"
  echo "[连接] 启动 OpenClaw → Star 状态推送（访客名: ${name}）..."
  (cd "$ROOT" && OFFICE_URL="http://127.0.0.1:$STAR_PORT" OFFICE_JOIN_KEY="${OFFICE_JOIN_KEY:-ocj_example_team_01}" OFFICE_AGENT_NAME="${name}" .venv/bin/python office-agent-push.py) >> /tmp/office-agent-push.log 2>&1 &
  sleep 1
  echo "[连接] 已启动，几秒后可在 Star 办公室看到 OpenClaw 访客"
}

ensure_join_key
start_star
start_openclaw
connect_star_openclaw

echo ""
echo "=============================================="
echo "  网页地址"
echo "=============================================="
echo "  Star 像素办公室:  http://127.0.0.1:$STAR_PORT"
echo "  OpenClaw 控制台:  http://127.0.0.1:$OPENCLAW_PORT"
echo "=============================================="
echo ""
echo "若刚启动，请等几秒再打开链接。OpenClaw 已作为访客连接 Star，状态来自 $ROOT/state.json。"
echo "停止推送: pkill -f office-agent-push.py"
