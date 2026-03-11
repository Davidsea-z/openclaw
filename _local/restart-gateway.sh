#!/usr/bin/env bash
# gateway 健康检查 + 自动重启 + 消息通知
# 用法：bash ~/openclaw/_local/restart-gateway.sh
# 建议加入 crontab：*/5 * * * * bash ~/openclaw/_local/restart-gateway.sh >> /tmp/gateway-watchdog.log 2>&1

set -euo pipefail

PHONE="+85260403724"
OPENCLAW_DIR="$HOME/openclaw"
LOG_FILE="/tmp/openclaw-gateway.log"
WATCHDOG_LOG="/tmp/gateway-watchdog.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$WATCHDOG_LOG"
}

notify() {
  local msg="$1"
  cd "$OPENCLAW_DIR"
  # WhatsApp
  pnpm openclaw message send \
    --channel whatsapp \
    --target "$PHONE" \
    --message "$msg" 2>/dev/null && log "✅ WhatsApp 通知已发送" || log "⚠️ WhatsApp 通知失败"
  # iMessage
  pnpm openclaw message send \
    --channel imessage \
    --target "$PHONE" \
    --message "$msg" 2>/dev/null && log "✅ iMessage 通知已发送" || log "⚠️ iMessage 通知失败"
}

start_gateway() {
  log "🔄 正在启动 gateway..."
  cd "$OPENCLAW_DIR"
  pkill -9 -f openclaw-gateway 2>/dev/null || true
  sleep 2
  nohup pnpm openclaw gateway run \
    --bind loopback \
    --port 18789 \
    --force \
    > "$LOG_FILE" 2>&1 &
  sleep 5
  log "✅ gateway 已启动 (PID: $!)"
}

# 检查 gateway 是否在响应（HTTP 探活）
check_gateway() {
  local response
  response=$(curl -sf --max-time 5 http://127.0.0.1:18789/health 2>/dev/null)
  if echo "$response" | grep -q '"ok":true'; then
    return 0
  fi
  log "⚠️ gateway 健康检查失败，响应：${response:-无响应}"
  return 1
}

# 主逻辑
log "=== Gateway 健康检查 ==="

if check_gateway; then
  log "✅ Gateway 运行正常，无需操作"
else
  log "❌ Gateway 异常，开始重启..."
  start_gateway

  TIME=$(date '+%Y-%m-%d %H:%M')
  notify "🔔 [OpenClaw] Gateway 已于 ${TIME} 自动重启，重新上线啦～"
fi
