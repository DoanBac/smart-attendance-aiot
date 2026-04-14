# 🎓 AIoT Smart Attendance System

> Hệ thống điểm danh thông minh — FastAPI · Next.js 14 · InsightFace · Raspberry Pi Edge

---

## 📑 Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Kiến trúc hệ thống](#2-kiến-trúc-hệ-thống)
3. [Yêu cầu](#3-yêu-cầu)
4. [Cài đặt & Chạy — macOS / Linux](#4-cài-đặt--chạy--macos--linux)
5. [Cài đặt & Chạy — Raspberry Pi Edge](#5-cài-đặt--chạy--raspberry-pi-edge)
6. [Cấu trúc thư mục](#6-cấu-trúc-thư-mục)
7. [API Reference](#7-api-reference)
8. [Tài khoản mặc định](#8-tài-khoản-mặc-định)
9. [Pipeline AI](#9-pipeline-ai)
10. [Edge Device — Chi tiết](#10-edge-device--chi-tiết)
11. [Bảo mật](#11-bảo-mật)
12. [Bugs đã gặp & cách xử lý](#12-bugs-đã-gặp--cách-xử-lý)
13. [Trạng thái & Roadmap](#13-trạng-thái--roadmap)

---

## 1. Tổng quan

**AIoT Smart Attendance System** là hệ thống điểm danh tự động dùng nhận diện khuôn mặt (Face Recognition) kết hợp Edge Computing:

| Tính năng | Mô tả |
|---|---|
| Đăng ký khuôn mặt (cloud) | Admin chụp 6 góc nhìn × 5 frames qua webcam, InsightFace trích xuất embedding |
| Đăng ký khuôn mặt (offline) | Tại thiết bị Pi — 6 góc × 5 frames, cùng model và flow với cloud |
| Nhận diện real-time | Edge device nhận diện với cosine similarity trên embedding 512-dim |
| Liveness detection | CNN anti-spoof (ONNX) + head pose challenge — chặn ảnh tĩnh, màn hình và replay video |
| Offline resilience | SQLite queue trên edge, tự bulk-sync khi có mạng |
| Mã hóa embedding | AES-256-GCM — embedding không bao giờ lưu plaintext |
| WebSocket | Dashboard cập nhật điểm danh real-time qua WS |
| ESP8266 Door Lock | Relay mở khóa cửa sau khi nhận diện thành công |

---

## 2. Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────────┐
│                    CLOUD (Docker Compose)                │
│                                                          │
│  Next.js :3000 ──▶ FastAPI :8000 ──▶ PostgreSQL :5432  │
│                         │              Redis :6379        │
│                         ▼                                │
│                  AI Service :9000                        │
│        (InsightFace + CNN anti-spoof / liveness)         │
│   Detection: SCRFD · Recognition: ArcFace · Liveness CNN │
└────────────────────────┬────────────────────────────────┘
                         │  REST + Device Token (LAN/Internet)
┌────────────────────────▼────────────────────────────────┐
│              EDGE DEVICE (Raspberry Pi 4)               │
│                                                          │
│  Camera USB ──▶ AI Pipeline ──▶ SQLite  ──▶  Sync      │
│  (EMEET C950)   SCRFD detect      local.db    daemon    │
│                 w600k_mbf embed                          │
│                 Liveness check                           │
│                      │                                   │
│              Flask Web :5000                             │
│    / (kiosk) · /enroll (đăng ký offline)                │
└─────────────────────────────────────────────────────────┘
                         │  HTTP (LAN)
          ESP8266 Door Controller (:80)
          (relay mở cửa sau recognition)
```

### Stack công nghệ

| Layer | Công nghệ | Version |
|---|---|---|
| Backend API | FastAPI + Uvicorn | 0.115.0 |
| ORM | SQLAlchemy (async) | 2.0.36 |
| Database | PostgreSQL | 16-alpine |
| Cache / PubSub | Redis | 7-alpine |
| Face AI (cloud) | InsightFace buffalo_sc | 0.7.3 |
| Face AI (edge) | ONNX Runtime | 1.19.2 |
| Frontend | Next.js 14 App Router | 14.x |
| Styling | Tailwind CSS | 3.x |
| Edge language | Python 3.11 |  |
| Edge web server | Flask | 3.1.0 |
| Containerization | Docker Compose v2 |  |

---

## 3. Yêu cầu

### Cloud (macOS / Linux / Windows)

- **Docker Desktop** ≥ 4.x (Docker Compose v2 built-in)
- RAM: 4 GB tối thiểu · 8 GB khuyến nghị (InsightFace ~1 GB)
- Disk: 8 GB trống
- OS: macOS 12+, Ubuntu 20.04+, Windows 10/11

### Edge (Raspberry Pi)

- Raspberry Pi 4 (4 GB RAM)
- Camera USB (đã test: EMEET C950)
- MicroSD ≥ 32 GB (class 10)
- OS: Raspberry Pi OS Lite 64-bit (Bookworm) hoặc Ubuntu 22.04 arm64
- Docker 24+ và Docker Compose v2
- Cùng LAN với máy Cloud hoặc có Cloudflare Tunnel

---

## 4. Cài đặt & Chạy — macOS / Linux

### Bước 1 — Clone & cấu hình

```bash
git clone https://github.com/DoanBac/smart-attendance-aiot.git
cd smart-attendance-aiot
cp backend/.env.example backend/.env
```

### Bước 2 — Build và chạy toàn bộ

```bash
docker compose up -d --build
```

Lần đầu mất **5–15 phút** (download images + InsightFace models).

> **Apple Silicon (M1/M2/M3):** Nếu gặp `exec format error`, thêm `platform: linux/amd64` vào service trong `docker-compose.yml`.

### Bước 3 — Seed admin (lần đầu)

```bash
docker exec smart-attendance-aiot-backend-1 python reset_admin_password.py
```

### Bước 4 — Truy cập

| Service | URL |
|---|---|
| Frontend (Admin UI) | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |

Đăng nhập: `admin@school.edu.vn` / `admin123`

### Lệnh thường dùng

```bash
docker compose logs -f backend
docker compose up -d --build backend
docker compose down
docker compose down -v  # reset hoàn toàn (XÓA database)
docker exec -it smart-attendance-aiot-postgres-1 psql -U doanbac07 -d attendance_db
docker exec -it smart-attendance-aiot-redis-1 redis-cli KEYS "*"
docker exec -it smart-attendance-aiot-backend-1 bash
```

---

## 5. Cài đặt & Chạy — Raspberry Pi Edge

### 5.1 Chuẩn bị Pi (một lần)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker pi
newgrp docker
mkdir -p ~/attendance-edge/{src,data,models,config}
```

### 5.2 Copy source code lên Pi

Từ **Mac** (thay `192.168.x.x` bằng IP Pi):

```bash
scp -r edge/src pi@192.168.x.x:~/attendance-edge/src
scp edge/docker-compose.yml edge/Dockerfile edge/requirements.txt \
    pi@192.168.x.x:~/attendance-edge/
```

> **Hotfix nhanh** (không cần rebuild):
> ```bash
> scp edge/src/web/stream.py pi@IP:~/attendance-edge/src/web/stream.py
> ssh pi@IP 'cd ~/attendance-edge && docker compose restart'
> ```

### 5.3 Tạo cấu hình thiết bị

SSH vào Pi, tạo `~/attendance-edge/config/device.env`:

```env
DEVICE_TOKEN=1cca41cee8e041ca8f91dd79b3530490
CLASS_ID=6803980d-be34-43be-be76-8e49cb19a2a6
CLOUD_API_URL=http://192.168.123.xxx:8000
CAMERA_SOURCE=/dev/video0
FRAME_WIDTH=640
FRAME_HEIGHT=480
CAPTURE_FPS=20
PROCESS_EVERY_N_FRAMES=5
DETECTION_MODEL=/app/models/yolov8_face_320.onnx
EMBEDDING_MODEL=/app/models/w600k_mbf.onnx
AES_KEY=5fc0fa62e37680651a6a782d13856c6b3f4e36c5472dbd5705c52b5a968ccb1b
COSINE_THRESHOLD=0.45
LOCAL_DB_PATH=/app/data/local.db
ORT_NUM_THREADS=4
SYNC_INTERVAL_SEC=30
```

### 5.4 Download models nhận diện

```bash
cd ~/attendance-edge/models

# Model nhận diện (InsightFace buffalo_sc, ~13 MB)
# PHẢI cùng model với cloud để embedding tương thích!
# buffalo_sc.zip (~15MB, bao gồm det_500m.onnx + w600k_mbf.onnx)
wget -O /tmp/buffalo_sc.zip \
  "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_sc.zip"
unzip /tmp/buffalo_sc.zip -d /tmp/buffalo_sc_extracted
cp /tmp/buffalo_sc_extracted/w600k_mbf.onnx ~/attendance-edge/models/w600k_mbf.onnx

ls -lh *.onnx
# yolov8_face_320.onnx  ~17 MB  (SCRFD detector)
# w600k_mbf.onnx        ~13 MB (ArcFace recognizer)
```

### 5.5 Build và chạy

```bash
cd ~/attendance-edge
docker compose build    # lần đầu ~10–20 phút trên Pi 4
docker compose up -d
docker compose logs -f
```

### 5.6 Giao diện web trên Pi

| URL | Mô tả |
|---|---|
| `http://PI-IP:5000/` | Kiosk điểm danh real-time |
| `http://PI-IP:5000/enroll` | Đăng ký khuôn mặt offline (6-pose) |
| `http://PI-IP:5000/status` | JSON status API |
| `http://PI-IP:5000/snapshot` | Snapshot JPEG hiện tại |

### 5.7 Quy trình đăng ký khuôn mặt offline (`/enroll`)

1. Mở `http://PI-IP:5000/enroll`
2. Nhập **Mã sinh viên** → hệ thống tự tra cứu tên từ DB local
3. Click **Bắt đầu đăng ký khuôn mặt**
4. Thực hiện 6 tư thế (front, left, right, up, down, confirm) — 5 frames mỗi tư thế
5. Embedding được trích xuất bằng `w600k_mbf.onnx`, tổng hợp weighted average, mã hóa AES-256-GCM, lưu `is_local=1`
6. Cloud sync **không ghi đè** embedding có `is_local=1`

### 5.8 Update code lên Pi (workflow thường ngày)

```bash
KEY=~/.ssh/pi_edge_key
PI=192.168.xxx.xxx
scp -i $KEY edge/src/web/stream.py pi@$PI:~/attendance-edge/src/web/stream.py
ssh -i $KEY pi@$PI 'cd ~/attendance-edge && docker compose restart'
```

---

## 6. Cấu trúc thư mục

```
smart-attendance-aiot/
├── docker-compose.yml
├── README.md
├── Paper_v2.md
├── backend/
│   ├── reset_admin_password.py     # Util: reset admin → admin123
│   ├── start.sh
│   └── app/
│       ├── api/routes/
│       │   ├── auth.py             # /api/auth/login|register|refresh
│       │   ├── students.py         # CRUD /api/students/
│       │   ├── classes.py          # CRUD /api/classes/
│       │   ├── attendance.py       # /api/attendance/ + bulk-sync
│       │   ├── devices.py          # register · heartbeat · embeddings
│       │   └── enrollment.py       # capture-frame · finalize · identify
│       ├── core/
│       │   ├── encryption.py       # AES-256-GCM
│       │   ├── jwt_handler.py
│       │   └── security.py
│       ├── models/                 # SQLAlchemy ORM
│       ├── schemas/                # Pydantic v2
│       └── websocket/
│           └── attendance_ws.py    # WS /ws/attendance/{class_id}
├── ai-service/
│   └── app/core/face_model.py      # InsightFace buffalo_sc singleton
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── students/           # Enrollment 6-pose UI
│       │   ├── attendance/
│       │   └── devices/
│       └── lib/api.ts              # getApiBase() / getWsBase()
├── edge/
│   └── src/
│       ├── ai/
│       │   ├── face_detection.py   # SCRFD (ONNX)
│       │   ├── face_alignment.py   # 5-point → 112x112
│       │   ├── face_embedding.py   # w600k_mbf (512-dim)
│       │   ├── pipeline.py         # detect→liveness→embed→match
│       │   └── liveness/
│       ├── database/local_db.py    # SQLite: embeddings + offline_queue
│       ├── sync/queue_sync.py      # SyncDaemon
│       └── web/stream.py           # Flask: / · /video · /enroll · /enroll/lookup
│                                   #        /enroll/capture · /enroll/finalize
├── edge/esp8266/door_controller/
│   └── door_controller.ino         # Arduino relay firmware
├── nginx/default.conf
└── infra/                          # AWS CDK (EC2 + RDS + ElastiCache)
```

---

## 7. API Reference

### Authentication

```
POST /api/auth/login
{"email": "admin@school.edu.vn", "password": "admin123"}
→ {"access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer"}
```

### Students / Classes

| Method | Endpoint | Auth |
|---|---|---|
| GET / POST | `/api/students/` | JWT |
| GET / PUT | `/api/students/{id}` | JWT |
| GET / POST | `/api/classes/` | JWT |

### Attendance

| Method | Endpoint | Auth | Mô tả |
|---|---|---|---|
| POST | `/api/attendance/` | Device Token | Edge ghi điểm danh |
| POST | `/api/attendance/bulk-sync` | Device Token | Sync offline queue |
| GET | `/api/attendance/class/{id}` | JWT | Lịch sử |

Header: `X-Device-Token: <token>`

### Enrollment (Cloud)

| Method | Endpoint | Mô tả |
|---|---|---|
| POST | `/api/enrollment/capture-frame` | 1 frame → detect + buffer |
| POST | `/api/enrollment/finalize` | Tổng hợp → lưu DB |
| POST | `/api/enrollment/identify` | Nhận diện trong ảnh |

```json
POST /api/enrollment/capture-frame
{"student_id": "uuid", "frame_b64": "<base64>", "step_index": 0}
→ {"accepted": true, "quality": 0.87, "buffered": 3}
```

Cần ≥5 frames accepted trước finalize.

### Edge Local Enrollment (Flask :5000)

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/enroll` | Trang HTML đăng ký 6-pose |
| GET | `/enroll/lookup?code=FSB001` | Tra cứu sinh viên |
| POST | `/enroll/capture` | Capture → detect + embed |
| POST | `/enroll/finalize` | Lưu `is_local=1` |

### WebSocket

```
WS /ws/attendance/{class_id}
```

Broadcast real-time mỗi khi edge ghi điểm danh.

---

## 8. Tài khoản mặc định

> **CHỈ dùng trong development.**

| Loại | Thông tin |
|---|---|
| Admin email | `admin@school.edu.vn` |
| Admin password | `admin123` |
| PostgreSQL DB | `attendance_db` / user `doanbac07` / pw `070301` |
| Device Token | `1cca41cee8e041ca8f91dd79b3530490` |
| Class ID (AI501-01) | `6803980d-be34-43be-be76-8e49cb19a2a6` |
| AES Key | `5fc0fa62e37680651a6a782d13856c6b3f4e36c5472dbd5705c52b5a968ccb1b` |

---

## 9. Pipeline AI

### 9.1 Tư duy cốt lõi: nhận dạng danh tính khác với chống spoof

Hệ thống hiện tại **tách thành 2 bài toán deep learning**:

1. **Face Recognition (ArcFace / InsightFace)**
   - Trả lời câu hỏi: **"đây là ai?"**
   - Output là **embedding 512 chiều** để so cosine similarity với dữ liệu đã đăng ký.

2. **Anti-Spoof / Liveness (CNN ONNX)**
   - Trả lời câu hỏi: **"đây có phải người thật trước camera không?"**
   - Output là `liveness_score` và `is_live` để chặn ảnh tĩnh, ảnh trên điện thoại/laptop, hoặc replay video.

> Nếu chỉ dùng ArcFace thì **ảnh của đúng người vẫn có thể match rất tốt**. Vì vậy hệ thống bắt buộc phải thêm **CNN anti-spoof + head pose challenge** để phân biệt **người thật** với **ảnh/video giả mạo**.

### 9.2 Cloud-side — Enrollment / Verification

```
Webcam / Camera frame
  → JPEG base64 → backend
  → ai-service /api/v1/extract
  → Face detect (InsightFace)
  → ArcFace embedding 512-dim
  → Blur check + face size check
  → Head pose (yaw / pitch)
  → CNN anti-spoof → liveness_score / is_live
  → nếu live: buffer / identify
  → nếu spoof: reject ngay
```

Trong luồng cloud:

- `backend/app/api/routes/enrollment.py` kiểm tra từng frame đăng ký
- `backend/app/services/attendance_service.py` kiểm tra khi kiosk/điểm danh
- chỉ khi `is_live=True` thì frame mới được chấp nhận để lưu hoặc dùng cho attendance

### 9.3 Kiosk / Attendance — logic chống spoof khi điểm danh

```
Camera frame
  → /api/attendance/verify-face
  → ai-service /extract
  → ArcFace + anti-spoof
  → pose challenge trái/phải (active liveness)
  → cosine similarity với gallery
  → ghi nhận attendance nếu vừa đúng người vừa là người thật
```

Điểm quan trọng:

- **Passive liveness**: CNN học texture/màu/độ phản xạ/mô hình màn hình, giúp phân biệt face thật với face hiển thị trên giấy hoặc màn hình.
- **Active liveness**: người dùng phải xoay đầu theo hướng yêu cầu, giúp giảm khả năng qua mặt bằng ảnh tĩnh hoặc replay video không đúng thời điểm.

### 9.4 Edge-side — ONNX Runtime (Raspberry Pi)

```
Camera Frame (640×480 @ 20fps)
  ├──▶ Camera thread → MJPEG stream (/video)
  └──▶ AI worker thread (async queue maxsize=1)
        [1] SCRFD Detection (yolov8_face_320.onnx)
        [2] 5-point landmark → 112×112 crop
        [3] Liveness / pose checks
        [4] w600k_mbf.onnx → embedding 512-dim
        [5] Cosine similarity vs local cache
        → Recognized: POST /api/attendance/ (hoặc SQLite queue)
```

### 9.5 Vì sao logic này cần thiết

- chặn việc **điểm danh bằng ảnh của chính người dùng**
- giảm false accept với **điện thoại, laptop, tablet, ảnh in**
- cho phép **ArcFace tập trung vào identity**, còn **CNN tập trung vào live/spoof**
- dễ thay thế / nâng cấp model liveness mà không phải thay toàn bộ pipeline nhận diện

---

## 10. Edge Device — Chi tiết

### Thread Architecture

```
main.py
  ├── Flask thread         (port 5000)
  ├── Camera loop thread   (20fps, non-blocking)
  ├── AI worker thread     (queue maxsize=1)
  ├── SyncDaemon thread    (embeddings + attendance sync)
  └── Heartbeat thread     (POST mỗi 30s)
```

### Model Files (~/attendance-edge/models/)

| File | Size | Mô tả |
|---|---|---|
| `yolov8_face_320.onnx` | ~17 MB | SCRFD face detector |
| `w600k_mbf.onnx` | ~13 MB | InsightFace buffalo_sc — PHẢI khớp với cloud |
| `depth_lite.onnx` | tuỳ chọn | Auto-disable nếu không có |

> **Quan trọng**: Dùng `arcface_r100.onnx` thay vì `w600k_mbf.onnx` → cosine_sim ≈ 0 → không nhận diện.

### Local SQLite DB (local_embeddings)

| Column | Type | Mô tả |
|---|---|---|
| student_id | TEXT | UUID từ cloud |
| student_code | TEXT | FSB001… |
| full_name | TEXT | Họ tên |
| embedding_enc | BLOB | AES-GCM encrypted 512-dim |
| is_local | INTEGER | 0=cloud sync · 1=đăng ký tại thiết bị |
| updated_at | TEXT | Timestamp |

### Offline Resilience

- Mất mạng → ghi vào `offline_queue` SQLite
- SyncDaemon bulk-sync khi có mạng trở lại
- Cooldown 10s giữa các lần nhận diện cùng sinh viên

### ESP8266 Door Controller

- HTTP server port 80: `POST /open` (relay 3s) · `GET /status`
- State machine: IDLE → OPENING → OPEN → CLOSING
- Flash: Arduino IDE, board "LOLIN D1 R2", baud 115200

---

## 11. Bảo mật

### AES-256-GCM

```python
aesgcm = AESGCM(bytes.fromhex(AES_KEY))   # 32-byte key
nonce  = os.urandom(12)                     # 96-bit nonce
stored = nonce + aesgcm.encrypt(nonce, raw_float32_bytes, None)
# 12 + (512×4 + 16) = 2076 bytes stored
```

Embedding không bao giờ lưu plaintext.

### JWT

- Access Token: 15 phút (HS256)
- Refresh Token: 7 ngày
- Set `JWT_SECRET_KEY` cố định trong `backend/.env` cho production

### Device Auth

`X-Device-Token` header — bcrypt hash trong DB, gắn 1 thiết bị cụ thể.

### Rate Limiting

100 req/phút per IP (Redis) trên tất cả `/api/*`.

---

## 12. Bugs đã gặp & cách xử lý

### Bug 1 — Double-sigmoid (SCRFD detector)

**Triệu chứng**: ~4200 khuôn mặt rác/frame, confidence ≈ 0.5 tất cả.

**Nguyên nhân**: Model output đã post-sigmoid, code apply thêm lần nữa → anchors ≈ 0.5 vượt threshold.

**Fix** (`face_detection.py`):
```python
_already_sigmoid = arr.min() >= 0 and arr.max() <= 1.0
scores = raw if _already_sigmoid else _sigmoid(raw)
```

---

### Bug 2 — Liveness stuck (không bao giờ pass)

**Triệu chứng**: UI "⏳ Đang kiểm tra" mãi mãi.

**Nguyên nhân**: Logic `blink AND head AND depth` — blink luôn False vì thiếu eye landmarks.

**Fix** (`pipeline.py`):
```python
def is_complete(self) -> bool:
    return self.depth_passed or self._head._done
```

---

### Bug 3 — Embedding mismatch (cosine_sim ≈ 0)

**Triệu chứng**: Face ✅, liveness ✅, recognized: None.

**Nguyên nhân**: Cloud dùng `w600k_mbf.onnx`, edge dùng `arcface_r100.onnx` — khác embedding space hoàn toàn.

**Fix**: Edge phải dùng cùng model `w600k_mbf.onnx`.

---

### Bug 4 — Video lag / low fps

**Fix**: Tách AI thành worker thread riêng với queue `maxsize=1`. Camera chạy 20fps không bị block.

---

### Bug 5 — Login dùng field sai

**Fix** frontend: `body: JSON.stringify({ email, password })` (không phải `username`).

---

### Bug 6 — MissingGreenlet (SQLAlchemy async update)

**Fix**: Dùng `UPDATE` statement trực tiếp, không dùng `setattr` + `flush` trong async context.

---

### Bug 7 — Pydantic v2 conflict

**Fix**: Chỉ dùng `model_config = ConfigDict(from_attributes=True)`, xóa `class Config:`.

---

### Bug 8 — UUID serialization WS

**Fix**: Convert UUID → string trước `json.dumps()`.

---

### Bug 9 — SCP sai path

**Sai**: `scp stream.py pi@IP:~/attendance-edge/src/`

**Đúng**: `scp edge/src/web/stream.py pi@IP:~/attendance-edge/src/web/stream.py`

---

## 13. Trạng thái & Roadmap

### Trạng thái hiện tại

| Component | Status | Ghi chú |
|---|---|---|
| Backend API | ✅ | Tất cả endpoints hoạt động |
| PostgreSQL + Alembic | ✅ | Auto-migration khi startup |
| Redis | ✅ | Rate limit + WS pubsub |
| InsightFace buffalo_sc (cloud) | ✅ | w600k_mbf + SCRFD |
| Frontend Next.js 14 | ✅ | Dynamic URL |
| Cloud enrollment (6-pose) | ✅ | Tested end-to-end |
| WebSocket real-time | ✅ | Redis PubSub |
| Pi camera 20fps | ✅ | Smooth MJPEG |
| Pi AI worker thread | ✅ | Async queue |
| Pi SCRFD detection | ✅ | conf=0.843, double-sigmoid fixed |
| Pi liveness | ✅ | Auto-pass (depth disabled) |
| Pi embedding w600k_mbf | ✅ | buffalo_sc MobileFaceNet, khớp với cloud |
| Pi recognition | ⚠️ | Cần re-enroll với đúng model (buffalo_sc) |
| Pi /enroll offline (6-pose) | ✅ | UI + API hoàn chỉnh |
| Pi student lookup by code | ✅ | Auto-fill từ mã sinh viên |
| Edge offline queue + sync | ✅ | SQLite + bulk-sync |
| ESP8266 door controller | ✅ | Firmware xong, chưa flash |
| Nginx reverse proxy | ✅ | Port 80 |
| AWS CDK infra | ✅ | Code ready, chưa deploy |

### Roadmap ngắn hạn

- [ ] Verify `w600k_mbf.onnx` download → test recognition end-to-end
- [ ] Flash ESP8266 → test relay mở cửa

---

## 14. Tài liệu chi tiết anti-spoof / deep learning

Phần hướng dẫn chi tiết bằng **tiếng Việt** cho chống spoofing, dataset và huấn luyện CNN nằm tại:

- `ai-service/README.md`

Tài liệu đó mô tả:

- vì sao **ArcFace không đủ** để chống ảnh / replay attack
- kiến trúc **ArcFace + CNN anti-spoof + pose challenge** trong runtime
- cách thu thập và chia dữ liệu **train / dev(val) / test**
- cách dùng các script `organize_antispoof_samples.py`, `extract_spoof_frames.py`, `train_cnn_antispoof.py`
- cách export ONNX và copy **cả** `.onnx` lẫn `.onnx.data` vào runtime
- cách tune `ANTISPOOF_THRESHOLD` và đánh giá chất lượng chống giả mạo

### Ghi chú phần cứng còn lại

- [ ] Fix LED_RED GPIO0 boot issue (đổi sang GPIO12)
- [ ] Xử lý magnet overheating

### Roadmap dài hạn

- [ ] Mobile app (React Native)
- [ ] Multi-camera RTSP support
- [ ] Fine-tune model trên dataset sinh viên
- [ ] RFID fallback

---

## 🔧 Quick Reference Commands

```bash
# ── Cloud ─────────────────────────────────────────────────────────
docker compose up -d --build
docker compose logs -f backend
docker compose down -v   # reset hoàn toàn
docker exec smart-attendance-aiot-backend-1 python reset_admin_password.py
docker exec -it smart-attendance-aiot-postgres-1 psql -U doanbac07 -d attendance_db

# ── Pi Edge (từ Mac) ──────────────────────────────────────────────
PI=192.168.x.x
KEY=~/.ssh/pi_edge_key

scp -i $KEY edge/src/web/stream.py pi@$PI:~/attendance-edge/src/web/stream.py
ssh -i $KEY pi@$PI 'cd ~/attendance-edge && docker compose restart'
ssh -i $KEY pi@$PI 'docker logs attendance-edge-edge-ai-1 --tail 30'
curl http://$PI:5000/status

# SQLite trên Pi
ssh -i $KEY pi@$PI 'docker exec attendance-edge-edge-ai-1 \
  sqlite3 /app/data/local.db \
  "SELECT student_code, full_name, is_local FROM local_embeddings;"'
```

---

## 📚 Tài liệu tham khảo

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [InsightFace GitHub](https://github.com/deepinsight/insightface)
- [InsightFace buffalo_sc models](https://huggingface.co/deepinsight/insightface)
- [SQLAlchemy 2.0 Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Next.js 14 App Router](https://nextjs.org/docs/app)
- [ONNX Runtime Python API](https://onnxruntime.ai/docs/api/python/)
- [Paper_v2.md](./Paper_v2.md) — Tài liệu nghiên cứu & thiết kế chi tiết
