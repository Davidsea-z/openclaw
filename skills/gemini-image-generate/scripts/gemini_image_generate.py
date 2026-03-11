#!/usr/bin/env python3
"""Qwen/DashScope Image Generate - Drop-in CLI replacement for gemini_image_generate.py.

Uses Alibaba DashScope (通义万相) API for image generation.

Expected interface (same as original, called by Star Office UI backend):
  python qwen_image_generate.py \
    --prompt "..." \
    --model <model_name> \
    --out-dir /tmp/xxx \
    --cleanup \
    [--aspect-ratio 16:9] \
    [--reference-image /path/to/ref.webp]

Environment:
  GEMINI_API_KEY    - DashScope API key (app.py passes it under this name)
  DASHSCOPE_API_KEY - also accepted (alias)
  GEMINI_MODEL      - override model (app.py passes it under this name)
  QWEN_MODEL        - also accepted (alias)

Output (last line of stdout, same as original):
  {"files": ["/tmp/xxx/generated_0.png"]}
"""

import argparse
import json
import os
import re
import sys
from http import HTTPStatus

try:
    import dashscope
    from dashscope import ImageSynthesis
    HAS_DASHSCOPE = True
except ImportError:
    HAS_DASHSCOPE = False

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# 把 app.py 传来的用户模型名映射到真实 DashScope model id
MODEL_ALIASES: dict = {
    "nanobanana-pro":         "wanx2.1-t2i-plus",
    "nanobanana-2":           "wanx2.1-t2i-turbo",
    "wanx2.1-t2i-plus":      "wanx2.1-t2i-plus",
    "wanx2.1-t2i-turbo":     "wanx2.1-t2i-turbo",
    "wanx2.0-t2i-turbo":     "wanx2.0-t2i-turbo",
    # 兜底：gemini 原始名也映射到高质量万相模型
    "gemini-2.0-flash-exp-image-generation": "wanx2.1-t2i-turbo",
    "gemini-2.5-flash-image": "wanx2.1-t2i-plus",
    "gemini-3-pro-image-preview": "wanx2.1-t2i-plus",
}

# 宽高比 → DashScope size 格式（用 * 分隔）
ASPECT_TO_SIZE: dict = {
    "16:9":  "1280*720",
    "9:16":  "720*1280",
    "1:1":   "1024*1024",
    "4:3":   "1024*768",
    "3:4":   "768*1024",
}


def resolve_model(raw: str) -> str:
    name = (raw or "").strip()
    if name in MODEL_ALIASES:
        return MODEL_ALIASES[name]
    # 已经是有效的 DashScope model id（以 wanx 开头）
    if name.startswith("wanx"):
        return name
    # 默认使用快速模型
    return "wanx2.1-t2i-turbo"


# 8 个随机像素风主题的中文版（对应 app.py 里的英文主题）
_THEME_ZH_MAP = {
    "8-bit dungeon guild room":                "像素风地下城公会大厅，石砌墙壁，火把照明，中世纪奇幻风格",
    "8-bit stardew-valley inspired cozy farm tavern": "像素风星露谷风格温馨农场小酒馆，木质装饰，暖黄灯光，田园风",
    "8-bit nordic fantasy tavern":             "像素风北欧奇幻酒馆，毛皮装饰，壁炉，维京风格",
    "8-bit magitech workshop":                 "像素风魔法科技工坊，齿轮蒸汽，魔法水晶，蒸汽朋克风格",
    "8-bit elven forest inn":                  "像素风精灵森林旅店，藤蔓树木，绿色光晕，自然奇幻风格",
    "8-bit pixel cyber tavern":                "像素风赛博朋克酒吧，霓虹灯，蓝紫主色调，未来都市风格",
    "8-bit desert caravan inn":                "像素风沙漠商队驿站，织毯装饰，暖橙色调，阿拉伯风格",
    "8-bit snow mountain lodge":               "像素风雪山小屋，木质壁炉，皮草装饰，北国冬日风格",
}

_STYLE_HINT_PATTERN = re.compile(
    r"Only change visual style/theme/material/lighting according to:\s*(.+?)\s*\.\s*Do not add",
    re.IGNORECASE | re.DOTALL,
)

# 通用中文办公室背景基础描述（替换英文 base prompt）
_ZH_BASE = (
    "像素风俯视角办公室场景，8-bit复古RPG风格，"
    "保持左侧工作区、中央休息区、右侧区域的空间布局不变，"
    "只改变视觉风格和装饰元素，不添加文字水印，"
    "整体画面清晰完整，适合作为游戏背景图。"
    "风格主题："
)


def build_zh_prompt(raw_prompt: str) -> str:
    """把 app.py 传来的英文 prompt 转换为适合 DashScope 的中文 prompt。"""
    # 尝试提取风格描述（"according to: <style>" 格式）
    m = _STYLE_HINT_PATTERN.search(raw_prompt)
    if m:
        style_hint = m.group(1).strip()
        # 若是已知的英文主题，换成中文版
        zh_style = _THEME_ZH_MAP.get(style_hint, style_hint)
        return _ZH_BASE + zh_style
    # 自定义 prompt（找中介输入的），直接在前面加基础描述
    return _ZH_BASE + raw_prompt


def download_url(url: str, out_path: str) -> bool:
    try:
        resp = _requests.get(url, timeout=90)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"ERROR: 下载图片失败 {url}: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate image via Qwen/DashScope API")
    parser.add_argument("--prompt", required=True, help="Generation prompt")
    parser.add_argument("--model", default="", help="Model name (mapped to DashScope model)")
    parser.add_argument("--out-dir", required=True, help="Output directory for generated files")
    parser.add_argument("--cleanup", action="store_true", help="Ignored (kept for CLI compat)")
    parser.add_argument("--aspect-ratio", default="", help="Aspect ratio hint e.g. 16:9")
    parser.add_argument("--reference-image", default="", help="Reference image path (not used by wanx; prompt enforces layout)")
    args = parser.parse_args()

    # API key：优先 DASHSCOPE_API_KEY，回退到 GEMINI_API_KEY（app.py 传的就是这个）
    api_key = (
        os.environ.get("DASHSCOPE_API_KEY", "").strip()
        or os.environ.get("GEMINI_API_KEY", "").strip()
    )
    if not api_key:
        print("ERROR: DASHSCOPE_API_KEY or GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    # 模型：env 优先，然后 --model 参数
    raw_model = (
        os.environ.get("QWEN_MODEL", "").strip()
        or os.environ.get("GEMINI_MODEL", "").strip()
        or args.model
    )
    model_id = resolve_model(raw_model)

    # 输出目录
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    if not HAS_DASHSCOPE:
        print("ERROR: dashscope 包未安装，请在 .venv 中执行: pip install dashscope", file=sys.stderr)
        sys.exit(1)
    if not HAS_REQUESTS:
        print("ERROR: requests 包未安装，请在 .venv 中执行: pip install requests", file=sys.stderr)
        sys.exit(1)

    # 尺寸推断
    size = ASPECT_TO_SIZE.get(args.aspect_ratio, "1280*720")

    # 把英文 prompt 转成中文，避免 DashScope 内容审核误判
    zh_prompt = build_zh_prompt(args.prompt)

    # 调用 DashScope
    dashscope.api_key = api_key
    try:
        rsp = ImageSynthesis.call(
            api_key=api_key,
            model=model_id,
            prompt=zh_prompt,
            n=1,
            size=size,
        )
    except Exception as e:
        print(f"ERROR: DashScope 调用异常: {e}", file=sys.stderr)
        sys.exit(1)

    if rsp.status_code != HTTPStatus.OK:
        print(
            f"ERROR: DashScope API 错误 {rsp.status_code}: "
            f"{getattr(rsp, 'code', '')} - {getattr(rsp, 'message', '')}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 提取结果 URL 列表
    output_obj = getattr(rsp, "output", None) or {}
    if hasattr(output_obj, "results"):
        results = output_obj.results or []
    elif isinstance(output_obj, dict):
        results = output_obj.get("results") or []
    else:
        results = []

    if not results:
        print("ERROR: DashScope 未返回任何图片", file=sys.stderr)
        sys.exit(1)

    output_files = []
    for idx, item in enumerate(results):
        url = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
        if not url:
            continue
        out_path = os.path.join(out_dir, f"generated_{idx}.png")
        if download_url(url, out_path):
            output_files.append(out_path)

    if not output_files:
        print("ERROR: 所有图片下载失败", file=sys.stderr)
        sys.exit(1)

    # 最后一行输出 JSON（backend 读取这一行）
    print(json.dumps({"files": output_files}))


if __name__ == "__main__":
    main()
