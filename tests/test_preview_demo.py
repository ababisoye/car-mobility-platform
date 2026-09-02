import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PreviewDemoTests(unittest.TestCase):
    def test_preview_supports_the_end_to_end_booking_lifecycle(self):
        code = r'''
import json, runpy
from datetime import datetime, timedelta
namespace = runpy.run_path("scripts/preview-demo.py")
demo = namespace["demo"]
pickup = datetime.now().replace(microsecond=0) + timedelta(days=2)
event = {"rawPath": "/bookings", "body": json.dumps({"name": "Preview Customer", "phone": "+2348000000200", "hub": "Lagos", "trip_type": "Local", "pickup": "Ikoyi", "destination": "Lekki", "pickup_at": pickup.isoformat(), "end_at": (pickup + timedelta(hours=3)).isoformat()}), "headers": {}, "requestContext": {"http": {"method": "POST"}}}
result = demo.lambda_handler(event, None)
body = json.loads(result["body"])
assert result["statusCode"] == 201, result
assert body["booking_id"] in namespace["TABLES"]["local-bookings"].items
assert any(item["booking_id"] == body["booking_id"] for item in namespace["TABLES"]["local-notifications"].items.values())

booking_id, token = body["booking_id"], body["access_token"]
staff = {"x-staff-password": "demo-admin"}
customer = {"x-booking-token": token}
def call(method, path, payload=None, headers=None, expected=200):
    event = {"rawPath": path, "body": json.dumps(payload) if payload is not None else None, "headers": headers or {}, "requestContext": {"http": {"method": method}}}
    response = demo.lambda_handler(event, None)
    assert response["statusCode"] == expected, (method, path, response)
    return json.loads(response["body"])

call("PATCH", f"/admin/bookings/{booking_id}", {"status": "REVIEWING"}, staff)
call("POST", f"/admin/bookings/{booking_id}/quotes", {"amount_ngn": 125000, "valid_until": (pickup + timedelta(days=1)).isoformat(), "notes": "Preview quote"}, staff, 201)
call("PATCH", f"/bookings/{booking_id}/quote", {"decision": "ACCEPTED"}, customer)
call("PATCH", f"/admin/bookings/{booking_id}", {"status": "CONFIRMED"}, staff)
vehicle = call("POST", "/admin/vehicles", {"name": "Preview SUV", "hub": "Lagos", "category": "Executive SUV"}, staff, 201)
chauffeur = call("POST", "/admin/chauffeurs", {"name": "Preview Chauffeur", "hub": "Lagos", "interstate_eligible": "YES"}, staff, 201)
call("PATCH", f"/admin/bookings/{booking_id}/assignment", {"vehicle_id": vehicle["vehicle_id"], "chauffeur_id": chauffeur["chauffeur_id"]}, staff)
call("PATCH", f"/admin/bookings/{booking_id}", {"status": "IN_PROGRESS"}, staff)
completed = call("PATCH", f"/admin/bookings/{booking_id}", {"status": "COMPLETED"}, staff)
assert completed["status"] == "COMPLETED"
assert namespace["TABLES"]["local-vehicles"].items[vehicle["vehicle_id"]]["status"] == "AVAILABLE"
assert namespace["TABLES"]["local-chauffeurs"].items[chauffeur["chauffeur_id"]]["status"] == "AVAILABLE"
'''
        environment = os.environ.copy()
        for name in (
            "BOOKINGS_TABLE", "VEHICLES_TABLE", "CHAUFFEURS_TABLE", "QUOTES_TABLE",
            "NOTIFICATIONS_TABLE", "PAYMENTS_TABLE", "ADMIN_PASSWORD_HASH",
            "OPERATOR_PASSWORD_HASH", "PAYMENT_WEBHOOK_SECRET",
        ):
            environment.pop(name, None)

        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, env=environment,
            capture_output=True, text=True, timeout=15, check=False,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
