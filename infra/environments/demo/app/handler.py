import base64
import hashlib
import hmac
import html
import json
import os
import time
import uuid
from decimal import Decimal
from datetime import datetime

import boto3


BOOKINGS_TABLE_NAME = os.environ["BOOKINGS_TABLE"]
VEHICLES_TABLE_NAME = os.environ["VEHICLES_TABLE"]
CHAUFFEURS_TABLE_NAME = os.environ["CHAUFFEURS_TABLE"]
TABLE = boto3.resource("dynamodb").Table(BOOKINGS_TABLE_NAME)
VEHICLES = boto3.resource("dynamodb").Table(VEHICLES_TABLE_NAME)
CHAUFFEURS = boto3.resource("dynamodb").Table(CHAUFFEURS_TABLE_NAME)
DYNAMO_CLIENT = boto3.client("dynamodb")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
TTL_DAYS = int(os.environ.get("BOOKING_TTL_DAYS", "30"))
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
HUBS = {"Lagos", "Ogun", "Oyo", "Abuja"}
TRIP_TYPES = {"Local", "Interstate"}
BOOKING_STATUSES = {"REQUESTED", "REVIEWING", "QUOTED", "CONFIRMED", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "DECLINED", "CANCELLED"}
VEHICLE_STATUSES = {"AVAILABLE", "RESERVED", "ON_TRIP", "MAINTENANCE", "INACTIVE"}
CHAUFFEUR_STATUSES = {"AVAILABLE", "ASSIGNED", "OFF_DUTY", "INACTIVE"}


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
    try:
        if datetime.fromisoformat(booking["end_at"]) <= datetime.fromisoformat(booking["pickup_at"]):
            return response(400, {"error": "Expected end time must be after pickup time."})
    except ValueError:
        return response(400, {"error": "Provide valid pickup and expected end times."})

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


def admin_password(event):
    headers = {str(key).lower(): value for key, value in (event.get("headers") or {}).items()}
    return headers.get("x-admin-password", "")


def admin_authenticated(event):
    if not ADMIN_PASSWORD_HASH:
        return False
    try:
        iterations, salt, expected = ADMIN_PASSWORD_HASH.split(":", 2)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            admin_password(event).encode("utf-8"),
            base64.b64decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def require_admin(event):
    if not ADMIN_PASSWORD_HASH:
        return response(503, {"error": "Dashboard authentication is not configured."})
    if not admin_authenticated(event):
        return response(401, {"error": "Invalid admin password."})
    return None


def list_bookings(event):
    denied = require_admin(event)
    if denied:
        return denied
    result = TABLE.scan(Limit=50)
    items = sorted(result.get("Items", []), key=lambda item: item.get("created_at", 0), reverse=True)
    return response(200, {"bookings": items, "count": len(items), "limited": "Last 50 scanned records"})


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
    if status in {"ASSIGNED", "IN_PROGRESS", "COMPLETED"} and not all(current.get(field) for field in ("vehicle_id", "chauffeur_id")):
        return response(409, {"error": "Assign a vehicle and chauffeur before selecting this status."})
    try:
        result = TABLE.update_item(
            Key={"booking_id": booking_id},
            UpdateExpression="SET #s = :status, updated_at = :updated",
            ConditionExpression="attribute_exists(booking_id)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": status, ":updated": int(time.time())},
            ReturnValues="ALL_NEW",
        )
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return response(404, {"error": "Booking request not found."})
        raise
    return response(200, result["Attributes"])


def availability_records(event, table, id_field, record_type):
    denied = require_admin(event)
    if denied:
        return denied
    if event.get("requestContext", {}).get("http", {}).get("method") == "GET":
        items = table.scan(Limit=100).get("Items", [])
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
    table.put_item(Item=item, ConditionExpression=f"attribute_not_exists({id_field})")
    return response(201, item)


def update_availability(event, table, id_field, record_id, statuses):
    denied = require_admin(event)
    if denied:
        return denied
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "Request body must be valid JSON."})
    status = clean(data.get("status"), 20).upper()
    if status not in statuses:
        return response(400, {"error": "Select a valid availability status."})
    try:
        result = table.update_item(
            Key={id_field: record_id},
            UpdateExpression="SET #s = :status, updated_at = :updated",
            ConditionExpression=f"attribute_exists({id_field})",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": status, ":updated": int(time.time())},
            ReturnValues="ALL_NEW",
        )
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return response(404, {"error": "Availability record not found."})
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
    if vehicle.get("hub") != booking.get("hub") or chauffeur.get("hub") != booking.get("hub"):
        return response(409, {"error": "Vehicle and chauffeur must belong to the booking hub."})
    if vehicle.get("status") != "AVAILABLE" or chauffeur.get("status") != "AVAILABLE":
        return response(409, {"error": "Selected vehicle or chauffeur is no longer available."})
    for existing in TABLE.scan(Limit=100).get("Items", []):
        if existing.get("booking_id") == booking_id or existing.get("status") in {"DECLINED", "CANCELLED", "COMPLETED"}:
            continue
        same_resource = existing.get("vehicle_id") == vehicle_id or existing.get("chauffeur_id") == chauffeur_id
        if same_resource and all(existing.get(field) for field in ("pickup_at", "end_at")) and intervals_overlap(booking, existing):
            return response(409, {"error": "Vehicle or chauffeur has an overlapping assignment."})
    now = str(int(time.time()))
    try:
        DYNAMO_CLIENT.transact_write_items(
            TransactItems=[
                {"Update": {"TableName": BOOKINGS_TABLE_NAME, "Key": {"booking_id": {"S": booking_id}}, "UpdateExpression": "SET #s = :assigned, vehicle_id = :vehicle, chauffeur_id = :chauffeur, updated_at = :updated", "ConditionExpression": "attribute_exists(booking_id) AND #s <> :assigned", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":assigned": {"S": "ASSIGNED"}, ":vehicle": {"S": vehicle_id}, ":chauffeur": {"S": chauffeur_id}, ":updated": {"N": now}}}},
                {"Update": {"TableName": VEHICLES_TABLE_NAME, "Key": {"vehicle_id": {"S": vehicle_id}}, "UpdateExpression": "SET #s = :reserved, updated_at = :updated", "ConditionExpression": "#s = :available", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":reserved": {"S": "RESERVED"}, ":available": {"S": "AVAILABLE"}, ":updated": {"N": now}}}},
                {"Update": {"TableName": CHAUFFEURS_TABLE_NAME, "Key": {"chauffeur_id": {"S": chauffeur_id}}, "UpdateExpression": "SET #s = :assigned, updated_at = :updated", "ConditionExpression": "#s = :available", "ExpressionAttributeNames": {"#s": "status"}, "ExpressionAttributeValues": {":assigned": {"S": "ASSIGNED"}, ":available": {"S": "AVAILABLE"}, ":updated": {"N": now}}}},
            ]
        )
    except Exception as error:
        error_response = getattr(error, "response", {})
        if error_response.get("Error", {}).get("Code") == "TransactionCanceledException":
            return response(409, {"error": "Assignment changed concurrently; refresh and try again."})
        raise
    return response(200, {"booking_id": booking_id, "status": "ASSIGNED", "vehicle_id": vehicle_id, "chauffeur_id": chauffeur_id})


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
<div><label for="end_at">Expected end date and time *</label><input id="end_at" name="end_at" type="datetime-local" required></div>
<div><label for="pickup">Pickup location *</label><input id="pickup" name="pickup" maxlength="200" required></div>
<div><label for="destination">Destination *</label><input id="destination" name="destination" maxlength="200" required></div>
<div class="full"><label for="vehicle_preference">Vehicle preference</label><input id="vehicle_preference" name="vehicle_preference" maxlength="100" placeholder="Example: executive SUV"></div>
<div class="full"><label for="notes">Notes</label><textarea id="notes" name="notes" maxlength="500"></textarea></div>
<div class="full"><button id="submit" type="submit">Request a quote</button></div></div></form><div id="result" class="result" role="status"></div>
<p class="fine">Requests are automatically deleted after 30 days. Do not submit identity documents, payment details or sensitive personal information.</p></main>
<script>const f=document.querySelector('#booking'),b=document.querySelector('#submit'),r=document.querySelector('#result');f.addEventListener('submit',async e=>{e.preventDefault();b.disabled=true;r.style.display='block';r.textContent='Submitting…';const data=Object.fromEntries(new FormData(f));try{const x=await fetch('/bookings',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)}),j=await x.json();if(!x.ok)throw Error(j.error||'Request failed');r.innerHTML='<strong>Request recorded.</strong><br>Reference: '+j.booking_id;f.reset()}catch(err){r.textContent=err.message}finally{b.disabled=false}});</script></body></html>"""


def admin_page():
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Operations Dashboard</title><style>
:root{color-scheme:dark;--gold:#d8b36a;--panel:#191b1f;--muted:#aeb4be}*{box-sizing:border-box}body{margin:0;background:#0d0e10;color:#f7f7f5;font:15px/1.5 system-ui,sans-serif}.wrap{max-width:1180px;margin:auto;padding:34px 18px 60px}h1{font:700 clamp(2rem,5vw,3.4rem)/1.05 Georgia,serif;margin:.3rem 0}h2{font:700 1.6rem Georgia,serif}.eyebrow{color:var(--gold);letter-spacing:.16em;text-transform:uppercase}.muted{color:var(--muted)}.login,.card,.panel,.resource{background:var(--panel);border:1px solid #30343a;border-radius:12px;padding:18px}.login{max-width:520px;margin:28px 0}.row{display:flex;gap:10px;align-items:end}label{display:block;color:#ddd;font-size:.9rem;margin-bottom:5px;flex:1}input,select{width:100%;background:#111317;color:white;border:1px solid #3a3e45;border-radius:8px;padding:11px;font:inherit}button{background:var(--gold);border:0;border-radius:8px;color:#111;font-weight:800;padding:12px 17px;cursor:pointer}.toolbar{display:flex;justify-content:space-between;align-items:center;margin:28px 0 14px}.cards,.resource-list{display:grid;gap:12px}.card{display:grid;grid-template-columns:1.1fr 1fr 1fr .8fr;gap:18px}.inventory{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:38px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}.form-grid button{align-self:end}.resource{display:grid;grid-template-columns:1fr .8fr;gap:12px;align-items:center}.name{font-weight:800}.ref{font:12px monospace;color:#858c97;overflow-wrap:anywhere}.error{color:#ff9c9c}.hidden{display:none}@media(max-width:780px){.card,.inventory{grid-template-columns:1fr}.row{align-items:stretch;flex-direction:column}.form-grid{grid-template-columns:1fr}}
</style></head><body><main class="wrap"><div class="eyebrow">Demo operations</div><h1>Booking requests</h1><p class="muted">Review recent requests and update their workflow status.</p>
<section id="login" class="login"><div class="row"><label>Admin password<input id="password" type="password" autocomplete="current-password"></label><button id="open">Open dashboard</button></div><p id="message" class="error" role="alert"></p></section>
<section id="dashboard" class="hidden"><div class="toolbar"><strong id="count">Requests</strong><button id="refresh">Refresh all</button></div><div id="cards" class="cards"></div>
<div class="inventory"><section class="panel"><h2>Vehicles</h2><form id="vehicle-form" class="form-grid"><label>Vehicle name<input name="name" required placeholder="Mercedes GLE"></label><label>Hub<select name="hub" required><option>Lagos</option><option>Ogun</option><option>Oyo</option><option>Abuja</option></select></label><label>Category<input name="category" placeholder="Executive SUV"></label><label>Ownership<select name="ownership"><option>Company</option><option>Partner</option></select></label><button type="submit">Add vehicle</button></form><div id="vehicles" class="resource-list"></div></section>
<section class="panel"><h2>Chauffeurs</h2><form id="chauffeur-form" class="form-grid"><label>Chauffeur name<input name="name" required></label><label>Hub<select name="hub" required><option>Lagos</option><option>Ogun</option><option>Oyo</option><option>Abuja</option></select></label><button type="submit">Add chauffeur</button></form><div id="chauffeurs" class="resource-list"></div></section></div></section></main>
<script>
const login=document.querySelector('#login'),dashboard=document.querySelector('#dashboard'),cards=document.querySelector('#cards'),message=document.querySelector('#message'),password=document.querySelector('#password'),count=document.querySelector('#count'),vehicles=document.querySelector('#vehicles'),chauffeurs=document.querySelector('#chauffeurs');
const statuses=['REQUESTED','REVIEWING','QUOTED','CONFIRMED','ASSIGNED','IN_PROGRESS','COMPLETED','DECLINED','CANCELLED'];
const vehicleStatuses=['AVAILABLE','RESERVED','ON_TRIP','MAINTENANCE','INACTIVE'],chauffeurStatuses=['AVAILABLE','ASSIGNED','OFF_DUTY','INACTIVE'];
function field(parent,text,cls=''){const node=document.createElement('div');node.textContent=text||'—';if(cls)node.className=cls;parent.append(node)}
async function api(path,options={}){options.headers={...(options.headers||{}),'x-admin-password':password.value};const response=await fetch(path,options),data=await response.json();if(!response.ok)throw Error(data.error||'Request failed');return data}
function choice(items,idField,label){const select=document.createElement('select'),placeholder=document.createElement('option');placeholder.value='';placeholder.textContent=label;select.append(placeholder);for(const item of items){const option=document.createElement('option');option.value=item[idField];option.textContent=item.name;select.append(option)}return select}
function render(items,vehicleItems,chauffeurItems){cards.replaceChildren();count.textContent=items.length+' request'+(items.length===1?'':'s');for(const item of items){const card=document.createElement('article');card.className='card';const who=document.createElement('div');field(who,item.name,'name');field(who,item.phone);field(who,item.email);field(who,item.booking_id,'ref');const trip=document.createElement('div');field(trip,item.trip_type+' · '+item.hub,'name');field(trip,item.pickup+' → '+item.destination);field(trip,item.pickup_at+' → '+item.end_at);const vehicle=document.createElement('div');field(vehicle,item.vehicle_preference||'No vehicle preference','name');field(vehicle,item.notes||'No notes','muted');const control=document.createElement('div'),select=document.createElement('select');for(const status of statuses){const option=document.createElement('option');option.value=option.textContent=status;option.selected=status===item.status;select.append(option)}select.addEventListener('change',async()=>{select.disabled=true;try{await api('/admin/bookings/'+encodeURIComponent(item.booking_id),{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({status:select.value})})}catch(error){message.textContent=error.message}finally{select.disabled=false}});control.append(select);if(!item.vehicle_id&&!item.chauffeur_id){const availableVehicles=vehicleItems.filter(resource=>resource.hub===item.hub&&resource.status==='AVAILABLE'),availableChauffeurs=chauffeurItems.filter(resource=>resource.hub===item.hub&&resource.status==='AVAILABLE'),vehicleChoice=choice(availableVehicles,'vehicle_id','Select vehicle'),chauffeurChoice=choice(availableChauffeurs,'chauffeur_id','Select chauffeur'),assign=document.createElement('button');assign.textContent='Assign';assign.addEventListener('click',async()=>{if(!vehicleChoice.value||!chauffeurChoice.value){message.textContent='Select both a vehicle and chauffeur.';return}assign.disabled=true;try{await api('/admin/bookings/'+encodeURIComponent(item.booking_id)+'/assignment',{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({vehicle_id:vehicleChoice.value,chauffeur_id:chauffeurChoice.value})});await load()}catch(error){message.textContent=error.message}finally{assign.disabled=false}});control.append(vehicleChoice,chauffeurChoice,assign)}else{field(control,'Resources assigned','name')}card.append(who,trip,vehicle,control);cards.append(card)}}
function renderResources(target,items,type){target.replaceChildren();const idField=type==='vehicles'?'vehicle_id':'chauffeur_id',options=type==='vehicles'?vehicleStatuses:chauffeurStatuses;for(const item of items){const card=document.createElement('article');card.className='resource';const details=document.createElement('div');field(details,item.name,'name');field(details,item.hub+(item.category?' · '+item.category:'')+(item.ownership?' · '+item.ownership:''));const select=document.createElement('select');for(const status of options){const option=document.createElement('option');option.value=option.textContent=status;option.selected=status===item.status;select.append(option)}select.addEventListener('change',async()=>{select.disabled=true;try{await api('/admin/'+type+'/'+encodeURIComponent(item[idField]),{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({status:select.value})})}catch(error){message.textContent=error.message}finally{select.disabled=false}});card.append(details,select);target.append(card)}}
async function load(){message.textContent='';try{const [bookingData,vehicleData,chauffeurData]=await Promise.all([api('/admin/bookings'),api('/admin/vehicles'),api('/admin/chauffeurs')]);login.classList.add('hidden');dashboard.classList.remove('hidden');render(bookingData.bookings,vehicleData.items,chauffeurData.items);renderResources(vehicles,vehicleData.items,'vehicles');renderResources(chauffeurs,chauffeurData.items,'chauffeurs')}catch(error){message.textContent=error.message}}
async function createResource(event,type){event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form));try{await api('/admin/'+type,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)});form.reset();await load()}catch(error){message.textContent=error.message}}
document.querySelector('#open').addEventListener('click',load);document.querySelector('#refresh').addEventListener('click',load);password.addEventListener('keydown',event=>{if(event.key==='Enter')load()});
document.querySelector('#vehicle-form').addEventListener('submit',event=>createResource(event,'vehicles'));document.querySelector('#chauffeur-form').addEventListener('submit',event=>createResource(event,'chauffeurs'));
</script></body></html>"""


def lambda_handler(event, context):
    request = event.get("requestContext", {}).get("http", {})
    method = request.get("method", "GET")
    path = event.get("rawPath", "/")

    if method == "GET" and path == "/":
        return response(200, page(), "text/html; charset=utf-8")
    if method == "GET" and path == "/health":
        return response(200, {"status": "ok", "mode": "zero-funding-demo"})
    if method == "GET" and path == "/admin":
        return response(200, admin_page(), "text/html; charset=utf-8")
    if method == "GET" and path == "/admin/bookings":
        return list_bookings(event)
    if method == "PATCH" and path.startswith("/admin/bookings/") and path.endswith("/assignment"):
        return assign_booking(event, html.escape(path.split("/")[-2]))
    if method == "PATCH" and path.startswith("/admin/bookings/"):
        return update_booking(event, html.escape(path.rsplit("/", 1)[-1]))
    if method in {"GET", "POST"} and path == "/admin/vehicles":
        return availability_records(event, VEHICLES, "vehicle_id", "vehicle")
    if method == "PATCH" and path.startswith("/admin/vehicles/"):
        return update_availability(event, VEHICLES, "vehicle_id", html.escape(path.rsplit("/", 1)[-1]), VEHICLE_STATUSES)
    if method in {"GET", "POST"} and path == "/admin/chauffeurs":
        return availability_records(event, CHAUFFEURS, "chauffeur_id", "chauffeur")
    if method == "PATCH" and path.startswith("/admin/chauffeurs/"):
        return update_availability(event, CHAUFFEURS, "chauffeur_id", html.escape(path.rsplit("/", 1)[-1]), CHAUFFEUR_STATUSES)
    if method == "POST" and path == "/bookings":
        return create_booking(event)
    if method == "GET" and path.startswith("/bookings/"):
        return booking_status(html.escape(path.rsplit("/", 1)[-1]))
    return response(404, {"error": "Not found."})
