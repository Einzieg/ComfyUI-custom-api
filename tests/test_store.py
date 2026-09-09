import json

import pytest

from custom_api.errors import APIError
from custom_api.presets import new_config
from custom_api.store import ConfigStore, redact
from tests.mock_provider import TEST_KEY


def test_lobehub_icon_persistence_and_validation(configured):
    store, _, _ = configured
    config = store.public()
    config["providers"][0]["icon"] = "lobehub:qwen"
    store.save(config)
    assert store.public()["providers"][0]["icon"] == "lobehub:qwen"
    for invalid in ("lobehub:../../config", "lobehub:missing-icon", "lobehub:notarealbrand"):
        config = store.public()
        config["providers"][0]["icon"] = invalid
        with pytest.raises(APIError, match="invalid_config"):
            store.save(config)
    assert store.public()["providers"][0]["icon"] == "lobehub:qwen"


def test_credentials_never_enter_config_or_export(configured):
    store, _, _ = configured
    assert TEST_KEY not in json.dumps(store.public())
    assert TEST_KEY not in (store.directory / "config.json").read_text(encoding="utf-8")
    assert store.public()["providers"][0]["has_key"]
    config = store.public()
    config["providers"][0]["name"] = "Renamed provider"
    store.save(config)
    assert store.secret(config["providers"][0]) == TEST_KEY


def test_optimistic_save_preserves_other_window_changes(configured):
    store, _, _ = configured
    old = store.public()
    changed = store.public()
    changed["providers"][0]["name"] = "First window"
    store.save(changed)
    with pytest.raises(APIError, match="config_conflict"):
        store.save(old)
    assert store.public()["providers"][0]["name"] == "First window"


def test_failed_validation_preserves_configuration(configured):
    store, _, _ = configured
    config = store.read()
    config["templates"][0]["kind"] = "bad"
    with pytest.raises(APIError):
        store.save(config)
    assert store.read()["templates"][0]["kind"] == "text"


def test_missing_and_corrupt_config_do_not_get_overwritten(tmp_path):
    store = ConfigStore(tmp_path)
    assert store.read() == new_config()
    (tmp_path / "config.json").write_text("broken", encoding="utf-8")
    with pytest.raises(APIError, match="config_read_failed"):
        store.read()
    assert (tmp_path / "config.json").read_text(encoding="utf-8") == "broken"


def test_environment_key_and_explicit_clear(configured, monkeypatch):
    store, _, _ = configured
    config = store.public()
    store.save(config, {"fixture": ""})
    assert not store.public()["providers"][0]["has_key"]
    config = store.public()
    config["providers"][0]["api_key_env"] = "CUSTOM_API_TEST_KEY"
    monkeypatch.setenv("CUSTOM_API_TEST_KEY", TEST_KEY)
    store.save(config)
    assert store.secret(store.read()["providers"][0]) == TEST_KEY


def test_icons_and_binding_references_are_validated(configured):
    store, _, _ = configured
    config = store.read()
    config["providers"][0]["icon"] = "data:image/svg+xml;base64,PHN2Zz4="
    with pytest.raises(APIError):
        store.save(config)
    config = store.read()
    config["models"][0]["bindings"]["text"] = "images-generate"
    with pytest.raises(APIError):
        store.save(config)


def test_redaction():
    result = redact({"Authorization": "Bearer " + TEST_KEY, "message": "echo " + TEST_KEY, "nested": [{"apiKey": "xxx"}]}, [TEST_KEY])
    assert TEST_KEY not in json.dumps(result)
    assert "xxx" not in json.dumps(result)


def test_credential_references_do_not_rewrite_json_keys_or_model_ids(configured):
    store, _, _ = configured
    config = store.read()
    config["templates"][0]["request"]["headers"]["Authorization"] = "Bearer name"
    store.save(config, {"fixture": "name"})
    saved = store.read()
    assert saved["providers"][0]["name"] == "Local fixture"
    assert saved["templates"][0]["request"]["headers"]["Authorization"] == "Bearer {{api_key}}"
    assert saved["models"][0]["model_id"] == "fixture-text"
    assert store.public()["models"][0]["name"] == "Fixture Text"
