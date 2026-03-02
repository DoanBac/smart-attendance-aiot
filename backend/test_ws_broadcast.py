"""
Test end-to-end: WebSocket connect → send attendance via REST → receive broadcast.
Run: docker exec smart-attendance-aiot-backend-1 python test_ws_broadcast.py
"""
import asyncio
import json
import httpx
import websockets


async def main():
    # 1. Login
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "http://localhost:8000/api/auth/login",
            json={"email": "admin@school.edu.vn", "password": "admin123"},
        )
        token = r.json()["access_token"]
        print(f"[1] Login OK, token: {token[:30]}...")

    # 2. Connect WebSocket
    uri = "ws://localhost:8000/ws/attendance/2"
    received = []

    async with websockets.connect(uri) as ws:
        print(f"[2] WS connected to {uri}")

        # 3. Gửi attendance từ coroutine khác
        async def send_attendance():
            await asyncio.sleep(0.5)  # để WS sẵn sàng
            async with httpx.AsyncClient() as c:
                resp = await c.post(
                    "http://localhost:8000/api/attendance/",
                    headers={"X-Device-Token": "b7da9fc490c04c20bcd0d4c8165a1ae4"},
                    json={
                        "student_id": 4,
                        "class_id": 2,
                        "timestamp": "2026-03-02T12:00:00",
                        "confidence": 0.93,
                        "liveness_score": 0.87,
                        "method": "face_recognition",
                        "status": "present",
                    },
                )
                print(f"[3] Attendance POST: {resp.status_code} → id={resp.json().get('id')}")

        # 4. Nhận broadcast từ WS
        async def receive():
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                print(f"[4] WS BROADCAST received: event={data.get('event')}, student_id={data.get('data',{}).get('student_id')}")
                received.append(data)
            except asyncio.TimeoutError:
                print("[4] TIMEOUT — no broadcast received in 5s")

        await asyncio.gather(send_attendance(), receive())

    # 5. Kết quả
    if received:
        print("\n✅ END-TO-END TEST PASSED — WebSocket broadcast working!")
    else:
        print("\n❌ TEST FAILED — no broadcast received")


asyncio.run(main())
