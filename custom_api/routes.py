import asyncio
import copy
import functools
import json
import time
import uuid
from urllib.parse import urlsplit

from aiohttp import web

from .errors import APIError
from .media import decode_image, preview_url
from .store import redact

PREFIX = "/custom-model-api"


def register_routes(routes, store, engine):
    jobs = {}

    def route(method, path):
        def decorate(fn):
            @functools.wraps(fn)
            async def handler(request):
                try:
                    # JSON-only mutations and same-origin checks prevent browser form/CSRF requests.
                    origin = request.headers.get("Origin")
                    if origin and urlsplit(origin).netloc != request.host:
                        raise APIError("forbidden_origin", status=403)
                    if method != "GET" and request.content_type != "application/json":
                        raise APIError("invalid_request", "Expected application/json.", 415)
                    response = await fn(request)
                    response.headers["Cache-Control"] = "no-store"
                    response.headers["X-Content-Type-Options"] = "nosniff"
                    return response
                except APIError as exc:
                    error = redact(exc.as_dict(), store.secrets())
                    return web.json_response({"error": error}, status=exc.status, headers={"Cache-Control": "no-store"})
                except (ValueError, TypeError, KeyError) as exc:
                    return web.json_response({"error": {"code": "invalid_request", "detail": type(exc).__name__}}, status=400)
            getattr(routes, method.lower())(PREFIX + path)(handler)
            return handler
        return decorate

    async def payload(request):
        if request.content_length and request.content_length > 48 * 1024 * 1024:
            raise APIError("media_too_large", status=413)
        value = await request.json()
        if not isinstance(value, dict):
            raise APIError("invalid_request")
        return value

    @route("GET", "/config")
    async def get_config(request):
        return web.json_response(store.public())

    @route("PUT", "/config")
    async def put_config(request):
        body = await payload(request)
        return web.json_response(store.save(body["config"], body.get("secrets", {})))

    @route("GET", "/export")
    async def export_config(request):
        config = store.public()
        config["revision"] = 0
        for provider in config["providers"]:
            provider.pop("has_key", None)
        return web.json_response(config, headers={"Content-Disposition": 'attachment; filename="model-api-config.json"'})

    @route("POST", "/import")
    async def import_config(request):
        from .store import validate
        incoming = copy.deepcopy((await payload(request))["config"])
        validate(incoming)
        current = store.read()
        mapping = {}
        for group in ("providers", "templates", "models"):
            mapping[group] = {item["id"]: uuid.uuid4().hex for item in incoming[group]}
            for item in incoming[group]:
                item["id"] = mapping[group][item["id"]]
                item.pop("api_key", None)
                item.pop("has_key", None)
                if group == "providers":
                    item.pop("api_key_env", None)
                if group == "models":
                    item["provider_id"] = mapping["providers"][item["provider_id"]]
                    item["bindings"] = {op: mapping["templates"][tid] for op, tid in item.get("bindings", {}).items()}
                current[group].append(item)
        return web.json_response(store.save(current))

    @route("POST", "/providers/{provider_id}/models")
    async def discover(request):
        return web.json_response(await engine.discover(request.match_info["provider_id"]))

    @route("GET", "/history")
    async def history(request):
        with engine._lock:
            entries = list(engine.history)
        return web.json_response({"items": entries})

    @route("POST", "/test")
    async def test(request):
        body = await payload(request)
        arguments = {"model_id": body["model_id"], "operation": body["operation"], "prompt": body.get("prompt", ""),
                     "system": body.get("system", ""), "supplied": body.get("parameters", {}),
                     "images": [decode_image(v) for v in body.get("images", [])],
                     "mask": decode_image(body["mask"]) if body.get("mask") else None}
        if body.get("preview", False):
            return web.json_response(await engine.execute(**arguments, preview=True))
        # Keep at most 16 finished debug jobs, and cap simultaneous tests.
        for jid in list(jobs):
            if jobs[jid]["task"].done() and (time.monotonic() - jobs[jid]["created"] > 1800 or len(jobs) >= 16):
                del jobs[jid]
        if sum(not j["task"].done() for j in jobs.values()) >= 8:
            raise APIError("too_many_tests", status=429)
        job_id = uuid.uuid4().hex
        entry = {"created": time.monotonic(), "state": "running"}
        def progress(data):
            entry["progress"] = data
        async def run():
            try:
                result = await engine.execute(**arguments, progress=progress)
                result["images"] = [preview_url(data) for data in result["images"]]
                entry.update(state="success", result=result)
            except APIError as exc:
                entry.update(state="error", error=redact(exc.as_dict(), store.secrets()))
            except asyncio.CancelledError:
                entry.update(state="cancelled")
            except Exception:
                entry.update(state="error", error={"code": "request_failed", "detail": "Unexpected test failure."})
        entry["task"] = asyncio.create_task(run())
        jobs[job_id] = entry
        return web.json_response({"id": job_id, "state": "running"}, status=202)

    @route("GET", "/jobs/{job_id}")
    async def get_job(request):
        job = jobs.get(request.match_info["job_id"])
        if not job:
            raise APIError("job_not_found", status=404)
        return web.json_response({k: v for k, v in job.items() if k not in ("task", "created")})

    @route("POST", "/jobs/{job_id}/cancel")
    async def cancel_job(request):
        job = jobs.get(request.match_info["job_id"])
        if not job:
            raise APIError("job_not_found", status=404)
        if not job["task"].done():
            job["task"].cancel()
        return web.json_response({"state": "cancelling"})

    return jobs
