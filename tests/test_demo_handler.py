import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        key = next(key for key in Item if key.endswith("_id"))
        self.items[Item[key]] = Item
        return {}

    def get_item(self, Key, **kwargs):
        item = self.items.get(next(iter(Key.values())))
        if not item:
            return {}
        return {"Item": item}

    def scan(self, **kwargs):
        return {"Items": list(self.items.values())}

    def update_item(self, Key, ExpressionAttributeValues, **kwargs):
        item = self.items[next(iter(Key.values()))]
        if ":status" in ExpressionAttributeValues:
            item["status"] = ExpressionAttributeValues[":status"]
        if ":quoted" in ExpressionAttributeValues:
            item.update(
                status=ExpressionAttributeValues[":quoted"],
                latest_quote_id=ExpressionAttributeValues[":quote_id"],
                quote_version=ExpressionAttributeValues[":version"],
                quote_amount_ngn=ExpressionAttributeValues[":amount"],
                quote_status=ExpressionAttributeValues[":issued"],
                accepted_quote_id=ExpressionAttributeValues[":empty"],
            )
        if ":decision" in ExpressionAttributeValues:
            item.update(
                status=ExpressionAttributeValues[":decision_status"],
                quote_status=ExpressionAttributeValues[":decision"],
                accepted_quote_id=ExpressionAttributeValues[":accepted_quote_id"],
                quote_decided_at=ExpressionAttributeValues[":updated"],
            )
        if ":payment_id" in ExpressionAttributeValues:
            item["payment_id"] = ExpressionAttributeValues[":payment_id"]
            item["payment_status"] = ExpressionAttributeValues[":payment_status"]
        if ":booking_status" in ExpressionAttributeValues:
            item["status"] = ExpressionAttributeValues[":booking_status"]
            item["payment_status"] = ExpressionAttributeValues[":payment_status"]
        item["updated_at"] = ExpressionAttributeValues[":updated"]
        return {"Attributes": item}


FAKE_TABLES = {
    "test-bookings": FakeTable(),
    "test-vehicles": FakeTable(),
    "test-chauffeurs": FakeTable(),
    "test-quotes": FakeTable(),
    "test-notifications": FakeTable(),
    "test-payments": FakeTable(),
}


class FakeDynamoClient:
    def transact_write_items(self, TransactItems):
        for transaction in TransactItems:
            update = transaction["Update"]
            table = FAKE_TABLES[update["TableName"]]
            key = next(iter(update["Key"].values()))["S"]
            item = table.items[key]
            values = update["ExpressionAttributeValues"]
            if update["TableName"] == "test-bookings" and ":status" in values:
                item.update(status=values[":status"]["S"], resources_released_at=int(values[":updated"]["N"]), updated_at=int(values[":updated"]["N"]))
            elif update["TableName"] == "test-bookings":
                item.update(status="ASSIGNED", vehicle_id=values[":vehicle"]["S"], chauffeur_id=values[":chauffeur"]["S"], updated_at=int(values[":updated"]["N"]))
            else:
                target = ":available" if "= :available" in update["UpdateExpression"] else (":reserved" if ":reserved" in values else ":assigned")
                item["status"] = values[target]["S"]
                item["updated_at"] = int(values[":updated"]["N"])
        return {}


fake_boto3 = types.SimpleNamespace(
    resource=lambda service: types.SimpleNamespace(Table=lambda name: FAKE_TABLES[name]),
    client=lambda service: FakeDynamoClient(),
)
sys.modules["boto3"] = fake_boto3
os.environ["BOOKINGS_TABLE"] = "test-bookings"
os.environ["VEHICLES_TABLE"] = "test-vehicles"
os.environ["CHAUFFEURS_TABLE"] = "test-chauffeurs"
os.environ["QUOTES_TABLE"] = "test-quotes"
os.environ["NOTIFICATIONS_TABLE"] = "test-notifications"
os.environ["PAYMENTS_TABLE"] = "test-payments"
os.environ["PAYMENT_WEBHOOK_SECRET"] = "test-payment-webhook-secret-32-characters"
os.environ["BOOKING_TTL_DAYS"] = "30"
os.environ["ALLOWED_ORIGIN"] = "*"
test_salt = b"unit-test-salt"
test_digest = hashlib.pbkdf2_hmac("sha256", b"test-admin-password", test_salt, 10_000)
os.environ["ADMIN_PASSWORD_HASH"] = (
    f"10000:{base64.b64encode(test_salt).decode()}:{base64.b64encode(test_digest).decode()}"
)
operator_salt = b"unit-operator-salt"
operator_digest = hashlib.pbkdf2_hmac("sha256", b"test-operator-password", operator_salt, 10_000)
os.environ["OPERATOR_PASSWORD_HASH"] = (
    f"10000:{base64.b64encode(operator_salt).decode()}:{base64.b64encode(operator_digest).decode()}"
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
    def setUp(self):
        self.real_log_event = handler.log_event
        handler.log_event = lambda *_args, **_kwargs: None

    def tearDown(self):
        handler.log_event = self.real_log_event

    def test_home_page_loads(self):
        result = handler.lambda_handler(event("GET", "/"), None)
        self.assertEqual(result["statusCode"], 200)
        self.assertIn("Request a quote", result["body"])
        self.assertIn(r"Request recorded.\nReference", result["body"])
        self.assertIn("Check my booking", result["body"])
        self.assertIn("x-booking-token", result["body"])

    def test_requests_have_structured_safe_correlation_logs(self):
        request = event("POST", "/bookings", {"name": "Do Not Log This Name", "phone": "+2348111111111", "hub": "Lagos", "trip_type": "Local", "pickup": "Ikoyi", "destination": "Airport", "pickup_at": "2027-05-01T09:00", "end_at": "2027-05-01T12:00"})
        request["requestContext"]["requestId"] = "request-test-123"
        captured = io.StringIO()
        handler.log_event = self.real_log_event
        with redirect_stdout(captured):
            result = handler.lambda_handler(request, None)
        issued_token = json.loads(result["body"])["access_token"]
        records = [json.loads(line) for line in captured.getvalue().splitlines()]
        self.assertEqual(result["headers"]["x-request-id"], "request-test-123")
        self.assertEqual(records[0]["event"], "request_started")
        self.assertEqual(records[-1]["event"], "request_completed")
        self.assertTrue(all(record["request_id"] == "request-test-123" for record in records))
        self.assertTrue(all(record["actor_role"] == "PUBLIC" for record in records))
        self.assertNotIn("Do Not Log This Name", captured.getvalue())
        self.assertNotIn("+2348111111111", captured.getvalue())
        self.assertNotIn(issued_token, captured.getvalue())

    def test_health_reports_release_version(self):
        result = handler.lambda_handler(event("GET", "/health"), None)
        payload = json.loads(result["body"])
        self.assertEqual(payload["service"], "luxury-rental-demo")
        self.assertEqual(payload["release_version"], "local")

    def test_openapi_contract_is_served(self):
        result = handler.lambda_handler(event("GET", "/openapi.json"), None)
        payload = json.loads(result["body"])
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["headers"]["content-type"], "application/json; charset=utf-8")
        self.assertEqual(payload["info"]["title"], "Luxury Chauffeur Booking Demo API")

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
            "end_at": "2026-09-10T18:00",
            "vehicle_preference": "Executive SUV",
            "notes": "Demo only",
        }
        created = handler.lambda_handler(event("POST", "/bookings", request), None)
        self.assertEqual(created["statusCode"], 201)
        created_body = json.loads(created["body"])
        booking_id = created_body["booking_id"]
        access = {"x-booking-token": created_body["access_token"]}
        self.assertEqual(FAKE_TABLES["test-bookings"].items[booking_id]["schema_version"], 1)

        status = handler.lambda_handler(event("GET", f"/bookings/{booking_id}", headers=access), None)
        self.assertEqual(status["statusCode"], 200)
        self.assertEqual(json.loads(status["body"])["status"], "REQUESTED")
        self.assertEqual(handler.lambda_handler(event("GET", f"/bookings/{booking_id}"), None)["statusCode"], 404)
        self.assertEqual(handler.lambda_handler(event("GET", f"/bookings/{booking_id}", headers={"x-booking-token": "wrong"}), None)["statusCode"], 404)
        admin_list = handler.lambda_handler(event("GET", "/admin/bookings", headers={"x-admin-password": "test-admin-password"}), None)
        listed_booking = next(item for item in json.loads(admin_list["body"])["bookings"] if item["booking_id"] == booking_id)
        self.assertNotIn("customer_token_hash", listed_booking)

    def test_invalid_hub_is_rejected(self):
        request = {
            "name": "Demo Customer",
            "phone": "+2348000000000",
            "hub": "Invalid",
            "trip_type": "Local",
            "pickup": "A",
            "destination": "B",
            "pickup_at": "2026-09-10T09:00",
            "end_at": "2026-09-10T18:00",
        }
        result = handler.lambda_handler(event("POST", "/bookings", request), None)
        self.assertEqual(result["statusCode"], 400)

    def test_booking_contact_and_trip_boundaries_are_enforced(self):
        valid = {
            "name": "Boundary Test", "phone": "+2348000000099", "email": "safe@example.com",
            "hub": "Lagos", "trip_type": "Local", "pickup": "Ikoyi", "destination": "Lekki",
            "pickup_at": "2027-01-01T09:00", "end_at": "2027-01-01T12:00",
        }
        invalid_cases = [
            ({"phone": "12345"}, "phone"),
            ({"email": "not-an-email"}, "email"),
            ({"pickup_at": "2020-01-01T09:00", "end_at": "2020-01-01T12:00"}, "future"),
            ({"pickup_at": "2027-01-01T09:00", "end_at": "2027-02-02T09:00"}, "30 days"),
            ({"pickup_at": "2027-01-01T09:00", "end_at": "2027-01-01T12:00Z"}, "valid pickup"),
        ]
        for changes, expected in invalid_cases:
            with self.subTest(changes=changes):
                result = handler.lambda_handler(event("POST", "/bookings", {**valid, **changes}), None)
                self.assertEqual(result["statusCode"], 400)
                self.assertIn(expected, json.loads(result["body"])["error"].lower())

    def test_oversized_request_is_rejected_before_parsing(self):
        request = event("POST", "/bookings")
        request["body"] = "x" * (handler.MAX_REQUEST_BYTES + 1)
        result = handler.lambda_handler(request, None)
        self.assertEqual(result["statusCode"], 413)

    def test_resource_routes_require_exact_shape_and_uuid(self):
        headers = {"x-admin-password": "test-admin-password"}
        resource_id = "00000000-0000-4000-8000-000000000001"
        malformed = handler.lambda_handler(
            event("PATCH", f"/admin/bookings/{resource_id}/unexpected", {"status": "REVIEWING"}, headers), None
        )
        invalid_id = handler.lambda_handler(event("GET", "/bookings/not-a-uuid", headers={"x-booking-token": "token"}), None)
        self.assertEqual(malformed["statusCode"], 404)
        self.assertEqual(invalid_id["statusCode"], 404)

    def test_notification_outbox_can_be_processed(self):
        headers = {"x-admin-password": "test-admin-password"}
        booking = handler.lambda_handler(
            event("POST", "/bookings", {"name": "Notification Test", "phone": "+2348000000005", "hub": "Ogun", "trip_type": "Local", "pickup": "Ibara", "destination": "Kuto", "pickup_at": "2027-02-01T09:00", "end_at": "2027-02-01T12:00"}),
            None,
        )
        self.assertEqual(booking["statusCode"], 201)
        outbox = handler.lambda_handler(event("GET", "/admin/notifications", headers=headers), None)
        pending = next(item for item in json.loads(outbox["body"])["notifications"] if item["event_type"] == "BOOKING_REQUESTED")
        processed = handler.lambda_handler(
            event("PATCH", f"/admin/notifications/{pending['notification_id']}", {"status": "PROCESSED"}, headers),
            None,
        )
        self.assertEqual(json.loads(processed["body"])["status"], "PROCESSED")

    def test_admin_dashboard_requires_password(self):
        page = handler.lambda_handler(event("GET", "/admin"), None)
        denied = handler.lambda_handler(event("GET", "/admin/bookings"), None)
        self.assertEqual(page["statusCode"], 200)
        self.assertIn("Operations Dashboard", page["body"])
        self.assertEqual(denied["statusCode"], 401)

    def test_operator_can_work_bookings_but_cannot_change_fleet(self):
        operator = {"x-admin-password": "test-operator-password"}
        session = handler.lambda_handler(event("GET", "/admin/session", headers=operator), None)
        listed = handler.lambda_handler(event("GET", "/admin/vehicles", headers=operator), None)
        create_vehicle = handler.lambda_handler(event("POST", "/admin/vehicles", {"name": "Forbidden Vehicle", "hub": "Lagos"}, operator), None)
        booking = handler.lambda_handler(event("POST", "/bookings", {"name": "Operator Test", "phone": "+2348000000007", "hub": "Lagos", "trip_type": "Local", "pickup": "Ikoyi", "destination": "Lekki", "pickup_at": "2027-06-01T09:00", "end_at": "2027-06-01T12:00"}), None)
        booking_id = json.loads(booking["body"])["booking_id"]
        reviewed = handler.lambda_handler(event("PATCH", f"/admin/bookings/{booking_id}", {"status": "REVIEWING"}, operator), None)
        self.assertEqual(json.loads(session["body"])["role"], "OPERATOR")
        self.assertEqual(listed["statusCode"], 200)
        self.assertEqual(create_vehicle["statusCode"], 403)
        self.assertEqual(reviewed["statusCode"], 200)

    def test_admin_session_has_full_role(self):
        session = handler.lambda_handler(event("GET", "/admin/session", headers={"x-admin-password": "test-admin-password"}), None)
        self.assertEqual(json.loads(session["body"])["role"], "ADMIN")

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
                    "end_at": "2026-09-12T14:00",
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

    def test_admin_can_atomically_assign_resources(self):
        headers = {"x-admin-password": "test-admin-password"}
        booking = handler.lambda_handler(
            event("POST", "/bookings", {"name": "Assignment Test", "phone": "+2348000000002", "hub": "Oyo", "trip_type": "Local", "pickup": "Bodija", "destination": "Ring Road", "pickup_at": "2026-10-01T09:00", "end_at": "2026-10-01T12:00"}),
            None,
        )
        vehicle = handler.lambda_handler(event("POST", "/admin/vehicles", {"name": "Lexus RX", "hub": "Oyo"}, headers), None)
        chauffeur = handler.lambda_handler(event("POST", "/admin/chauffeurs", {"name": "Assignment Chauffeur", "hub": "Oyo"}, headers), None)
        assigned = handler.lambda_handler(
            event(
                "PATCH",
                f"/admin/bookings/{json.loads(booking['body'])['booking_id']}/assignment",
                {"vehicle_id": json.loads(vehicle["body"])["vehicle_id"], "chauffeur_id": json.loads(chauffeur["body"])["chauffeur_id"]},
                headers,
            ),
            None,
        )
        self.assertEqual(assigned["statusCode"], 200)
        self.assertEqual(json.loads(assigned["body"])["status"], "ASSIGNED")
        booking_body = json.loads(booking["body"])
        vehicle_id = json.loads(vehicle["body"])["vehicle_id"]
        chauffeur_id = json.loads(chauffeur["body"])["chauffeur_id"]
        overlapping = handler.lambda_handler(
            event("POST", "/bookings", {"name": "Conflict Test", "phone": "+2348000000003", "hub": "Oyo", "trip_type": "Local", "pickup": "Dugbe", "destination": "Bodija", "pickup_at": "2026-10-01T10:00", "end_at": "2026-10-01T13:00"}),
            None,
        )
        rejected = handler.lambda_handler(
            event(
                "PATCH",
                f"/admin/bookings/{json.loads(overlapping['body'])['booking_id']}/assignment",
                {"vehicle_id": json.loads(vehicle["body"])["vehicle_id"], "chauffeur_id": json.loads(chauffeur["body"])["chauffeur_id"]},
                headers,
            ),
            None,
        )
        self.assertEqual(rejected["statusCode"], 409)
        invalid_cancel = handler.lambda_handler(
            event("PATCH", f"/bookings/{booking_body['booking_id']}", {"action": "DELETE"}, {"x-booking-token": booking_body["access_token"]}), None
        )
        self.assertEqual(invalid_cancel["statusCode"], 400)
        cancelled = handler.lambda_handler(
            event("PATCH", f"/bookings/{booking_body['booking_id']}", {"action": "CANCEL"}, {"x-booking-token": booking_body["access_token"]}), None
        )
        self.assertEqual(json.loads(cancelled["body"])["status"], "CANCELLED")
        self.assertEqual(FAKE_TABLES["test-vehicles"].items[vehicle_id]["status"], "AVAILABLE")
        self.assertEqual(FAKE_TABLES["test-chauffeurs"].items[chauffeur_id]["status"], "AVAILABLE")
        terminal_assignment = handler.lambda_handler(
            event("PATCH", f"/admin/bookings/{booking_body['booking_id']}/assignment", {"vehicle_id": vehicle_id, "chauffeur_id": chauffeur_id}, headers), None
        )
        self.assertEqual(terminal_assignment["statusCode"], 409)
        reassigned = handler.lambda_handler(
            event("PATCH", f"/admin/bookings/{json.loads(overlapping['body'])['booking_id']}/assignment", {"vehicle_id": vehicle_id, "chauffeur_id": chauffeur_id}, headers), None
        )
        self.assertEqual(reassigned["statusCode"], 200)
        second_booking_id = json.loads(overlapping["body"])["booking_id"]
        handler.lambda_handler(event("PATCH", f"/admin/bookings/{second_booking_id}", {"status": "IN_PROGRESS"}, headers), None)
        completed = handler.lambda_handler(event("PATCH", f"/admin/bookings/{second_booking_id}", {"status": "COMPLETED"}, headers), None)
        self.assertEqual(json.loads(completed["body"])["status"], "COMPLETED")
        self.assertEqual(FAKE_TABLES["test-vehicles"].items[vehicle_id]["status"], "AVAILABLE")
        self.assertEqual(FAKE_TABLES["test-chauffeurs"].items[chauffeur_id]["status"], "AVAILABLE")

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

    def test_quotes_are_versioned_and_latest_is_public(self):
        headers = {"x-admin-password": "test-admin-password"}
        booking = handler.lambda_handler(
            event("POST", "/bookings", {"name": "Quote Test", "phone": "+2348000000004", "hub": "Lagos", "trip_type": "Interstate", "pickup": "Ikoyi", "destination": "Abeokuta", "pickup_at": "2027-01-10T09:00", "end_at": "2027-01-10T18:00"}),
            None,
        )
        booking_body = json.loads(booking["body"])
        booking_id = booking_body["booking_id"]
        customer_headers = {"x-booking-token": booking_body["access_token"]}
        first = handler.lambda_handler(event("POST", f"/admin/bookings/{booking_id}/quotes", {"amount_ngn": 250000, "valid_until": "2027-01-05T18:00", "notes": "Initial estimate"}, headers), None)
        second = handler.lambda_handler(event("POST", f"/admin/bookings/{booking_id}/quotes", {"amount_ngn": 275000, "valid_until": "2027-01-06T18:00", "notes": "Includes interstate tolls"}, headers), None)
        history = handler.lambda_handler(event("GET", f"/admin/bookings/{booking_id}/quotes", headers=headers), None)
        latest = handler.lambda_handler(event("GET", f"/bookings/{booking_id}/quote", headers=customer_headers), None)
        self.assertEqual(first["statusCode"], 201)
        self.assertEqual(json.loads(second["body"])["version"], 2)
        self.assertEqual(json.loads(history["body"])["count"], 2)
        self.assertEqual(json.loads(latest["body"])["amount_ngn"], 275000)

    def test_customer_can_accept_or_decline_latest_quote_once(self):
        staff = {"x-admin-password": "test-admin-password"}
        decisions = (("ACCEPTED", "QUOTED"), ("DECLINED", "REVIEWING"))
        for index, (decision, expected_booking_status) in enumerate(decisions):
            with self.subTest(decision=decision):
                booking = handler.lambda_handler(
                    event("POST", "/bookings", {"name": f"Decision {index}", "phone": f"+234800000001{index}", "hub": "Lagos", "trip_type": "Local", "pickup": "Ikoyi", "destination": "Lekki", "pickup_at": "2027-04-01T09:00", "end_at": "2027-04-01T12:00"}), None
                )
                created = json.loads(booking["body"])
                booking_id = created["booking_id"]
                customer = {"x-booking-token": created["access_token"]}
                handler.lambda_handler(event("POST", f"/admin/bookings/{booking_id}/quotes", {"amount_ngn": 200000 + index, "valid_until": "2027-03-25T18:00"}, staff), None)
                denied = handler.lambda_handler(event("PATCH", f"/bookings/{booking_id}/quote", {"decision": decision}, {"x-booking-token": "wrong"}), None)
                decided = handler.lambda_handler(event("PATCH", f"/bookings/{booking_id}/quote", {"decision": decision}, customer), None)
                repeated = handler.lambda_handler(event("PATCH", f"/bookings/{booking_id}/quote", {"decision": decision}, customer), None)
                latest = handler.lambda_handler(event("GET", f"/bookings/{booking_id}/quote", headers=customer), None)
                self.assertEqual(denied["statusCode"], 404)
                self.assertEqual(json.loads(decided["body"])["status"], expected_booking_status)
                self.assertEqual(json.loads(latest["body"])["status"], decision)
                self.assertEqual(repeated["statusCode"], 409)

    def test_signed_payment_webhook_is_idempotent(self):
        headers = {"x-admin-password": "test-admin-password"}
        booking = handler.lambda_handler(
            event("POST", "/bookings", {"name": "Payment Test", "phone": "+2348000000006", "hub": "Abuja", "trip_type": "Local", "pickup": "Maitama", "destination": "Airport", "pickup_at": "2027-03-01T09:00", "end_at": "2027-03-01T12:00"}),
            None,
        )
        booking_body = json.loads(booking["body"])
        booking_id = booking_body["booking_id"]
        customer_headers = {"x-booking-token": booking_body["access_token"]}
        handler.lambda_handler(event("POST", f"/admin/bookings/{booking_id}/quotes", {"amount_ngn": 180000, "valid_until": "2027-02-25T18:00"}, headers), None)
        blocked = handler.lambda_handler(event("POST", f"/admin/bookings/{booking_id}/payments", {}, headers), None)
        self.assertEqual(blocked["statusCode"], 409)
        handler.lambda_handler(event("PATCH", f"/bookings/{booking_id}/quote", {"decision": "ACCEPTED"}, customer_headers), None)
        created = handler.lambda_handler(event("POST", f"/admin/bookings/{booking_id}/payments", {}, headers), None)
        self.assertEqual(created["statusCode"], 201)
        payment_id = json.loads(created["body"])["payment_id"]

        webhook = event("POST", "/webhooks/payments", {"event_id": "provider-event-1", "payment_id": payment_id, "status": "PAID"})
        webhook["headers"] = {"x-webhook-signature": hmac.new(os.environ["PAYMENT_WEBHOOK_SECRET"].encode(), webhook["body"].encode(), hashlib.sha256).hexdigest()}
        first = handler.lambda_handler(webhook, None)
        duplicate = handler.lambda_handler(webhook, None)
        public_status = handler.lambda_handler(event("GET", f"/bookings/{booking_id}/payment", headers=customer_headers), None)
        booking_status = handler.lambda_handler(event("GET", f"/bookings/{booking_id}", headers=customer_headers), None)
        notifications = handler.lambda_handler(event("GET", "/admin/notifications", headers=headers), None)
        payment_confirmations = [item for item in json.loads(notifications["body"])["notifications"] if item.get("booking_id") == booking_id and item.get("event_type") == "PAYMENT_CONFIRMED"]
        self.assertEqual(first["statusCode"], 200)
        self.assertFalse(json.loads(first["body"])["duplicate"])
        self.assertTrue(json.loads(duplicate["body"])["duplicate"])
        self.assertEqual(json.loads(public_status["body"])["status"], "PAID")
        self.assertEqual(json.loads(booking_status["body"])["status"], "CONFIRMED")
        self.assertEqual(len(payment_confirmations), 1)
        paid_cancellation = handler.lambda_handler(event("PATCH", f"/bookings/{booking_id}", {"action": "CANCEL"}, customer_headers), None)
        self.assertEqual(paid_cancellation["statusCode"], 409)

    def test_payment_webhook_rejects_invalid_signature(self):
        result = handler.lambda_handler(event("POST", "/webhooks/payments", {"event_id": "bad", "payment_id": "unknown", "status": "PAID"}, {"x-webhook-signature": "invalid"}), None)
        self.assertEqual(result["statusCode"], 401)

    def test_admin_can_manage_chauffeur_availability(self):
        headers = {"x-admin-password": "test-admin-password"}
        created = handler.lambda_handler(
            event("POST", "/admin/chauffeurs", {"name": "Demo Chauffeur", "hub": "Abuja"}, headers),
            None,
        )
        self.assertEqual(created["statusCode"], 201)
        chauffeur_id = json.loads(created["body"])["chauffeur_id"]
        listed = handler.lambda_handler(event("GET", "/admin/chauffeurs", headers=headers), None)
        self.assertIn(chauffeur_id, {item["chauffeur_id"] for item in json.loads(listed["body"])["items"]})
        updated = handler.lambda_handler(
            event("PATCH", f"/admin/chauffeurs/{chauffeur_id}", {"status": "OFF_DUTY"}, headers),
            None,
        )
        self.assertEqual(json.loads(updated["body"])["status"], "OFF_DUTY")


if __name__ == "__main__":
    unittest.main()
