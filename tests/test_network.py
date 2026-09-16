import asyncio
import copy
import json
import socket

import aiohttp
import pytest
from aiohttp import web

from custom_api.engine import Engine
from custom_api.errors import APIError
from custom_api.network import NetworkPolicy, PublicResolver, parsed_url
from custom_api.routes import register_routes
from custom_api.store import ConfigStore
from tests.conftest import fixture_config
from tests.mock_provider import start_provider


@pytest.mark.parametrize("url", [
    "https://unapproved.example/v1", "http://127.0.0.1:8188/", "http://10.0.0.1/",
    "http://169.254.169.254/latest/meta-data/", "http://[::1]/",
    "https://api.example.evil.test/", "https://api.example:444/", "http://api.example/",
])
def test_unapproved_origins_fail_closed(url):
    with pytest.raises(APIError, match="network_origin_blocked"):
        NetworkPolicy(mode="strict", allowed_origins=["https://api.example"]).check_url(url)
    with pytest.raises(APIError):
        NetworkPolicy(mode="strict").check_url(url)


@pytest.mark.parametrize("url", [
    "http://169.254.169.254", "http://[fe80::1]", "http://[::ffff:169.254.169.254]",
    "http://[64:ff9b::a9fe:a9fe]", "http://[2002:a9fe:a9fe::1]", "http://0.0.0.0",
    "http://224.0.0.1", "http://100.100.100.200",
])
def test_metadata_and_special_addresses_cannot_be_approved(url):
    with pytest.raises(APIError, match="network_address_blocked"):
        NetworkPolicy(mode="strict", allowed_origins=[url])


@pytest.mark.parametrize("url", [
    "https://*.example", "https://api.example/path", "https://api.example?target=1",
    "https://user:secret@api.example", "https://api.example./", "https://api.example\\@evil.test",
    "https://api.example\n", "http://[fe80::1%25eth0]", "file:///etc/passwd",
    "http://2130706433", "http://127.1", "http://0177.0.0.1", "http://0x7f000001", "http://0x7f.0.0.1",
])
def test_ambiguous_or_wildcard_allowlist_entries_rejected(url):
    with pytest.raises(APIError):
        NetworkPolicy(mode="strict", allowed_origins=[url])


def test_local_services_require_an_explicit_ip_and_port(provider):
    origin = str(parsed_url(provider.url).origin())
    policy = NetworkPolicy(mode="strict", allowed_origins=[origin])
    assert policy.check_url(provider.url) == provider.url
    with pytest.raises(APIError):
        policy.check_url("http://127.0.0.1:8188")


def test_missing_invalid_and_valid_operator_policy(tmp_path):
    path = tmp_path / "network-policy.json"
    assert not NetworkPolicy.from_file(path).allowed_origins
    path.write_text('{"allowed_origins": "*"}', encoding="utf-8")
    with pytest.raises(APIError, match="network_policy_invalid"):
        NetworkPolicy.from_file(path)
    path.write_text(json.dumps({"allowed_origins": ["https://API.EXAMPLE:443"], "allowed_key_env": ["EXAMPLE_KEY"]}), encoding="utf-8-sig")
    policy = NetworkPolicy.from_file(path)
    assert policy.allowed_origins == {"https://api.example"}
    assert policy.allowed_key_env == {"EXAMPLE_KEY"}


def dns_answer(ip, port):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))


@pytest.mark.parametrize("addresses", [
    ["127.0.0.1"], ["10.0.0.1"], ["169.254.169.254"], ["::ffff:127.0.0.1"],
    ["64:ff9b::a9fe:a9fe"], ["8.8.8.8", "192.168.1.1"], ["fc00::1"], [],
])
def test_dns_answers_are_checked_before_connection(monkeypatch, addresses):
    async def scenario():
        async def answers(host, port, **kwargs):
            return [dns_answer(ip, port) for ip in addresses]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", answers)
        with pytest.raises(APIError, match="network_address_blocked"):
            await PublicResolver().resolve("approved.example", 443)
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["default", "strict"])
def test_dns_results_are_pinned_and_rebinding_is_rechecked(monkeypatch, mode):
    async def scenario():
        calls = []
        async def answers(host, port, **kwargs):
            calls.append(host)
            return [dns_answer("8.8.8.8" if len(calls) == 1 else "127.0.0.1", port)]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", answers)
        async with NetworkPolicy(mode=mode, allowed_origins=["https://approved.example"]).session(aiohttp.ClientTimeout(total=2)) as session:
            results = await session.connector._resolve_host("approved.example", 443)
            assert len(calls) == 1
            assert results[0]["host"] == "8.8.8.8"
            assert results[0]["flags"] & socket.AI_NUMERICHOST
            with pytest.raises(APIError, match="network_address_blocked"):
                await session.connector._resolve_host("approved.example", 443)
            assert len(calls) == 2
    asyncio.run(scenario())


def test_config_import_and_disk_execution_cannot_authorize_an_internal_host(configured, tmp_path):
    store, _, permitted = configured
    target = start_provider()
    policy_path = store.directory / "network-policy.json"
    original_policy = json.dumps(store.network_policy.as_dict())
    policy_path.write_text(original_policy, encoding="utf-8")
    store = ConfigStore(store.directory)
    engine = Engine(store)
    malicious = fixture_config(target.url)
    malicious["revision"] = store.read()["revision"]
    malicious["allowed_origins"] = [str(parsed_url(target.url).origin())]
    malicious["network_policy"] = {"allowed_origins": malicious["allowed_origins"]}

    async def scenario():
        routes = web.RouteTableDef()
        register_routes(routes, store, engine)
        app = web.Application()
        app.add_routes(routes)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        root = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/custom-model-api"
        try:
            async with aiohttp.ClientSession() as client:
                code = json.loads((store.directory / "management-access.json").read_text(encoding="utf-8"))["pairing_code"]
                async with client.post(root + "/session", json={"pairing_code": code}) as response:
                    client.headers["X-Custom-API-Session"] = (await response.json())["token"]
                # A direct HTTP client sends no browser Origin header.
                for method, path, body in (("PUT", "/config", {"config": malicious}), ("POST", "/import", {"config": malicious})):
                    async with client.request(method, root + path, json=body) as response:
                        assert response.status == 403
                        assert (await response.json())["error"]["code"] == "network_origin_blocked"
                assert store.read()["providers"][0]["base_url"] == permitted.url
                assert policy_path.read_text(encoding="utf-8") == original_policy
                # Disk configuration cannot bypass the independent execution policy.
                (store.directory / "config.json").write_text(json.dumps(malicious), encoding="utf-8")
                for action in (engine.execute("text-model", "text"), engine.discover("fixture")):
                    with pytest.raises(APIError, match="network_origin_blocked"):
                        await action
                assert not target.calls
        finally:
            await runner.cleanup()
    try:
        asyncio.run(scenario())
    finally:
        target.shutdown()
        target.server_close()


def test_proxy_and_authority_headers_cannot_bypass_policy(configured):
    store, engine, provider = configured
    config = store.read()
    config["providers"][0]["proxy"] = "http://169.254.169.254"
    with pytest.raises(APIError, match="network_proxy_blocked"):
        store.save(config)
    for header in ("Host", "hOsT", "Proxy-Authorization", "Proxy-Connection"):
        config = store.read()
        config["templates"][0]["request"]["headers"][header] = "internal.invalid"
        with pytest.raises(APIError, match="network_header_blocked"):
            store.save(config)
    provider_config = copy.deepcopy(store.read()["providers"][0])
    provider_config["auth"] = {"type": "header", "header": "Host"}
    with pytest.raises(APIError, match="network_header_blocked"):
        engine.build(provider_config, {"path": "/"}, {"api_key": "internal.invalid"})
    assert not provider.calls


def test_environment_keys_require_separate_operator_approval(configured, monkeypatch):
    store, _, _ = configured
    monkeypatch.setenv("UNRELATED_SYSTEM_SECRET", "must-not-read")
    config = store.read()
    config["providers"][0]["api_key_env"] = "UNRELATED_SYSTEM_SECRET"
    with pytest.raises(APIError, match="network_key_env_blocked"):
        store.save(config)
    assert store.secret(config["providers"][0]) == ""


def test_unapproved_image_url_and_dns_alias_never_reach_target(configured, monkeypatch):
    store, engine, provider = configured
    target = start_provider()
    async def scenario():
        async with engine.policy.session(aiohttp.ClientTimeout(total=2)) as session:
            with pytest.raises(APIError, match="network_origin_blocked"):
                await engine.download(session, target.url.replace("/v1", "/image.png"), store.read()["providers"][0], {})
        alias = f"http://approved.example:{target.server_port}"
        policy = NetworkPolicy(mode="strict", allowed_origins=[alias])
        engine.policy = policy
        async def answers(host, port, **kwargs):
            return [dns_answer("127.0.0.1", port)]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", answers)
        async with policy.session(aiohttp.ClientTimeout(total=2)) as session:
            with pytest.raises(APIError, match="network_address_blocked"):
                await engine.download(session, alias + "/image.png", store.read()["providers"][0], {})
        assert not target.calls
    try:
        asyncio.run(scenario())
    finally:
        target.shutdown()
        target.server_close()


def test_image_redirect_is_checked_before_the_next_connection(configured):
    store, engine, provider = configured
    target = start_provider()
    provider.redirect_url = target.url + "/generated.png"
    async def scenario():
        async with engine.policy.session(aiohttp.ClientTimeout(total=2)) as session:
            with pytest.raises(APIError, match="network_origin_blocked"):
                p = store.read()["providers"][0]
                await engine.download(session, provider.url + "/redirect", p, {"api_key": store.secret(p)})
        assert len(provider.calls) == 1
        assert not target.calls
    try:
        asyncio.run(scenario())
    finally:
        target.shutdown()
        target.server_close()
