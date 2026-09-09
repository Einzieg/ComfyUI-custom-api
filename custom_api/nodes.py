import hashlib
import json

from . import runtime
from .errors import APIError
from .media import image_tensors, tensor_images, tensor_mask


def inputs(operations, image=False):
    result = {
        "required": {
            "provider_id": ("STRING", {"default": "", "tooltip": "Select a provider using the model picker."}),
            "model_id": ("STRING", {"default": "", "tooltip": "Stable model configuration ID."}),
            "operation": (operations,),
            "prompt": ("STRING", {"multiline": True, "default": ""}),
            "parameters": ("STRING", {"multiline": True, "default": "{}", "tooltip": "JSON parameters; can also be connected from another node."}),
            "cache_mode": (["reuse", "refresh"], {"default": "reuse"}),
            "request_nonce": ("INT", {"default": 0, "min": 0, "max": 2147483647, "tooltip": "Change this number to make a new API request."}),
        },
        "optional": {"image": ("IMAGE",)},
        "hidden": {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO"},
    }
    if image:
        result["optional"]["mask"] = ("MASK",)
    else:
        result["required"]["system"] = ("STRING", {"multiline": True, "default": ""})
    return result


def localized_error(error, language):
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "web" / "locales" / ("zh.json" if language == "zh" else "en.json")
    try:
        messages = json.loads(path.read_text(encoding="utf-8"))
        message = messages.get("error." + error.code, error.code)
    except (OSError, ValueError):
        message = error.code
    return RuntimeError(f"{message} [{error.code}]" + (f"\n{error.detail}" if error.detail else ""))


class APIBase:
    CATEGORY = "Model API"
    FUNCTION = "execute"

    @classmethod
    def IS_CHANGED(cls, model_id="", operation="text", cache_mode="reuse", **kwargs):
        if cache_mode == "refresh":
            return float("nan")
        try:
            provider, model, template = runtime.engine.resolve(model_id, operation)
            provider = {k: v for k, v in provider.items() if k not in ("name", "icon", "models_request", "models_path", "model_id_path", "model_name_path")}
            model = {k: v for k, v in model.items() if k not in ("name", "group", "source")}
            template = {k: v for k, v in template.items() if k != "name"}
            template["parameters"] = [{k: v for k, v in p.items() if k != "label"} for p in template.get("parameters", [])]
            value = [provider, model, template, runtime.store.secret(provider)]
            return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        except APIError:
            return "unavailable-" + str(runtime.store.read()["revision"])

    async def call(self, provider_id, model_id, operation, prompt, parameters, image=None, mask=None, system="", unique_id=None, extra_pnginfo=None, **kwargs):
        language = "en"
        for node in (extra_pnginfo or {}).get("workflow", {}).get("nodes", []):
            if str(node.get("id")) == str(unique_id):
                language = node.get("properties", {}).get("custom_api_language", "en")
                break
        try:
            try:
                params = json.loads(parameters)
            except (ValueError, TypeError) as exc:
                raise APIError("invalid_parameters", "Expected a JSON object.") from exc
            if not isinstance(params, dict):
                raise APIError("invalid_parameters", "Expected a JSON object.")
            provider, _, _ = runtime.engine.resolve(model_id, operation)
            if provider_id and provider["id"] != provider_id:
                raise APIError("model_unavailable", "Model does not belong to the selected provider.")
            import comfy.model_management
            def progress(data):
                if unique_id:
                    from server import PromptServer
                    PromptServer.instance.send_sync("custom-api-progress", {"node_id": unique_id, **data})
            return await runtime.engine.execute(model_id, operation, prompt, system, params,
                                                tensor_images(image), tensor_mask(mask),
                                                check=comfy.model_management.throw_exception_if_processing_interrupted,
                                                progress=progress)
        except APIError as error:
            raise localized_error(error, language) from None


class APIText(APIBase):
    DESCRIPTION = "Call a text or vision model configured in Model API. Credentials stay on the server."
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "response_json", "metadata_json")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return inputs(["text", "vision"])

    async def execute(self, **kwargs):
        result = await self.call(**kwargs)
        return {"ui": {"text": [result["text"]]}, "result": (result["text"], json.dumps(result["raw"], ensure_ascii=False), json.dumps(result["metadata"], ensure_ascii=False))}


class APIImage(APIBase):
    DESCRIPTION = "Generate or edit images with an API. Outputs an image list, preserving each image's original size."
    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "response_json", "metadata_json")
    OUTPUT_IS_LIST = (True, False, False)

    @classmethod
    def INPUT_TYPES(cls):
        return inputs(["image", "image_edit"], image=True)

    async def execute(self, **kwargs):
        result = await self.call(**kwargs)
        return image_tensors(result["images"]), json.dumps(result["raw"], ensure_ascii=False), json.dumps(result["metadata"], ensure_ascii=False)


class APIParameter:
    CATEGORY = "Model API"
    FUNCTION = "build"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("parameters",)
    DESCRIPTION = "Add a typed parameter to a JSON object. Chain nodes to build parameters for an API node."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"name": ("STRING", {"default": "temperature"}),
                             "value": ("STRING", {"default": "0.7", "multiline": True}),
                             "value_type": (["json", "string"],)},
                "optional": {"parameters": ("STRING", {"default": "{}", "forceInput": True})}}

    def build(self, name, value, value_type, parameters="{}"):
        try:
            result = json.loads(parameters)
            if not isinstance(result, dict) or not name:
                raise ValueError("Expected a parameter name and an object.")
            result[name] = value if value_type == "string" else json.loads(value)
            return (json.dumps(result, ensure_ascii=False),)
        except ValueError as exc:
            raise ValueError("invalid_parameters: " + str(exc)) from None


NODE_CLASS_MAPPINGS = {"CustomAPIText": APIText, "CustomAPIImage": APIImage, "CustomAPIParameter": APIParameter}
NODE_DISPLAY_NAME_MAPPINGS = {"CustomAPIText": "API Text / Vision", "CustomAPIImage": "API Image", "CustomAPIParameter": "API Parameter"}
