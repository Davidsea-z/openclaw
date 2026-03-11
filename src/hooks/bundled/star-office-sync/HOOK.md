---
name: star-office-sync
description: "将 WhatsApp / iMessage 等各 channel 的收发事件同步到 Star-Office-UI 看板，每个 channel 显示为独立角色"
metadata:
  {
    "openclaw":
      {
        "emoji": "🏢",
        "events": ["message:received", "message:sent"],
        "install": [{ "id": "bundled", "kind": "bundled", "label": "Bundled with OpenClaw" }],
      },
  }
---

# Star Office Sync Hook

监听消息收发事件，自动更新 Star-Office-UI 的状态文件，让每个 channel 在像素看板上显示为独立角色。

## 状态映射

| 事件                                     | 状态                     |
| ---------------------------------------- | ------------------------ |
| `message:received`（收到消息）           | `receiving` → 进入工作桌 |
| `message:sent`（回复发出，success=true） | `idle` → 回到休息区      |

## Channel 角色命名

| Channel      | 看板角色名             |
| ------------ | ---------------------- |
| `whatsapp`   | `OpenClaw-whatsapp`    |
| `imessage`   | `OpenClaw-imessage`    |
| `telegram`   | `OpenClaw-telegram`    |
| 其他 channel | `OpenClaw-<channelId>` |

## 前提

Star-Office-UI 后端已启动（`./scripts/start-star-and-openclaw.sh`），`multi-push.py` 在后台扫描 `state-*.json` 并推送到看板。

## 配置（openclaw.json）

```json
{
  "hooks": {
    "internal": {
      "enabled": true,
      "entries": {
        "star-office-sync": {
          "enabled": true,
          "stateDir": "/path/to/Star-Office-UI"
        }
      }
    }
  }
}
```

`stateDir` 留空时自动发现：

1. 环境变量 `STAR_OFFICE_DIR`
2. `~/.openclaw/workspace/Star-Office-UI`
3. openclaw 仓库同级 `Star-Office-UI/` 目录

## 禁用

```json
{ "hooks": { "internal": { "entries": { "star-office-sync": { "enabled": false } } } } }
```
