import html
import json
import os
import time
import uuid

import boto3


TABLE = boto3.resource("dynamodb").Table(os.environ["BOOKINGS_TABLE"])
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
TTL_DAYS = int(os.environ.get("BOOKING_TTL_DAYS", "30"))
HUBS = {"Lagos", "Ogun", "Oyo", "Abuja"}
TRIP_TYPES = {"Local", "Interstate"}


def response(status, body, content_type="application/json; charset=utf-8"):
    payload = body if isinstance(body, str) else json.dumps(body)
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
        },
        "body": payload,
    }


def clean(value, maximum):
    return str(value or "").strip()[:maximum]


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
        "pickup_at": clean(data.get("pickup_at"), 40),
        "vehicle_preference": clean(data.get("vehicle_preference"), 100),
        "notes": clean(data.get("notes"), 500),
    }

    required = ["name", "phone", "hub", "trip_type", "pickup", "destination", "pickup_at"]
    missing = [field for field in required if not booking[field]]
    if missing:
        return response(400, {"error": "Complete all required fields.", "fields": missing})
    if booking["hub"] not in HUBS or booking["trip_type"] not in TRIP_TYPES:
        return response(400, {"error": "Select a valid hub and trip type."})

    now = int(time.time())
    booking_id = str(uuid.uuid4())
    item = {
        "booking_id": booking_id,
        "status": "REQUESTED",
        "created_at": now,
        "expires_at": now + TTL_DAYS * 86400,
        **booking,
    }
    TABLE.put_item(Item=item, ConditionExpression="attribute_not_exists(booking_id)")
    return response(201, {"booking_id": booking_id, "status": "REQUESTED", "message": "Your demo request has been recorded."})


def booking_status(booking_id):
    result = TABLE.get_item(Key={"booking_id": booking_id}, ProjectionExpression="booking_id, #s, created_at", ExpressionAttributeNames={"#s": "status"})
    item = result.get("Item")
    if not item:
        return response(404, {"error": "Booking request not found."})
    return response(200, item)


def page():
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Luxury Chauffeur Booking Demo</title>
<style>
:root{color-scheme:dark;--gold:#d8b36a;--ink:#111;--panel:#1b1d21;--muted:#aeb4be}*{box-sizing:border-box}body{margin:0;background:#0d0e10;color:#f7f7f5;font:16px/1.5 system-ui,sans-serif}.wrap{max-width:900px;margin:auto;padding:32px 18px 60px}header{padding:46px 0 22px}small,.eyebrow{color:var(--gold);letter-spacing:.16em;text-transform:uppercase}h1{font:700 clamp(2rem,7vw,4.4rem)/1.03 Georgia,serif;margin:.4rem 0 1rem;max-width:780px}.lead{color:var(--muted);max-width:650px}.notice{border-left:3px solid var(--gold);background:#17191c;padding:12px 16px;margin:24px 0;color:#ddd}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.full{grid-column:1/-1}label{display:block;color:#ddd;font-size:.9rem;margin-bottom:5px}input,select,textarea{width:100%;border:1px solid #373b42;border-radius:8px;background:#121418;color:white;padding:12px;font:inherit}textarea{min-height:95px;resize:vertical}button{border:0;border-radius:8px;background:var(--gold);color:var(--ink);font-weight:800;padding:13px 20px;cursor:pointer}button:disabled{opacity:.55}.result{margin-top:18px;padding:14px;border-radius:8px;background:#17191c;display:none}.fine{color:#868d98;font-size:.82rem;margin-top:22px}@media(max-width:640px){.grid{grid-template-columns:1fr}.full{grid-column:auto}}
</style></head><body><main class="wrap"><header><div class="eyebrow">Nigeria · Demonstration</div><h1>Chauffeur-driven luxury, requested in minutes.</h1><p class="lead">Submit a demonstration request from Lagos, Ogun, Oyo or Abuja for a local or approved interstate journey.</p></header>
<div class="notice"><strong>Demo only.</strong> This form does not confirm a vehicle, collect payment or create a binding rental.</div>
<form id="booking"><div class="grid">
<div><label for="name">Name *</label><input id="name" name="name" maxlength="100" required></div>
<div><label for="phone">Phone *</label><input id="phone" name="phone" maxlength="30" required></div>
<div><label for="email">Email</label><input id="email" name="email" type="email" maxlength="150"></div>
<div><label for="hub">Fleet hub *</label><select id="hub" name="hub" required><option value="">Choose</option><option>Lagos</option><option>Ogun</option><option>Oyo</option><option>Abuja</option></select></div>
<div><label for="trip_type">Trip type *</label><select id="trip_type" name="trip_type" required><option>Local</option><option>Interstate</option></select></div>
<div><label for="pickup_at">Pickup date and time *</label><input id="pickup_at" name="pickup_at" type="datetime-local" required></div>
<div><label for="pickup">Pickup location *</label><input id="pickup" name="pickup" maxlength="200" required></div>
<div><label for="destination">Destination *</label><input id="destination" name="destination" maxlength="200" required></div>
<div class="full"><label for="vehicle_preference">Vehicle preference</label><input id="vehicle_preference" name="vehicle_preference" maxlength="100" placeholder="Example: executive SUV"></div>
<div class="full"><label for="notes">Notes</label><textarea id="notes" name="notes" maxlength="500"></textarea></div>
<div class="full"><button id="submit" type="submit">Request a quote</button></div></div></form><div id="result" class="result" role="status"></div>
<p class="fine">Requests are automatically deleted after 30 days. Do not submit identity documents, payment details or sensitive personal information.</p></main>
<script>const f=document.querySelector('#booking'),b=document.querySelector('#submit'),r=document.querySelector('#result');f.addEventListener('submit',async e=>{e.preventDefault();b.disabled=true;r.style.display='block';r.textContent='Submitting…';const data=Object.fromEntries(new FormData(f));try{const x=await fetch('/bookings',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)}),j=await x.json();if(!x.ok)throw Error(j.error||'Request failed');r.innerHTML='<strong>Request recorded.</strong><br>Reference: '+j.booking_id;f.reset()}catch(err){r.textContent=err.message}finally{b.disabled=false}});</script></body></html>"""


def lambda_handler(event, context):
    request = event.get("requestContext", {}).get("http", {})
    method = request.get("method", "GET")
    path = event.get("rawPath", "/")

    if method == "GET" and path == "/":
        return response(200, page(), "text/html; charset=utf-8")
    if method == "GET" and path == "/health":
        return response(200, {"status": "ok", "mode": "zero-funding-demo"})
    if method == "POST" and path == "/bookings":
        return create_booking(event)
    if method == "GET" and path.startswith("/bookings/"):
        return booking_status(html.escape(path.rsplit("/", 1)[-1]))
    return response(404, {"error": "Not found."})

