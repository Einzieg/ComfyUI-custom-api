import asyncio
import json
from contextlib import asynccontextmanager

import aiohttp
import pytest
from aiohttp import web

from custom_api.access import loopback_listener
from custom_api.engine import Engine
from custom_api.errors import APIError
from custom_api.network import NetworkPolicy, parsed_url
from custom_api.routes import register_routes
from custom_api.store import ConfigStore
from tests.conftest import fixture_config
from tests.mock_provider import TEST_KEY


@asynccontextmanager
async def management(store, *, local=False):
    engine = Engine(store)
    routes = web.RouteTableDef()
    register_routes(routes, store, engine, local_session=local)
    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    origin = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
    try:
        async with aiohttp.ClientSession() as client:
            yield client, origin, engine
    finally:
        await runner.cleanup()


def pairing_code(store):
    return json.loads((store.directory / "management-access.json").read_text(encoding="utf-8"))["pairing_code"]


async def pair(client, origin, code):
    async with client.post(origin + "/custom-model-api/session", json={"pairing_code": code}) as response:
        assert response.status == 200
        client.headers["X-Custom-API-Session"] = (await response.json())["token"]


@pytest.mark.parametrize("listen, expected", [("127.0.0.1", True), ("::1", True), ("127.0.0.1,::1", True),
                                               ("0.0.0.0", False), ("::", False), ("127.0.0.1,192.168.1.2", False)])
def test_only_loopback_listeners_auto_pair(listen, expected):
    assert loopback_listener(listen) == expected


def test_management_authentication_origin_and_remote_pairing(tmp_path):
    store = ConfigStore(tmp_path)

    async def scenario():
        async with management(store) as (client, origin, _):
            root = origin + "/custom-model-api"
            for method, path in [("GET", "/config"), ("GET", "/export"), ("GET", "/history"),
                                 ("PUT", "/config"), ("POST", "/import"), ("POST", "/test"),
                                 ("PUT", "/network-policy"), ("POST", "/network-policy/local"),
                                 ("POST", "/providers/example/models"), ("GET", "/jobs/example"),
                                 ("POST", "/jobs/example/cancel")]:
                async with client.request(method, root + path, json={}) as response:
                    assert response.status == 401, path
            for body in ({}, {"pairing_code": "wrong"}, {"pairing_code": "中文"}):
                async with client.post(root + "/session", json=body, headers={"Origin": origin}) as response:
                    assert response.status == 401
            await pair(client, origin, pairing_code(store))
            for headers in ({"Origin": "https://evil.example"}, {"Origin": origin.replace("http:", "https:")},
                            {"Origin": origin, "Sec-Fetch-Site": "cross-site"}, {"Origin": "null"}):
                async with client.get(root + "/config", headers=headers) as response:
                    assert response.status == 403
            async with client.get(root + "/config", headers={"Origin": origin}) as response:
                assert response.status == 200
                assert "management" not in await response.text()
            old_token = client.headers["X-Custom-API-Session"]
        async with management(store) as (client, origin, _):
            async with client.get(origin + "/custom-model-api/config", headers={"X-Custom-API-Session": old_token}) as response:
                assert response.status == 401
            await pair(client, origin, pairing_code(store))
    asyncio.run(scenario())


def test_local_auto_session_rejects_dns_rebinding_forwarding_and_missing_origin(tmp_path):
    async def scenario():
        async with management(ConfigStore(tmp_path), local=True) as (client, origin, _):
            root = origin + "/custom-model-api"
            for headers in ({}, {"Origin": "http://evil.example", "Host": "evil.example"},
                            {"Origin": origin, "X-Forwarded-For": "127.0.0.1"},
                            {"Origin": origin, "Forwarded": "for=127.0.0.1"}):
                async with client.post(root + "/session", json={}, headers=headers) as response:
                    assert response.status == 401
            async with client.post(root + "/session", json={}, headers={"Origin": origin}) as response:
                assert response.status == 200
                client.headers["X-Custom-API-Session"] = (await response.json())["token"]
            async with client.get(root + "/config") as response:
                assert response.status == 200
    asyncio.run(scenario())


def test_default_mode_grants_are_separate_persistent_and_revocable(tmp_path, provider):
    store = ConfigStore(tmp_path)
    assert store.network_policy.mode == "default"
    # No file or per-domain allow-list is needed for public APIs and CDNs.
    for url in ("https://api.example/v1", "https://cdn.example/image.png", "http://8.8.8.8/"):
        assert store.network_policy.check_url(url) == url

    async def scenario():
        async with management(store) as (client, origin, engine):
            root = origin + "/custom-model-api"
            await pair(client, origin, pairing_code(store))
            config = fixture_config(provider.url)
            config["local_origins"] = [str(parsed_url(provider.url).origin())]
            config["network_policy"] = {"mode": "default", "local_origins": config["local_origins"]}
            for path, method in (("/config", "PUT"), ("/import", "POST")):
                async with client.request(method, root + path, json={"config": config}) as response:
                    assert response.status == 403
            assert not store.network_policy.local_origins
            assert not provider.calls
            for bad in ("http://169.254.169.254", "http://100.100.100.200", "http://localhost:11434", "https://api.example", "http://127.0.0.1/v1"):
                async with client.post(root + "/network-policy/local", json={"origin": bad}) as response:
                    assert response.status in (400, 403)
            local = str(parsed_url(provider.url).origin())
            async with client.post(root + "/network-policy/local", json={"origin": local}) as response:
                assert response.status == 200
            store.save(fixture_config(provider.url), {"fixture": TEST_KEY})
            assert (await engine.discover("fixture"))["added"] >= 0
            assert provider.calls
            assert NetworkPolicy.from_file(tmp_path / "network-policy.json").local_origins == {local}
            async with client.get(root + "/export") as response:
                exported = await response.text()
                assert "local_origins" not in exported
                assert pairing_code(store) not in exported
            policy = store.network_policy.as_dict()
            policy["local_origins"] = []
            async with client.put(root + "/network-policy", json=policy) as response:
                assert response.status == 200
            calls = len(provider.calls)
            with pytest.raises(APIError, match="network_address_blocked"):
                await engine.discover("fixture")
            assert len(provider.calls) == calls
            policy.update(mode="strict", allowed_origins=[local])
            async with client.put(root + "/network-policy", json=policy) as response:
                assert response.status == 200
            await engine.discover("fixture")
            with pytest.raises(APIError, match="network_origin_blocked"):
                engine.policy.check_url("https://api.example")
            # Invalid updates preserve both the live policy and disk state.
            async with client.put(root + "/network-policy", json={"mode": "anything"}) as response:
                assert response.status == 400
            assert store.network_policy.mode == "strict"
            assert NetworkPolicy.from_file(tmp_path / "network-policy.json").mode == "strict"
    asyncio.run(scenario())


@pytest.mark.parametrize("url", ["http://127.0.0.1", "http://10.0.0.1", "http://[::1]", "http://169.254.169.254",
                                "http://[::ffff:127.0.0.1]", "http://100.100.100.200", "http://[64:ff9b::7f00:1]"])
def test_default_mode_blocks_private_and_special_ip_literals(url):
    with pytest.raises(APIError, match="network_address_blocked"):
        NetworkPolicy().check_url(url)


def test_default_mode_image_redirect_cannot_reach_unapproved_local_server(tmp_path, provider):
    from tests.mock_provider import start_provider
    target = start_provider()
    provider.redirect_url = target.url + "/generated.png"
    policy = NetworkPolicy(local_origins=[str(parsed_url(provider.url).origin())])
    store = ConfigStore(tmp_path, policy)
    store.save(fixture_config(provider.url), {"fixture": TEST_KEY})
    engine = Engine(store)

    async def scenario():
        async with policy.session(aiohttp.ClientTimeout(total=2)) as session:
            with pytest.raises(APIError, match="network_address_blocked"):
                await engine.download(session, provider.url + "/redirect", store.read()["providers"][0], {"api_key": TEST_KEY})
        assert len(provider.calls) == 1
        assert not target.calls
    try:
        asyncio.run(scenario())
    finally:
        target.shutdown()
        target.server_close()
