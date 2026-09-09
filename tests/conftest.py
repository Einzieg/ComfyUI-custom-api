import pytest

from custom_api.engine import Engine
from custom_api.presets import new_config
from custom_api.store import ConfigStore
from tests.mock_provider import TEST_KEY, start_provider


def fixture_config(url):
    config = new_config()
    config["providers"] = [{"id": "fixture", "name": "Local fixture", "icon": "◈", "base_url": url, "enabled": True, "auth": {"type": "bearer"}, "timeout": 5, "concurrency": 2}]
    config["models"] = [{"id": "text-model", "provider_id": "fixture", "model_id": "fixture-text", "name": "Fixture Text", "bindings": {"text": "chat-completions", "vision": "chat-completions"}, "defaults": {}},
                        {"id": "image-model", "provider_id": "fixture", "model_id": "fixture-image", "name": "Fixture Image", "bindings": {"image": "images-generate", "image_edit": "images-edit"}, "defaults": {}}]
    return config


@pytest.fixture
def provider():
    server = start_provider()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def configured(tmp_path, provider):
    store = ConfigStore(tmp_path / "private")
    store.save(fixture_config(provider.url), {"fixture": TEST_KEY})
    return store, Engine(store), provider
