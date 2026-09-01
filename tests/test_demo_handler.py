import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        self.items[Item["booking_id"]] = Item
        return {}

    def get_item(self, Key, **kwargs):
        item = self.items.get(Key["booking_id"])
        if not item:
            return {}
        return {"Item": {key: item[key] for key in ("booking_id", "status", "created_at")}}


FAKE_TABLE = FakeTable()
fake_boto3 = types.SimpleNamespace(
    resource=lambda service: types.SimpleNamespace(Table=lambda name: FAKE_TABLE)
)
sys.modules["boto3"] = fake_boto3
os.environ["BOOKINGS_TABLE"] = "test-bookings"
os.environ["BOOKING_TTL_DAYS"] = "30"
os.environ["ALLOWED_ORIGIN"] = "*"

handler_path = (
    Path(__file__).parents[1]
    / "infra"
    / "environments"
    / "demo"
    / "app"
    / "handler.py"
)
spec = importlib.util.spec_from_file_location("demo_handler", handler_path)
handler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler)


def event(method, path, body=None):
    return {
        "requestContext": {"http": {"method": method}},
        "rawPath": path,
        "body": json.dumps(body) if body is not None else None,
    }


class DemoHandlerTests(unittest.TestCase):
    def test_home_page_loads(self):
        result = handler.lambda_handler(event("GET", "/"), None)
        self.assertEqual(result["statusCode"], 200)
        self.assertIn("Request a quote", result["body"])

    def test_booking_can_be_created_and_checked(self):
        request = {
            "name": "Demo Customer",
            "phone": "+2348000000000",
            "email": "demo@example.com",
            "hub": "Lagos",
            "trip_type": "Interstate",
            "pickup": "Victoria Island",
            "destination": "Ibadan",
            "pickup_at": "2026-09-10T09:00",
            "vehicle_preference": "Executive SUV",
            "notes": "Demo only",
        }
        created = handler.lambda_handler(event("POST", "/bookings", request), None)
        self.assertEqual(created["statusCode"], 201)
        booking_id = json.loads(created["body"])["booking_id"]

        status = handler.lambda_handler(event("GET", f"/bookings/{booking_id}"), None)
        self.assertEqual(status["statusCode"], 200)
        self.assertEqual(json.loads(status["body"])["status"], "REQUESTED")

    def test_invalid_hub_is_rejected(self):
        request = {
            "name": "Demo Customer",
            "phone": "+2348000000000",
            "hub": "Invalid",
            "trip_type": "Local",
            "pickup": "A",
            "destination": "B",
            "pickup_at": "2026-09-10T09:00",
        }
        result = handler.lambda_handler(event("POST", "/bookings", request), None)
        self.assertEqual(result["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()

