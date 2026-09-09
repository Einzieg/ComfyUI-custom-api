"""A deliberately small, non-executable template language.

Paths: $.key, [0], [*], and ["key.with.dots"]. Whole-value placeholders
preserve JSON types. Interpolated placeholders become strings. No eval.
"""

import copy
import json
import math
import re
from urllib.parse import quote, urlsplit

from .errors import APIError

TOKEN = re.compile(r'\.([\w-]+)|\[(\d+|\*|"(?:[^"\\]|\\.)*")\]')
PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
MISSING = object()


def select(data, path, default=MISSING):
    if not isinstance(path, str):
        raise APIError("invalid_path", str(path))
    if not path or path == "$":
        return data
    path = path if path.startswith("$") else "$." + path
    pos, values, many = 1, [data], False
    while pos < len(path):
        match = TOKEN.match(path, pos)
        if not match:
            raise APIError("invalid_path", path)
        key = match.group(1)
        item = match.group(2)
        if item == "*":
            many = True
            values = [v for container in values for v in
                      (list(container.values()) if isinstance(container, dict)
                       else container if isinstance(container, list) else [])]
        else:
            key = key if key is not None else (json.loads(item) if item.startswith('"') else int(item))
            result = []
            for value in values:
                if isinstance(value, dict) and key in value:
                    result.append(value[key])
                elif isinstance(value, list) and isinstance(key, int) and key < len(value):
                    result.append(value[key])
            values = result
        pos = match.end()
    if not values:
        if default is not MISSING:
            return default
        raise APIError("missing_value", path)
    return values if many else values[0]


def render(value, context):
    if isinstance(value, dict):
        return {k: render(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, context) for v in value]
    if not isinstance(value, str):
        return value
    whole = PLACEHOLDER.fullmatch(value)
    if whole:
        return copy.deepcopy(select(context, whole.group(1)))

    def replace(match):
        found = select(context, match.group(1))
        return found if isinstance(found, str) else json.dumps(found, ensure_ascii=False)

    return PLACEHOLDER.sub(replace, value)


def render_path(path, context):
    return PLACEHOLDER.sub(lambda m: quote(str(select(context, m.group(1))), safe=""), path)


def validate_url(url):
    try:
        parts = urlsplit(url)
        valid = parts.scheme in ("http", "https") and bool(parts.hostname) and not parts.username and not parts.password
        parts.port
    except (ValueError, TypeError):
        valid = False
    if not valid or parts.fragment:
        raise APIError("invalid_url", "Use an http(s) URL without embedded credentials or a fragment.")
    return url


def endpoint(base_url, path):
    # An endpoint is relative to the configured base, including its /v1 suffix.
    if not isinstance(path, str) or "://" in path or path.startswith("//"):
        raise APIError("invalid_path", "Endpoints must be relative to the provider base URL.")
    validate_url(base_url)
    if urlsplit(base_url).query:
        raise APIError("invalid_url", "Put query parameters in the Query configuration.")
    return validate_url(base_url.rstrip("/") + "/" + path.lstrip("/"))


def parameters(schema, supplied):
    if not isinstance(supplied, dict):
        raise APIError("invalid_parameters", "Expected a JSON object.")
    result = copy.deepcopy(supplied)
    for field in schema:
        name, kind = field["name"], field["type"]
        if name not in result and "default" in field:
            result[name] = copy.deepcopy(field["default"])
        if name not in result:
            if field.get("required"):
                raise APIError("invalid_parameters", f"{name}: required")
            continue
        value = result[name]
        valid = {"string": isinstance(value, str), "integer": type(value) is int,
                 "number": type(value) in (int, float), "boolean": type(value) is bool,
                 "json": True, "enum": value in field.get("options", [])}.get(kind, False)
        if not valid:
            raise APIError("invalid_parameters", f"{name}: expected {kind}")
        if type(value) in (int, float):
            if not math.isfinite(value):
                raise APIError("invalid_parameters", f"{name}: expected a finite number")
            if "min" in field and value < field["min"] or "max" in field and value > field["max"]:
                raise APIError("invalid_parameters", f"{name}: outside allowed range")
    return result
