"""Generate the host's locale files from the plugin's shared translation keys."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


for locale in ("en", "zh"):
    strings = json.loads((ROOT / "locales" / locale / "main.json").read_text(encoding="utf-8"))["customAPI"]
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
            inputs["request_nonce"]["tooltip"] = strings["node.requestNonceHint"]
            inputs["parameters"]["tooltip"] = strings["defaultParametersHint"]
            if kind == "image":
                inputs["mask"] = {"name": strings["node.mask"]}
        outputs = ["parameters"] if kind == "parameter" else ["textOutput" if kind == "text" else "imagesOutput", "response_json", "metadata_json"]
        defs[node] = {"display_name": strings[f"node.{kind}"], "description": strings[f"node.{kind}Description"], "inputs": inputs,
                      "outputs": {str(i): {"name": strings[f"node.{name}"]} for i, name in enumerate(outputs)}}
    write(ROOT / "locales" / locale / "nodeDefs.json", defs)
    write(ROOT / "locales" / locale / "commands.json", {"CustomAPI_Manage": {"label": strings["title"]}})
