import json

from custom_api import runtime
from custom_api.nodes import APIParameter, APIText


def test_cache_tracks_request_configuration_not_display_labels(configured, monkeypatch):
    store, engine, _ = configured
    monkeypatch.setattr(runtime, "store", store)
    monkeypatch.setattr(runtime, "engine", engine)
    initial = APIText.IS_CHANGED(model_id="text-model", operation="text")
    config = store.read()
    config["providers"][0]["name"] = "中文名称"
    config["providers"][0]["icon"] = "☀"
    config["models"][0]["name"] = "新别名"
    config["templates"][0]["parameters"][0]["label"] = {"zh": "温度"}
    store.save(config)
    assert APIText.IS_CHANGED(model_id="text-model", operation="text") == initial
    config = store.read()
    config["templates"][0]["request"]["path"] = "/other"
    store.save(config)
    assert APIText.IS_CHANGED(model_id="text-model", operation="text") != initial
    assert "language" not in APIText.INPUT_TYPES()["required"]


def test_parameter_nodes_keep_json_types_and_merge():
    builder = APIParameter()
    first = builder.build("temperature", "0.3", "json")[0]
    second = builder.build("prompt", "quoted text", "string", first)[0]
    assert json.loads(second) == {"temperature": 0.3, "prompt": "quoted text"}
