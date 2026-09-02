import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PreviewDemoTests(unittest.TestCase):
    def test_preview_can_create_a_booking_transactionally(self):
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
