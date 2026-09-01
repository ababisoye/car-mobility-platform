import base64
import hashlib
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
        key = next(key for key in Item if key.endswith("_id"))
        self.items[Item[key]] = Item
        return {}

    def get_item(self, Key, **kwargs):
        item = self.items.get(Key["booking_id"])
        if not item:
            return {}
        return {"Item": {key: item[key] for key in ("booking_id", "status", "created_at")}}

    def scan(self, **kwargs):
        return {"Items": list(self.items.values())}

    def update_item(self, Key, ExpressionAttributeValues, **kwargs):
        item = self.items[next(iter(Key.values()))]
        item["status"] = ExpressionAttributeValues[":status"]
        item["updated_at"] = ExpressionAttributeValues[":updated"]
        return {"Attributes": item}


FAKE_TABLES = {
    "test-bookings": FakeTable(),
    "test-vehicles": FakeTable(),
    "test-chauffeurs": FakeTable(),
}
fake_boto3 = types.SimpleNamespace(
    resource=lambda service: types.SimpleNamespace(Table=lambda name: FAKE_TABLES[name])
)
sys.modules["boto3"] = fake_boto3
os.environ["BOOKINGS_TABLE"] = "test-bookings"
os.environ["VEHICLES_TABLE"] = "test-vehicles"
os.environ["CHAUFFEURS_TABLE"] = "test-chauffeurs"
os.environ["BOOKING_TTL_DAYS"] = "30"
os.environ["ALLOWED_ORIGIN"] = "*"
test_salt = b"unit-test-salt"
test_digest = hashlib.pbkdf2_hmac("sha256", b"test-admin-password", test_salt, 10_000)
os.environ["ADMIN_PASSWORD_HASH"] = (
    f"10000:{base64.b64encode(test_salt).decode()}:{base64.b64encode(test_digest).decode()}"
)

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


def event(method, path, body=None, headers=None):
    return {
        "requestContext": {"http": {"method": method}},
        "rawPath": path,
        "body": json.dumps(body) if body is not None else None,
        "headers": headers or {},
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

    def test_admin_dashboard_requires_password(self):
        page = handler.lambda_handler(event("GET", "/admin"), None)
        denied = handler.lambda_handler(event("GET", "/admin/bookings"), None)
        self.assertEqual(page["statusCode"], 200)
        self.assertIn("Operations Dashboard", page["body"])
        self.assertEqual(denied["statusCode"], 401)

    def test_admin_can_list_and_update_booking(self):
        headers = {"x-admin-password": "test-admin-password"}
        created = handler.lambda_handler(
            event(
                "POST",
                "/bookings",
                {
                    "name": "Operations Test",
                    "phone": "+2348000000001",
                    "hub": "Abuja",
                    "trip_type": "Local",
                    "pickup": "Wuse",
                    "destination": "Maitama",
                    "pickup_at": "2026-09-12T10:00",
                },
            ),
            None,
        )
        booking_id = json.loads(created["body"])["booking_id"]
        listed = handler.lambda_handler(event("GET", "/admin/bookings", headers=headers), None)
        self.assertEqual(listed["statusCode"], 200)
        self.assertTrue(json.loads(listed["body"])["bookings"])
        updated = handler.lambda_handler(
            event("PATCH", f"/admin/bookings/{booking_id}", {"status": "REVIEWING"}, headers),
            None,
        )
        self.assertEqual(updated["statusCode"], 200)
        self.assertEqual(json.loads(updated["body"])["status"], "REVIEWING")

    def test_admin_can_manage_vehicle_availability(self):
        headers = {"x-admin-password": "test-admin-password"}
        created = handler.lambda_handler(
            event(
                "POST",
                "/admin/vehicles",
                {"name": "Mercedes GLE", "hub": "Lagos", "category": "SUV", "ownership": "Partner"},
                headers,
            ),
            None,
        )
        self.assertEqual(created["statusCode"], 201)
        vehicle_id = json.loads(created["body"])["vehicle_id"]
        updated = handler.lambda_handler(
            event("PATCH", f"/admin/vehicles/{vehicle_id}", {"status": "MAINTENANCE"}, headers),
            None,
        )
        self.assertEqual(json.loads(updated["body"])["status"], "MAINTENANCE")

    def test_admin_can_manage_chauffeur_availability(self):
        headers = {"x-admin-password": "test-admin-password"}
        created = handler.lambda_handler(
            event("POST", "/admin/chauffeurs", {"name": "Demo Chauffeur", "hub": "Abuja"}, headers),
            None,
        )
        self.assertEqual(created["statusCode"], 201)
        chauffeur_id = json.loads(created["body"])["chauffeur_id"]
        listed = handler.lambda_handler(event("GET", "/admin/chauffeurs", headers=headers), None)
        self.assertEqual(json.loads(listed["body"])["count"], 1)
        updated = handler.lambda_handler(
            event("PATCH", f"/admin/chauffeurs/{chauffeur_id}", {"status": "OFF_DUTY"}, headers),
            None,
        )
        self.assertEqual(json.loads(updated["body"])["status"], "OFF_DUTY")


if __name__ == "__main__":
    unittest.main()
