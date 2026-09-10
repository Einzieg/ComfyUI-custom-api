import asyncio
import contextlib
import copy
import io
import json
import threading
import time
import uuid
from collections import deque
from urllib.parse import urljoin

import aiohttp

from .errors import APIError
from .media import MAX_IMAGE_BYTES, MAX_IMAGES, data_url, decode_image, validate_image
from .network import parsed_url
from .presets import request as request_spec
from .store import redact
from .templates import endpoint, parameters, render, render_path, select, validate_url

MAX_RESPONSE = 64 * 1024 * 1024


async def interruptible(awaitable, check=None):
    task = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            if check:
                check()
            await asyncio.wait({task}, timeout=0.2)
        return await task
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


def compact(value, maximum=16000):
    text = json.dumps(value, ensure_ascii=False, default=str)
    return value if len(text) <= maximum else {"truncated": True, "preview": text[:maximum]}


class Engine:
    def __init__(self, store):
        self.store = store
        self.policy = store.network_policy
        self.history = deque(maxlen=50)
        self._lock = threading.Lock()
        self._limits = {}

    def resolve(self, model_id, operation):
        config = self.store.read()
        model = next((m for m in config["models"] if m["id"] == model_id), None)
        if not model or not model.get("enabled", True):
            raise APIError("model_unavailable", model_id)
        provider = next((p for p in config["providers"] if p["id"] == model["provider_id"]), None)
        if not provider or not provider.get("enabled", True):
            raise APIError("provider_unavailable")
        template_id = model.get("bindings", {}).get(operation)
        template = next((t for t in config["templates"] if t["id"] == template_id), None)
        if not template:
            raise APIError("unsupported_operation", operation)
        return provider, model, template

    def context(self, provider, model, template, prompt, system, supplied, images, mask):
        if len(images) > MAX_IMAGES:
            raise APIError("media_too_large", f"Maximum batch: {MAX_IMAGES} images.")
        urls = [data_url(validate_image(data)) for data in images]
        content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": url}} for url in urls]
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": content if images else prompt}]
        values = {**model.get("defaults", {}), **supplied}
        return {"model": model["model_id"], "prompt": prompt, "system": system,
                "messages": messages, "params": parameters(template.get("parameters", []), values),
                "images": urls, "image": urls[0] if urls else "", "image_base64": urls[0].split(",", 1)[1] if urls else "",
                "mask": data_url(mask) if mask else "", "api_key": self.store.secret(provider)}

    def build(self, provider, spec, context):
        self.policy.check_provider(provider)
        url = self.policy.check_url(endpoint(provider["base_url"], render_path(spec.get("path", ""), context)))
        headers = render(spec.get("headers", {}), context)
        query = render(spec.get("query", {}), context)
        auth = provider.get("auth", {"type": "bearer"})
        key = context.get("api_key", "")
        kind = auth.get("type", "bearer")
        if kind != "none" and not key:
            raise APIError("missing_api_key", provider["name"])
        if kind == "bearer":
            headers["Authorization"] = "Bearer " + key
        elif kind == "header":
            headers[auth.get("header") or "x-api-key"] = auth.get("prefix", "") + key
        elif kind == "query":
            query[auth.get("query") or "key"] = key
        query = {k: v if isinstance(v, str) else json.dumps(v) for k, v in query.items() if v is not None}
        if any(not isinstance(v, str) or "\n" in v or "\r" in v for v in headers.values()):
            raise APIError("invalid_config", "Headers must contain plain strings.")
        self.policy.check_headers(headers)
        return {"method": spec.get("method", "POST"), "url": url, "headers": headers, "query": query,
                "encoding": spec.get("encoding", "json"), "body": render(spec.get("body", {}), context),
                "files": spec.get("files", [])}

    def safe_preview(self, built, context, provider):
        preview = copy.deepcopy(built)
        for name in ("images", "image", "image_base64", "mask"):
            value = context.get(name)
            if value:
                for asset in value if isinstance(value, list) else [value]:
                    preview = self._replace(preview, asset, "[image data]")
        preview = redact(preview, self.store.secrets())
        auth = provider.get("auth", {})
        if auth.get("type") == "query":
            preview["query"][auth.get("query") or "key"] = "[redacted]"
        if auth.get("type") == "header":
            preview["headers"][auth.get("header") or "x-api-key"] = "[redacted]"
        return compact(preview)

    @staticmethod
    def _replace(value, old, new):
        if isinstance(value, dict):
            return {k: Engine._replace(v, old, new) for k, v in value.items()}
        if isinstance(value, list):
            return [Engine._replace(v, old, new) for v in value]
        return value.replace(old, new) if isinstance(value, str) else value

    @contextlib.asynccontextmanager
    async def slot(self, provider, check=None):
        pid, count = provider["id"], provider.get("concurrency", 2)
        with self._lock:
            if pid not in self._limits:
                self._limits[pid] = {"active": 0}
        acquired = False
        try:
            while not acquired:
                if check:
                    check()
                with self._lock:
                    state = self._limits[pid]
                    if state["active"] < count:
                        state["active"] += 1
                        acquired = True
                if not acquired:
                    await asyncio.sleep(0.2)
            yield
        finally:
            if acquired:
                with self._lock:
                    self._limits[pid]["active"] -= 1

    async def _bytes(self, response, limit):
        if response.content_length and response.content_length > limit:
            raise APIError("media_too_large")
        buffer = bytearray()
        async for chunk in response.content.iter_chunked(64 * 1024):
            buffer.extend(chunk)
            if len(buffer) > limit:
                raise APIError("media_too_large")
        return bytes(buffer)

    async def send(self, session, provider, spec, context, images=(), mask=None, check=None):
        built = self.build(provider, spec, context)
        kwargs = {"headers": built["headers"], "params": built["query"], "allow_redirects": False}
        body = built["body"]
        if built["method"] != "GET":
            if built["encoding"] == "json":
                kwargs["json"] = body
            elif built["encoding"] == "form":
                if not isinstance(body, dict):
                    raise APIError("invalid_config", "Form body must be an object.")
                kwargs["data"] = {k: v if isinstance(v, str) else json.dumps(v) for k, v in body.items()}
            else:
                if not isinstance(body, dict):
                    raise APIError("invalid_config", "Multipart body must be an object.")
                form = aiohttp.FormData()
                for k, value in body.items():
                    form.add_field(k, value if isinstance(value, str) else json.dumps(value))
                for definition in built["files"]:
                    source = definition["source"]
                    blobs = images if source == "images" else images[:1] if source == "image" else [mask] if mask else []
                    if not blobs and not definition.get("optional", False):
                        raise APIError("missing_image", source)
                    for i, data in enumerate(blobs):
                        # Input tensor images are PNG; debug uploads are normalized below.
                        from PIL import Image
                        with Image.open(io.BytesIO(data)) as im:
                            buffer = io.BytesIO()
                            im.save(buffer, "PNG")
                        form.add_field(definition["field"], buffer.getvalue(), filename=f"{source}-{i}.png", content_type="image/png")
                kwargs["data"] = form
                kwargs["headers"] = {k: v for k, v in kwargs["headers"].items() if k.lower() != "content-type"}

        async def perform():
            # Only read-only GET requests are retried. Never replay a paid submission.
            for attempt in range(3 if built["method"] == "GET" else 1):
                async with session.request(built["method"], built["url"], **kwargs) as response:
                    if response.status in (429, 502, 503, 504) and built["method"] == "GET" and attempt < 2:
                        delay = response.headers.get("Retry-After", "")
                        await asyncio.sleep(min(float(delay), 15) if delay.replace(".", "", 1).isdigit() else 2 ** attempt)
                        continue
                    data = await self._bytes(response, MAX_RESPONSE)
                    if response.status >= 300:
                        detail = redact(data.decode("utf-8", "replace")[:2000], self.store.secrets())
                        raise APIError("upstream_http", f"HTTP {response.status}: {detail}", 502)
                    if response.content_type.startswith("image/"):
                        return {"_binary_image": data}
                    try:
                        return json.loads(data)
                    except (ValueError, UnicodeDecodeError) as exc:
                        raise APIError("invalid_response", "Expected JSON or an image response.", 502) from exc
        try:
            return await interruptible(perform(), check)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise APIError("request_failed", type(exc).__name__ + ": " + redact(str(exc), self.store.secrets()), 502) from exc

    async def download(self, session, value, provider, context, check=None):
        if not value.startswith(("https://", "http://")):
            return decode_image(value)
        validate_url(value)
        origin = str(parsed_url(provider["base_url"]).origin())

        async def fetch():
            url = self.policy.check_url(value)
            for _ in range(4):
                url = self.policy.check_url(url)
                headers, params = {}, {}
                # Never send the provider key to a different image host/CDN.
                if str(parsed_url(url).origin()) == origin:
                    auth = self.build(provider, request_spec("/", method="GET"), context)
                    headers, params = auth["headers"], auth["query"]
                async with session.get(url, headers=headers, params=params, allow_redirects=False) as response:
                    if response.status in (301, 302, 303, 307, 308) and response.headers.get("Location"):
                        url = validate_url(urljoin(url, response.headers["Location"]))
                        continue
                    if response.status != 200:
                        raise APIError("download_failed", f"HTTP {response.status}", 502)
                    return validate_image(await self._bytes(response, MAX_IMAGE_BYTES))
            raise APIError("download_failed", "Too many redirects.", 502)
        return await interruptible(fetch(), check)

    async def execute(self, model_id, operation, prompt="", system="", supplied=None, images=(), mask=None, preview=False, check=None, progress=None):
        provider, model, template = self.resolve(model_id, operation)
        if operation in ("vision", "image_edit") and not images:
            raise APIError("missing_image")
        context = self.context(provider, model, template, prompt, system, supplied or {}, images, mask)
        built = self.build(provider, template["request"], context)
        safe = self.safe_preview(built, context, provider)
        if preview:
            return {"request": safe, "response_mapping": template["response"], "poll": template.get("poll")}
        started = time.monotonic()
        record = {"id": uuid.uuid4().hex, "time": time.time(), "provider": provider["name"], "model": model["name"],
                  "operation": operation, "status": "running", "request": safe}
        timeout = aiohttp.ClientTimeout(total=provider.get("timeout", 120), connect=20)
        try:
            async with self.slot(provider, check), self.policy.session(timeout) as session:
                result = await self.send(session, provider, template["request"], context, images, mask, check)
                response_map = template["response"]
                poll = template.get("poll")
                if poll:
                    error = select(result, response_map.get("error", "$.error.message"), None)
                    if error:
                        raise APIError("upstream_error", str(error), 502)
                    context["task_id"] = select(result, poll["task_id"])
                    record["task_id"] = context["task_id"]
                    if progress:
                        progress({"task_id": context["task_id"], "status": "submitted"})
                    async def poll_task():
                        while True:
                            result = await self.send(session, provider, poll["request"], context, check=check)
                            status = str(select(result, poll["status"]))
                            if progress:
                                progress({"task_id": context["task_id"], "status": status})
                            if status in poll["failure"]:
                                raise APIError("task_failed", str(select(result, response_map.get("error", "$.error.message"), status)), 502)
                            if status in poll["success"]:
                                return result
                            await interruptible(asyncio.sleep(poll.get("interval", 2)), check)
                    try:
                        result = await asyncio.wait_for(poll_task(), timeout=poll.get("timeout", 600))
                    except BaseException as exc:
                        if poll.get("cancel"):
                            try:
                                await asyncio.wait_for(self.send(session, provider, poll["cancel"], context), timeout=10)
                                record["remote_cancel"] = "requested"
                            except Exception:
                                record["remote_cancel"] = "failed"
                        if isinstance(exc, asyncio.TimeoutError):
                            raise APIError("poll_timeout", f"Task ID: {context['task_id']}", 504) from exc
                        raise
                error = select(result, response_map.get("error", "$.error.message"), None)
                if error:
                    raise APIError("upstream_error", str(error), 502)
                output_images, text = [], ""
                if template["kind"] == "image":
                    if isinstance(result, dict) and "_binary_image" in result:
                        output_images = [validate_image(result["_binary_image"])]
                    else:
                        values = select(result, response_map.get("images", "$.data[*]"))
                        values = values if isinstance(values, list) else [values]
                        if not values or len(values) > MAX_IMAGES:
                            raise APIError("invalid_response", "Expected 1–16 images.")
                        for item in values:
                            field = response_map.get("image_value", "auto")
                            if field != "auto":
                                item = select(item, field)
                            elif isinstance(item, dict):
                                item = item.get("b64_json") or item.get("url") or item.get("base64")
                            if not isinstance(item, str):
                                raise APIError("invalid_image", "Configure response.image_value for this response.")
                            output_images.append(await self.download(session, item, provider, context, check))
                else:
                    text = select(result, response_map.get("text", "$.choices[0].message.content"))
                    if not isinstance(text, str):
                        text = json.dumps(text, ensure_ascii=False)
                raw = {"binary_image": True} if isinstance(result, dict) and "_binary_image" in result else result
                sanitized = redact(raw, self.store.secrets())
                # Logs omit base64 payloads while node output can retain usable result URLs.
                record["response"] = compact(sanitized, 8000)
                record["status"] = "success"
                return {"text": redact(text, self.store.secrets()), "images": output_images, "raw": compact(sanitized, 64000),
                        "metadata": {"request_id": record["id"], "model": model["model_id"],
                                     "duration_ms": round((time.monotonic() - started) * 1000),
                                     "usage": select(raw, response_map.get("usage", "$.usage"), None)}}
        except APIError as exc:
            exc.detail = redact(exc.detail, self.store.secrets())
            exc.args = (f"{exc.code}: {exc.detail}",)
            record.update(status="error", error=exc.as_dict())
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            error = APIError("request_failed", redact(str(exc), self.store.secrets()), 502)
            record.update(status="error", error=error.as_dict())
            raise error from exc
        except BaseException:
            record["status"] = "cancelled"
            raise
        finally:
            record["duration_ms"] = round((time.monotonic() - started) * 1000)
            with self._lock:
                self.history.appendleft(record)

    async def discover(self, provider_id):
        config = self.store.read()
        provider = next((p for p in config["providers"] if p["id"] == provider_id), None)
        if not provider:
            raise APIError("provider_unavailable")
        context = {"api_key": self.store.secret(provider)}
        async with self.slot(provider), self.policy.session(aiohttp.ClientTimeout(total=provider.get("timeout", 120))) as session:
            response = await self.send(session, provider, provider.get("models_request", request_spec("/models", method="GET")), context)
        items = select(response, provider.get("models_path", "$.data"))
        if not isinstance(items, list):
            raise APIError("invalid_response", "Model list mapping must select an array.")
        existing = {m["model_id"] for m in config["models"] if m["provider_id"] == provider_id}
        added = 0
        for item in items:
            mid = select(item, provider.get("model_id_path", "$.id")) if isinstance(item, dict) else item
            if not isinstance(mid, str) or not mid or mid in existing:
                continue
            label = select(item, provider.get("model_name_path", "$.id"), mid) if isinstance(item, dict) else mid
            config["models"].append({"id": uuid.uuid4().hex, "provider_id": provider_id, "model_id": mid,
                                     "name": str(label), "enabled": True, "source": "discovered", "bindings": {}, "defaults": {}})
            existing.add(mid)
            added += 1
        return {"config": self.store.save(config), "added": added, "total": len(items)}
