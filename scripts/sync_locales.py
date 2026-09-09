"""Generate the host's locale files from the plugin's shared translation keys."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


for locale in ("en", "zh"):
    strings = json.loads((ROOT / "web" / "locales" / f"{locale}.json").read_text(encoding="utf-8"))
    defs = {}
    for node, kind in (("CustomAPIText", "text"), ("CustomAPIImage", "image"), ("CustomAPIParameter", "parameter")):
        fields = ["name", "value", "value_type", "parameters"] if kind == "parameter" else [
            "provider_id", "model_id", "operation", "prompt", "parameters", "cache_mode", "request_nonce"]
        if kind == "text":
            fields.append("system")
        inputs = {field: {"name": strings[f"node.{field}"]} for field in fields}
        if kind != "parameter":
            inputs["image"] = {"name": strings["node.imageInput"]}
            inputs["operation"]["options"] = {op: strings[f"operation.{op}"] for op in (["text", "vision"] if kind == "text" else ["image", "image_edit"])}
            inputs["cache_mode"]["options"] = {mode: strings[f"cache.{mode}"] for mode in ("reuse", "refresh")}
            inputs["request_nonce"]["tooltip"] = "修改编号可发起新请求；不是模型随机种子。" if locale == "zh" else "Change this value for a new API request. This is not a model seed."
            inputs["parameters"]["tooltip"] = strings["defaultParametersHint"]
            if kind == "image":
                inputs["mask"] = {"name": strings["node.mask"]}
        outputs = ["parameters"] if kind == "parameter" else ["textOutput" if kind == "text" else "imagesOutput", "response_json", "metadata_json"]
        description = {"text": "调用自定义文本或识图 API，密钥由服务器管理。", "image": "调用自定义生图或图像编辑 API，输出图片列表并保留原始尺寸。", "parameter": "构建带类型的 JSON 参数，可通过连线组合多个参数。"} if locale == "zh" else {"text": "Call a custom text or vision API. Credentials stay on the server.", "image": "Generate or edit images using a custom API, preserving their original sizes.", "parameter": "Build typed JSON parameters and combine them through node connections."}
        defs[node] = {"display_name": strings[f"node.{kind}"], "description": description[kind], "inputs": inputs,
                      "outputs": {str(i): {"name": strings[f"node.{name}"]} for i, name in enumerate(outputs)}}
    write(ROOT / "locales" / locale / "nodeDefs.json", defs)
    write(ROOT / "locales" / locale / "main.json", {"settingsCategories": {"CustomAPI": strings["title"], "Language": strings["language"]}})
    write(ROOT / "locales" / locale / "settings.json", {"CustomAPI_Language": {"name": strings["language"], "options": {value: strings[f"language.{value}"] for value in ("auto", "en", "zh")}}})
    write(ROOT / "locales" / locale / "commands.json", {"CustomAPI_Manage": {"label": strings["title"]}})
