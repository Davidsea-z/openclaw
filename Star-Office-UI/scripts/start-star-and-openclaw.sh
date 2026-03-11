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

# 确保 Python venv 存在并安装依赖（自动恢复，跨平台）
ensure_venv() {
  local venv="$ROOT/.venv"
  local req="$ROOT/backend/requirements.txt"
  # 检测 venv 内 python 是否可用（macOS 上 pip 可能装在 bin 或 Scripts）
  local py=""
  if [[ -x "$venv/bin/python" ]]; then
    py="$venv/bin/python"
  elif [[ -x "$venv/Scripts/python.exe" ]]; then
    py="$venv/Scripts/python.exe"
  fi

  if [[ -z "$py" ]]; then
    echo "[Star] 未找到 .venv，正在创建..."
    python3 -m venv "$venv"
    py="$venv/bin/python"
  fi

  # 检查 flask 是否已安装（代表依赖齐全）
  if ! "$py" -c "import flask" &>/dev/null; then
    echo "[Star] 安装 Python 依赖（$req）..."
    "$py" -m pip install -q -r "$req"
  fi

  # 首次运行确保 state.json 存在
  if [[ ! -f "$ROOT/state.json" ]] && [[ -f "$ROOT/state.sample.json" ]]; then
    cp "$ROOT/state.sample.json" "$ROOT/state.json"
    echo "[Star] 已从 state.sample.json 初始化 state.json"
  fi
}

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
  local py=""
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    py="$ROOT/.venv/bin/python"
  else
    py="python3"
  fi
  (cd "$ROOT/backend" && "$py" app.py) &
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

# 连接：启动 multi-push.py，自动管理所有会话（state.json + state-*.json）
connect_star_openclaw() {
  if ! lsof -i :"$STAR_PORT" -t &>/dev/null; then
    echo "[连接] Star 未运行，跳过连接"
    return 0
  fi
  if ! curl -sf -o /dev/null "http://127.0.0.1:$STAR_PORT/health" 2>/dev/null; then
    echo "[连接] Star 未就绪，跳过连接"
    return 0
  fi
  # 已有 multi-push 在跑则跳过
  if pgrep -f "multi-push.py" &>/dev/null; then
    echo "[连接] multi-push.py 已在运行，跳过"
    return 0
  fi
  # 兼容旧版：仍支持单 agent 模式（设 OFFICE_SINGLE_PUSH=1）
  if [[ "${OFFICE_SINGLE_PUSH:-0}" == "1" ]]; then
    local name="${OFFICE_AGENT_NAME:-OpenClaw}"
    echo "[连接] 单 agent 模式，推送（访客名: ${name}）..."
    local py=""
    if [[ -x "$ROOT/.venv/bin/python" ]]; then py="$ROOT/.venv/bin/python"; else py="python3"; fi
    (cd "$ROOT" && OFFICE_URL="http://127.0.0.1:$STAR_PORT" OFFICE_JOIN_KEY="${OFFICE_JOIN_KEY:-ocj_example_team_01}" OFFICE_AGENT_NAME="${name}" "$py" office-agent-push.py) >> /tmp/office-agent-push.log 2>&1 &
  else
    local prefix="${OFFICE_AGENT_PREFIX:-OpenClaw}"
    echo "[连接] 启动 multi-push（前缀: ${prefix}，扫描 state*.json）..."
    local py=""
    if [[ -x "$ROOT/.venv/bin/python" ]]; then py="$ROOT/.venv/bin/python"; else py="python3"; fi
    (cd "$ROOT" && OFFICE_URL="http://127.0.0.1:$STAR_PORT" \
      OFFICE_JOIN_KEY="${OFFICE_JOIN_KEY:-ocj_example_team_01}" \
      OFFICE_AGENT_PREFIX="${prefix}" \
      "$py" multi-push.py) >> /tmp/office-multi-push.log 2>&1 &
  fi
  sleep 1
  echo "[连接] 已启动，几秒后可在 Star 办公室看到 OpenClaw 角色"
}

ensure_venv
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
echo "若刚启动，请等几秒再打开链接。"
echo "多会话状态文件:"
echo "  主会话:     $ROOT/state.json"
echo "  其他会话:   $ROOT/state-<session>.json（例如 state-discord.json）"
echo ""
echo "更新状态: python3 set_state.py writing \"工作中\""
echo "多会话:   python3 set_state.py writing \"Discord任务\" --session discord"
echo "停止推送: pkill -f multi-push.py"
