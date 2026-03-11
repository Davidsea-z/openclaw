#!/usr/bin/env node
/**
 * 导出 OpenClaw main agent 指定时间之后的对话为纯文本。
 * 用法: npx tsx scripts/export-main-session-txt.ts [--after 17:03] [--date 2026-03-10] [--out file.txt]
 * 默认: 今天 17:03 之后，输出到 openclaw-main-export-<date>-1703.txt
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const OPENCLAW_HOME = process.env.OPENCLAW_HOME || path.join(os.homedir(), ".openclaw");
const SESSIONS_DIR = path.join(OPENCLAW_HOME, "agents", "main", "sessions");

type LogLine = {
  type?: string;
  timestamp?: string;
  message?: { role?: string; content?: unknown; timestamp?: number };
};

function extractText(content: unknown): string {
  if (typeof content === "string") {
    return content.trim();
  }
  if (Array.isArray(content)) {
    const parts = content
      .filter((c): c is { type?: string; text?: string } => c && typeof c === "object")
      .filter((c) => c.type === "text" && typeof c.text === "string")
      .map((c) => (c as { text: string }).text.trim());
    return parts.join("\n").trim();
  }
  return "";
}

function parseTime(ts: string | number | undefined): number {
  if (ts === undefined) {
    return 0;
  }
  if (typeof ts === "number") {
    return ts > 1e12 ? ts : ts * 1000;
  }
  try {
    return new Date(ts).getTime();
  } catch {
    return 0;
  }
}

function main() {
  const args = process.argv.slice(2);
  let afterTime = "17:03";
  let dateStr = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  let outPath = "";

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--after" && args[i + 1]) {
      afterTime = args[i + 1];
      i++;
    } else if (args[i] === "--date" && args[i + 1]) {
      dateStr = args[i + 1];
      i++;
    } else if (args[i] === "--out" && args[i + 1]) {
      outPath = args[i + 1];
      i++;
    }
  }

  const [h, m] = afterTime.split(":").map(Number);
  const cutoffLocal = new Date(dateStr);
  cutoffLocal.setHours(h ?? 0, m ?? 0, 0, 0);
  const cutoffMs = cutoffLocal.getTime();

  if (!outPath) {
    const suffix = afterTime.replace(":", "");
    outPath = path.join(process.cwd(), `openclaw-main-export-${dateStr}-${suffix}.txt`);
  }

  const entries: { ts: number; role: string; text: string }[] = [];

  if (!fs.existsSync(SESSIONS_DIR)) {
    console.error("Sessions dir not found:", SESSIONS_DIR);
    process.exit(1);
  }

  const files = fs
    .readdirSync(SESSIONS_DIR)
    .filter((f) => f.endsWith(".jsonl") && !f.includes(".reset."));
  for (const file of files) {
    const fp = path.join(SESSIONS_DIR, file);
    const lines = fs.readFileSync(fp, "utf-8").split("\n");
    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }
      try {
        const obj: LogLine = JSON.parse(line);
        if (obj.type !== "message" || !obj.message) {
          continue;
        }
        const role = obj.message.role === "user" ? "用户" : "助手";
        const text = extractText(obj.message.content);
        if (!text) {
          continue;
        }
        const ts = parseTime(obj.timestamp ?? obj.message.timestamp);
        if (ts < cutoffMs) {
          continue;
        }
        entries.push({ ts, role, text });
      } catch {
        // skip invalid lines
      }
    }
  }

  entries.sort((a, b) => a.ts - b.ts);

  const lines: string[] = [
    `# OpenClaw main 对话导出`,
    `# 时间范围: ${dateStr} ${afterTime} 之后`,
    `# 导出时间: ${new Date().toISOString()}`,
    "",
  ];
  for (const e of entries) {
    const timeStr = new Date(e.ts).toLocaleString("zh-CN", { hour12: false });
    lines.push(`[${timeStr}] ${e.role}:`);
    lines.push(e.text);
    lines.push("");
  }

  fs.writeFileSync(outPath, lines.join("\n"), "utf-8");
  console.log(`已导出 ${entries.length} 条消息到 ${outPath}`);
}

main();
