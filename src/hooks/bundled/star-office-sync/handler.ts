/**
 * Star Office UI 状态同步 Hook
 *
 * 监听 message 事件，自动更新 Star-Office-UI 的 state-<channel>.json，
 * 让每个 channel（whatsapp / imessage / telegram 等）在看板上显示为独立角色。
 *
 * 事件映射：
 *   message:received  → receiving（收到消息）
 *   message:sent      → idle（回复已发出）
 *
 * 状态文件命名：
 *   whatsapp  → state-whatsapp.json
 *   imessage  → state-imessage.json
 *   telegram  → state-telegram.json
 *   （其他 channel 同理）
 *
 * 配置（openclaw.json）：
 * ```json
 * {
 *   "hooks": {
 *     "internal": {
 *       "entries": {
 *         "star-office-sync": {
 *           "enabled": true,
 *           "stateDir": "/path/to/Star-Office-UI"
 *         }
 *       }
 *     }
 *   }
 * }
 * ```
 * stateDir 留空时自动发现（STAR_OFFICE_DIR 环境变量 → workspace 同级 Star-Office-UI 目录）。
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createSubsystemLogger } from "../../../logging/subsystem.js";
import type { HookHandler } from "../../hooks.js";
import { isMessageReceivedEvent, isMessageSentEvent } from "../../internal-hooks.js";

const log = createSubsystemLogger("hooks/star-office-sync");

// session 名只允许字母数字连字符，防止路径拼接注入
const SAFE_SESSION_RE = /^[a-zA-Z0-9_-]{1,32}$/;

/** 将 channelId 规范化为安全的文件名 segment */
function toSafeSession(channelId: string): string | null {
  // 标准化：去空格、小写、替换常见分隔符
  const normalized = channelId.trim().toLowerCase().replace(/[\s.]/g, "-");
  return SAFE_SESSION_RE.test(normalized) ? normalized : null;
}

/**
 * 自动发现 Star-Office-UI 根目录。
 * 优先级：
 *   1. config.stateDir（openclaw.json hooks.internal.entries.star-office-sync.stateDir）
 *   2. 环境变量 STAR_OFFICE_DIR
 *   3. ~/.openclaw/workspace/Star-Office-UI
 *   4. import.meta.url 同包根目录的 Star-Office-UI 子目录
 *      dist/hooks/bundled/star-office-sync/ → 上 4 级 = 仓库根目录
 *      src/hooks/bundled/star-office-sync/  → 上 4 级 = 仓库根目录
 */
function resolveStarOfficeDir(configStateDir?: unknown): string | null {
  // 1. 显式配置（优先级最高）
  if (typeof configStateDir === "string" && configStateDir.trim()) {
    return configStateDir.trim();
  }

  // 2. 环境变量 STAR_OFFICE_DIR
  const envDir = process.env.STAR_OFFICE_DIR?.trim();
  if (envDir) {
    return envDir;
  }

  // 3. ~/.openclaw/workspace/Star-Office-UI
  const openhome = process.env.OPENCLAW_HOME ?? path.join(os.homedir(), ".openclaw");
  const workspaceCandidate = path.join(openhome, "workspace", "Star-Office-UI");
  if (fs.existsSync(workspaceCandidate)) {
    return workspaceCandidate;
  }

  // 4. 从本文件位置上溯到仓库根，再找 Star-Office-UI/
  //    文件路径：<root>/dist/hooks/bundled/star-office-sync/handler.js（4 层）
  //              <root>/src/hooks/bundled/star-office-sync/handler.ts（4 层）
  try {
    const moduleDir = path.dirname(new URL(import.meta.url).pathname);
    const repoRoot = path.resolve(moduleDir, "..", "..", "..", "..");
    const candidate = path.join(repoRoot, "Star-Office-UI");
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  } catch {
    // import.meta.url 不可用时忽略
  }

  return null;
}

/**
 * 从 openclaw.json 直接读取 stateDir 配置。
 * message:received / message:sent 事件的 context 不携带 cfg，
 * 所以在模块初始化时提前读取一次，避免每次事件都重新读文件。
 */
function readStateDirFromConfig(): string | null {
  try {
    const openhome = process.env.OPENCLAW_HOME ?? path.join(os.homedir(), ".openclaw");
    const configFile = path.join(openhome, "openclaw.json");
    if (!fs.existsSync(configFile)) {
      return null;
    }
    const raw = fs.readFileSync(configFile, "utf-8");
    const cfg = JSON.parse(raw) as Record<string, unknown>;
    const entries = cfg?.hooks as Record<string, unknown>;
    const internal = entries?.internal as Record<string, unknown>;
    const hookEntries = internal?.entries as Record<string, unknown>;
    const hookCfg = hookEntries?.["star-office-sync"] as Record<string, unknown> | undefined;
    const dir = hookCfg?.["stateDir"];
    return typeof dir === "string" && dir.trim() ? dir.trim() : null;
  } catch {
    return null;
  }
}

// 模块加载时读取一次，避免每次 hook 触发都读文件
const _configStateDir: string | null = readStateDirFromConfig();
const _resolvedStarOfficeDir: string | null = resolveStarOfficeDir(_configStateDir);

// 启动时打印发现的路径，方便调试
if (_resolvedStarOfficeDir) {
  log.info(`star-office-sync: stateDir=${_resolvedStarOfficeDir}`);
} else {
  log.warn(
    "star-office-sync: Star-Office-UI 目录未找到，hook 将静默跳过。" +
      " 请设置 STAR_OFFICE_DIR 或在 openclaw.json 中配置 hooks.internal.entries.star-office-sync.stateDir",
  );
}

/** 原子写入 state-<session>.json，防止并发写入产生截断文件 */
function writeStateFile(stateDir: string, session: string, state: string, detail: string): void {
  const filename = session === "" ? "state.json" : `state-${session}.json`;
  const target = path.join(stateDir, filename);
  const tmp = `${target}.tmp`;
  const data = {
    state,
    detail,
    progress: 0,
    updated_at: new Date().toISOString(),
    session: session || undefined,
  };
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2) + "\n", "utf-8");
  fs.renameSync(tmp, target);
}

const starOfficeSync: HookHandler = async (event) => {
  // message:received / message:sent 事件不携带 cfg，直接用模块初始化时缓存的路径
  const stateDir = _resolvedStarOfficeDir;
  if (!stateDir) {
    return;
  }

  if (isMessageReceivedEvent(event)) {
    const channelId = event.context.channelId;
    const session = toSafeSession(channelId);
    if (!session) {
      log.warn(`star-office-sync: 无法规范化 channelId="${channelId}"，跳过`);
      return;
    }
    try {
      writeStateFile(stateDir, session, "receiving", `收到 ${channelId} 消息`);
      log.debug(`star-office-sync: ${channelId} → receiving`);
    } catch (err) {
      log.error(`star-office-sync: 写入 state-${session}.json 失败: ${String(err)}`);
    }
    return;
  }

  if (isMessageSentEvent(event)) {
    const channelId = event.context.channelId;
    // 只在发送成功时切回 idle
    if (!event.context.success) {
      return;
    }
    const session = toSafeSession(channelId);
    if (!session) {
      return;
    }
    try {
      writeStateFile(stateDir, session, "idle", `已回复 ${channelId}`);
      log.debug(`star-office-sync: ${channelId} → idle`);
    } catch (err) {
      log.error(`star-office-sync: 写入 state-${session}.json 失败: ${String(err)}`);
    }
    return;
  }
};

export default starOfficeSync;
