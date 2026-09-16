"""Full workflow smoke test against this repository's isolated .dev ComfyUI host."""
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.conftest import fixture_config
from tests.mock_provider import TEST_KEY, png

BASE = "http://127.0.0.1:8191"
PROVIDER = "http://127.0.0.1:8192"
session = requests.Session()
session.trust_env = False


def api(path, method="GET", **kwargs):
    if path.startswith("/custom-model-api/") and path != "/custom-model-api/session":
        kwargs.setdefault("headers", {})["X-Custom-API-Session"] = management["token"]
    response = session.request(method, BASE + path, timeout=20, **kwargs)
    response.raise_for_status()
    return response.json()


def submit(prompt):
    result = api("/prompt", "POST", json={"prompt": prompt})
    for _ in range(150):
        history = api("/history/" + result["prompt_id"])
        if history:
            entry = history[result["prompt_id"]]
            assert entry["status"]["status_str"] == "success", entry["status"]
            return entry
        time.sleep(0.1)
    raise AssertionError("Workflow did not finish")


def text_inputs(**updates):
    return {"provider_id": "fixture", "model_id": "text-model", "operation": "text", "prompt": "本地工作流集成测试",
            "parameters": "{}", "cache_mode": "reuse", "request_nonce": 0, "system": "", **updates}


management = api("/custom-model-api/session", "POST", json={}, headers={"Origin": BASE})
api("/custom-model-api/network-policy/local", "POST", json={"origin": PROVIDER})
config = fixture_config(PROVIDER + "/v1")
config["revision"] = api("/custom-model-api/config")["revision"]
api("/custom-model-api/config", "PUT", json={"config": config, "secrets": {"fixture": TEST_KEY}})
assert len(api("/object_info/CustomAPIText")) == 1
workflow = {"1": {"class_type": "CustomAPIText", "inputs": text_inputs()}}
first = submit(workflow)
assert "测试成功" in first["outputs"]["1"]["text"][0]
before = session.get(PROVIDER + "/stats").json()["posts"]
submit(workflow)
after = session.get(PROVIDER + "/stats").json()["posts"]
assert after == before, "Unchanged workflow repeated a paid API call"
workflow["1"]["inputs"]["request_nonce"] = 1
submit(workflow)
assert session.get(PROVIDER + "/stats").json()["posts"] == after + 1
print("Text execution, cache reuse, request nonce: PASS")

image_inputs = text_inputs(model_id="image-model", operation="image")
image_inputs.pop("system")
image_workflow = {"1": {"class_type": "CustomAPIImage", "inputs": image_inputs},
                  "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0], "filename_prefix": "custom-api-smoke"}}}
image_history = submit(image_workflow)
files = image_history["outputs"]["2"]["images"]
assert len(files) == 2
for file in files:
    response = session.get(BASE + "/view", params=file)
    response.raise_for_status()
    assert response.content.startswith(b"\x89PNG")
    from PIL import Image
    import io
    with Image.open(io.BytesIO(response.content)) as im:
        assert TEST_KEY not in json.dumps(im.info)
print("Image API -> SaveImage, multiple image sizes, metadata without key: PASS")

upload = session.post(BASE + "/upload/image", files={"image": ("fixture.png", png(), "image/png")}).json()
vision = {"1": {"class_type": "LoadImage", "inputs": {"image": upload["name"]}},
          "2": {"class_type": "CustomAPIText", "inputs": text_inputs(operation="vision", image=["1", 0])}}
assert "测试成功" in submit(vision)["outputs"]["2"]["text"][0]
edit_inputs = {**image_inputs, "operation": "image_edit", "image": ["3", 0]}
edit = {"3": {"class_type": "LoadImage", "inputs": {"image": upload["name"]}},
        "1": {"class_type": "CustomAPIImage", "inputs": edit_inputs},
        "2": image_workflow["2"]}
assert len(submit(edit)["outputs"]["2"]["images"]) == 1
print("LoadImage -> vision and multipart image edit: PASS")

config = api("/custom-model-api/config")
config["models"][1]["bindings"]["image"] = "async-image-example"
config["templates"][-1]["poll"]["interval"] = 0.2
api("/custom-model-api/config", "PUT", json={"config": config})
assert len(submit(image_workflow)["outputs"]["2"]["images"]) == 1
print("Template configuration invalidates cache; async image -> SaveImage: PASS")
config = api("/custom-model-api/config")
config["models"][1]["bindings"]["image"] = "images-generate"
api("/custom-model-api/config", "PUT", json={"config": config})
print("All real ComfyUI workflow checks passed.")
