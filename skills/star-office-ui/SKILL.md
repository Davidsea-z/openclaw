---
name: star-office-ui
description: "像素办公室看板技能：让 OpenClaw 在本地或远程像素办公室实时展示工作状态（idle/writing/researching/executing/syncing/error），支持多 Agent 同屏、昨日小记、Gemini AI 装修。本技能指向仓库内已安装的 Star-Office-UI，无需额外 clone。"
metadata: { "openclaw": { "emoji": "🏢", "requires": { "anyBins": ["python3"] } } }
---

# Star Office UI Skill（本地集成版）

> 本技能对应仓库内的 `Star-Office-UI/`，已预置完整后端与协同脚本，无需额外 clone。

## 快速上手（一句话给主人）

> 这是一个像素办公室看板，你的 AI 助手会根据工作状态自动走到不同位置（工作区/休息区/Bug区），还能看到昨天的工作小记。

---

## 1. 启动后端（一键）

在仓库根目录执行：

```bash
cd Star-Office-UI
./scripts/start-star-and-openclaw.sh
```

然后访问 **http://127.0.0.1:19000** 查看像素办公室。

或单独启动后端：

```bash
cd Star-Office-UI
.venv/bin/python backend/app.py
```

---

## 2. 作为 Agent 主动更新自己的状态（最重要！）

**在每次任务前后，你必须更新状态**：

```bash
# 开始任务前（接到用户消息时）
cd Star-Office-UI && python3 set_state.py receiving "收到消息，准备处理"

# 调研/搜索时
cd Star-Office-UI && python3 set_state.py researching "正在调研..."

# 写代码/写文档时
cd Star-Office-UI && python3 set_state.py writing "正在编写..."

# 执行命令时
cd Star-Office-UI && python3 set_state.py executing "执行中..."

# 任务完成后
cd Star-Office-UI && python3 set_state.py idle "已完成，待命中"

# 遇到报错时
cd Star-Office-UI && python3 set_state.py error "发现问题，正在排查"
```

> **状态联动规则**：接任务前切 `writing/researching/executing`，完成后切 `idle`，报错切 `error`。这样主人能在浏览器里实时看到你在做什么。

---

## 3. 状态区域映射

| 状态          | 像素办公室区域   | 触发条件        |
| ------------- | ---------------- | --------------- |
| `idle`        | 休息区（沙发）   | 待命、任务完成  |
| `writing`     | 工作区（办公桌） | 写代码、写文档  |
| `researching` | 工作区           | 搜索、调研      |
| `executing`   | 工作区           | 运行命令        |
| `receiving`   | 工作区           | 收到消息/处理中 |
| `replying`    | 工作区           | 正在回复        |
| `syncing`     | 工作区           | 同步数据        |
| `error`       | Bug 区（红区）   | 异常、报错      |

---

## 4. 多会话同屏（最重要的多任务场景）

**OpenClaw 同时处理多个会话时，每个会话在 Star 办公室显示为独立角色。**

架构：

```
state.json          → "OpenClaw"（主会话/WebChat）
state-discord.json  → "OpenClaw-discord"
state-telegram.json → "OpenClaw-telegram"
state-whatsapp.json → "OpenClaw-whatsapp"
```

`multi-push.py` 自动扫描所有 `state-*.json`，每个对应一个角色（无需手动 join）。

### 会话内状态更新方式

```bash
# 主会话
cd Star-Office-UI && python3 set_state.py writing "处理 WebChat 请求"

# Discord 会话
cd Star-Office-UI && python3 set_state.py researching "Discord 消息处理中" --session discord

# Telegram 会话
cd Star-Office-UI && python3 set_state.py executing "执行 Telegram 任务" --session telegram

# WhatsApp 会话
cd Star-Office-UI && python3 set_state.py idle "已回复" --session whatsapp
```

### Agent 工作流规范（多会话版）

每次收到消息时：

1. **先切状态**（对应你所在的会话）：`python3 set_state.py receiving "收到消息" --session <channel>`
2. **开始处理**：`python3 set_state.py writing "处理中" --session <channel>`
3. **完成后复位**：`python3 set_state.py idle "已完成" --session <channel>`

多个会话并行时，主人能在看板上同时看到多个角色各自的状态。

---

## 5. 让其他龙虾加入（多 Agent 同屏）

如果有其他 OpenClaw 想出现在你主人的办公室：

```bash
# 使用 join-keys.sample.json 里的 key
cd Star-Office-UI
OFFICE_JOIN_KEY=ocj_example_team_01 OFFICE_AGENT_NAME="访客A" OFFICE_URL=http://127.0.0.1:19000 \
  .venv/bin/python office-agent-push.py
```

`join-keys.json` 里有 `ocj_starteam01`～`ocj_starteam08`，同一个 key 最多 3 个 agent 同时在线。

---

## 6. 测试协同是否正常

```bash
cd Star-Office-UI
./scripts/test-openclaw-synergy.sh
```

---

## 7. 同步 OpenClaw 日志到「昨日小记」

```bash
cd Star-Office-UI
# 同步昨天的会话记录到 memory/YYYY-MM-DD.md
python3 scripts/sync-openclaw-logs-to-memo.py

# 预览（不写文件）
python3 scripts/sync-openclaw-logs-to-memo.py --dry-run
```

---

## 8. 公网访问（可选，Cloudflare Tunnel 最快）

```bash
cloudflared tunnel --url http://127.0.0.1:19000
```

拿到 `https://xxx.trycloudflare.com` 告诉主人。

---

## 9. 配置 Gemini 生图（可选）

基础功能不需要 API。如需 AI 装修，在侧边栏填入 `GEMINI_API_KEY`，或：

```bash
export GEMINI_API_KEY="your-key"
export GEMINI_MODEL="gemini-2.0-flash"
```

---

## 10. 安全提醒

- 侧边栏默认密码：`1234`，生产/公网场景必须改强密码
- `export ASSET_DRAWER_PASS="your-strong-pass"`
- 代码 MIT 协议；**美术资产禁止商用**

---

## 11. 常见问题

**Q: 后端启动失败？**

```bash
cd Star-Office-UI && python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
```

**Q: state.json 不存在？**

```bash
cp Star-Office-UI/state.sample.json Star-Office-UI/state.json
```

**Q: 端口 19000 被占用？**

```bash
STAR_BACKEND_PORT=19001 ./scripts/start-star-and-openclaw.sh
```
