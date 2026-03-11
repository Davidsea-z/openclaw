#!/usr/bin/env bash
# 测试 Star-Office-UI 与 OpenClaw 的协同：后端健康、join、push、set_state、/status
# 用法：在 Star-Office-UI 项目根目录执行 ./scripts/test-openclaw-synergy.sh
# 前提：Star-Office-UI 后端已启动（默认 http://127.0.0.1:19000）

set -euo pipefail

OFFICE_URL="${OFFICE_URL:-http://127.0.0.1:19000}"
JOIN_KEY="${OFFICE_JOIN_KEY:-ocj_example_team_01}"
AGENT_NAME="${OFFICE_AGENT_NAME:-OpenClaw}"

echo "==> 1. 健康检查 GET $OFFICE_URL/health"
curl -sf -o /dev/null "$OFFICE_URL/health" && echo "    OK" || { echo "    FAIL"; exit 1; }

echo "==> 2. 主 Star 状态 GET $OFFICE_URL/status"
curl -s "$OFFICE_URL/status" | python3 -m json.tool 2>/dev/null || curl -s "$OFFICE_URL/status"

echo "==> 3. 访客加入 POST $OFFICE_URL/join-agent"
JOIN_RESP=$(curl -s -X POST "$OFFICE_URL/join-agent" -H "Content-Type: application/json" \
  -d "{\"name\":\"$AGENT_NAME\",\"joinKey\":\"$JOIN_KEY\",\"state\":\"idle\",\"detail\":\"联调测试\"}")
echo "$JOIN_RESP" | python3 -m json.tool 2>/dev/null || echo "$JOIN_RESP"
if ! echo "$JOIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('ok') else 1)" 2>/dev/null; then
  echo "    JOIN 失败"; exit 1
fi
AGENT_ID=$(echo "$JOIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('agentId',''))")
echo "    agentId=$AGENT_ID"

echo "==> 4. 推送状态 POST $OFFICE_URL/agent-push"
PUSH_RESP=$(curl -s -X POST "$OFFICE_URL/agent-push" -H "Content-Type: application/json" \
  -d "{\"agentId\":\"$AGENT_ID\",\"joinKey\":\"$JOIN_KEY\",\"state\":\"writing\",\"detail\":\"协同测试中\",\"name\":\"$AGENT_NAME\"}")
echo "$PUSH_RESP" | python3 -m json.tool 2>/dev/null || echo "$PUSH_RESP"

echo "==> 5. 访客列表 GET $OFFICE_URL/agents"
curl -s "$OFFICE_URL/agents" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for a in (data if isinstance(data, list) else data.get('agents', [])):
    print(f\"    - {a.get('name')} ({a.get('state')}) @ {a.get('area')}\")
" 2>/dev/null || curl -s "$OFFICE_URL/agents"

echo ""
echo "协同测试通过。在浏览器打开 $OFFICE_URL 可查看像素办公室。"
echo "本地改状态: python3 set_state.py writing \"工作中\" 或 idle \"待命中\""
