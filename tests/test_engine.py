import asyncio
import json

import pytest

from custom_api.errors import APIError
from custom_api.media import image_tensors
from tests.mock_provider import TEST_KEY, png


def test_text_vision_and_preview(configured):
    _, engine, provider = configured
    preview = asyncio.run(engine.execute("text-model", "text", prompt="中文", preview=True))
    assert not provider.calls
    assert TEST_KEY not in json.dumps(preview)
    result = asyncio.run(engine.execute("text-model", "vision", prompt='a "quote"', images=[png(), png()]))
    assert "测试成功" in result["text"]
    call = provider.calls[-1]
    assert call["headers"]["Authorization"] == "Bearer " + TEST_KEY
    assert len(call["body"]["messages"][0]["content"]) == 3
    assert call["body"]["temperature"] == 0.7
    assert TEST_KEY not in json.dumps(list(engine.history))


def test_images_decode_urls_base64_and_preserve_sizes(configured):
    _, engine, _ = configured
    result = asyncio.run(engine.execute("image-model", "image", prompt="sample"))
    assert len(result["images"]) == 2
    tensors = image_tensors(result["images"])
    assert [tuple(t.shape) for t in tensors] == [(1, 24, 32, 3), (1, 28, 20, 3)]


def test_multipart_edit_uploads_multiple_images(configured):
    _, engine, provider = configured
    result = asyncio.run(engine.execute("image-model", "image_edit", prompt="edit", images=[png(), png()]))
    assert len(result["images"]) == 1
    fields = provider.calls[0]["body"]["fields"]
    assert sum(field[0] == "image[]" for field in fields) == 2
    assert next(field[2] for field in fields if field[0] == "model") == b"fixture-image"


def test_no_retry_on_paid_post_and_safe_errors(configured):
    store, engine, provider = configured
    config = store.read()
    config["templates"][0]["request"]["path"] = "/limited"
    store.save(config)
    with pytest.raises(APIError, match="HTTP 429"):
        asyncio.run(engine.execute("text-model", "text"))
    assert len(provider.calls) == 1
    config = store.read()
    config["templates"][0]["request"]["path"] = "/leak"
    store.save(config)
    with pytest.raises(APIError) as error:
        asyncio.run(engine.execute("text-model", "text"))
    assert TEST_KEY not in str(error.value)
    assert TEST_KEY not in json.dumps(list(engine.history))


def test_discovery_retries_read_only_and_preserves_manual_settings(configured):
    store, engine, provider = configured
    provider.model_failures = 1
    result = asyncio.run(engine.discover("fixture"))
    assert result["added"] == 0
    assert len(provider.calls) == 2
    assert store.read()["models"][0]["name"] == "Fixture Text"
    assert store.read()["models"][0]["bindings"]["vision"] == "chat-completions"


def configure_poll(store):
    config = store.read()
    config["models"][1]["bindings"]["image"] = "async-image-example"
    poll = config["templates"][-1]["poll"]
    poll["interval"] = 0.2
    poll["timeout"] = 1
    poll["cancel"] = {"method": "POST", "path": "/tasks/{{task_id}}/cancel"}
    store.save(config)


def test_async_poll_and_progress(configured):
    store, engine, provider = configured
    configure_poll(store)
    updates = []
    result = asyncio.run(engine.execute("image-model", "image", progress=updates.append))
    assert len(result["images"]) == 1
    assert [u["status"] for u in updates] == ["submitted", "running", "completed"]
    assert sum(c["method"] == "POST" for c in provider.calls) == 1


def test_poll_timeout_requests_remote_cancel(configured):
    store, engine, provider = configured
    configure_poll(store)
    with pytest.raises(APIError, match="poll_timeout"):
        asyncio.run(engine.execute("image-model", "image", prompt="never"))
    assert any(call["path"].endswith("/cancel") for call in provider.calls)
    assert engine.history[0]["task_id"] == "never"


def test_interrupt_stops_polling(configured):
    store, engine, provider = configured
    configure_poll(store)
    def check():
        if provider.polls:
            raise RuntimeError("User interrupted")
    with pytest.raises(RuntimeError, match="interrupted"):
        asyncio.run(engine.execute("image-model", "image", prompt="never", check=check))
    assert engine.history[0]["status"] == "cancelled"


def test_provider_concurrency_across_requests(configured):
    store, engine, provider = configured
    config = store.read()
    config["providers"][0]["concurrency"] = 1
    config["templates"][0]["request"]["path"] = "/slow"
    store.save(config)
    async def work():
        await asyncio.gather(engine.execute("text-model", "text"), engine.execute("text-model", "text"))
    import time
    start = time.monotonic()
    asyncio.run(work())
    assert time.monotonic() - start >= 0.4


def test_missing_image_rejected_before_api_call(configured):
    _, engine, provider = configured
    with pytest.raises(APIError, match="missing_image"):
        asyncio.run(engine.execute("text-model", "vision"))
    assert not provider.calls


def test_custom_header_auth_and_form_encoding(configured):
    store, engine, provider = configured
    config = store.read()
    config["providers"][0]["auth"] = {"type": "header", "header": "X-Token"}
    config["templates"][0]["request"].update(encoding="form", body={"text": "{{prompt}}", "count": "{{params.max_tokens}}"})
    store.save(config)
    asyncio.run(engine.execute("text-model", "text", prompt="表单测试"))
    call = provider.calls[-1]
    assert call["headers"]["X-Token"] == TEST_KEY
    assert call["body"] == {"text": ["表单测试"], "count": ["1024"]}
    assert TEST_KEY not in json.dumps(engine.history[0])


def test_query_auth_redaction_and_missing_key(configured):
    store, engine, _ = configured
    config = store.read()
    config["providers"][0]["auth"] = {"type": "query", "query": "credential"}
    store.save(config)
    preview = asyncio.run(engine.execute("text-model", "text", preview=True))
    assert preview["request"]["query"]["credential"] == "[redacted]"
    config = store.read()
    store.save(config, {"fixture": ""})
    with pytest.raises(APIError, match="missing_api_key"):
        asyncio.run(engine.execute("text-model", "text"))


def test_cdn_download_does_not_forward_provider_key(configured):
    import aiohttp
    from tests.mock_provider import start_provider
    store, engine, _ = configured
    cdn = start_provider()
    from custom_api.network import NetworkPolicy, parsed_url
    engine.policy = NetworkPolicy([*engine.policy.allowed_origins, str(parsed_url(cdn.url).origin())])
    async def download():
        p = store.read()["providers"][0]
        async with aiohttp.ClientSession() as session:
            await engine.download(session, cdn.url.replace("/v1", "/image.png"), p, {"api_key": TEST_KEY})
    try:
        asyncio.run(download())
        assert "Authorization" not in cdn.calls[0]["headers"]
    finally:
        cdn.shutdown()
        cdn.server_close()


def test_binary_response_and_mask_upload(configured):
    store, engine, provider = configured
    from custom_api.media import tensor_mask
    import torch
    config = store.read()
    config["templates"][1]["request"]["path"] = "/binary"
    store.save(config)
    assert len(asyncio.run(engine.execute("image-model", "image"))["images"]) == 1
    mask = tensor_mask(torch.ones((1, 24, 32)))
    asyncio.run(engine.execute("image-model", "image_edit", images=[png()], mask=mask))
    assert any(part[0] == "mask" for part in provider.calls[-1]["body"]["fields"])


def test_image_auth_recognizes_equivalent_default_ports(configured, monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from custom_api.network import NetworkPolicy

    store, engine, _ = configured
    provider = {**store.read()["providers"][0], "base_url": "https://api.example:443/v1"}
    engine.policy = NetworkPolicy(["https://api.example"])
    captured = []
    class Session:
        @asynccontextmanager
        async def get(self, url, **kwargs):
            captured.append(kwargs["headers"])
            yield SimpleNamespace(status=200, headers={})
    async def image_bytes(response, limit):
        return png()
    monkeypatch.setattr(engine, "_bytes", image_bytes)
    asyncio.run(engine.download(Session(), "https://api.example/generated.png", provider, {"api_key": TEST_KEY}))
    assert captured == [{"Authorization": "Bearer " + TEST_KEY}]
