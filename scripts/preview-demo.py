"""Run the Lambda booking demo locally without AWS credentials."""

import importlib.util
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


TABLE = MemoryTable()
fake_boto3 = types.ModuleType("boto3")
fake_boto3.resource = lambda _service: types.SimpleNamespace(Table=lambda _name: TABLE)
sys.modules["boto3"] = fake_boto3
os.environ.setdefault("BOOKINGS_TABLE", "local-bookings")

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

    def log_message(self, message, *args):
        print(f"[preview] {message % args}")


if __name__ == "__main__":
    address = ("127.0.0.1", 8080)
    print(f"Booking demo available at http://{address[0]}:{address[1]}")
    ThreadingHTTPServer(address, PreviewHandler).serve_forever()
