"""Operator-owned outbound policy; never populated from API configuration."""

import asyncio
import ipaddress
import json
import re
import socket
from pathlib import Path

import aiohttp
from yarl import URL

from .errors import APIError


LOCAL_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128", "fc00::/7",
))
TRANSITION_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32",
))
AUTHORITY_HEADERS = frozenset(("host", ":authority", "proxy-authorization", "proxy-connection"))


def parsed_url(value):
    try:
        if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
            raise ValueError()
        url = URL(value)
        if (url.scheme not in ("http", "https") or not url.raw_host or url.user is not None
                or url.password is not None or url.fragment or "%" in url.raw_host or "*" in url.raw_host):
            raise ValueError()
        if not url.port or url.raw_host.endswith("."):
            raise ValueError()
        # aiohttp treats numeric hosts as IP literals and bypasses its resolver.
        # Require canonical IP syntax before that fast path can be reached.
        if (":" in url.raw_host or url.raw_host.replace(".", "").isdigit()
                or re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+)){0,3}", url.raw_host, re.I)):
            ipaddress.ip_address(url.raw_host)
        return url
    except (ValueError, TypeError, UnicodeError) as exc:
        raise APIError("invalid_url", "Use an http(s) URL without credentials, control characters or a fragment.") from exc


def checked_address(value, *, explicit=False):
    address = ipaddress.ip_address(value)
    if address.version == 6:
        if any(address in network for network in TRANSITION_NETWORKS):
            raise APIError("network_address_blocked", "IPv6 transition addresses are not allowed.", 403)
        address = address.ipv4_mapped or address
    local = explicit and any(address.version == net.version and address in net for net in LOCAL_NETWORKS)
    if (address.is_multicast or address.is_link_local or address.is_unspecified
            or not (address.is_global or local)):
        raise APIError("network_address_blocked", "This address is outside the permitted network boundary.", 403)
    return address


class PublicResolver(aiohttp.abc.AbstractResolver):
    """Return validated IPs to the connector, without a second DNS lookup."""

    async def resolve(self, host, port=0, family=socket.AF_INET):
        answers = await asyncio.get_running_loop().getaddrinfo(host, port, family=family, type=socket.SOCK_STREAM)
        result = []
        for address_family, _, protocol, _, address in answers:
            checked_address(address[0])
            result.append({"hostname": host, "host": address[0], "port": port,
                           "family": address_family, "proto": protocol,
                           "flags": socket.AI_NUMERICHOST | socket.AI_NUMERICSERV})
        if not result:
            raise APIError("network_address_blocked", "The approved host has no permitted IP address.", 403)
        return result

    async def close(self):
        pass


class NetworkPolicy:
    def __init__(self, allowed_origins=(), allowed_key_env=()):
        origins = set()
        for value in allowed_origins:
            url = parsed_url(value)
            if url.path not in ("", "/") or url.query_string:
                raise APIError("network_policy_invalid", "Allow-list entries must be origins: scheme, host and optional port.", 500)
            try:
                ipaddress.ip_address(url.raw_host)
            except ValueError:
                pass
            else:
                checked_address(url.raw_host, explicit=True)
            origins.add(str(url.origin()))
        if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in allowed_key_env):
            raise APIError("network_policy_invalid", "Invalid environment-variable allow-list.", 500)
        self.allowed_origins = frozenset(origins)
        self.allowed_key_env = frozenset(allowed_key_env)

    @classmethod
    def from_file(cls, path):
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict) or set(value) - {"allowed_origins", "allowed_key_env"}:
                raise ValueError()
            if any(not isinstance(value.get(key, []), list) for key in ("allowed_origins", "allowed_key_env")):
                raise ValueError()
            return cls(value.get("allowed_origins", []), value.get("allowed_key_env", []))
        except (OSError, ValueError, TypeError, APIError) as exc:
            raise APIError("network_policy_invalid", "Check the local network-policy.json file and restart ComfyUI.", 500) from exc

    def check_url(self, value):
        url = parsed_url(value)
        if str(url.origin()) not in self.allowed_origins:
            raise APIError("network_origin_blocked", f"Approve {url.origin()} in the local network-policy.json file and restart ComfyUI.", 403)
        try:
            ipaddress.ip_address(url.raw_host)
        except ValueError:
            pass  # DNS results are checked by PublicResolver at connection time.
        else:
            checked_address(url.raw_host, explicit=True)
        return str(url)

    def check_provider(self, provider):
        self.check_url(provider.get("base_url", ""))
        if provider.get("proxy"):
            raise APIError("network_proxy_blocked", "Clear the saved HTTP proxy. Explicit proxies bypass destination DNS validation.", 403)
        if provider.get("api_key_env") and provider["api_key_env"] not in self.allowed_key_env:
            raise APIError("network_key_env_blocked", "Approve the API key variable in the local network-policy.json file.", 403)

    @staticmethod
    def check_headers(headers):
        if any(not isinstance(name, str) for name in headers):
            raise APIError("invalid_config", "HTTP header names must be strings.")
        if any(name.lower() in AUTHORITY_HEADERS for name in headers):
            raise APIError("network_header_blocked", "Host and proxy routing headers cannot be overridden.", 403)
        if any(not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) for name in headers):
            raise APIError("invalid_config", "HTTP header names must be valid tokens.")

    def session(self, timeout):
        return aiohttp.ClientSession(timeout=timeout, cookie_jar=aiohttp.DummyCookieJar(), trust_env=False,
                                     connector=aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False))
