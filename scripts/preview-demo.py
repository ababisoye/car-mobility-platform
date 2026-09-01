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
        key = next(key for key in Item if key.endswith("_id"))
        self.items[Item[key]] = Item
        return {}

    def get_item(self, Key, **_kwargs):
        item = self.items.get(next(iter(Key.values())))
        return {"Item": item} if item else {}

    def scan(self, **_kwargs):
        return {"Items": list(self.items.values())}

    def update_item(self, Key, ExpressionAttributeValues, **_kwargs):
        item = self.items[next(iter(Key.values()))]
        if ":status" in ExpressionAttributeValues:
            item["status"] = ExpressionAttributeValues[":status"]
        if ":quoted" in ExpressionAttributeValues:
            item.update(
                status=ExpressionAttributeValues[":quoted"],
                latest_quote_id=ExpressionAttributeValues[":quote_id"],
                quote_version=ExpressionAttributeValues[":version"],
                quote_amount_ngn=ExpressionAttributeValues[":amount"],
            )
        if ":payment_id" in ExpressionAttributeValues:
            item["payment_id"] = ExpressionAttributeValues[":payment_id"]
            item["payment_status"] = ExpressionAttributeValues[":payment_status"]
        if ":booking_status" in ExpressionAttributeValues:
            item["status"] = ExpressionAttributeValues[":booking_status"]
            item["payment_status"] = ExpressionAttributeValues[":payment_status"]
        item["updated_at"] = ExpressionAttributeValues[":updated"]
        return {"Attributes": item}


TABLES = {
    "local-bookings": MemoryTable(),
    "local-vehicles": MemoryTable(),
    "local-chauffeurs": MemoryTable(),
    "local-quotes": MemoryTable(),
    "local-notifications": MemoryTable(),
    "local-payments": MemoryTable(),
}


class MemoryDynamoClient:
    def transact_write_items(self, TransactItems):
        for transaction in TransactItems:
            update = transaction["Update"]
            table = TABLES[update["TableName"]]
            key = next(iter(update["Key"].values()))["S"]
            item = table.items[key]
            values = update["ExpressionAttributeValues"]
            if update["TableName"] == "local-bookings":
                item.update(
                    status="ASSIGNED",
                    vehicle_id=values[":vehicle"]["S"],
                    chauffeur_id=values[":chauffeur"]["S"],
                    updated_at=int(values[":updated"]["N"]),
                )
            else:
                item["status"] = values.get(":reserved", values.get(":assigned"))["S"]
                item["updated_at"] = int(values[":updated"]["N"])
        return {}


fake_boto3 = types.ModuleType("boto3")
fake_boto3.resource = lambda _service: types.SimpleNamespace(Table=lambda name: TABLES[name])
fake_boto3.client = lambda _service: MemoryDynamoClient()
sys.modules["boto3"] = fake_boto3
os.environ.setdefault("BOOKINGS_TABLE", "local-bookings")
os.environ.setdefault("VEHICLES_TABLE", "local-vehicles")
os.environ.setdefault("CHAUFFEURS_TABLE", "local-chauffeurs")
os.environ.setdefault("QUOTES_TABLE", "local-quotes")
os.environ.setdefault("NOTIFICATIONS_TABLE", "local-notifications")
os.environ.setdefault("PAYMENTS_TABLE", "local-payments")
os.environ.setdefault("PAYMENT_WEBHOOK_SECRET", "local-payment-webhook-secret-32-characters")
local_salt = b"local-preview-only"
local_digest = hashlib.pbkdf2_hmac("sha256", b"demo-admin", local_salt, 10_000)
local_operator_salt = b"local-operator-only"
local_operator_digest = hashlib.pbkdf2_hmac("sha256", b"demo-operator", local_operator_salt, 10_000)
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    f"10000:{base64.b64encode(local_salt).decode()}:{base64.b64encode(local_digest).decode()}",
)
os.environ.setdefault(
    "OPERATOR_PASSWORD_HASH",
    f"10000:{base64.b64encode(local_operator_salt).decode()}:{base64.b64encode(local_operator_digest).decode()}",
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
    print("Local operator access: /admin (password: demo-operator)")
    ThreadingHTTPServer(address, PreviewHandler).serve_forever()
