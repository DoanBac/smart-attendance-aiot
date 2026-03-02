#!/usr/bin/env python3
"""
Edge Device Sync — End-to-End Test via Cloudflare Tunnel
─────────────────────────────────────────────────────────
Mô phỏng đầy đủ vòng đời của Edge Device (Raspberry Pi):

  1. Admin: đăng nhập + tạo class + đăng ký device + gán student
  2. Edge: GET /health                     ← kiểm tra online
  3. Edge: GET /api/devices/embeddings/    ← tải facial embeddings
  4. Edge: POST /api/devices/heartbeat     ← gửi heartbeat
  5. Edge: POST /api/attendance/bulk-sync  ← đẩy batch attendance offline
  6. Frontend WS nhận broadcast realtime  ← xác nhận toàn bộ pipeline

Chạy:
    python3 backend/test_edge_sync.py
    python3 backend/test_edge_sync.py --url https://xxx.trycloudflare.com
"""

import argparse
import datetime as _dt
import json
import sys
import threading
import time
import traceback

import requests
import websocket   # pip install websocket-client

# ─── Config ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--url", default="https://dark-everybody-editorials-interaction.trycloudflare.com",
                    help="Public Cloud URL (Cloudflare tunnel hoặc localhost:8000)")
parser.add_argument("--local-ws", default="ws://localhost:8000",
                    help="WebSocket URL (local — frontend dùng cái này)")
args = parser.parse_args()

CLOUD_URL  = args.url.rstrip("/")
LOCAL_WS   = args.local_ws.rstrip("/")
ADMIN_EMAIL = "admin@school.edu.vn"
ADMIN_PASS  = "admin123"

# ─── Helper ───────────────────────────────────────────────────────────────────
SEP  = "─" * 60
PASS = "  ✅ "
FAIL = "  ❌ "
INFO = "  ℹ️   "

def ok(msg):  print(f"{PASS}{msg}")
def fail(msg, body=""): print(f"{FAIL}{msg}"); body and print(f"      {body}")
def info(msg): print(f"{INFO}{msg}")

# ─── WebSocket listener (local — same channel as frontend dashboard) ──────────
ws_events = []
ws_connected = threading.Event()

def _on_open(ws): ws_connected.set()
def _on_message(ws, msg):
    try: ws_events.append(json.loads(msg))
    except: pass
def _on_error(ws, err): pass
def _on_close(ws, *_): pass

# ─── Test ─────────────────────────────────────────────────────────────────────
def run():
    errors = []
    local_api = "http://localhost:8000"   # Admin API — direct (admin không đi qua cloudflare)
    edge_api  = CLOUD_URL                  # Edge API  — qua Cloudflare tunnel

    # ── Step 0: Ping Cloud qua public URL ────────────────────────────────────
    print(f"\n{'═'*60}")
    print(f" Cloud URL : {CLOUD_URL}")
    print(f" Local WS  : {LOCAL_WS}")
    print(f"{'═'*60}\n")

    print("── Step 0: Edge ping Cloud URL (health check) ───────────────")
    try:
        r = requests.get(f"{edge_api}/health", timeout=10)
        if r.status_code == 200:
            ok(f"Cloud reachable via {edge_api}")
            info(f"Response: {r.json()}")
        else:
            fail(f"Health returned {r.status_code}", r.text[:200])
            errors.append("health")
    except Exception as e:
        fail(f"Cannot reach {edge_api}", str(e))
        print("\n  💡 Tip: chạy  docker compose logs cloudflared  để lấy URL mới")
        sys.exit(1)

    # ── Step 1: Admin login (local) ───────────────────────────────────────────
    print("\n── Step 1: Admin login ──────────────────────────────────────")
    r = requests.post(f"{local_api}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    if r.status_code != 200:
        fail(f"Login failed {r.status_code}", r.text[:300])
        sys.exit(1)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    ok(f"Logged in as {ADMIN_EMAIL}")

    # ── Step 2: Create class ──────────────────────────────────────────────────
    print("\n── Step 2: Create class ─────────────────────────────────────")
    code = f"EDG{int(time.time()) % 100000}"
    r = requests.post(f"{local_api}/api/classes/",
                      json={"class_code": code, "class_name": "Edge Sync Test Class",
                            "subject": "AIoT", "semester": "2026-1"},
                      headers=headers)
    if r.status_code not in (200, 201):
        fail(f"Create class {r.status_code}", r.text[:200])
        sys.exit(1)
    class_id = r.json()["id"]
    ok(f"Class created  id={class_id}  code={code}")

    # ── Step 3: Register device ───────────────────────────────────────────────
    print("\n── Step 3: Register Edge device ─────────────────────────────")
    r = requests.post(f"{local_api}/api/devices/register",
                      json={"device_name": "EdgeTest-Pi4", "class_id": class_id,
                            "location": "Lab A"},
                      headers=headers)
    if r.status_code not in (200, 201):
        fail(f"Register device {r.status_code}", r.text[:200])
        sys.exit(1)
    device = r.json()
    device_id    = device["id"]
    device_token = device["device_token"]
    ok(f"Device registered  id={device_id}  token={device_token[:16]}...")

    device_headers = {"X-Device-Token": device_token, "Content-Type": "application/json"}

    # ── Step 4: Assign student to class ──────────────────────────────────────
    print("\n── Step 4: Assign student to class ──────────────────────────")
    r = requests.get(f"{local_api}/api/students/", headers=headers)
    students = [s for s in r.json() if s.get("status") == "active"]
    if not students:
        fail("No active students found. Enroll a student first.")
        sys.exit(1)
    student = students[0]
    student_id = student["id"]
    info(f"Student  id={student_id}  code={student['student_code']}  name={student['full_name']}")

    r = requests.patch(f"{local_api}/api/students/{student_id}",
                       json={"class_id": class_id}, headers=headers)
    if r.status_code not in (200, 201):
        fail(f"Assign student {r.status_code}", r.text[:200])
    else:
        ok(f"Student {student_id} moved to class {class_id}")

    # ── Step 5: Connect WebSocket (local) ────────────────────────────────────
    print("\n── Step 5: Connect WebSocket (local — như frontend dashboard) ")
    ws_url = f"{LOCAL_WS}/ws/attendance/{class_id}"
    ws = websocket.WebSocketApp(ws_url,
                                on_open=_on_open, on_message=_on_message,
                                on_error=_on_error, on_close=_on_close)
    wst = threading.Thread(target=ws.run_forever, daemon=True)
    wst.start()
    if ws_connected.wait(timeout=5):
        ok(f"WS connected  {ws_url}")
    else:
        fail("WS connection timeout")
        errors.append("ws_connect")

    # ── Step 6: Edge → heartbeat (via Cloudflare) ────────────────────────────
    print("\n── Step 6: Edge → POST heartbeat (via Cloudflare URL) ───────")
    r = requests.post(f"{edge_api}/api/devices/heartbeat",
                      json={"status": "active"},
                      headers=device_headers, timeout=15)
    if r.status_code == 200:
        ok(f"Heartbeat OK  response={r.json()}")
    else:
        fail(f"Heartbeat {r.status_code}", r.text[:200])
        errors.append("heartbeat")

    # ── Step 7: Edge → download embeddings (via Cloudflare) ──────────────────
    print("\n── Step 7: Edge → GET embeddings/{class_id} (via Cloudflare) ")
    r = requests.get(f"{edge_api}/api/devices/embeddings/{class_id}",
                     headers=device_headers, timeout=20)
    if r.status_code == 200:
        data = r.json()
        ok(f"Embeddings downloaded  count={data['count']}  class_id={data['class_id']}")
        if data["count"] == 0:
            info("No face embeddings yet (student not enrolled). That's fine for sync test.")
    else:
        fail(f"Embeddings {r.status_code}", r.text[:200])
        errors.append("embeddings")

    # ── Step 8: Edge → bulk-sync attendance (via Cloudflare) ─────────────────
    print("\n── Step 8: Edge → POST bulk-sync attendance (via Cloudflare) ")
    now = _dt.datetime.utcnow()
    records = [
        {
            "student_id": student_id,
            "class_id":   class_id,
            "timestamp":  (now - _dt.timedelta(minutes=5)).isoformat(),
            "confidence": 0.91,
            "liveness_score": 0.87,
            "method": "face_recognition",
            "status": "present",
        },
        {
            "student_id": student_id,
            "class_id":   class_id,
            "timestamp":  (now - _dt.timedelta(minutes=2)).isoformat(),
            "confidence": 0.95,
            "liveness_score": 0.92,
            "method": "face_recognition",
            "status": "present",
        },
    ]
    r = requests.post(f"{edge_api}/api/attendance/bulk-sync",
                      json={"records": records, "device_token": device_token},
                      headers=device_headers, timeout=20)
    if r.status_code == 200:
        result = r.json()
        ok(f"Bulk-sync OK  saved={result.get('saved', '?')}  records")
    else:
        fail(f"Bulk-sync {r.status_code}", r.text[:300])
        errors.append("bulk_sync")

    # ── Step 9: Wait for realtime WS broadcast ───────────────────────────────
    print("\n── Step 9: Wait for WS broadcast (realtime to frontend) ─────")
    deadline = time.time() + 8
    received = []
    while time.time() < deadline:
        if ws_events:
            received = ws_events[:]
            break
        time.sleep(0.2)

    if received:
        ok(f"WebSocket broadcast RECEIVED ✔  ({len(received)} event(s))")
        for ev in received:
            info(f"event={ev.get('event')}  student_id={ev.get('data',{}).get('student_id')}  status={ev.get('data',{}).get('status')}")
    else:
        fail("No WS broadcast received within 8s")
        errors.append("ws_broadcast")

    ws.close()

    # ── Step 10: Cleanup ──────────────────────────────────────────────────────
    print("\n── Step 10: Cleanup ─────────────────────────────────────────")
    requests.delete(f"{local_api}/api/devices/{device_id}", headers=headers)
    requests.delete(f"{local_api}/api/classes/{class_id}",  headers=headers)
    info("Deleted test device and class.")

    # ── Result ────────────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    if errors:
        print(f"  ❌  Test FAILED — issues: {', '.join(errors)}")
    else:
        print("  🎉  Edge Device Sync PASSED — full pipeline OK")
        print(f"       Cloud URL  : {CLOUD_URL}")
        print(f"       WebSocket  : {LOCAL_WS}")
    print(f"{'═'*60}\n")

    return len(errors) == 0


if __name__ == "__main__":
    try:
        import websocket
    except ImportError:
        print("Installing websocket-client...")
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
        import websocket

    passed = run()
    sys.exit(0 if passed else 1)
