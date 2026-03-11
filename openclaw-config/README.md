# OpenClaw 千问模型配置（本目录）

本目录提供在此仓库下使用**千问（Qwen）**模型 API 的 OpenClaw 配置模板（**Coding Plan**：阿里云百炼）。

## 方式一：阿里云百炼 Coding Plan（推荐，与 `优化配置说明.md` 一致）

使用 **阿里云百炼 Coding 端点**（`https://coding.dashscope.aliyuncs.com/v1`），模型为 `qwen3.5-plus`。

### 1. 设置 / 重新设置 API Key（环境变量）

**变量名（必须一致）：** `DASHSCOPE_API_KEY`

任选一种方式存储，CLI 与 Gateway 都会读取：

**推荐：写入 OpenClaw 状态目录下的 `.env`**（Gateway 由 Mac 应用启动时也会加载）

```bash
mkdir -p ~/.openclaw
# 以下二选一：新建或覆盖
echo 'DASHSCOPE_API_KEY=你的百炼CodingPlan_API_Key' > ~/.openclaw/.env
# 或追加（若该文件已有其他变量）
echo 'DASHSCOPE_API_KEY=你的百炼CodingPlan_API_Key' >> ~/.openclaw/.env
```

若使用本仓库内状态目录（`OPENCLAW_STATE_DIR=./.openclaw-state`），则放在该目录下：

```bash
echo 'DASHSCOPE_API_KEY=你的百炼CodingPlan_API_Key' >> .openclaw-state/.env
```

**或仅当前终端有效：**

```bash
export DASHSCOPE_API_KEY="你的百炼CodingPlan_API_Key"
```

模板见本目录下的 `.env.example`（不要提交真实 Key 到仓库）。

### 2. 使用本目录配置运行

在仓库根目录执行（**必须加 `--agent main`**，否则嵌入式模式会报错「Pass --to, --session-id, or --agent」）：

```bash
export OPENCLAW_CONFIG_PATH="$(pwd)/openclaw-config/openclaw.json"
pnpm openclaw agent --agent main --message "你好"
```

若希望**状态也落在仓库内**（会话、models.json 等）：

```bash
export OPENCLAW_CONFIG_PATH="$(pwd)/openclaw-config/openclaw.json"
export OPENCLAW_STATE_DIR="$(pwd)/.openclaw-state"
pnpm openclaw agent --agent main --message "你好"
```

首次使用会自动创建 `.openclaw-state/`，已加入 `.gitignore`，不会提交。

### 3. 可选：限制上下文与输出长度

在 `openclaw-config/openclaw.json` 的 `agents.defaults` 中可增加：

```json
"contextWindow": 8000,
"maxOutputTokens": 2000
```

---

## 方式二：官方 Qwen Portal（OAuth，免费额度）

使用 [Qwen Portal](https://portal.qwen.ai) 的 OAuth，无需 API Key，有免费额度（如每日 2000 次请求）。

### 1. 启用插件并登录

```bash
openclaw plugins enable qwen-portal-auth
openclaw models auth login --provider qwen-portal --set-default
```

### 2. 与本目录配置一起使用

若仍想用本目录的 `openclaw.json` 做其他配置，可保留 `OPENCLAW_CONFIG_PATH`，并在配置中设置默认模型为千问 Portal：

```json
"agents": {
  "defaults": {
    "model": { "primary": "qwen-portal/coder-model" }
  }
}
```

模型 ID：`qwen-portal/coder-model`、`qwen-portal/vision-model`。

---

## 配置说明

| 环境变量               | 说明                                   |
| ---------------------- | -------------------------------------- |
| `OPENCLAW_CONFIG_PATH` | 指定本目录下的 `openclaw.json`         |
| `OPENCLAW_STATE_DIR`   | 可选，状态目录（会话、models.json 等） |
| `DASHSCOPE_API_KEY`    | 百炼 Coding API Key（方式一必填）      |

文档：[Model providers](https://docs.openclaw.ai/concepts/model-providers)、[Qwen](https://docs.openclaw.ai/providers/qwen)。

---

## 故障排查：HTTP 401 / invalid access token or token expired

若 TUI 或 Agent 报错 **`HTTP 401: invalid access token or token expired`**，且当前模型是 **bailian/xxx**，说明 **bailian 使用的 API Key 无效或过期**（与 gateway token 无关）。

### 1. 确认是哪个 Key

- **bailian** 使用环境变量 **`DASHSCOPE_API_KEY`**（阿里云百炼 / DashScope Coding）。
- 若当前模型是 **bailian/qwen3.5-plus**：必须保证 `DASHSCOPE_API_KEY` 已设置且有效。
- 若当前模型是 **bailian/glm-5**：GLM-5 属于智谱（Z.ai），不在百炼。应改用 **zai** 提供商和 **ZAI_API_KEY**，模型为 **zai/glm-5**，不要用 bailian 调 GLM-5。

### 2. 修复 bailian（百炼）401

1. 登录 [阿里云百炼 / DashScope](https://dashscope.console.aliyun.com/)，在「API-KEY 管理」中创建或复制 **Coding Plan** 可用的 Key。
2. 写入 OpenClaw 能读到的环境（任选其一）：
   - **推荐**：`~/.openclaw/.env`  
     `echo 'DASHSCOPE_API_KEY=sk-你的key' >> ~/.openclaw/.env`
   - 或当前 shell：`export DASHSCOPE_API_KEY="sk-你的key"`
3. **重启 Gateway**（若由 Mac 菜单栏启动，退出 OpenClaw 再打开），然后重试 TUI/agent。

### 3. 若要用 GLM-5（智谱 / Z.ai）

请用 **zai** 提供商，不要用 bailian：

1. 在 [Z.ai / 智谱](https://open.bigmodel.cn/) 获取 API Key。
2. 设置环境变量 **ZAI_API_KEY**（例如写入 `~/.openclaw/.env`：`ZAI_API_KEY=你的智谱key`）。
3. 在配置里使用 **zai/glm-5** 作为主模型，例如：
   - `openclaw config set agents.defaults.model.primary "zai/glm-5"`
   - 或编辑 `openclaw.json` 中 `agents.defaults.model.primary` 为 `"zai/glm-5"`，并确保 `models.providers.zai` 存在（可先运行 `openclaw configure` 选 Z.ai 按提示配置）。
4. 重启 Gateway 后重试。
