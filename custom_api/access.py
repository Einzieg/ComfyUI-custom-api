"""Management authentication, separate from provider credentials and exports."""

import ipaddress
import secrets

from yarl import URL

from .errors import APIError


def loopback(value):
    try:
        address = ipaddress.ip_address(value)
        return (address.ipv4_mapped or address).is_loopback if address.version == 6 else address.is_loopback
    except ValueError:
        return value == "localhost"


def loopback_listener(listen):
    return isinstance(listen, str) and bool(listen) and all(loopback(host.strip()) for host in listen.split(","))


class ManagementAccess:
    def __init__(self, store, local_session=False):
        self.local_session = local_session
        with store._lock:
            saved = store._read("management-access.json", {})
            if not saved:
                saved = {"pairing_code": secrets.token_urlsafe(32)}
                store._write("management-access.json", saved)
            self.pairing_code = saved["pairing_code"]
            if not isinstance(self.pairing_code, str) or len(self.pairing_code) < 32:
                raise APIError("management_access_invalid", "Invalid management-access.json.", 500)
        self.session_token = secrets.token_urlsafe(32)

    @staticmethod
    def check_origin(request):
        origin = request.headers.get("Origin")
        try:
            expected = URL(f"{request.scheme}://{request.host}").origin()
            if origin and (URL(origin).origin() != expected or str(URL(origin)) != str(expected)):
                raise ValueError()
        except ValueError as exc:
            raise APIError("forbidden_origin", status=403) from exc
        if request.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            raise APIError("forbidden_origin", status=403)

    def authenticate(self, request):
        token = request.headers.get("X-Custom-API-Session", "")
        if not token.isascii() or not secrets.compare_digest(token, self.session_token):
            raise APIError("management_auth_required", status=401)

    def create_session(self, request, body):
        # Do not trust forwarding headers, DNS aliases or a proxy's loopback peer.
        peer = request.transport.get_extra_info("peername") if request.transport else None
        host = URL(f"{request.scheme}://{request.host}").host
        local = (self.local_session and peer and loopback(peer[0]) and loopback(host)
                 and request.headers.get("Origin") and not any(
                     key.lower() == "forwarded" or key.lower().startswith("x-forwarded-") for key in request.headers))
        code = body.get("pairing_code", "")
        if not local and not (isinstance(code, str) and code.isascii() and secrets.compare_digest(code, self.pairing_code)):
            raise APIError("management_auth_required", "Enter the pairing code from the server's private management-access.json.", 401)
        return {"token": self.session_token}
