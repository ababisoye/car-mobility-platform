"""Run the Lambda booking demo locally without AWS credentials."""

import importlib.util
import base64
import hashlib
import json
import os
import sys
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class MemoryTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, **_kwargs):
        self.items[Item["booking_id"]] = Item
        return {}

    def get_item(self, Key, **_kwargs):
        item = self.items.get(Key["booking_id"])
        return {"Item": item} if item else {}

    def scan(self, **_kwargs):
        return {"Items": list(self.items.values())}

    def update_item(self, Key, ExpressionAttributeValues, **_kwargs):
        item = self.items[Key["booking_id"]]
        item["status"] = ExpressionAttributeValues[":status"]
        item["updated_at"] = ExpressionAttributeValues[":updated"]
        return {"Attributes": item}


TABLE = MemoryTable()
fake_boto3 = types.ModuleType("boto3")
fake_boto3.resource = lambda _service: types.SimpleNamespace(Table=lambda _name: TABLE)
sys.modules["boto3"] = fake_boto3
os.environ.setdefault("BOOKINGS_TABLE", "local-bookings")
local_salt = b"local-preview-only"
local_digest = hashlib.pbkdf2_hmac("sha256", b"demo-admin", local_salt, 10_000)
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    f"10000:{base64.b64encode(local_salt).decode()}:{base64.b64encode(local_digest).decode()}",
)

project_root = Path(__file__).resolve().parents[1]
handler_path = project_root / "infra" / "environments" / "demo" / "app" / "handler.py"
spec = importlib.util.spec_from_file_location("demo_handler", handler_path)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class PreviewHandler(BaseHTTPRequestHandler):
    def _handle(self):
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else None
        event = {
            "rawPath": self.path.split("?", 1)[0],
            "body": body,
            "headers": {key: value for key, value in self.headers.items()},
            "requestContext": {"http": {"method": self.command}},
        }
        result = demo.lambda_handler(event, None)
        payload = result["body"].encode("utf-8")
        self.send_response(result["statusCode"])
        for key, value in result.get("headers", {}).items():
            self.send_header(key, value)
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _handle
    do_POST = _handle
    do_PATCH = _handle

    def log_message(self, message, *args):
        print(f"[preview] {message % args}")


if __name__ == "__main__":
    address = ("127.0.0.1", 8080)
    print(f"Booking demo available at http://{address[0]}:{address[1]}")
    print("Local operations dashboard: /admin (password: demo-admin)")
    ThreadingHTTPServer(address, PreviewHandler).serve_forever()
