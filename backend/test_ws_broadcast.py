"""
WebSocket Real-time Broadcast — End-to-end Test
================================================
Self-contained: creates class + device on-the-fly, tests WS broadcast, cleans up.

Run from project root:
    pip install requests websockets
    python backend/test_ws_broadcast.py
"""
import asyncio, json, sys, threading, time
import requests
import websockets

BASE    = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"
EMAIL   = "admin@school.edu.vn"
PASSW   = "admin123"

received_events: list = []
ws_error: list        = []

def ok(m):   print(f"  \u2705  {m}")
def fail(m): print(f"  \u274c  {m}"); sys.exit(1)
def info(m): print(f"  \u2139\ufe0f   {m}")

# ── 1. Login ─────────────────────────────────────────────────────────────────
print("\n\u2500\u2500 Step 1: Login \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
r = requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSW})
if r.status_code != 200:
    fail(f"Login failed ({r.status_code}): {r.text}")
token   = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
ok(f"Logged in as {EMAIL}")

# ── 2. Create test class ──────────────────────────────────────────────────────
print("\n\u2500\u2500 Step 2: Create test class \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
import time as _time
_code = f"TST{int(_time.time()) % 100000}"
r = requests.post(f"{BASE}/api/classes/", headers=headers,
                  json={"class_code": _code, "class_name": "WS-Test-Class", "description": "auto test"})
if r.status_code not in (200, 201):
    fail(f"Create class ({r.status_code}): {r.text}")
class_id = r.json()["id"]
ok(f"Class created  id={class_id}")

# ── 3. Register test device ──────────────────────────────────────────────────
print("\n\u2500\u2500 Step 3: Register device \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
r = requests.post(f"{BASE}/api/devices/register", headers=headers,
                  json={"device_name": f"WS-Test-{_code}", "class_id": class_id, "location": "Lab"})
if r.status_code not in (200, 201):
    fail(f"Register device ({r.status_code}): {r.text}")
dev       = r.json()
dev_token = dev.get("device_token", dev.get("token", ""))
dev_id    = dev.get("id")
if not dev_token:
    fail(f"No device_token in response: {dev}")
ok(f"Device registered  id={dev_id}  token={dev_token[:16]}...")
dev_headers = {"X-Device-Token": dev_token}

# ── 4. Assign student to class ───────────────────────────────────────────────
print("\n\u2500\u2500 Step 4: Assign student to class \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
r = requests.get(f"{BASE}/api/students/", headers=headers)
students = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
if not students:
    fail("No students found. Create at least one student and retry.")
student    = students[0]
student_id = student["id"]
info(f"Student  id={student_id}  code={student['student_code']}  name={student['full_name']}")
r2 = requests.put(f"{BASE}/api/students/{student_id}", headers=headers, json={"class_id": class_id})
if r2.status_code in (200, 201):
    ok(f"Student {student_id} moved to class {class_id}")
else:
    info(f"Could not move student ({r2.status_code}) — will try attendance anyway")

# ── 5. Open WebSocket listener in background thread ─────────────────────────
print("\n\u2500\u2500 Step 5: Connect WebSocket \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
ws_ready = threading.Event()

async def _listen(cid, timeout=8):
    uri = f"{WS_BASE}/ws/attendance/{cid}"
    try:
        async with websockets.connect(uri) as ws:
            ws_ready.set()
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    received_events.append(json.loads(msg))
                    return
                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        ws_error.append(str(e))
        ws_ready.set()

threading.Thread(target=lambda: asyncio.run(_listen(class_id)), daemon=True).start()
ws_ready.wait(timeout=6)

if ws_error:
    fail(f"WS connection error: {ws_error[0]}")
ok(f"WS connected  ws://localhost:8000/ws/attendance/{class_id}")

# ── 6. POST attendance with device token (simulates Edge) ────────────────────
print("\n\u2500\u2500 Step 6: POST attendance (simulated Edge) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
time.sleep(0.4)
from datetime import datetime as _dt
r = requests.post(f"{BASE}/api/attendance/", headers=dev_headers, json={
    "student_id": student_id,
    "class_id":   class_id,
    "status":     "present",
    "confidence": 0.97,
    "method":     "face_recognition",
    "timestamp":  _dt.utcnow().isoformat(),
})
if r.status_code not in (200, 201):
    fail(f"POST attendance ({r.status_code}): {r.text}")
att = r.json()
ok(f"Attendance created  id={att.get('id')}  student={att.get('student_id')}  status={att.get('status')}")

# ── 7. Verify broadcast ───────────────────────────────────────────────────────
print("\n\u2500\u2500 Step 7: Wait for WS broadcast \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
deadline = time.time() + 6
while not received_events and time.time() < deadline:
    time.sleep(0.2)

if received_events:
    ok("WebSocket broadcast RECEIVED \u2714")
    evt = received_events[0]
    info(f"event  = {evt.get('event')}")
    info(f"data   = {json.dumps(evt.get('data', {}), indent=4)}")
else:
    fail("No WS event received within 6 s — broadcast NOT working")

# ── 8. Cleanup ────────────────────────────────────────────────────────────────
print("\n\u2500\u2500 Step 8: Cleanup \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
r_dev   = requests.delete(f"{BASE}/api/devices/{dev_id}", headers=headers)
info(f"Deleted test device {dev_id} → HTTP {r_dev.status_code}")
r_class = requests.delete(f"{BASE}/api/classes/{class_id}", headers=headers)
info(f"Deleted test class  {class_id} → HTTP {r_class.status_code}")

print("\n═" * 36)
print("  🎉  WebSocket real-time test PASSED")
print("═" * 36 + "\n")

