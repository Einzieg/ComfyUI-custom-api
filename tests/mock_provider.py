"""Local-only provider fixture. No real credentials, billing or external requests."""
import argparse
import base64
import io
import json
import threading
import time
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

TEST_KEY = "test-key-local-fixture-ONLY-123456"


def png(width=32, height=24, color=(45, 117, 230)):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, "PNG")
    return buffer.getvalue()


class ProviderServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address=("127.0.0.1", 0)):
        super().__init__(address, ProviderHandler)
        self.calls = []
        self.polls = 0
        self.model_failures = 0

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}/v1"


class ProviderHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, value, status=200, content_type="application/json", **headers):
        data = json.dumps(value).encode("utf-8") if content_type == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for key, value in headers.items():
            self.send_header(key.replace("_", "-"), value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        self.server.calls.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
        if self.path.startswith("/v1/models"):
            if self.server.model_failures > 0:
                self.server.model_failures -= 1
                return self.reply({"error": "busy"}, 503, Retry_After="0")
            return self.reply({"data": [{"id": "fixture-text"}, {"id": "fixture-image"}]})
        if self.path.startswith("/v1/tasks/"):
            self.server.polls += 1
            never = "never" in self.path
            return self.reply({"status": "running" if never or self.server.polls < 2 else "completed", "result": {"images": [self.server.url + "/generated.png"]}})
        if self.path == "/v1/generated.png" or self.path.startswith("/image.png"):
            return self.reply(png(), content_type="image/png")
        if self.path == "/stats":
            return self.reply({"calls": len(self.server.calls), "posts": sum(c["method"] == "POST" for c in self.server.calls)})
        return self.reply({"error": "not found"}, 404)

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        multipart = "multipart/form-data" in self.headers.get("Content-Type", "")
        if multipart:
            message = BytesParser(policy=default).parsebytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + data)
            body = {"fields": [(part.get_param("name", header="content-disposition"), part.get_content_type(), part.get_payload(decode=True)) for part in message.iter_parts()]}
        elif self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
            from urllib.parse import parse_qs
            body = parse_qs(data.decode())
        else:
            body = json.loads(data or "{}")
        self.server.calls.append({"method": "POST", "path": self.path, "body": body, "headers": dict(self.headers)})
        if self.path == "/v1/limited":
            return self.reply({"error": {"message": "rate limit"}}, 429)
        if self.path == "/v1/leak":
            return self.reply({"error": {"message": TEST_KEY}}, 400)
        if self.path == "/v1/tasks":
            return self.reply({"task_id": "never" if body.get("prompt") == "never" else "fixture-task"})
        if self.path.endswith("/cancel"):
            return self.reply({"cancelled": True})
        if self.path == "/v1/images/edits":
            return self.reply({"data": [{"b64_json": base64.b64encode(png()).decode()}]})
        if self.path == "/v1/binary":
            return self.reply(png(), content_type="image/png")
        if self.path == "/v1/images/generations":
            return self.reply({"data": [{"url": self.server.url + "/generated.png"}, {"b64_json": base64.b64encode(png(20, 28)).decode()}]})
        if self.path == "/v1/slow":
            time.sleep(0.2)
        return self.reply({"choices": [{"message": {"content": "测试成功 · Custom API works"}}], "usage": {"total_tokens": 12}, "echo": body})


def start_provider():
    server = ProviderServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8192)
    args = parser.parse_args()
    server = ProviderServer(("127.0.0.1", args.port))
    print(server.url, flush=True)
    server.serve_forever()
