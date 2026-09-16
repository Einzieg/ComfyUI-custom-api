import asyncio
import json

from aiohttp import ClientSession, web

from custom_api.routes import register_routes
from tests.mock_provider import TEST_KEY


def test_management_routes_and_debug_jobs(configured):
    store, engine, _ = configured
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
            async with ClientSession() as client:
                code = json.loads((store.directory / "management-access.json").read_text(encoding="utf-8"))["pairing_code"]
                async with client.post(root + "/session", json={"pairing_code": code}) as response:
                    client.headers["X-Custom-API-Session"] = (await response.json())["token"]
                async with client.get(root + "/config") as response:
                    public = await response.json()
                    assert response.headers["Cache-Control"] == "no-store"
                    assert TEST_KEY not in json.dumps(public)
                async with client.get(root + "/export") as response:
                    exported = await response.json()
                    assert "has_key" not in exported["providers"][0]
                async with client.put(root + "/config", data="{}", headers={"Origin": "https://malicious.invalid"}) as response:
                    assert response.status == 403
                async with client.put(root + "/config", data="{}") as response:
                    assert response.status == 415
                async with client.post(root + "/test", json={"model_id": "text-model", "operation": "text", "prompt": "test"}) as response:
                    assert response.status == 202
                    job = await response.json()
                for _ in range(100):
                    async with client.get(root + "/jobs/" + job["id"]) as response:
                        state = await response.json()
                    if state["state"] != "running":
                        break
                    await asyncio.sleep(0.02)
                assert state["state"] == "success"
                assert "测试成功" in state["result"]["text"]
                async with client.post(root + "/import", json={"config": exported}) as response:
                    assert response.status == 200
                    imported = await response.json()
                    assert len(imported["providers"]) == 2
                    assert not imported["providers"][-1]["has_key"]
                    assert imported["models"][-1]["provider_id"] != "fixture"
        finally:
            await runner.cleanup()
    asyncio.run(scenario())
