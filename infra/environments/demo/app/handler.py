import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from contextvars import ContextVar
from decimal import Decimal
from datetime import datetime, timedelta
from pathlib import Path

import boto3


BOOKINGS_TABLE_NAME = os.environ["BOOKINGS_TABLE"]
VEHICLES_TABLE_NAME = os.environ["VEHICLES_TABLE"]
CHAUFFEURS_TABLE_NAME = os.environ["CHAUFFEURS_TABLE"]
QUOTES_TABLE_NAME = os.environ["QUOTES_TABLE"]
NOTIFICATIONS_TABLE_NAME = os.environ["NOTIFICATIONS_TABLE"]
PAYMENTS_TABLE_NAME = os.environ["PAYMENTS_TABLE"]
TABLE = boto3.resource("dynamodb").Table(BOOKINGS_TABLE_NAME)
VEHICLES = boto3.resource("dynamodb").Table(VEHICLES_TABLE_NAME)
CHAUFFEURS = boto3.resource("dynamodb").Table(CHAUFFEURS_TABLE_NAME)
QUOTES = boto3.resource("dynamodb").Table(QUOTES_TABLE_NAME)
NOTIFICATIONS = boto3.resource("dynamodb").Table(NOTIFICATIONS_TABLE_NAME)
PAYMENTS = boto3.resource("dynamodb").Table(PAYMENTS_TABLE_NAME)
DYNAMO_CLIENT = boto3.client("dynamodb")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
TTL_DAYS = int(os.environ.get("BOOKING_TTL_DAYS", "30"))
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
OPERATOR_PASSWORD_HASH = os.environ.get("OPERATOR_PASSWORD_HASH", "")
PAYMENT_WEBHOOK_SECRET = os.environ.get("PAYMENT_WEBHOOK_SECRET", "")
RELEASE_VERSION = os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", "local")
SCHEMA_VERSION = 1
MAX_REQUEST_BYTES = 16_384
MAX_IDEMPOTENCY_KEY_LENGTH = 200
IDEMPOTENCY_NAMESPACE = uuid.UUID("79a04631-d896-4ef0-8874-932ead4f4588")
MIN_PBKDF2_ITERATIONS = 210_000
MAX_PBKDF2_ITERATIONS = 2_000_000
MIN_PASSWORD_SALT_BYTES = 16
PASSWORD_DIGEST_BYTES = 32
OPENAPI_TEXT = Path(__file__).with_name("openapi.json").read_text(encoding="utf-8")
REQUEST_ID = ContextVar("request_id", default="unknown")
ACTOR_ROLE = ContextVar("actor_role", default="PUBLIC")
HUBS = {"Lagos", "Ogun", "Oyo", "Abuja"}
TRIP_TYPES = {"Local", "Interstate"}
HUB_STATES = {"Lagos": "Lagos", "Ogun": "Ogun", "Oyo": "Oyo", "Abuja": "FCT"}
NIGERIAN_STATES = {
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo",
    "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa",
    "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara",
}
BOOKING_STATUSES = {"REQUESTED", "REVIEWING", "QUOTED", "CONFIRMED", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "DECLINED", "CANCELLED"}
BOOKING_TRANSITIONS = {
    "REQUESTED": {"REVIEWING", "DECLINED", "CANCELLED"},
    "REVIEWING": {"QUOTED", "DECLINED", "CANCELLED"},
    "QUOTED": {"REVIEWING", "CONFIRMED", "DECLINED", "CANCELLED"},
    "CONFIRMED": {"ASSIGNED", "CANCELLED"},
    "ASSIGNED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED"},
    "COMPLETED": set(),
    "DECLINED": set(),
    "CANCELLED": set(),
}
VEHICLE_STATUSES = {"AVAILABLE", "RESERVED", "ON_TRIP", "MAINTENANCE", "INACTIVE"}
CHAUFFEUR_STATUSES = {"AVAILABLE", "ASSIGNED", "OFF_DUTY", "INACTIVE"}
VEHICLE_MANUAL_TRANSITIONS = {
    "AVAILABLE": {"MAINTENANCE", "INACTIVE"},
    "MAINTENANCE": {"AVAILABLE", "INACTIVE"},
    "INACTIVE": {"AVAILABLE", "MAINTENANCE"},
    "RESERVED": set(),
    "ON_TRIP": set(),
}
CHAUFFEUR_MANUAL_TRANSITIONS = {
    "AVAILABLE": {"OFF_DUTY", "INACTIVE"},
    "OFF_DUTY": {"AVAILABLE", "INACTIVE"},
    "INACTIVE": {"AVAILABLE", "OFF_DUTY"},
    "ASSIGNED": set(),
}


def response(status, body, content_type="application/json; charset=utf-8"):
    payload = body if isinstance(body, str) else json.dumps(body, default=lambda value: int(value) if isinstance(value, Decimal) else str(value))
    return {
        "statusCode": status,
        "headers": {
            "content-type": content_type,
            "access-control-allow-origin": ALLOWED_ORIGIN,
            "cache-control": "no-store",
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "no-referrer",
            "content-security-policy": "default-src 'self' 'unsafe-inline'; connect-src 'self' https:; form-action 'self'; frame-ancestors 'none'",
            "x-request-id": REQUEST_ID.get(),
        },
        "body": payload,
    }


def log_event(event_name, level="INFO", **fields):
    record = {
        "timestamp": int(time.time()),
        "level": level,
        "service": "luxury-rental-demo",
        "release_version": RELEASE_VERSION,
        "request_id": REQUEST_ID.get(),
        "actor_role": ACTOR_ROLE.get(),
        "event": event_name,
        **fields,
    }
    print(json.dumps(record, separators=(",", ":"), default=str))


def clean(value, maximum):
    return str(value or "").strip()[:maximum]


def current_datetime(tzinfo=None):
    return datetime.now(tzinfo)


def valid_uuid(value):
    try:
        return str(uuid.UUID(str(value))) == str(value).lower()
    except (ValueError, TypeError, AttributeError):
        return False


def booking_access_token(event):
    headers = {str(key).lower(): value for key, value in (event.get("headers") or {}).items()}
    return clean(headers.get("x-booking-token"), 200)


def request_header(event, name):
    headers = {str(key).lower(): value for key, value in (event.get("headers") or {}).items()}
    return clean(headers.get(name.lower()), MAX_IDEMPOTENCY_KEY_LENGTH)


def booking_access_allowed(event, booking):
    supplied = booking_access_token(event)
    expected = booking.get("customer_token_hash", "") if booking else ""
    actual = hashlib.sha256(supplied.encode("utf-8")).hexdigest() if supplied else ""
    return bool(supplied and expected and hmac.compare_digest(actual, expected))


def notification_record(booking_id, event_type, message, audience="CUSTOMER"):
    now = int(time.time())
    return {
        "schema_version": SCHEMA_VERSION,
        "notification_id": str(uuid.uuid4()),
        "booking_id": booking_id,
        "event_type": event_type,
        "audience": audience,
        "channel": "PENDING_PROVIDER",
        "message": clean(message, 300),
        "status": "PENDING",
        "created_at": now,
        "expires_at": now + (30 * 86400),
    }


def queue_notification(booking_id, event_type, message, audience="CUSTOMER"):
    item = notification_record(booking_id, event_type, message, audience)
    NOTIFICATIONS.put_item(Item=item, ConditionExpression="attribute_not_exists(notification_id)")
    return item


def dynamodb_item(item):
    return {
        key: ({"N": str(value)} if isinstance(value, (int, Decimal)) else {"S": str(value)})
        for key, value in item.items()
    }


def create_booking(event):
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})

    booking = {
        "name": clean(data.get("name"), 100),
        "phone": clean(data.get("phone"), 30),
        "email": clean(data.get("email"), 150),
        "hub": clean(data.get("hub"), 20),
        "trip_type": clean(data.get("trip_type"), 20),
        "pickup": clean(data.get("pickup"), 200),
        "destination": clean(data.get("destination"), 200),
        "destination_state": clean(data.get("destination_state"), 30),
        "pickup_at": clean(data.get("pickup_at"), 40),
        "end_at": clean(data.get("end_at"), 40),
        "vehicle_preference": clean(data.get("vehicle_preference"), 100),
        "notes": clean(data.get("notes"), 500),
    }

    required = ["name", "phone", "hub", "trip_type", "pickup", "destination", "pickup_at", "end_at"]
    missing = [field for field in required if not booking[field]]
    if missing:
        return response(400, {"error": "Complete all required fields.", "fields": missing})
    if booking["hub"] not in HUBS or booking["trip_type"] not in TRIP_TYPES:
        return response(400, {"error": "Select a valid hub and trip type."})
    if booking["trip_type"] == "Interstate":
        if booking["destination_state"] not in NIGERIAN_STATES:
            return response(400, {"error": "Select a valid destination state for an interstate trip."})
        if booking["destination_state"] == HUB_STATES[booking["hub"]]:
            return response(400, {"error": "An interstate destination must be outside the fleet hub state."})
    elif booking["destination_state"] and booking["destination_state"] != HUB_STATES[booking["hub"]]:
        return response(400, {"error": "Select Interstate when the destination is outside the fleet hub state."})
    phone_digits = re.sub(r"\D", "", booking["phone"])
    if not 10 <= len(phone_digits) <= 15 or not re.fullmatch(r"\+?[0-9 ()-]+", booking["phone"]):
        return response(400, {"error": "Provide a valid phone number."})
    if booking["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", booking["email"]):
        return response(400, {"error": "Provide a valid email address."})
    try:
        pickup_time = datetime.fromisoformat(booking["pickup_at"])
        end_time = datetime.fromisoformat(booking["end_at"])
        now = current_datetime(pickup_time.tzinfo)
        if end_time <= pickup_time:
            return response(400, {"error": "Expected end time must be after pickup time."})
        if pickup_time <= now:
            return response(400, {"error": "Pickup time must be in the future."})
        if pickup_time > now + timedelta(days=366):
            return response(400, {"error": "Pickup time cannot be more than 366 days ahead."})
        if end_time - pickup_time > timedelta(days=30):
            return response(400, {"error": "A booking request cannot exceed 30 days."})
    except (TypeError, ValueError):
        return response(400, {"error": "Provide valid pickup and expected end times."})

    now = int(time.time())
    idempotency_key = request_header(event, "x-idempotency-key")
    supplied_token = booking_access_token(event)
    if idempotency_key and (len(idempotency_key) < 16 or len(supplied_token) < 32):
        return response(400, {"error": "Idempotent booking requests require a key of at least 16 characters and a customer token of at least 32 characters."})
    idempotency_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else ""
    request_fingerprint = hashlib.sha256(json.dumps(booking, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    booking_id = str(uuid.uuid5(IDEMPOTENCY_NAMESPACE, idempotency_hash)) if idempotency_key else str(uuid.uuid4())
    access_token = supplied_token if idempotency_key else secrets.token_urlsafe(32)
    if idempotency_key:
        existing = TABLE.get_item(Key={"booking_id": booking_id}).get("Item")
        if existing:
            if existing.get("request_fingerprint") != request_fingerprint or not booking_access_allowed(event, existing):
                return response(409, {"error": "This idempotency key is already associated with another booking request."})
            return response(200, {"booking_id": booking_id, "access_token": access_token, "status": existing["status"], "message": "The original booking request was returned; no duplicate was created.", "duplicate": True})
    item = {
        "schema_version": SCHEMA_VERSION,
        "booking_id": booking_id,
        "status": "REQUESTED",
        "created_at": now,
        "expires_at": now + TTL_DAYS * 86400,
        "customer_token_hash": hashlib.sha256(access_token.encode("utf-8")).hexdigest(),
        **booking,
    }
    if idempotency_key:
        item.update(idempotency_hash=idempotency_hash, request_fingerprint=request_fingerprint)
    notification = notification_record(booking_id, "BOOKING_REQUESTED", "Your booking request was received and is awaiting review.")
    try:
        DYNAMO_CLIENT.transact_write_items(TransactItems=[
            {"Put": {"TableName": BOOKINGS_TABLE_NAME, "Item": dynamodb_item(item), "ConditionExpression": "attribute_not_exists(booking_id)"}},
            {"Put": {"TableName": NOTIFICATIONS_TABLE_NAME, "Item": dynamodb_item(notification), "ConditionExpression": "attribute_not_exists(notification_id)"}},
        ])
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") != "TransactionCanceledException" or not idempotency_key:
            raise
        existing = TABLE.get_item(Key={"booking_id": booking_id}).get("Item")
        if not existing:
            return response(409, {"error": "The booking request was not committed; retry the same request."})
        if existing.get("request_fingerprint") != request_fingerprint or not booking_access_allowed(event, existing):
            return response(409, {"error": "This idempotency key is already associated with another booking request."})
        return response(200, {"booking_id": booking_id, "access_token": access_token, "status": existing["status"], "message": "The original booking request was returned; no duplicate was created.", "duplicate": True})
    log_event("booking_created", booking_id=booking_id, hub=booking["hub"], trip_type=booking["trip_type"])
    return response(201, {"booking_id": booking_id, "access_token": access_token, "status": "REQUESTED", "message": "Your demo request has been recorded. Save the access token; it is shown only once."})


def booking_status(event, booking_id):
    result = TABLE.get_item(Key={"booking_id": booking_id})
    item = result.get("Item")
    if not booking_access_allowed(event, item):
        return response(404, {"error": "Booking request not found."})
    return response(200, {key: item[key] for key in ("booking_id", "status", "created_at")})


def admin_password(event):
    headers = {str(key).lower(): value for key, value in (event.get("headers") or {}).items()}
    return headers.get("x-staff-password") or headers.get("x-admin-password", "")


def password_matches(password, encoded_hash):
    if not encoded_hash:
        return False
    try:
        iterations_text, salt_text, expected_text = encoded_hash.split(":", 2)
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text, validate=True)
        expected = base64.b64decode(expected_text, validate=True)
        if not MIN_PBKDF2_ITERATIONS <= iterations <= MAX_PBKDF2_ITERATIONS:
            return False
        if len(salt) < MIN_PASSWORD_SALT_BYTES or len(expected) != PASSWORD_DIGEST_BYTES:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, base64.binascii.Error):
        return False


def authenticated_role(event):
    password = admin_password(event)
    if password_matches(password, ADMIN_PASSWORD_HASH):
        ACTOR_ROLE.set("ADMIN")
        return "ADMIN"
    if password_matches(password, OPERATOR_PASSWORD_HASH):
        ACTOR_ROLE.set("OPERATOR")
        return "OPERATOR"
    return None


def require_admin(event, allowed_roles=None):
    if not ADMIN_PASSWORD_HASH:
        return response(503, {"error": "Dashboard authentication is not configured."})
    role = authenticated_role(event)
    if not role:
        return response(401, {"error": "Invalid staff password."})
    if allowed_roles and role not in allowed_roles:
        return response(403, {"error": "Administrator access is required for this action."})
    return None


def staff_session(event):
    denied = require_admin(event)
    if denied:
        return denied
    return response(200, {"role": ACTOR_ROLE.get()})


def operations_summary(event):
    denied = require_admin(event)
    if denied:
        return denied
    bookings = TABLE.scan(Limit=100).get("Items", [])
    vehicles = VEHICLES.scan(Limit=100).get("Items", [])
    chauffeurs = CHAUFFEURS.scan(Limit=100).get("Items", [])
    payments = [item for item in PAYMENTS.scan(Limit=100).get("Items", []) if item.get("record_type") == "PAYMENT"]

    def counts(items, field, known_values):
        return {value: sum(1 for item in items if item.get(field) == value) for value in sorted(known_values)}

    payment_statuses = counts(payments, "status", {"PENDING", "PAID", "FAILED"})
    return response(200, {
        "generated_at": int(time.time()),
        "scope": {"mode": "bounded_demo_scan", "maximum_records_per_table": 100},
        "bookings": {
            "total": len(bookings),
            "by_status": counts(bookings, "status", BOOKING_STATUSES),
            "by_hub": counts(bookings, "hub", HUBS),
            "interstate": sum(1 for item in bookings if item.get("trip_type") == "Interstate"),
            "accepted_quotes": sum(1 for item in bookings if item.get("quote_status") == "ACCEPTED"),
        },
        "fleet": {
            "vehicles": {"total": len(vehicles), "by_status": counts(vehicles, "status", VEHICLE_STATUSES)},
            "chauffeurs": {"total": len(chauffeurs), "by_status": counts(chauffeurs, "status", CHAUFFEUR_STATUSES)},
        },
        "payments": {
            "total": len(payments),
            "by_status": payment_statuses,
            "paid_amount_ngn": sum(int(item.get("amount_ngn", 0)) for item in payments if item.get("status") == "PAID"),
            "pending_amount_ngn": sum(int(item.get("amount_ngn", 0)) for item in payments if item.get("status") == "PENDING"),
        },
    })


def list_bookings(event):
    denied = require_admin(event)
    if denied:
        return denied
    result = TABLE.scan(Limit=50)
    private_fields = {"customer_token_hash", "idempotency_hash", "request_fingerprint"}
    items = [{key: value for key, value in item.items() if key not in private_fields} for item in result.get("Items", [])]
    for item in items:
        item["allowed_transitions"] = sorted(BOOKING_TRANSITIONS.get(item.get("status"), set()))
    items.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    return response(200, {"bookings": items, "count": len(items), "limited": "Last 50 scanned records"})


def change_booking_status(booking, status):
    booking_id = booking["booking_id"]
    current_status = booking.get("status", "")
    now = int(time.time())
    release_resources = status in {"DECLINED", "CANCELLED", "COMPLETED"} and all(
        booking.get(field) for field in ("vehicle_id", "chauffeur_id")
    )
    start_trip = status == "IN_PROGRESS" and all(booking.get(field) for field in ("vehicle_id", "chauffeur_id"))
    terminal = status in {"DECLINED", "CANCELLED", "COMPLETED"}
    messages = {
        "DECLINED": "The booking request was declined.",
        "CANCELLED": "The booking was cancelled.",
        "COMPLETED": "The trip was completed. Thank you for riding with us.",
    }
    notification = notification_record(booking_id, f"BOOKING_{status}", messages[status]) if terminal else None
    try:
        if release_resources:
            DYNAMO_CLIENT.transact_write_items(
                TransactItems=[
                    {"Update": {"TableName": BOOKINGS_TABLE_NAME, "Key": {"booking_id": {"S": booking_id}}, "UpdateExpression": "SET #s = :status, resources_released_at = :updated, updated_at = :updated", "ConditionExpression": "#s = :current_status", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":status": {"S": status}, ":current_status": {"S": current_status}, ":updated": {"N": str(now)}}}},
                    {"Update": {"TableName": VEHICLES_TABLE_NAME, "Key": {"vehicle_id": {"S": booking["vehicle_id"]}}, "UpdateExpression": "SET #s = :available, updated_at = :updated", "ConditionExpression": "#s = :reserved OR #s = :on_trip", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":available": {"S": "AVAILABLE"}, ":reserved": {"S": "RESERVED"}, ":on_trip": {"S": "ON_TRIP"}, ":updated": {"N": str(now)}}}},
                    {"Update": {"TableName": CHAUFFEURS_TABLE_NAME, "Key": {"chauffeur_id": {"S": booking["chauffeur_id"]}}, "UpdateExpression": "SET #s = :available, updated_at = :updated", "ConditionExpression": "#s = :assigned", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":available": {"S": "AVAILABLE"}, ":assigned": {"S": "ASSIGNED"}, ":updated": {"N": str(now)}}}},
                    {"Put": {"TableName": NOTIFICATIONS_TABLE_NAME, "Item": dynamodb_item(notification), "ConditionExpression": "attribute_not_exists(notification_id)"}},
                ]
            )
            updated = {**booking, "status": status, "resources_released_at": now, "updated_at": now}
        elif start_trip:
            trip_notification = notification_record(booking_id, "TRIP_STARTED", "Your chauffeur-driven trip is now in progress.")
            DYNAMO_CLIENT.transact_write_items(TransactItems=[
                {"Update": {"TableName": BOOKINGS_TABLE_NAME, "Key": {"booking_id": {"S": booking_id}}, "UpdateExpression": "SET #s = :in_progress, updated_at = :updated", "ConditionExpression": "#s = :assigned", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":in_progress": {"S": "IN_PROGRESS"}, ":assigned": {"S": "ASSIGNED"}, ":updated": {"N": str(now)}}}},
                {"Update": {"TableName": VEHICLES_TABLE_NAME, "Key": {"vehicle_id": {"S": booking["vehicle_id"]}}, "UpdateExpression": "SET #s = :on_trip, updated_at = :updated", "ConditionExpression": "#s = :reserved", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":on_trip": {"S": "ON_TRIP"}, ":reserved": {"S": "RESERVED"}, ":updated": {"N": str(now)}}}},
                {"Update": {"TableName": CHAUFFEURS_TABLE_NAME, "Key": {"chauffeur_id": {"S": booking["chauffeur_id"]}}, "UpdateExpression": "SET updated_at = :updated", "ConditionExpression": "#s = :assigned", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":assigned": {"S": "ASSIGNED"}, ":updated": {"N": str(now)}}}},
                {"Put": {"TableName": NOTIFICATIONS_TABLE_NAME, "Item": dynamodb_item(trip_notification), "ConditionExpression": "attribute_not_exists(notification_id)"}},
            ])
            updated = {**booking, "status": status, "updated_at": now}
        elif terminal:
            DYNAMO_CLIENT.transact_write_items(TransactItems=[
                {"Update": {"TableName": BOOKINGS_TABLE_NAME, "Key": {"booking_id": {"S": booking_id}}, "UpdateExpression": "SET #s = :status, updated_at = :updated", "ConditionExpression": "#s = :current_status", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":status": {"S": status}, ":current_status": {"S": current_status}, ":updated": {"N": str(now)}}}},
                {"Put": {"TableName": NOTIFICATIONS_TABLE_NAME, "Item": dynamodb_item(notification), "ConditionExpression": "attribute_not_exists(notification_id)"}},
            ])
            updated = {**booking, "status": status, "updated_at": now}
        else:
            result = TABLE.update_item(
                Key={"booking_id": booking_id},
                UpdateExpression="SET #s = :status, updated_at = :updated",
                ConditionExpression="attribute_exists(booking_id) AND #s = :current_status",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":status": status, ":current_status": current_status, ":updated": now},
                ReturnValues="ALL_NEW",
            )
            updated = result["Attributes"]
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") in {"ConditionalCheckFailedException", "TransactionCanceledException"}:
            return None
        raise
    log_event("booking_status_changed", booking_id=booking_id, previous_status=current_status, status=status, resources_released=release_resources)
    return updated


def cancel_booking(event, booking_id):
    booking = TABLE.get_item(Key={"booking_id": booking_id}).get("Item")
    if not booking_access_allowed(event, booking):
        return response(404, {"error": "Booking request not found."})
    try:
        action = clean(json.loads(event.get("body") or "{}").get("action"), 20).upper()
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})
    if action != "CANCEL":
        return response(400, {"error": "Action must be CANCEL."})
    if booking.get("status") in {"IN_PROGRESS", "COMPLETED", "CANCELLED", "DECLINED"}:
        return response(409, {"error": "This booking can no longer be cancelled online."})
    if booking.get("payment_status") in {"PENDING", "PAID"}:
        return response(409, {"error": "Contact operations to resolve the payment before cancelling this booking."})
    updated = change_booking_status(booking, "CANCELLED")
    if not updated:
        return response(409, {"error": "The booking changed while cancellation was submitted; refresh and try again."})
    return response(200, {"booking_id": booking_id, "status": "CANCELLED"})


def update_booking(event, booking_id):
    denied = require_admin(event)
    if denied:
        return denied
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})
    status = clean(data.get("status"), 20).upper()
    if status not in BOOKING_STATUSES:
        return response(400, {"error": "Select a valid booking status."})
    current = TABLE.get_item(Key={"booking_id": booking_id}).get("Item")
    if not current:
        return response(404, {"error": "Booking request not found."})
    allowed = BOOKING_TRANSITIONS.get(current.get("status"), set())
    if status not in allowed:
        return response(409, {"error": f"Cannot move a booking from {current.get('status')} to {status}."})
    if status == "CONFIRMED" and current.get("quote_status") != "ACCEPTED" and current.get("payment_status") != "PAID":
        return response(409, {"error": "An accepted quote or confirmed payment is required before confirmation."})
    if status == "CANCELLED" and current.get("payment_status") in {"PENDING", "PAID"}:
        return response(409, {"error": "Resolve the payment before cancelling this booking."})
    if status in {"IN_PROGRESS", "COMPLETED"} and not all(current.get(field) for field in ("vehicle_id", "chauffeur_id")):
        return response(409, {"error": "Assign a vehicle and chauffeur before selecting this status."})
    updated = change_booking_status(current, status)
    if not updated:
        return response(409, {"error": "The booking or assigned resources changed; refresh and try again."})
    return response(200, updated)


def availability_records(event, table, id_field, record_type):
    method = event.get("requestContext", {}).get("http", {}).get("method")
    denied = require_admin(event, {"ADMIN"} if method == "POST" else {"ADMIN", "OPERATOR"})
    if denied:
        return denied
    if method == "GET":
        items = [dict(item) for item in table.scan(Limit=100).get("Items", [])]
        transitions = VEHICLE_MANUAL_TRANSITIONS if id_field == "vehicle_id" else CHAUFFEUR_MANUAL_TRANSITIONS
        for item in items:
            item["allowed_statuses"] = sorted(transitions.get(item.get("status"), set()))
        items.sort(key=lambda item: (item.get("hub", ""), item.get("name", "")))
        return response(200, {"items": items, "count": len(items)})
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})
    name = clean(data.get("name"), 100)
    hub = clean(data.get("hub"), 20)
    if not name or hub not in HUBS:
        return response(400, {"error": "Provide a name and valid fleet hub."})
    now = int(time.time())
    item = {
        "schema_version": SCHEMA_VERSION,
        id_field: str(uuid.uuid4()),
        "name": name,
        "hub": hub,
        "status": "AVAILABLE",
        "created_at": now,
        "record_type": record_type,
    }
    if record_type == "vehicle":
        item["category"] = clean(data.get("category"), 60)
        item["ownership"] = clean(data.get("ownership"), 30) or "Company"
    else:
        interstate_eligible = clean(data.get("interstate_eligible"), 3).upper() or "NO"
        if interstate_eligible not in {"YES", "NO"}:
            return response(400, {"error": "Select whether the chauffeur is eligible for interstate trips."})
        item["interstate_eligible"] = interstate_eligible
    table.put_item(Item=item, ConditionExpression=f"attribute_not_exists({id_field})")
    return response(201, item)


def update_availability(event, table, id_field, record_id, statuses):
    denied = require_admin(event, {"ADMIN"})
    if denied:
        return denied
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})
    status = clean(data.get("status"), 20).upper()
    if status not in statuses:
        return response(400, {"error": "Select a valid availability status."})
    current = table.get_item(Key={id_field: record_id}).get("Item")
    if not current:
        return response(404, {"error": "Availability record not found."})
    transitions = VEHICLE_MANUAL_TRANSITIONS if id_field == "vehicle_id" else CHAUFFEUR_MANUAL_TRANSITIONS
    if status not in transitions.get(current.get("status"), set()):
        return response(409, {"error": f"Cannot manually move {current.get('status')} to {status}."})
    try:
        result = table.update_item(
            Key={id_field: record_id},
            UpdateExpression="SET #s = :status, updated_at = :updated",
            ConditionExpression=f"attribute_exists({id_field}) AND #s = :current_status",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": status, ":current_status": current["status"], ":updated": int(time.time())},
            ReturnValues="ALL_NEW",
        )
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            latest = table.get_item(Key={id_field: record_id}).get("Item")
            if not latest:
                return response(404, {"error": "Availability record not found."})
            return response(409, {"error": "Availability changed concurrently; refresh and try again."})
        raise
    return response(200, result["Attributes"])


def intervals_overlap(first, second):
    return first["pickup_at"] < second["end_at"] and second["pickup_at"] < first["end_at"]


def assign_booking(event, booking_id):
    denied = require_admin(event)
    if denied:
        return denied
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})
    vehicle_id = clean(data.get("vehicle_id"), 50)
    chauffeur_id = clean(data.get("chauffeur_id"), 50)
    if not vehicle_id or not chauffeur_id:
        return response(400, {"error": "Select both a vehicle and chauffeur."})
    booking = TABLE.get_item(Key={"booking_id": booking_id}).get("Item")
    vehicle = VEHICLES.get_item(Key={"vehicle_id": vehicle_id}).get("Item")
    chauffeur = CHAUFFEURS.get_item(Key={"chauffeur_id": chauffeur_id}).get("Item")
    if not booking or not vehicle or not chauffeur:
        return response(404, {"error": "Booking, vehicle or chauffeur was not found."})
    if booking.get("status") != "CONFIRMED":
        return response(409, {"error": "Only a confirmed booking can receive an assignment."})
    if vehicle.get("hub") != booking.get("hub") or chauffeur.get("hub") != booking.get("hub"):
        return response(409, {"error": "Vehicle and chauffeur must belong to the booking hub."})
    if vehicle.get("status") != "AVAILABLE" or chauffeur.get("status") != "AVAILABLE":
        return response(409, {"error": "Selected vehicle or chauffeur is no longer available."})
    if booking.get("trip_type") == "Interstate" and chauffeur.get("interstate_eligible") != "YES":
        return response(409, {"error": "Select a chauffeur approved for interstate trips."})
    for existing in TABLE.scan(Limit=100).get("Items", []):
        if existing.get("booking_id") == booking_id or existing.get("status") in {"DECLINED", "CANCELLED", "COMPLETED"}:
            continue
        same_resource = existing.get("vehicle_id") == vehicle_id or existing.get("chauffeur_id") == chauffeur_id
        if same_resource and all(existing.get(field) for field in ("pickup_at", "end_at")) and intervals_overlap(booking, existing):
            return response(409, {"error": "Vehicle or chauffeur has an overlapping assignment."})
    now = str(int(time.time()))
    notification = notification_record(booking_id, "RESOURCES_ASSIGNED", "A vehicle and chauffeur have been assigned to your booking.")
    try:
        DYNAMO_CLIENT.transact_write_items(
            TransactItems=[
                {"Update": {"TableName": BOOKINGS_TABLE_NAME, "Key": {"booking_id": {"S": booking_id}}, "UpdateExpression": "SET #s = :assigned, vehicle_id = :vehicle, chauffeur_id = :chauffeur, updated_at = :updated", "ConditionExpression": "attribute_exists(booking_id) AND #s = :confirmed", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":assigned": {"S": "ASSIGNED"}, ":confirmed": {"S": "CONFIRMED"}, ":vehicle": {"S": vehicle_id}, ":chauffeur": {"S": chauffeur_id}, ":updated": {"N": now}}}},
                {"Update": {"TableName": VEHICLES_TABLE_NAME, "Key": {"vehicle_id": {"S": vehicle_id}}, "UpdateExpression": "SET #s = :reserved, updated_at = :updated", "ConditionExpression": "#s = :available", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":reserved": {"S": "RESERVED"}, ":available": {"S": "AVAILABLE"}, ":updated": {"N": now}}}},
                {"Update": {"TableName": CHAUFFEURS_TABLE_NAME, "Key": {"chauffeur_id": {"S": chauffeur_id}}, "UpdateExpression": "SET #s = :assigned, updated_at = :updated", "ConditionExpression": "#s = :available", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":assigned": {"S": "ASSIGNED"}, ":available": {"S": "AVAILABLE"}, ":updated": {"N": now}}}},
                {"Put": {"TableName": NOTIFICATIONS_TABLE_NAME, "Item": dynamodb_item(notification), "ConditionExpression": "attribute_not_exists(notification_id)"}},
            ]
        )
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") == "TransactionCanceledException":
            return response(409, {"error": "Assignment changed concurrently; refresh and try again."})
        raise
    log_event("resources_assigned", booking_id=booking_id, vehicle_id=vehicle_id, chauffeur_id=chauffeur_id)
    return response(200, {"booking_id": booking_id, "status": "ASSIGNED", "vehicle_id": vehicle_id, "chauffeur_id": chauffeur_id})


def booking_quotes(booking_id):
    items = [item for item in QUOTES.scan(Limit=100).get("Items", []) if item.get("booking_id") == booking_id]
    return sorted(items, key=lambda item: int(item.get("version", 0)), reverse=True)


def manage_quotes(event, booking_id):
    denied = require_admin(event)
    if denied:
        return denied
    booking = TABLE.get_item(Key={"booking_id": booking_id}).get("Item")
    if not booking:
        return response(404, {"error": "Booking request not found."})
    method = event.get("requestContext", {}).get("http", {}).get("method")
    quotes = booking_quotes(booking_id)
    if method == "GET":
        return response(200, {"quotes": quotes, "count": len(quotes)})
    if booking.get("status") not in {"REQUESTED", "REVIEWING", "QUOTED"}:
        return response(409, {"error": "The booking is not in a quotable state."})
    try:
        data = json.loads(event.get("body") or "{}")
        amount_ngn = int(data.get("amount_ngn"))
        valid_until = clean(data.get("valid_until"), 40)
        valid_time = datetime.fromisoformat(valid_until)
    except (json.JSONDecodeError, TypeError, ValueError):
        return response(400, {"error": "Provide a whole-number NGN amount and valid expiry time."})
    if amount_ngn < 1 or amount_ngn > 100_000_000:
        return response(400, {"error": "Quote amount must be between NGN 1 and NGN 100,000,000."})
    estimated_cost_ngn = None
    if data.get("estimated_cost_ngn") is not None:
        try:
            estimated_cost_ngn = int(data["estimated_cost_ngn"])
        except (TypeError, ValueError):
            return response(400, {"error": "Estimated cost must be a whole-number NGN amount."})
        if estimated_cost_ngn < 0 or estimated_cost_ngn > 100_000_000:
            return response(400, {"error": "Estimated cost must be between NGN 0 and NGN 100,000,000."})
    if valid_time <= current_datetime(valid_time.tzinfo):
        return response(400, {"error": "Quote expiry must be in the future."})
    version = max((int(item.get("version", 0)) for item in quotes), default=0) + 1
    quote_id = f"{booking_id}#{version}"
    now = int(time.time())
    quote = {
        "schema_version": SCHEMA_VERSION,
        "quote_id": quote_id,
        "booking_id": booking_id,
        "version": version,
        "amount_ngn": amount_ngn,
        "valid_until": valid_until,
        "notes": clean(data.get("notes"), 500),
        "status": "ISSUED",
        "created_at": now,
        "expires_at": int(valid_time.timestamp()) + (30 * 86400),
        "cost_status": "NOT_ESTIMATED",
    }
    if estimated_cost_ngn is not None:
        estimated_margin_ngn = amount_ngn - estimated_cost_ngn
        quote.update(
            cost_status="ESTIMATED",
            estimated_cost_ngn=estimated_cost_ngn,
            estimated_margin_ngn=estimated_margin_ngn,
            estimated_margin_bps=(estimated_margin_ngn * 10_000) // amount_ngn,
        )
    notification_id = str(uuid.uuid4())
    notification_message = f"Quote version {version} was issued for NGN {amount_ngn:,}."
    try:
        DYNAMO_CLIENT.transact_write_items(TransactItems=[
            {"Put": {"TableName": QUOTES_TABLE_NAME, "Item": dynamodb_item(quote), "ConditionExpression": "attribute_not_exists(quote_id)"}},
            {"Update": {"TableName": BOOKINGS_TABLE_NAME, "Key": {"booking_id": {"S": booking_id}}, "UpdateExpression": "SET #s = :quoted, latest_quote_id = :quote_id, quote_version = :version, quote_amount_ngn = :amount, quote_status = :issued, accepted_quote_id = :empty, updated_at = :updated", "ConditionExpression": "#s = :current_status", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":quoted": {"S": "QUOTED"}, ":quote_id": {"S": quote_id}, ":version": {"N": str(version)}, ":amount": {"N": str(amount_ngn)}, ":issued": {"S": "ISSUED"}, ":empty": {"S": ""}, ":updated": {"N": str(now)}, ":current_status": {"S": booking["status"]}}}},
            {"Put": {"TableName": NOTIFICATIONS_TABLE_NAME, "Item": {"schema_version": {"N": str(SCHEMA_VERSION)}, "notification_id": {"S": notification_id}, "booking_id": {"S": booking_id}, "event_type": {"S": "QUOTE_ISSUED"}, "audience": {"S": "CUSTOMER"}, "channel": {"S": "PENDING_PROVIDER"}, "message": {"S": notification_message}, "status": {"S": "PENDING"}, "created_at": {"N": str(now)}, "expires_at": {"N": str(now + (30 * 86400))}}, "ConditionExpression": "attribute_not_exists(notification_id)"}},
        ])
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") == "TransactionCanceledException":
            return response(409, {"error": "The booking or quote changed concurrently; refresh and try again."})
        raise
    log_event("quote_issued", booking_id=booking_id, quote_id=quote_id, version=version)
    return response(201, quote)


def latest_quote(event, booking_id):
    booking = TABLE.get_item(Key={"booking_id": booking_id}).get("Item")
    if not booking_access_allowed(event, booking):
        return response(404, {"error": "Booking request not found."})
    quotes = booking_quotes(booking_id)
    if not quotes:
        return response(404, {"error": "No quote has been issued for this booking."})
    quote = quotes[0]
    public_quote = {key: quote[key] for key in ("booking_id", "version", "amount_ngn", "valid_until", "notes", "status")}
    public_quote["status"] = booking.get("quote_status", public_quote["status"])
    return response(200, public_quote)


def decide_quote(event, booking_id):
    booking = TABLE.get_item(Key={"booking_id": booking_id}).get("Item")
    if not booking_access_allowed(event, booking):
        return response(404, {"error": "Booking request not found."})
    if booking.get("status") != "QUOTED":
        return response(409, {"error": "The booking is not awaiting a quote decision."})
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})
    decision = clean(data.get("decision"), 20).upper()
    if decision not in {"ACCEPTED", "DECLINED"}:
        return response(400, {"error": "Decision must be ACCEPTED or DECLINED."})
    quotes = booking_quotes(booking_id)
    if not quotes or booking.get("latest_quote_id") != quotes[0].get("quote_id"):
        return response(409, {"error": "No current quote is available for a decision."})
    quote = quotes[0]
    try:
        valid_time = datetime.fromisoformat(quote["valid_until"])
        expired = valid_time <= current_datetime(valid_time.tzinfo)
    except (TypeError, ValueError):
        expired = True
    if expired:
        return response(409, {"error": "The latest quote has expired; request a revised quote."})
    if booking.get("quote_status") in {"ACCEPTED", "DECLINED"}:
        return response(409, {"error": "The latest quote already has a decision."})
    now = int(time.time())
    booking_status = "QUOTED" if decision == "ACCEPTED" else "REVIEWING"
    accepted_quote_id = quote["quote_id"] if decision == "ACCEPTED" else ""
    notification_id = str(uuid.uuid4())
    notification_message = f"The customer {decision.lower()} quote version {quote['version']}."
    try:
        DYNAMO_CLIENT.transact_write_items(TransactItems=[
            {"Update": {"TableName": BOOKINGS_TABLE_NAME, "Key": {"booking_id": {"S": booking_id}}, "UpdateExpression": "SET #s = :decision_status, quote_status = :decision, accepted_quote_id = :accepted_quote_id, quote_decided_at = :updated, updated_at = :updated", "ConditionExpression": "attribute_exists(booking_id) AND latest_quote_id = :quote_id AND quote_status = :issued", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":decision_status": {"S": booking_status}, ":decision": {"S": decision}, ":accepted_quote_id": {"S": accepted_quote_id}, ":updated": {"N": str(now)}, ":quote_id": {"S": quote["quote_id"]}, ":issued": {"S": "ISSUED"}}}},
            {"Put": {"TableName": NOTIFICATIONS_TABLE_NAME, "Item": {"schema_version": {"N": str(SCHEMA_VERSION)}, "notification_id": {"S": notification_id}, "booking_id": {"S": booking_id}, "event_type": {"S": f"QUOTE_{decision}"}, "audience": {"S": "STAFF"}, "channel": {"S": "PENDING_PROVIDER"}, "message": {"S": notification_message}, "status": {"S": "PENDING"}, "created_at": {"N": str(now)}, "expires_at": {"N": str(now + (30 * 86400))}}, "ConditionExpression": "attribute_not_exists(notification_id)"}},
        ])
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") == "TransactionCanceledException":
            return response(409, {"error": "The quote changed while the decision was submitted; refresh and try again."})
        raise
    log_event("quote_decided", booking_id=booking_id, quote_id=quote["quote_id"], decision=decision)
    return response(200, {"booking_id": booking_id, "quote_version": quote["version"], "quote_status": decision, "status": booking_status})


def booking_payments(booking_id):
    items = [item for item in PAYMENTS.scan(Limit=100).get("Items", []) if item.get("record_type") == "PAYMENT" and item.get("booking_id") == booking_id]
    return sorted(items, key=lambda item: item.get("created_at", 0), reverse=True)


def manage_payments(event, booking_id):
    denied = require_admin(event)
    if denied:
        return denied
    booking = TABLE.get_item(Key={"booking_id": booking_id}).get("Item")
    if not booking:
        return response(404, {"error": "Booking request not found."})
    method = event.get("requestContext", {}).get("http", {}).get("method")
    payments = booking_payments(booking_id)
    if method == "GET":
        return response(200, {"payments": payments, "count": len(payments)})
    if booking.get("status") != "QUOTED":
        return response(409, {"error": "Only a quoted booking can receive a payment request."})
    quotes = booking_quotes(booking_id)
    if not quotes:
        return response(409, {"error": "Issue a quote before creating a payment request."})
    if any(item.get("status") == "PENDING" for item in payments):
        return response(409, {"error": "A payment request is already pending for this booking."})
    quote = quotes[0]
    valid_time = datetime.fromisoformat(quote["valid_until"])
    if valid_time <= current_datetime(valid_time.tzinfo):
        return response(409, {"error": "The latest quote has expired; issue a new quote first."})
    if booking.get("quote_status") != "ACCEPTED" or booking.get("accepted_quote_id") != quote.get("quote_id"):
        return response(409, {"error": "The customer must accept the latest quote before payment is requested."})
    now = int(time.time())
    payment_id = str(uuid.uuid4())
    item = {
        "schema_version": SCHEMA_VERSION, "record_id": f"PAYMENT#{payment_id}", "record_type": "PAYMENT", "payment_id": payment_id,
        "booking_id": booking_id, "quote_id": quote["quote_id"], "amount_ngn": quote["amount_ngn"],
        "currency": "NGN", "provider": "PENDING_ADAPTER", "status": "PENDING", "created_at": now,
        "expires_at": now + (30 * 86400),
    }
    notification_id = str(uuid.uuid4())
    notification_message = f"A payment request for NGN {int(quote['amount_ngn']):,} is ready."
    try:
        DYNAMO_CLIENT.transact_write_items(TransactItems=[
            {"Put": {"TableName": PAYMENTS_TABLE_NAME, "Item": {"schema_version": {"N": str(SCHEMA_VERSION)}, "record_id": {"S": item["record_id"]}, "record_type": {"S": "PAYMENT"}, "payment_id": {"S": payment_id}, "booking_id": {"S": booking_id}, "quote_id": {"S": quote["quote_id"]}, "amount_ngn": {"N": str(quote["amount_ngn"])}, "currency": {"S": "NGN"}, "provider": {"S": "PENDING_ADAPTER"}, "status": {"S": "PENDING"}, "created_at": {"N": str(now)}, "expires_at": {"N": str(item["expires_at"])}}, "ConditionExpression": "attribute_not_exists(record_id)"}},
            {"Update": {"TableName": BOOKINGS_TABLE_NAME, "Key": {"booking_id": {"S": booking_id}}, "UpdateExpression": "SET payment_id = :payment_id, payment_status = :pending, updated_at = :updated", "ConditionExpression": "#s = :quoted AND quote_status = :accepted AND accepted_quote_id = :quote_id AND (attribute_not_exists(payment_status) OR payment_status <> :pending)", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":payment_id": {"S": payment_id}, ":pending": {"S": "PENDING"}, ":updated": {"N": str(now)}, ":quoted": {"S": "QUOTED"}, ":accepted": {"S": "ACCEPTED"}, ":quote_id": {"S": quote["quote_id"]}}}},
            {"Put": {"TableName": NOTIFICATIONS_TABLE_NAME, "Item": {"schema_version": {"N": str(SCHEMA_VERSION)}, "notification_id": {"S": notification_id}, "booking_id": {"S": booking_id}, "event_type": {"S": "PAYMENT_REQUESTED"}, "audience": {"S": "CUSTOMER"}, "channel": {"S": "PENDING_PROVIDER"}, "message": {"S": notification_message}, "status": {"S": "PENDING"}, "created_at": {"N": str(now)}, "expires_at": {"N": str(now + (30 * 86400))}}, "ConditionExpression": "attribute_not_exists(notification_id)"}},
        ])
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") == "TransactionCanceledException":
            return response(409, {"error": "The booking or payment state changed; refresh before creating another payment request."})
        raise
    log_event("payment_requested", booking_id=booking_id, payment_id=payment_id)
    return response(201, item)


def latest_payment(event, booking_id):
    booking = TABLE.get_item(Key={"booking_id": booking_id}).get("Item")
    if not booking_access_allowed(event, booking):
        return response(404, {"error": "Booking request not found."})
    payments = booking_payments(booking_id)
    if not payments:
        return response(404, {"error": "No payment request exists for this booking."})
    payment = payments[0]
    return response(200, {key: payment[key] for key in ("payment_id", "booking_id", "amount_ngn", "currency", "status", "created_at")})


def payment_webhook(event):
    if not PAYMENT_WEBHOOK_SECRET:
        return response(503, {"error": "Payment webhook verification is not configured."})
    raw_body = event.get("body") or ""
    headers = {str(key).lower(): value for key, value in (event.get("headers") or {}).items()}
    supplied = clean(headers.get("x-webhook-signature"), 128).lower()
    expected = hmac.new(PAYMENT_WEBHOOK_SECRET.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(supplied, expected):
        return response(401, {"error": "Invalid webhook signature."})
    ACTOR_ROLE.set("PAYMENT_PROVIDER")
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})
    event_id = clean(data.get("event_id"), 100)
    payment_id = clean(data.get("payment_id"), 100)
    status = clean(data.get("status"), 20).upper()
    if not event_id or not payment_id or status not in {"PAID", "FAILED"}:
        return response(400, {"error": "Provide event_id, payment_id and a PAID or FAILED status."})
    event_key = f"EVENT#{event_id}"
    existing_event = PAYMENTS.get_item(Key={"record_id": event_key}).get("Item")
    if existing_event:
        return response(200, {"event_id": event_id, "payment_id": existing_event["payment_id"], "status": existing_event["status"], "duplicate": True})
    payment_key = f"PAYMENT#{payment_id}"
    payment = PAYMENTS.get_item(Key={"record_id": payment_key}).get("Item")
    if not payment:
        return response(404, {"error": "Payment request not found."})
    if payment.get("status") == "PAID" and status != "PAID":
        return response(409, {"error": "A confirmed payment cannot be changed to failed."})
    now = int(time.time())
    booking_status = "CONFIRMED" if status == "PAID" else "QUOTED"
    notification_id = str(uuid.uuid4())
    notification_event = "PAYMENT_CONFIRMED" if status == "PAID" else "PAYMENT_FAILED"
    notification_message = "Your payment was confirmed." if status == "PAID" else "Your payment attempt was not successful."
    try:
        DYNAMO_CLIENT.transact_write_items(TransactItems=[
            {"Update": {"TableName": PAYMENTS_TABLE_NAME, "Key": {"record_id": {"S": payment_key}}, "UpdateExpression": "SET #s = :status, updated_at = :updated", "ConditionExpression": "attribute_exists(record_id) AND #s = :current_status", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":status": {"S": status}, ":current_status": {"S": payment["status"]}, ":updated": {"N": str(now)}}}},
            {"Put": {"TableName": PAYMENTS_TABLE_NAME, "Item": {"schema_version": {"N": str(SCHEMA_VERSION)}, "record_id": {"S": event_key}, "record_type": {"S": "WEBHOOK_EVENT"}, "event_id": {"S": event_id}, "payment_id": {"S": payment_id}, "status": {"S": status}, "created_at": {"N": str(now)}, "expires_at": {"N": str(now + (30 * 86400))}}, "ConditionExpression": "attribute_not_exists(record_id)"}},
            {"Update": {"TableName": BOOKINGS_TABLE_NAME, "Key": {"booking_id": {"S": payment["booking_id"]}}, "UpdateExpression": "SET #s = :booking_status, payment_status = :payment_status, updated_at = :updated", "ConditionExpression": "attribute_exists(booking_id)", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":booking_status": {"S": booking_status}, ":payment_status": {"S": status}, ":updated": {"N": str(now)}}}},
            {"Put": {"TableName": NOTIFICATIONS_TABLE_NAME, "Item": {"schema_version": {"N": str(SCHEMA_VERSION)}, "notification_id": {"S": notification_id}, "booking_id": {"S": payment["booking_id"]}, "event_type": {"S": notification_event}, "audience": {"S": "CUSTOMER"}, "channel": {"S": "PENDING_PROVIDER"}, "message": {"S": notification_message}, "status": {"S": "PENDING"}, "created_at": {"N": str(now)}, "expires_at": {"N": str(now + (30 * 86400))}}, "ConditionExpression": "attribute_not_exists(notification_id)"}},
        ])
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") == "TransactionCanceledException":
            recorded = PAYMENTS.get_item(Key={"record_id": event_key}).get("Item")
            if recorded:
                return response(200, {"event_id": event_id, "payment_id": recorded["payment_id"], "status": recorded["status"], "duplicate": True})
            return response(409, {"error": "The payment or booking changed while the provider event was applied."})
        raise
    log_event("payment_webhook_applied", booking_id=payment["booking_id"], payment_id=payment_id, provider_event_id=event_id, payment_status=status)
    return response(200, {"event_id": event_id, "payment_id": payment_id, "status": status, "duplicate": False})


def notification_outbox(event, notification_id=None):
    denied = require_admin(event)
    if denied:
        return denied
    method = event.get("requestContext", {}).get("http", {}).get("method")
    if method == "GET":
        items = NOTIFICATIONS.scan(Limit=100).get("Items", [])
        items.sort(key=lambda item: item.get("created_at", 0), reverse=True)
        return response(200, {"notifications": items, "count": len(items)})
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})
    status = clean(data.get("status"), 20).upper()
    if status not in {"PROCESSED", "DISMISSED"}:
        return response(400, {"error": "Notification status must be PROCESSED or DISMISSED."})
    try:
        result = NOTIFICATIONS.update_item(
            Key={"notification_id": notification_id},
            UpdateExpression="SET #s = :status, updated_at = :updated, processed_by_role = :role",
            ConditionExpression="attribute_exists(notification_id) AND #s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": status, ":updated": int(time.time()), ":pending": "PENDING", ":role": ACTOR_ROLE.get()},
            ReturnValues="ALL_NEW",
        )
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            existing = NOTIFICATIONS.get_item(Key={"notification_id": notification_id}).get("Item")
            if not existing:
                return response(404, {"error": "Notification not found."})
            return response(409, {"error": f"Notification is already {existing.get('status', 'finalized')}."})
        raise
    return response(200, result["Attributes"])


def page():
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Luxury Chauffeur Booking Demo</title>
<style>
:root{color-scheme:dark;--gold:#d8b36a;--ink:#111;--panel:#1b1d21;--muted:#aeb4be}*{box-sizing:border-box}body{margin:0;background:#0d0e10;color:#f7f7f5;font:16px/1.5 system-ui,sans-serif}.wrap{max-width:900px;margin:auto;padding:32px 18px 60px}header{padding:46px 0 22px}small,.eyebrow{color:var(--gold);letter-spacing:.16em;text-transform:uppercase}h1{font:700 clamp(2rem,7vw,4.4rem)/1.03 Georgia,serif;margin:.4rem 0 1rem;max-width:780px}.lead{color:var(--muted);max-width:650px}.notice{border-left:3px solid var(--gold);background:#17191c;padding:12px 16px;margin:24px 0;color:#ddd}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.full{grid-column:1/-1}label{display:block;color:#ddd;font-size:.9rem;margin-bottom:5px}input,select,textarea{width:100%;border:1px solid #373b42;border-radius:8px;background:#121418;color:white;padding:12px;font:inherit}textarea{min-height:95px;resize:vertical}button{border:0;border-radius:8px;background:var(--gold);color:var(--ink);font-weight:800;padding:13px 20px;cursor:pointer}button:disabled{opacity:.55}.result{margin-top:18px;padding:14px;border-radius:8px;background:#17191c;display:none}.fine{color:#868d98;font-size:.82rem;margin-top:22px}@media(max-width:640px){.grid{grid-template-columns:1fr}.full{grid-column:auto}}
</style><style>.result{white-space:pre-wrap;overflow-wrap:anywhere}.lookup{margin-top:42px;padding:22px;border:1px solid #30343a;border-radius:12px;background:var(--panel)}.lookup h2{font:700 1.8rem Georgia,serif;margin:0 0 8px}.lookup-grid{display:grid;grid-template-columns:1fr 1fr auto;gap:12px;align-items:end}.decision-actions{display:none;gap:10px;margin-top:14px}.decision-actions.visible{display:flex}.decision-actions .decline{background:#30343a;color:#fff}@media(max-width:640px){.lookup-grid{grid-template-columns:1fr}}</style></head><body><main class="wrap"><header><div class="eyebrow">Nigeria · Demonstration</div><h1>Chauffeur-driven luxury, requested in minutes.</h1><p class="lead">Submit a demonstration request from Lagos, Ogun, Oyo or Abuja for a local or approved interstate journey.</p></header>
<div class="notice"><strong>Demo only.</strong> This form does not confirm a vehicle, collect payment or create a binding rental.</div>
<form id="booking"><div class="grid">
<div><label for="name">Name *</label><input id="name" name="name" maxlength="100" required></div>
<div><label for="phone">Phone *</label><input id="phone" name="phone" maxlength="30" required></div>
<div><label for="email">Email</label><input id="email" name="email" type="email" maxlength="150"></div>
<div><label for="hub">Fleet hub *</label><select id="hub" name="hub" required><option value="">Choose</option><option>Lagos</option><option>Ogun</option><option>Oyo</option><option>Abuja</option></select></div>
<div><label for="trip_type">Trip type *</label><select id="trip_type" name="trip_type" required><option>Local</option><option>Interstate</option></select></div>
<div><label for="pickup_at">Pickup date and time *</label><input id="pickup_at" name="pickup_at" type="datetime-local" required></div>
<div><label for="end_at">Expected end date and time *</label><input id="end_at" name="end_at" type="datetime-local" required></div>
<div><label for="pickup">Pickup location *</label><input id="pickup" name="pickup" maxlength="200" required></div>
<div><label for="destination">Destination *</label><input id="destination" name="destination" maxlength="200" required></div>
<div id="destination-state-row" hidden><label for="destination_state">Destination state *</label><select id="destination_state" name="destination_state"><option value="">Choose</option>__DESTINATION_STATE_OPTIONS__</select></div>
<div class="full"><label for="vehicle_preference">Vehicle preference</label><input id="vehicle_preference" name="vehicle_preference" maxlength="100" placeholder="Example: executive SUV"></div>
<div class="full"><label for="notes">Notes</label><textarea id="notes" name="notes" maxlength="500"></textarea></div>
<div class="full"><button id="submit" type="submit">Request a quote</button></div></div></form><div id="result" class="result" role="status"></div>
<p class="fine">Requests are automatically deleted after 30 days. Do not submit identity documents, payment details or sensitive personal information.</p>
<section class="lookup"><div class="eyebrow">Customer access</div><h2>Check my booking</h2><p class="lead">Use the reference and private token shown when the request was created.</p><form id="lookup" class="lookup-grid"><label>Booking reference<input id="lookup-reference" required autocomplete="off"></label><label>Access token<input id="lookup-token" type="password" required autocomplete="off"></label><button id="lookup-submit" type="submit">Check status</button></form><div id="lookup-result" class="result" role="status"></div><div id="quote-actions" class="decision-actions"><button id="accept-quote" type="button">Accept latest quote</button><button id="decline-quote" class="decline" type="button">Decline latest quote</button></div><div id="booking-actions" class="decision-actions"><button id="cancel-booking" class="decline" type="button">Cancel booking</button></div></section></main>
<script>const f=document.querySelector('#booking'),b=document.querySelector('#submit'),r=document.querySelector('#result'),lookup=document.querySelector('#lookup'),lookupButton=document.querySelector('#lookup-submit'),lookupResult=document.querySelector('#lookup-result'),reference=document.querySelector('#lookup-reference'),token=document.querySelector('#lookup-token'),quoteActions=document.querySelector('#quote-actions'),bookingActions=document.querySelector('#booking-actions'),acceptQuote=document.querySelector('#accept-quote'),declineQuote=document.querySelector('#decline-quote'),cancelBooking=document.querySelector('#cancel-booking');let currentCustomer=null,pendingSubmission=null;function randomToken(bytes=32){const values=crypto.getRandomValues(new Uint8Array(bytes));return Array.from(values,value=>value.toString(16).padStart(2,'0')).join('')}f.addEventListener('submit',async e=>{e.preventDefault();b.disabled=true;r.style.display='block';r.textContent='Submitting…';const data=Object.fromEntries(new FormData(f));if(!pendingSubmission)pendingSubmission={key:crypto.randomUUID(),token:randomToken()};try{const x=await fetch('/bookings',{method:'POST',headers:{'content-type':'application/json','x-idempotency-key':pendingSubmission.key,'x-booking-token':pendingSubmission.token},body:JSON.stringify(data)}),j=await x.json();if(!x.ok)throw Error(j.error||'Request failed');r.textContent=(j.duplicate?'Original request recovered.':'Request recorded.')+'\\nReference: '+j.booking_id+'\\nAccess token (save now): '+j.access_token;reference.value=j.booking_id;token.value=j.access_token;pendingSubmission=null;f.reset()}catch(err){r.textContent=err.message+' You may submit again safely.'}finally{b.disabled=false}});async function customerRequest(path,headers,optional=false,options={}){const response=await fetch(path,{...options,headers:{...headers,...(options.headers||{})}}),data=await response.json();if(optional&&response.status===404)return null;if(!response.ok)throw Error(data.error||'Request failed');return data}lookup.addEventListener('submit',async e=>{e.preventDefault();lookupButton.disabled=true;quoteActions.classList.remove('visible');bookingActions.classList.remove('visible');lookupResult.style.display='block';lookupResult.textContent='Checking…';const id=reference.value.trim(),headers={'x-booking-token':token.value};try{const status=await customerRequest('/bookings/'+encodeURIComponent(id),headers),[quote,payment]=await Promise.all([customerRequest('/bookings/'+encodeURIComponent(id)+'/quote',headers,true),customerRequest('/bookings/'+encodeURIComponent(id)+'/payment',headers,true)]),lines=['Booking status: '+status.status,quote?'Latest quote: NGN '+Number(quote.amount_ngn).toLocaleString()+' · '+quote.status:'Latest quote: not issued',payment?'Payment: '+payment.status:'Payment: not requested'];currentCustomer={id,headers};lookupResult.textContent=lines.join('\\n');quoteActions.classList.toggle('visible',Boolean(quote&&quote.status==='ISSUED'));bookingActions.classList.toggle('visible',!['IN_PROGRESS','COMPLETED','CANCELLED','DECLINED'].includes(status.status)&&(!payment||payment.status!=='PAID'))}catch(err){currentCustomer=null;lookupResult.textContent=err.message}finally{lookupButton.disabled=false}});async function decide(decision){if(!currentCustomer)return;acceptQuote.disabled=declineQuote.disabled=true;try{await customerRequest('/bookings/'+encodeURIComponent(currentCustomer.id)+'/quote',currentCustomer.headers,false,{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({decision})});lookup.requestSubmit()}catch(err){lookupResult.textContent=err.message}finally{acceptQuote.disabled=declineQuote.disabled=false}}acceptQuote.addEventListener('click',()=>decide('ACCEPTED'));declineQuote.addEventListener('click',()=>decide('DECLINED'));cancelBooking.addEventListener('click',async()=>{if(!currentCustomer||!confirm('Cancel this booking request?'))return;cancelBooking.disabled=true;try{await customerRequest('/bookings/'+encodeURIComponent(currentCustomer.id),currentCustomer.headers,false,{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({action:'CANCEL'})});lookup.requestSubmit()}catch(err){lookupResult.textContent=err.message}finally{cancelBooking.disabled=false}});</script>
<script>const tripType=document.querySelector('#trip_type'),hub=document.querySelector('#hub'),stateRow=document.querySelector('#destination-state-row'),stateSelect=document.querySelector('#destination_state'),hubStates={Lagos:'Lagos',Ogun:'Ogun',Oyo:'Oyo',Abuja:'FCT'};function syncInterstate(){const interstate=tripType.value==='Interstate',origin=hubStates[hub.value];stateRow.hidden=!interstate;stateSelect.required=interstate;for(const option of stateSelect.options)option.disabled=Boolean(interstate&&origin&&option.value===origin);if(!interstate||stateSelect.selectedOptions[0]?.disabled)stateSelect.value=''}tripType.addEventListener('change',syncInterstate);hub.addEventListener('change',syncInterstate);f.addEventListener('reset',()=>setTimeout(syncInterstate));syncInterstate();</script></body></html>""".replace("__DESTINATION_STATE_OPTIONS__", "".join(f'<option value="{state}">{state}</option>' for state in sorted(NIGERIAN_STATES)))


def admin_page():
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Operations Dashboard</title><style>
:root{color-scheme:dark;--gold:#d8b36a;--panel:#191b1f;--muted:#aeb4be}*{box-sizing:border-box}body{margin:0;background:#0d0e10;color:#f7f7f5;font:15px/1.5 system-ui,sans-serif}.wrap{max-width:1180px;margin:auto;padding:34px 18px 60px}h1{font:700 clamp(2rem,5vw,3.4rem)/1.05 Georgia,serif;margin:.3rem 0}h2{font:700 1.6rem Georgia,serif}.eyebrow{color:var(--gold);letter-spacing:.16em;text-transform:uppercase}.muted{color:var(--muted)}.login,.card,.panel,.resource,.notification,.metric{background:var(--panel);border:1px solid #30343a;border-radius:12px;padding:18px}.login{max-width:520px;margin:28px 0}.row{display:flex;gap:10px;align-items:end}label{display:block;color:#ddd;font-size:.9rem;margin-bottom:5px;flex:1}input,select{width:100%;background:#111317;color:white;border:1px solid #3a3e45;border-radius:8px;padding:11px;font:inherit}button{background:var(--gold);border:0;border-radius:8px;color:#111;font-weight:800;padding:12px 17px;cursor:pointer}.toolbar{display:flex;justify-content:space-between;align-items:center;margin:28px 0 14px}.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.metric strong{display:block;font:700 1.7rem Georgia,serif;color:var(--gold)}.cards,.resource-list,.notification-list{display:grid;gap:12px}.card{display:grid;grid-template-columns:1.1fr 1fr 1fr .8fr;gap:18px}.card input,.card select,.card button{margin-top:7px}.inventory{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:38px}.outbox{margin-top:18px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}.form-grid button{align-self:end}.resource,.notification{display:grid;grid-template-columns:1fr .8fr;gap:12px;align-items:center}.name{font-weight:800}.ref{font:12px monospace;color:#858c97;overflow-wrap:anywhere}.error{color:#ff9c9c}.hidden{display:none}@media(max-width:780px){.card,.inventory,.notification{grid-template-columns:1fr}.summary-grid{grid-template-columns:1fr 1fr}.row{align-items:stretch;flex-direction:column}.form-grid{grid-template-columns:1fr}}
</style></head><body><main class="wrap"><div class="eyebrow">Demo operations</div><h1>Booking requests</h1><p class="muted">Review recent requests and update their workflow status.</p>
<section id="login" class="login"><div class="row"><label>Staff password<input id="password" type="password" autocomplete="current-password"></label><button id="open">Open dashboard</button></div><p id="message" class="error" role="alert"></p></section>
<section id="dashboard" class="hidden"><div class="toolbar"><div><strong id="count">Requests</strong><div id="role" class="muted"></div></div><button id="refresh">Refresh all</button></div><div id="summary" class="summary-grid"></div><div id="cards" class="cards"></div>
<div class="inventory"><section class="panel"><h2>Vehicles</h2><form id="vehicle-form" class="form-grid"><label>Vehicle name<input name="name" required placeholder="Mercedes GLE"></label><label>Hub<select name="hub" required><option>Lagos</option><option>Ogun</option><option>Oyo</option><option>Abuja</option></select></label><label>Category<input name="category" placeholder="Executive SUV"></label><label>Ownership<select name="ownership"><option>Company</option><option>Partner</option></select></label><button type="submit">Add vehicle</button></form><div id="vehicles" class="resource-list"></div></section>
<section class="panel"><h2>Chauffeurs</h2><form id="chauffeur-form" class="form-grid"><label>Chauffeur name<input name="name" required></label><label>Hub<select name="hub" required><option>Lagos</option><option>Ogun</option><option>Oyo</option><option>Abuja</option></select></label><label>Interstate approved<select name="interstate_eligible" required><option value="NO">No</option><option value="YES">Yes</option></select></label><button type="submit">Add chauffeur</button></form><div id="chauffeurs" class="resource-list"></div></section></div>
<section class="panel outbox"><h2>Notification outbox</h2><p class="muted">Delivery-ready events are stored here without contacting a paid provider.</p><div id="notifications" class="notification-list"></div></section></section></main>
<script>
const login=document.querySelector('#login'),dashboard=document.querySelector('#dashboard'),summary=document.querySelector('#summary'),cards=document.querySelector('#cards'),message=document.querySelector('#message'),password=document.querySelector('#password'),count=document.querySelector('#count'),vehicles=document.querySelector('#vehicles'),chauffeurs=document.querySelector('#chauffeurs'),notifications=document.querySelector('#notifications'),roleLabel=document.querySelector('#role');let currentRole='';

function field(parent,text,cls=''){const node=document.createElement('div');node.textContent=text||'—';if(cls)node.className=cls;parent.append(node)}
async function api(path,options={}){if(path.endsWith('/quotes')&&options.method==='POST'&&options.body){const cost=document.activeElement?.closest('.card')?.querySelector('[data-estimated-cost]');if(cost?.value){const payload=JSON.parse(options.body);payload.estimated_cost_ngn=Number(cost.value);options.body=JSON.stringify(payload)}}options.headers={...(options.headers||{}),'x-staff-password':password.value};const response=await fetch(path,options),data=await response.json();if(!response.ok)throw Error(data.error||'Request failed');return data}
function choice(items,idField,label){const select=document.createElement('select'),placeholder=document.createElement('option');placeholder.value='';placeholder.textContent=label;select.append(placeholder);for(const item of items){const option=document.createElement('option');option.value=item[idField];option.textContent=item.name;select.append(option)}return select}
function renderSummary(data){summary.replaceChildren();const metrics=[['Bookings',data.bookings.total],['Available vehicles',data.fleet.vehicles.by_status.AVAILABLE],['Available chauffeurs',data.fleet.chauffeurs.by_status.AVAILABLE],['Paid value','NGN '+Number(data.payments.paid_amount_ngn).toLocaleString()]];for(const [label,value] of metrics){const card=document.createElement('article');card.className='metric';const number=document.createElement('strong');number.textContent=value;const text=document.createElement('span');text.textContent=label;card.append(number,text);summary.append(card)}}
function render(items,vehicleItems,chauffeurItems){cards.replaceChildren();count.textContent=items.length+' request'+(items.length===1?'':'s');for(const item of items){const card=document.createElement('article');card.className='card';const who=document.createElement('div');field(who,item.name,'name');field(who,item.phone);field(who,item.email);field(who,item.booking_id,'ref');const trip=document.createElement('div');field(trip,item.trip_type+' · '+item.hub,'name');field(trip,item.pickup+' → '+item.destination);field(trip,item.pickup_at+' → '+item.end_at);const vehicle=document.createElement('div');field(vehicle,item.vehicle_preference||'No vehicle preference','name');field(vehicle,item.notes||'No notes','muted');if(item.quote_version){field(vehicle,'Latest quote v'+item.quote_version+' · NGN '+Number(item.quote_amount_ngn).toLocaleString(),'name');field(vehicle,'Quote: '+(item.quote_status||'ISSUED')+' · Payment: '+(item.payment_status||'NOT REQUESTED'),'muted')}if(['REQUESTED','REVIEWING','QUOTED'].includes(item.status)){const quoteAmount=document.createElement('input'),quoteExpiry=document.createElement('input'),quoteNotes=document.createElement('input'),issueQuote=document.createElement('button');quoteAmount.type='number';quoteAmount.min='1';quoteAmount.placeholder='Amount in NGN';quoteAmount.setAttribute('aria-label','Quote amount in NGN');quoteExpiry.type='datetime-local';quoteExpiry.setAttribute('aria-label','Quote expiry');quoteNotes.placeholder='Quote notes';quoteNotes.setAttribute('aria-label','Quote notes');issueQuote.textContent=item.quote_version?'Issue revision':'Issue quote';issueQuote.addEventListener('click',async()=>{if(!quoteAmount.value||!quoteExpiry.value){message.textContent='Enter a quote amount and expiry.';return}issueQuote.disabled=true;try{await api('/admin/bookings/'+encodeURIComponent(item.booking_id)+'/quotes',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({amount_ngn:Number(quoteAmount.value),valid_until:quoteExpiry.value,notes:quoteNotes.value})});await load()}catch(error){message.textContent=error.message}finally{issueQuote.disabled=false}});vehicle.append(quoteAmount,quoteExpiry,quoteNotes,issueQuote)}if(item.status==='QUOTED'&&item.quote_status==='ACCEPTED'&&item.payment_status!=='PENDING'&&item.payment_status!=='PAID'){const requestPayment=document.createElement('button');requestPayment.textContent='Create payment request';requestPayment.addEventListener('click',async()=>{requestPayment.disabled=true;try{await api('/admin/bookings/'+encodeURIComponent(item.booking_id)+'/payments',{method:'POST',headers:{'content-type':'application/json'},body:'{}'});await load()}catch(error){message.textContent=error.message}finally{requestPayment.disabled=false}});vehicle.append(requestPayment)}const control=document.createElement('div'),select=document.createElement('select'),permitted=[item.status,...(item.allowed_transitions||[])];for(const status of permitted){const option=document.createElement('option');option.value=option.textContent=status;option.selected=status===item.status;select.append(option)}select.disabled=permitted.length===1;select.addEventListener('change',async()=>{select.disabled=true;try{await api('/admin/bookings/'+encodeURIComponent(item.booking_id),{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({status:select.value})});await load()}catch(error){message.textContent=error.message;await load()}});control.append(select);if(item.status==='CONFIRMED'&&!item.vehicle_id&&!item.chauffeur_id){const availableVehicles=vehicleItems.filter(resource=>resource.hub===item.hub&&resource.status==='AVAILABLE'),availableChauffeurs=chauffeurItems.filter(resource=>resource.hub===item.hub&&resource.status==='AVAILABLE'),vehicleChoice=choice(availableVehicles,'vehicle_id','Select vehicle'),chauffeurChoice=choice(availableChauffeurs,'chauffeur_id','Select chauffeur'),assign=document.createElement('button');assign.textContent='Assign';assign.addEventListener('click',async()=>{if(!vehicleChoice.value||!chauffeurChoice.value){message.textContent='Select both a vehicle and chauffeur.';return}assign.disabled=true;try{await api('/admin/bookings/'+encodeURIComponent(item.booking_id)+'/assignment',{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({vehicle_id:vehicleChoice.value,chauffeur_id:chauffeurChoice.value})});await load()}catch(error){message.textContent=error.message}finally{assign.disabled=false}});control.append(vehicleChoice,chauffeurChoice,assign)}else if(item.vehicle_id||item.chauffeur_id){field(control,'Resources assigned','name')}card.append(who,trip,vehicle,control);cards.append(card)}}
function enhanceProfitability(){for(const amount of cards.querySelectorAll('input[aria-label="Quote amount in NGN"]')){const container=amount.parentElement;if(container.querySelector('[data-estimated-cost]'))continue;const cost=document.createElement('input'),margin=document.createElement('div');cost.type='number';cost.min='0';cost.max='100000000';cost.placeholder='Estimated internal cost (optional)';cost.setAttribute('aria-label','Estimated internal cost in NGN');cost.dataset.estimatedCost='';margin.className='muted';margin.dataset.marginPreview='';margin.textContent='Margin: enter selling price and estimated cost';const update=()=>{if(amount.value===''||cost.value===''){margin.textContent='Margin: cost not estimated';return}const selling=Number(amount.value),estimated=Number(cost.value),profit=selling-estimated,percent=selling>0?(profit/selling)*100:0;margin.textContent='Estimated margin: NGN '+profit.toLocaleString()+' · '+percent.toFixed(1)+'%'};amount.addEventListener('input',update);cost.addEventListener('input',update);amount.insertAdjacentElement('afterend',cost);cost.insertAdjacentElement('afterend',margin)}}
const profitabilityObserver=new MutationObserver(enhanceProfitability);profitabilityObserver.observe(cards,{childList:true});
function renderResources(target,items,type){target.replaceChildren();const idField=type==='vehicles'?'vehicle_id':'chauffeur_id';for(const item of items){const card=document.createElement('article');card.className='resource';const details=document.createElement('div');field(details,item.name,'name');field(details,item.hub+(item.category?' · '+item.category:'')+(item.ownership?' · '+item.ownership:''));const select=document.createElement('select');for(const status of [item.status,...(item.allowed_statuses||[])]){const option=document.createElement('option');option.value=option.textContent=status;option.selected=status===item.status;select.append(option)}select.disabled=currentRole!=='ADMIN'||!(item.allowed_statuses||[]).length;select.addEventListener('change',async()=>{select.disabled=true;try{await api('/admin/'+type+'/'+encodeURIComponent(item[idField]),{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({status:select.value})});await load()}catch(error){await load();message.textContent=error.message}});card.append(details,select);target.append(card)}}
function renderNotifications(items){notifications.replaceChildren();for(const item of items){const card=document.createElement('article');card.className='notification';const details=document.createElement('div');field(details,item.event_type.replaceAll('_',' '),'name');field(details,item.message);field(details,'Booking '+item.booking_id,'ref');const action=document.createElement('button');action.textContent=item.status==='PENDING'?'Mark processed':item.status;action.disabled=item.status!=='PENDING';action.addEventListener('click',async()=>{action.disabled=true;try{await api('/admin/notifications/'+encodeURIComponent(item.notification_id),{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({status:'PROCESSED'})});await load()}catch(error){message.textContent=error.message}});card.append(details,action);notifications.append(card)}}
async function load(){message.textContent='';try{const [session,summaryData,bookingData,vehicleData,chauffeurData,notificationData]=await Promise.all([api('/admin/session'),api('/admin/summary'),api('/admin/bookings'),api('/admin/vehicles'),api('/admin/chauffeurs'),api('/admin/notifications')]);currentRole=session.role;roleLabel.textContent=currentRole==='ADMIN'?'Administrator · full fleet access':'Operator · fleet changes locked';document.querySelector('#vehicle-form').classList.toggle('hidden',currentRole!=='ADMIN');document.querySelector('#chauffeur-form').classList.toggle('hidden',currentRole!=='ADMIN');login.classList.add('hidden');dashboard.classList.remove('hidden');renderSummary(summaryData);render(bookingData.bookings,vehicleData.items,chauffeurData.items);renderResources(vehicles,vehicleData.items,'vehicles');renderResources(chauffeurs,chauffeurData.items,'chauffeurs');renderNotifications(notificationData.notifications)}catch(error){message.textContent=error.message}}
async function createResource(event,type){event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form));try{await api('/admin/'+type,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)});form.reset();await load()}catch(error){message.textContent=error.message}}
document.querySelector('#open').addEventListener('click',load);document.querySelector('#refresh').addEventListener('click',load);password.addEventListener('keydown',event=>{if(event.key==='Enter')load()});
document.querySelector('#vehicle-form').addEventListener('submit',event=>createResource(event,'vehicles'));document.querySelector('#chauffeur-form').addEventListener('submit',event=>createResource(event,'chauffeurs'));
</script></body></html>"""


def route_request(event):
    request = event.get("requestContext", {}).get("http", {})
    method = request.get("method", "GET")
    path = event.get("rawPath", "/")
    parts = [part for part in path.split("/") if part]

    def resource_id(index):
        value = parts[index] if len(parts) > index else ""
        return value if valid_uuid(value) else None

    if method == "GET" and path == "/":
        return response(200, page(), "text/html; charset=utf-8")
    if method == "GET" and path == "/health":
        return response(200, {"status": "ok", "mode": "zero-funding-demo", "service": "luxury-rental-demo", "release_version": RELEASE_VERSION})
    if method == "GET" and path == "/openapi.json":
        return response(200, OPENAPI_TEXT, "application/json; charset=utf-8")
    if method == "GET" and path == "/admin":
        return response(200, admin_page(), "text/html; charset=utf-8")
    if method == "GET" and path == "/admin/session":
        return staff_session(event)
    if method == "GET" and path == "/admin/summary":
        return operations_summary(event)
    if method == "GET" and path == "/admin/bookings":
        return list_bookings(event)
    if method == "PATCH" and len(parts) == 4 and parts[:2] == ["admin", "bookings"] and parts[3] == "assignment" and resource_id(2):
        return assign_booking(event, resource_id(2))
    if method in {"GET", "POST"} and len(parts) == 4 and parts[:2] == ["admin", "bookings"] and parts[3] == "quotes" and resource_id(2):
        return manage_quotes(event, resource_id(2))
    if method in {"GET", "POST"} and len(parts) == 4 and parts[:2] == ["admin", "bookings"] and parts[3] == "payments" and resource_id(2):
        return manage_payments(event, resource_id(2))
    if method == "PATCH" and len(parts) == 3 and parts[:2] == ["admin", "bookings"] and resource_id(2):
        return update_booking(event, resource_id(2))
    if method in {"GET", "POST"} and path == "/admin/vehicles":
        return availability_records(event, VEHICLES, "vehicle_id", "vehicle")
    if method == "PATCH" and len(parts) == 3 and parts[:2] == ["admin", "vehicles"] and resource_id(2):
        return update_availability(event, VEHICLES, "vehicle_id", resource_id(2), VEHICLE_STATUSES)
    if method in {"GET", "POST"} and path == "/admin/chauffeurs":
        return availability_records(event, CHAUFFEURS, "chauffeur_id", "chauffeur")
    if method == "PATCH" and len(parts) == 3 and parts[:2] == ["admin", "chauffeurs"] and resource_id(2):
        return update_availability(event, CHAUFFEURS, "chauffeur_id", resource_id(2), CHAUFFEUR_STATUSES)
    if method == "GET" and path == "/admin/notifications":
        return notification_outbox(event)
    if method == "PATCH" and len(parts) == 3 and parts[:2] == ["admin", "notifications"] and resource_id(2):
        return notification_outbox(event, resource_id(2))
    if method == "POST" and path == "/bookings":
        return create_booking(event)
    if method == "POST" and path == "/webhooks/payments":
        return payment_webhook(event)
    if method == "GET" and len(parts) == 3 and parts[0] == "bookings" and parts[2] == "quote" and resource_id(1):
        return latest_quote(event, resource_id(1))
    if method == "PATCH" and len(parts) == 3 and parts[0] == "bookings" and parts[2] == "quote" and resource_id(1):
        return decide_quote(event, resource_id(1))
    if method == "GET" and len(parts) == 3 and parts[0] == "bookings" and parts[2] == "payment" and resource_id(1):
        return latest_payment(event, resource_id(1))
    if method == "GET" and len(parts) == 2 and parts[0] == "bookings" and resource_id(1):
        return booking_status(event, resource_id(1))
    if method == "PATCH" and len(parts) == 2 and parts[0] == "bookings" and resource_id(1):
        return cancel_booking(event, resource_id(1))
    return response(404, {"error": "Not found."})


def lambda_handler(event, context):
    request = event.get("requestContext", {})
    http = request.get("http", {})
    request_id = clean(request.get("requestId") or getattr(context, "aws_request_id", "") or str(uuid.uuid4()), 100)
    token = REQUEST_ID.set(request_id)
    role_token = ACTOR_ROLE.set("PUBLIC")
    method = clean(http.get("method") or "GET", 10)
    path = clean(event.get("rawPath") or "/", 200)
    started = time.perf_counter()
    log_event("request_started", method=method, path=path)
    try:
        raw_body = event.get("body") or ""
        body_size = len(raw_body.encode("utf-8")) if isinstance(raw_body, str) else MAX_REQUEST_BYTES + 1
        result = response(413, {"error": "Request body exceeds 16 KB limit."}) if body_size > MAX_REQUEST_BYTES else route_request(event)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        status_code = int(result.get("statusCode", 500))
        log_event("request_completed", level="ERROR" if status_code >= 500 else "INFO", method=method, path=path, status_code=status_code, duration_ms=duration_ms)
        return result
    except Exception as error:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event("request_failed", level="ERROR", method=method, path=path, duration_ms=duration_ms, error_type=type(error).__name__)
        raise
    finally:
        ACTOR_ROLE.reset(role_token)
        REQUEST_ID.reset(token)
