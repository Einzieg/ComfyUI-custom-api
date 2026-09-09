"""Vendor the official LobeHub SVG package; runtime icon loading stays local."""
import json
import re
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "openai": "OpenAI", "qwen": "Qwen 通义千问", "deepseek": "DeepSeek", "claude": "Claude",
    "anthropic": "Anthropic", "gemini": "Gemini", "google": "Google", "grok": "Grok", "xai": "xAI",
    "doubao": "Doubao 豆包", "volcengine": "Volcengine 火山引擎", "bailian": "BaiLian 百炼",
    "aliyun": "Aliyun 阿里云", "alibabacloud": "Alibaba Cloud", "siliconcloud": "SiliconFlow 硅基流动",
    "zhipu": "Zhipu 智谱", "chatglm": "ChatGLM", "minimax": "MiniMax", "moonshot": "Moonshot AI",
    "kimi": "Kimi", "ollama": "Ollama", "lmstudio": "LM Studio", "openrouter": "OpenRouter",
    "comfyui": "ComfyUI", "lobehub": "LobeHub", "huggingface": "Hugging Face", "flux": "FLUX",
    "stability": "Stability AI", "bytedance": "ByteDance", "hunyuan": "Hunyuan 混元", "stepfun": "StepFun 阶跃星辰",
    "kling": "Kling 可灵", "jimeng": "Jimeng 即梦", "hailuo": "Hailuo 海螺", "tencent": "Tencent 腾讯",
}

destination = ROOT / "web" / "assets" / "lobehub"
destination.mkdir(parents=True, exist_ok=True)
with tarfile.open(sys.argv[1]) as archive:
    package = json.load(archive.extractfile("package/package.json"))
    sources = {Path(m.name).stem: m for m in archive.getmembers()
               if re.fullmatch(r"package/icons/[a-z0-9-]+\.svg", m.name) and m.isfile()}
    catalog = []
    for slug in sorted(sources):
        if "-" in slug:
            continue  # Main brand marks, with their color variant when present.
        variant = slug + "-color" if slug + "-color" in sources else slug
        payload = archive.extractfile(sources[variant]).read().decode("utf-8")
        if re.search(r"<script|<foreignObject|(?:href|src)=['\"](?:https?:|javascript:)", payload, re.I):
            raise ValueError(f"Unexpected active SVG content: {variant}")
        (destination / f"{slug}.svg").write_text(payload, encoding="utf-8")
        catalog.append({"id": slug, "name": LABELS.get(slug, slug.capitalize()), "mono": variant == slug})
    (destination / "catalog.json").write_text(json.dumps({"package": package["name"], "version": package["version"], "icons": catalog}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Vendored {len(catalog)} LobeHub brand icons from {package['name']}@{package['version']}")
