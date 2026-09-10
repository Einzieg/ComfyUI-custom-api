"""Atomic configuration storage. Secret values never enter the public schema."""

import copy
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import quote, quote_plus

from .errors import APIError
from .network import NetworkPolicy
from .presets import new_config
from .templates import endpoint, parameters, validate_url

ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
SECRET_KEY = re.compile(r"api.?key|authorization|password|secret|access.?token", re.I)


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {k: "[redacted]" if SECRET_KEY.search(k) else redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in sorted((s for s in secrets if s), key=len, reverse=True):
            for variant in {secret, quote(secret, safe=""), quote_plus(secret)}:
                value = value.replace(variant, "[redacted]")
        return value
    return value


def protect_requests(config, secrets):
    """Replace credential literals only in requests, never in IDs or JSON keys."""
    def reference(value):
        if isinstance(value, dict):
            return {k: reference(v) for k, v in value.items()}
        if isinstance(value, list):
            return [reference(v) for v in value]
        if isinstance(value, str):
            parts = re.split(r"(\{\{[^{}]+\}\})", value)
            for i, part in enumerate(parts):
                if part.startswith("{{") and part.endswith("}}"):
                    continue
                for secret in sorted((v for v in secrets if v), key=len, reverse=True):
                    part = part.replace(secret, "{{api_key}}")
                parts[i] = part
            value = "".join(parts)
        return value
    for provider in config["providers"]:
        if "models_request" in provider:
            provider["models_request"] = reference(provider["models_request"])
    for template in config["templates"]:
        template["request"] = reference(template["request"])
        if template.get("poll"):
            for kind in ("request", "cancel"):
                if kind in template["poll"]:
                    template["poll"][kind] = reference(template["poll"][kind])
    return config


def _request(spec):
    if not isinstance(spec, dict) or spec.get("method", "POST") not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        raise APIError("invalid_config", "Invalid HTTP method.")
    endpoint("https://example.invalid", spec.get("path", ""))
    if spec.get("encoding", "json") not in ("json", "form", "multipart"):
        raise APIError("invalid_config", "Expected json, form or multipart encoding.")
    for field in ("headers", "query"):
        if not isinstance(spec.get(field, {}), dict):
            raise APIError("invalid_config", f"{field} must be an object.")
    for key, val in spec.get("headers", {}).items():
        if not isinstance(val, str) or any(c in key + val for c in "\r\n"):
            raise APIError("invalid_config", "Invalid HTTP header.")
    NetworkPolicy.check_headers(spec.get("headers", {}))
    if not isinstance(spec.get("files", []), list):
        raise APIError("invalid_config", "files must be an array.")
    for file in spec.get("files", []):
        if file.get("source") not in ("image", "images", "mask") or not file.get("field"):
            raise APIError("invalid_config", "File sources: image, images, mask.")


def validate(config):
    if not isinstance(config, dict) or config.get("version") != 1:
        raise APIError("invalid_config", "Unsupported configuration version.")
    ids = {}
    for group in ("providers", "models", "templates"):
        items = config.get(group)
        if not isinstance(items, list) or len(items) > 2000:
            raise APIError("invalid_config", f"Invalid {group} collection.")
        ids[group] = set()
        for item in items:
            if not isinstance(item, dict) or not ID.fullmatch(str(item.get("id", ""))):
                raise APIError("invalid_config", f"{group}: invalid ID.")
            if item["id"] in ids[group]:
                raise APIError("invalid_config", f"{group}: duplicate ID.")
            ids[group].add(item["id"])
            if not isinstance(item.get("name"), str) or not item["name"].strip():
                raise APIError("invalid_config", f"{group}: name is required.")
    for p in config["providers"]:
        validate_url(p.get("base_url", ""))
        if p.get("proxy"):
            validate_url(p["proxy"])
        if p.get("auth", {}).get("type", "bearer") not in ("bearer", "header", "query", "none"):
            raise APIError("invalid_config", "Invalid authentication type.")
        if not 1 <= p.get("concurrency", 2) <= 32 or not 1 <= p.get("timeout", 120) <= 3600:
            raise APIError("invalid_config", "Invalid timeout or concurrency.")
        icon = p.get("icon", "")
        if isinstance(icon, str) and icon.startswith("lobehub:"):
            slug = icon[8:]
            if not re.fullmatch(r"[a-z0-9]+", slug) or not (Path(__file__).resolve().parents[1] / "web" / "assets" / "lobehub" / f"{slug}.svg").is_file():
                raise APIError("invalid_config", "Choose an icon from the bundled LobeHub library.")
            bundled_icon = True
        else:
            bundled_icon = False
        if not bundled_icon and (not isinstance(icon, str) or len(icon) > 700000 or (len(icon) > 32 and not re.fullmatch(r"data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+", icon))):
            raise APIError("invalid_config", "Use an emoji or PNG/JPEG/WebP icon (up to 512 KB).")
        _request(p.get("models_request", {"method": "GET", "path": "/models"}))
    for t in config["templates"]:
        if t.get("kind") not in ("text", "image"):
            raise APIError("invalid_config", "Template kind must be text or image.")
        _request(t.get("request"))
        if not isinstance(t.get("response"), dict):
            raise APIError("invalid_config", "Response mapping is required.")
        schema = t.get("parameters", [])
        if not isinstance(schema, list):
            raise APIError("invalid_config", "Parameter schema must be an array.")
        names = set()
        for field in schema:
            if not isinstance(field, dict) or not ID.fullmatch(field.get("name", "")) or field["name"] in names:
                raise APIError("invalid_config", "Invalid or duplicate parameter name.")
            names.add(field["name"])
            if field.get("type") not in ("string", "integer", "number", "boolean", "enum", "json"):
                raise APIError("invalid_config", "Invalid parameter type.")
            if field["type"] == "enum" and not isinstance(field.get("options"), list):
                raise APIError("invalid_config", "Enum parameters need options.")
            if "default" in field:
                parameters([field], {})
        if t.get("poll"):
            poll = t["poll"]
            _request(poll.get("request"))
            if not 0.2 <= poll.get("interval", 2) <= 60 or not 1 <= poll.get("timeout", 600) <= 7200:
                raise APIError("invalid_config", "Invalid polling interval or timeout.")
            if not poll.get("task_id") or not poll.get("status") or not poll.get("success") or not poll.get("failure"):
                raise APIError("invalid_config", "Polling needs task_id, status, success and failure.")
            if poll.get("cancel"):
                _request(poll["cancel"])
    for m in config["models"]:
        if m.get("provider_id") not in ids["providers"] or not isinstance(m.get("model_id"), str) or not m["model_id"]:
            raise APIError("invalid_config", "Model provider and model ID are required.")
        if not isinstance(m.get("bindings", {}), dict) or not isinstance(m.get("defaults", {}), dict):
            raise APIError("invalid_config", "Invalid model bindings or defaults.")
        for operation, template_id in m.get("bindings", {}).items():
            if operation not in ("text", "vision", "image", "image_edit") or template_id not in ids["templates"]:
                raise APIError("invalid_config", "Invalid model template binding.")
            template = next(t for t in config["templates"] if t["id"] == template_id)
            if template["kind"] != ("text" if operation in ("text", "vision") else "image"):
                raise APIError("invalid_config", "Template output does not match model operation.")
    return config


class ConfigStore:
    def __init__(self, directory, network_policy=None):
        self.directory = Path(directory)
        self.network_policy = network_policy or NetworkPolicy.from_file(self.directory / "network-policy.json")
        self._lock = threading.RLock()

    def _read(self, name, default):
        path = self.directory / name
        if not path.exists():
            return copy.deepcopy(default)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise APIError("config_read_failed", path.name, 500) from exc

    def _write(self, name, value):
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".write-", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.directory / name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def read(self):
        with self._lock:
            return self._read("config.json", new_config())

    def secret(self, provider):
        with self._lock:
            if provider.get("api_key_env"):
                name = provider["api_key_env"]
                return os.environ.get(name, "") if name in self.network_policy.allowed_key_env else ""
            return self._read("secrets.json", {}).get(provider["id"], "")

    def secrets(self):
        return [self.secret(p) for p in self.read()["providers"]]

    def public(self):
        config = self.read()
        values = [self.secret(p) for p in config["providers"]]
        # Credential references are restricted to request fields, preserving stable IDs.
        def clean(v):
            if isinstance(v, dict):
                return {k: clean(x) for k, x in v.items() if k not in ("api_key", "has_key")}
            if isinstance(v, list):
                return [clean(x) for x in v]
            return v
        config = protect_requests(clean(config), values)
        for p in config["providers"]:
            p["has_key"] = bool(self.secret(p))
        return config

    def save(self, config, secret_updates=None):
        with self._lock:
            current = self.read()
            if config.get("revision") != current["revision"]:
                raise APIError("config_conflict", "Reload before saving.", 409)
            config = copy.deepcopy(config)
            try:
                validate(config)
                for provider in config["providers"]:
                    self.network_policy.check_provider(provider)
            except (TypeError, ValueError, KeyError, AttributeError) as exc:
                raise APIError("invalid_config", "Invalid field type.") from exc
            credentials = self._read("secrets.json", {})
            for pid, secret in (secret_updates or {}).items():
                if pid not in {p["id"] for p in config["providers"]} or not isinstance(secret, str):
                    raise APIError("invalid_config", "Invalid secret update.")
                credentials[pid] = secret
            credentials = {p["id"]: credentials.get(p["id"], "") for p in config["providers"]}
            for p in config["providers"]:
                p.pop("api_key", None)
                p.pop("has_key", None)
            values = list(credentials.values()) + [self.secret(p) for p in config["providers"] if p.get("api_key_env")]
            config = protect_requests(config, values)
            validate(config)
            config["revision"] = current["revision"] + 1
            self._write("secrets.json", credentials)
            self._write("config.json", config)
            return self.public()
