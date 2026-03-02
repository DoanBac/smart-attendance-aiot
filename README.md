# 🎓 AIoT Smart Attendance System

> Hệ thống điểm danh thông minh sử dụng nhận diện khuôn mặt AIoT — FastAPI + Next.js + InsightFace + Edge Computing

---

## 📑 Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Kiến trúc](#2-kiến-trúc)
3. [Yêu cầu hệ thống](#3-yêu-cầu-hệ-thống)
4. [Cài đặt & Chạy](#4-cài-đặt--chạy)
5. [Cấu trúc thư mục](#5-cấu-trúc-thư-mục)
6. [API Reference](#6-api-reference)
7. [Dữ liệu mặc định & Tài khoản test](#7-dữ-liệu-mặc-định--tài-khoản-test)
8. [Pipeline AI nhận diện khuôn mặt](#8-pipeline-ai-nhận-diện-khuôn-mặt)
9. [Edge Device](#9-edge-device)
10. [Bảo mật](#10-bảo-mật)
11. [Các lỗi đã gặp & cách xử lý](#11-các-lỗi-đã-gặp--cách-xử-lý)
12. [Lưu ý quan trọng](#12-lưu-ý-quan-trọng)
13. [Hướng phát triển tiếp theo](#13-hướng-phát-triển-tiếp-theo)

---

## 1. Tổng quan hệ thống

**AIoT Smart Attendance System** là hệ thống điểm danh tự động sử dụng nhận diện khuôn mặt (Face Recognition) kết hợp giữa:

- **Cloud Backend** (FastAPI + PostgreSQL + Redis): Quản lý dữ liệu, API, lưu trữ embedding mã hóa
- **Web Frontend** (Next.js 14): Giao diện quản trị cho admin — quản lý sinh viên, lớp học, xem lịch sử điểm danh
- **Edge Device**: Thiết bị IoT gắn tại phòng học — chạy AI inference local, tự điểm danh offline khi mất mạng

### Tính năng chính

| Tính năng | Mô tả |
|---|---|
| Đăng ký khuôn mặt | Admin chụp ≥5 frames qua webcam browser, tự động tổng hợp embedding |
| Nhận diện real-time | Edge device nhận diện khuôn mặt với ArcFace (512-dim cosine similarity) |
| Liveness detection | 3-layer: EAR blink + Head pose PnP + Depth estimation — chống ảnh tĩnh/video replay |
| Offline resilience | Edge lưu queue SQLite khi mất mạng, tự sync khi có kết nối |
| Mã hóa embedding | AES-256-GCM — embedding không bao giờ lưu dạng plaintext |
| WebSocket real-time | Dashboard cập nhật điểm danh real-time qua WS |
| JWT Authentication | Access token 15 phút + Refresh token 7 ngày |

---

## 2. Kiến trúc

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLOUD (Docker)                           │
│                                                                   │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│   │  Next.js 14  │────▶│  FastAPI     │────▶│  PostgreSQL  │    │
│   │  :3000       │     │  :8000       │     │  :5432       │    │
│   └──────────────┘     └──────┬───────┘     └──────────────┘    │
│                               │                                   │
│                               │             ┌──────────────┐    │
│                               └────────────▶│    Redis     │    │
│                                             │  :6379       │    │
│                                             └──────────────┘    │
└─────────────────────────────────────────────────────────────────┘
              ▲  REST API + Device Token
              │
┌─────────────┴───────────────────────────────────────────────────┐
│                    EDGE DEVICE (Raspberry Pi / PC)               │
│                                                                   │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│   │   Camera     │────▶│  AI Pipeline │────▶│  SQLite DB   │    │
│   │  (USB/RTSP)  │     │  YOLOv8 +   │     │  (offline)   │    │
│   └──────────────┘     │  ArcFace R100│     └──────────────┘    │
│                         │  + Liveness  │                          │
│                         └──────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

### Stack công nghệ

| Layer | Công nghệ | Phiên bản |
|---|---|---|
| Backend API | FastAPI | 0.115.0 |
| ORM | SQLAlchemy (async) | 2.0.36 |
| Database | PostgreSQL | 16-alpine |
| Cache | Redis | 7-alpine |
| Face Recognition | InsightFace (buffalo_sc) | 0.7.3 |
| ONNX Runtime | onnxruntime | 1.19.2 |
| Frontend | Next.js | 14 |
| Styling | Tailwind CSS | 3.x |
| Containerization | Docker Compose | v2 |
| DB Driver | asyncpg | 0.30.0 |
| Validation | Pydantic v2 | 2.9.2 |

---

## 3. Yêu cầu hệ thống

### Tối thiểu

- **Docker Desktop** ≥ 4.x (với Docker Compose v2)
- **RAM**: 4 GB (8 GB khuyến nghị — InsightFace model ~1GB)
- **Disk**: 5 GB trống
- **OS**: Windows 10/11, Ubuntu 20.04+, macOS 12+

### Edge Device (nếu triển khai riêng)

- Raspberry Pi 4 (4GB RAM) hoặc Jetson Nano
- Camera USB hoặc Camera Module
- Python 3.10+
- OpenCV, onnxruntime

---

## 4. Cài đặt & Chạy

> **Yêu cầu duy nhất:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) — không cần cài Python, Node.js, hay bất kỳ thứ gì khác.

---

### 🍎 Hướng dẫn đầy đủ cho macOS (Apple Silicon & Intel)

#### Bước 1 — Cài Docker Desktop

```bash
# Cách 1: Tải trực tiếp (khuyên dùng)
# → https://www.docker.com/products/docker-desktop/
# Chọn bản "Mac with Apple Chip" (M1/M2/M3) hoặc "Mac with Intel Chip"

# Cách 2: Dùng Homebrew
brew install --cask docker
```

Sau khi cài, mở **Docker Desktop** và đợi icon Docker trên menu bar chuyển sang màu trắng (running).

#### Bước 2 — Clone repo

```bash
git clone https://github.com/DoanBac/smart-attendance-aiot.git
cd smart-attendance-aiot
```

#### Bước 3 — Tạo file `.env`

```bash
cp backend/.env.example backend/.env
```

> File `.env` đã có sẵn giá trị hợp lệ để chạy local. **Không cần sửa gì** cho môi trường dev.

#### Bước 4 — Build và chạy toàn bộ hệ thống

```bash
docker-compose up -d --build
```

Lần đầu sẽ mất **5–10 phút** (download images, build, cài packages AI). Các lần sau chỉ ~30 giây.

#### Bước 5 — Seed dữ liệu mặc định (lần đầu chạy)

```bash
# Reset password admin về admin123
docker exec smart-attendance-aiot-backend-1 python reset_admin_password.py
```

#### Bước 6 — Kiểm tra

```bash
docker-compose ps
```

Tất cả services phải ở trạng thái `Up` hoặc `healthy`:

| Service | Port | URL |
|---|---|---|
| Frontend (Next.js) | 3000 | http://localhost:3000 |
| Backend (FastAPI) | 8000 | http://localhost:8000 |
| API Docs (Swagger) | 8000 | http://localhost:8000/docs |
| PostgreSQL | 5432 | — (internal) |
| Redis | 6379 | — (internal) |

#### Bước 7 — Đăng nhập

Mở http://localhost:3000

| Field | Giá trị |
|---|---|
| Email | `admin@school.edu.vn` |
| Password | `admin123` |

---

### 🪟 Hướng dẫn cho Windows

Tương tự macOS — cài [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/), sau đó làm từ Bước 2 trở đi trong **PowerShell** hoặc **Git Bash**.

---

### 🔄 Các lệnh thường dùng

```bash
# Xem logs real-time
docker-compose logs -f backend
docker-compose logs -f frontend

# Dừng tất cả
docker-compose down

# Rebuild sau khi sửa code backend
docker-compose up -d --build backend

# Rebuild sau khi sửa code frontend
docker-compose up -d --build frontend

# Reset hoàn toàn (xóa cả database)
docker-compose down -v
docker-compose up -d --build

# Vào psql xem database
docker exec -it smart-attendance-aiot-postgres-1 psql -U doanbac07 -d attendance_db

# Xem enrollment sessions trong Redis
docker exec -it smart-attendance-aiot-redis-1 redis-cli KEYS "enrollment:*"
```

---

### ⚠️ Lưu ý Apple Silicon (M1/M2/M3)

Project dùng `onnxruntime` và `insightface` — **đã tương thích** với ARM64 thông qua Docker `linux/amd64` emulation. Nếu gặp lỗi `exec format error`:

```bash
# Thêm platform vào docker-compose.yml (nếu cần)
# services:
#   backend:
#     platform: linux/amd64   ← thêm dòng này

docker-compose up -d --build
```

---

### 🔑 Tài khoản & Token mặc định

| Loại | Giá trị |
|---|---|
| Admin email | `admin@school.edu.vn` |
| Admin password | `admin123` |
| Device token (test) | `b7da9fc490c04c20bcd0d4c8165a1ae4` |
| Device class | Class ID = 2 |

---

## 5. Cấu trúc thư mục

```
smart-attendance-aiot/
├── docker-compose.yml          # Orchestration: postgres, redis, backend, frontend
├── README.md
│
├── backend/                    # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # Entry point, router mounting, CORS, lifespan
│       ├── config.py           # Pydantic Settings (env vars)
│       ├── api/
│       │   ├── dependencies.py
│       │   ├── middleware/
│       │   │   ├── auth_middleware.py
│       │   │   └── rate_limiter.py
│       │   └── routes/
│       │       ├── auth.py          # POST /api/auth/login|register|refresh
│       │       ├── students.py      # CRUD /api/students/
│       │       ├── classes.py       # CRUD /api/classes/
│       │       ├── attendance.py    # POST /api/attendance/, bulk-sync, GET by class
│       │       ├── devices.py       # /api/devices/register|heartbeat|embeddings
│       │       └── enrollment.py    # /api/enrollment/capture-frame|finalize|upload-embedding|identify
│       ├── core/
│       │   ├── encryption.py   # AES-256-GCM encrypt/decrypt
│       │   ├── jwt_handler.py  # JWT encode/decode
│       │   └── security.py     # get_current_admin, verify_device_token
│       ├── database/
│       │   └── session.py      # AsyncEngine, SessionLocal, Base, get_db
│       ├── models/             # SQLAlchemy ORM models
│       │   ├── admin.py        # Table: admins
│       │   ├── student.py      # Table: students (face_embedding: LargeBinary)
│       │   ├── class_.py       # Table: classes
│       │   ├── device.py       # Table: devices
│       │   └── attendance.py   # Table: attendance
│       ├── schemas/            # Pydantic v2 request/response schemas
│       ├── services/           # Business logic
│       │   ├── auth_service.py
│       │   ├── student_service.py
│       │   ├── attendance_service.py
│       │   ├── device_service.py
│       │   └── face_service.py  # InsightFace + AES + liveness
│       └── websocket/
│           └── attendance_ws.py # WS /ws/attendance/{class_id}
│
├── frontend/                   # Next.js 14 (App Router)
│   ├── Dockerfile
│   ├── src/app/
│   │   ├── (auth)/login/       # Trang đăng nhập
│   │   ├── dashboard/          # Dashboard thống kê
│   │   ├── students/           # Quản lý sinh viên + enrollment
│   │   ├── classes/            # Quản lý lớp học
│   │   ├── attendance/         # Xem lịch sử điểm danh
│   │   ├── devices/            # Quản lý thiết bị
│   │   └── reports/            # Báo cáo
│   ├── src/components/
│   ├── src/hooks/
│   └── src/store/              # Zustand stores
│
└── edge/                       # Edge device application
    ├── Dockerfile
    ├── requirements.txt
    └── src/
        ├── main.py             # Main loop: capture → detect → liveness → identify → sync
        ├── config.py           # EdgeConfig from device.env
        ├── ai/
        │   ├── face_detection.py   # YOLOv8 face detector
        │   ├── face_alignment.py   # 5-point landmark alignment
        │   ├── face_embedding.py   # ArcFace R100 embedder
        │   ├── pipeline.py         # Full 7-step pipeline
        │   └── liveness/
        │       ├── blink_detection.py    # EAR blink counter
        │       ├── head_movement.py      # PnP head pose (solvePnP)
        │       └── depth_estimation.py   # Depth liveness
        ├── camera/stream.py        # Camera capture thread
        ├── database/local_db.py    # SQLite local cache
        └── sync/
            ├── queue_sync.py       # Background sync daemon
            └── heartbeat.py        # Cloud heartbeat reporter
```

---

## 6. API Reference

### Authentication

| Method | Endpoint | Auth | Mô tả |
|---|---|---|---|
| POST | `/api/auth/register` | Public | Tạo admin mới |
| POST | `/api/auth/login` | Public | Đăng nhập, nhận JWT |
| POST | `/api/auth/refresh` | Public | Refresh access token |

**Login Request:**
```json
POST /api/auth/login
{
  "email": "admin@school.com",
  "password": "Admin@123"
}
```

**Login Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### Students

| Method | Endpoint | Auth | Mô tả |
|---|---|---|---|
| GET | `/api/students/` | JWT | Danh sách sinh viên |
| POST | `/api/students/` | JWT | Tạo sinh viên mới |
| GET | `/api/students/{id}` | JWT | Thông tin sinh viên |
| PUT | `/api/students/{id}` | JWT | Cập nhật sinh viên |
| DELETE | `/api/students/{id}` | JWT | Xóa sinh viên |

Headers: `Authorization: Bearer <access_token>`

---

### Classes

| Method | Endpoint | Auth | Mô tả |
|---|---|---|---|
| GET | `/api/classes/` | JWT | Danh sách lớp |
| POST | `/api/classes/` | JWT | Tạo lớp |
| GET | `/api/classes/{id}` | JWT | Thông tin lớp |
| PUT | `/api/classes/{id}` | JWT | Cập nhật lớp |
| DELETE | `/api/classes/{id}` | JWT | Xóa lớp |

---

### Attendance

| Method | Endpoint | Auth | Mô tả |
|---|---|---|---|
| POST | `/api/attendance/` | Device Token | Edge device ghi điểm danh |
| POST | `/api/attendance/bulk-sync` | Device Token | Sync offline queue từ edge |
| GET | `/api/attendance/class/{class_id}` | JWT | Lịch sử điểm danh của lớp |

**Device Token header:** `X-Device-Token: <device_token>`

---

### Devices

| Method | Endpoint | Auth | Mô tả |
|---|---|---|---|
| POST | `/api/devices/register` | JWT | Đăng ký thiết bị mới |
| POST | `/api/devices/heartbeat` | Device Token | Cập nhật trạng thái thiết bị |
| GET | `/api/devices/` | JWT | Danh sách thiết bị |
| GET | `/api/devices/embeddings/{class_id}` | Device Token | Lấy embeddings (AES encrypted) cho edge |

---

### Enrollment (Face Registration)

| Method | Endpoint | Auth | Mô tả |
|---|---|---|---|
| POST | `/api/enrollment/capture-frame` | JWT | Gửi 1 frame JPEG base64 → trích xuất embedding |
| POST | `/api/enrollment/finalize` | JWT | Tổng hợp embeddings → lưu DB |
| POST | `/api/enrollment/upload-embedding` | JWT | Upload trực tiếp embedding base64 |
| POST | `/api/enrollment/identify` | JWT | Nhận diện khuôn mặt trong ảnh |

**Capture Frame:**
```json
POST /api/enrollment/capture-frame
{
  "student_id": 1,
  "frame_b64": "<base64 JPEG, không có data:image prefix>",
  "step_index": 0
}
```

**Response:**
```json
{
  "accepted": true,
  "quality": 0.8723,
  "buffered": 3
}
```

**Finalize:**
```json
POST /api/enrollment/finalize
{ "student_id": 1 }
```

> Cần ít nhất **5 frames hợp lệ** trước khi finalize. Embedding được lưu mã hóa AES-256-GCM.

---

### WebSocket

```
WS /ws/attendance/{class_id}
```

Real-time attendance updates cho dashboard. Gửi JSON mỗi khi có điểm danh mới trong lớp.

---

## 7. Dữ liệu mặc định & Tài khoản test

> Đây là dữ liệu đã được seed trong môi trường development. **KHÔNG dùng trong production.**

### Tài khoản Admin

| Email | Password | Ghi chú |
|---|---|---|
| `admin@school.com` | `Admin@123` | Tài khoản chính để test |
| `admin@school.edu.vn` | *(xem DB)* | Tài khoản phụ |

### Thông tin Database

```
Host: localhost:5432
Database: attendance_db
User: doanbac07
Password: 070301
```

Kết nối trực tiếp:
```bash
docker exec -it smart-attendance-aiot-postgres-1 psql -U doanbac07 -d attendance_db
```

### Device Token (Test)

```
b7da9fc490c04c20bcd0d4c8165a1ae4
```

Dùng trong header: `X-Device-Token: b7da9fc490c04c20bcd0d4c8165a1ae4`

### Dữ liệu test có sẵn

- **4 Sinh viên**: SV001, SV002, SV003, SV004 (tất cả thuộc lớp CS101)
- **2 Lớp học**: ID=1 (không có sinh viên), ID=2 (CS101 - Lập trình Python)
- **1 Thiết bị**: Token `b7da9fc490c04c20bcd0d4c8165a1ae4`, gắn với lớp CS101
- **Face embeddings**: Tất cả 4 sinh viên đã có embedding (mã hóa AES-256-GCM)
- **1 bản ghi điểm danh**: SV001 đã được điểm danh trong lớp CS101

---

## 8. Pipeline AI nhận diện khuôn mặt

### 8.1 Server-side (InsightFace buffalo_sc)

```
Frame JPEG
    │
    ▼
RetinaFace Detection (bounding box + 5 landmarks)
    │
    ▼
Face Alignment (112×112 affine transform)
    │
    ▼
ArcFace R100 Embedding (512-dim float32 vector)
    │
    ▼
Quality check (blur, brightness, face size)
    │
    ▼
Cosine Similarity vs stored embeddings
    │
    ▼
Threshold: 0.65 → MATCH / NO MATCH
```

**Model**: `buffalo_sc` (nhẹ, phù hợp CPU server)
- Detection: RetinaFace (ResNet-50 backbone)
- Recognition: ArcFace (ResNet-100 backbone)

### 8.2 Edge-side (ONNX Runtime)

```
Camera Frame
    │
    ▼
[Step 1] YOLOv8-Face (yolov8_face_320.onnx) — Detect face bbox
    │
    ▼
[Step 2] 5-Point Landmark Alignment
    │
    ▼
[Step 3] Image Enhancement (CLAHE, denoise)
    │
    ▼
[Step 4] Liveness Check (3-layer)
    │  ├── EAR Blink Detection (dlib landmarks)
    │  ├── Head Pose PnP (solvePnP với 3D model points)
    │  └── Depth Estimation (depth_estimator.onnx)
    │
    ▼
[Step 5] ArcFace R100 Embedding (arcface_r100.onnx)
    │
    ▼
[Step 6] Cosine Similarity vs local cache (SQLite)
    │
    ▼
[Step 7] POST /api/attendance/ hoặc enqueue offline
```

### 8.3 Multi-frame Enrollment (Browser Webcam)

Quy trình đăng ký khuôn mặt qua web:

1. Admin mở trang Student Detail → "Đăng ký khuôn mặt"
2. Frontend chụp ảnh từ webcam, gửi **từng frame** lên `/api/enrollment/capture-frame`
3. Server detect face → extract embedding → buffer vào `_enrollment_sessions[student_id]`
4. Sau khi đủ ≥5 frames accepted, frontend gọi `/api/enrollment/finalize`
5. Server tính **weighted average → re-normalize** → AES-256-GCM encrypt → lưu `students.face_embedding`

---

## 9. Edge Device

### 9.1 Cấu hình

Tạo file `edge/config/device.env`:

```env
DEVICE_TOKEN=b7da9fc490c04c20bcd0d4c8165a1ae4
CLASS_ID=2
CLOUD_API_URL=http://<your-server-ip>:8000
SYNC_INTERVAL_SEC=30

CAMERA_SOURCE=0
FRAME_WIDTH=1280
FRAME_HEIGHT=720
CAPTURE_FPS=10
PROCESS_EVERY_N_FRAMES=3

DETECTION_MODEL=/app/models/yolov8_face_320.onnx
EMBEDDING_MODEL=/app/models/arcface_r100.onnx
DEPTH_MODEL=/app/models/depth_estimator.onnx

COSINE_THRESHOLD=0.65
LIVENESS_BLINK_THRESHOLD=0.25

AES_KEY=0000000000000000000000000000000000000000000000000000000000000000
LOCAL_DB_PATH=/app/data/local.db
ORT_NUM_THREADS=4
```

> ⚠️ `AES_KEY` phải giống hệt key trong `backend/.env` để decrypt embeddings đúng.

### 9.2 Chạy Edge bằng Docker

```bash
cd edge
docker-compose up -d --build
```

### 9.3 Models cần thiết

Đặt vào `edge/models/`:
- `yolov8_face_320.onnx` — YOLOv8 face detection (320×320)
- `arcface_r100.onnx` — ArcFace ResNet-100 embedding
- `depth_estimator.onnx` — Depth liveness estimation

### 9.4 Offline Resilience

Khi cloud không khả dụng:
- Edge lưu record vào SQLite queue (`edge/data/local.db`)
- `SyncDaemon` background thread chạy mỗi `SYNC_INTERVAL_SEC` giây
- Gọi `POST /api/attendance/bulk-sync` khi có mạng
- Cooldown 10 giây giữa các lần nhận diện cùng một sinh viên

---

## 10. Bảo mật

### AES-256-GCM Encryption

Face embedding **KHÔNG BAO GIỜ** lưu dạng plaintext. Mọi embedding đều được:

```python
# Encrypt (backend/core/encryption.py)
key = bytes.fromhex(AES_KEY)  # 32 bytes
cipher = AESGCM(key)
nonce = os.urandom(12)         # 12 bytes random
ciphertext = cipher.encrypt(nonce, plaintext, None)
stored = nonce + ciphertext    # 12 + len(plaintext) bytes
```

### JWT

- **Access Token**: Hết hạn sau 15 phút
- **Refresh Token**: Hết hạn sau 7 ngày
- Thuật toán: HS256
- Claim: `sub` = admin email, `exp` = expiry

### Device Authentication

Edge device dùng `X-Device-Token` header (UUID v4). Token được hash và lưu trong DB. Mỗi token chỉ gắn với một device cụ thể.

### Rate Limiting

- 100 requests/phút per IP (Redis-backed)
- Áp dụng cho tất cả `/api/*` endpoints

---

## 11. Các lỗi đã gặp & cách xử lý

### 🐛 Bug 1: `ImportError: cannot import 'Base' from app.models`

**Nguyên nhân**: `app/models/__init__.py` rỗng. `Base` được định nghĩa trong `app/database/session.py`, không phải `app/models/`.

**Fix**: `main.py` phải import:
```python
# ❌ Sai
from app.models import Base

# ✅ Đúng
from app.database.session import engine, Base
```

---

### 🐛 Bug 2: `ImportError: store_embedding, identify_face`

**Nguyên nhân**: `enrollment.py` import `store_embedding` và `identify_face` như module-level functions, nhưng chúng là **class methods** của `FaceService`.

**Fix**: Thêm module-level proxy functions vào cuối `face_service.py`:
```python
# Module-level proxies (để import trực tiếp)
async def store_embedding(db, student_id, emb_b64):
    return await face_service.store_embedding(db, student_id, emb_b64)

async def identify_face(db, emb_b64, threshold=None):
    return await face_service.identify_face(db, emb_b64, threshold)
```

---

### 🐛 Bug 3: Timezone datetime error trong device heartbeat

**Nguyên nhân**: `datetime.now(timezone.utc)` tạo timezone-aware datetime, nhưng SQLAlchemy `DateTime` column (không có `timezone=True`) là naive.

**Fix** trong `device_service.py`:
```python
# ❌ Sai - timezone-aware
from datetime import datetime, timezone
device.last_heartbeat = datetime.now(timezone.utc)

# ✅ Đúng - naive UTC
from datetime import datetime
device.last_heartbeat = datetime.utcnow()
```

---

### 🐛 Bug 4: `MissingGreenlet` error khi update student

**Nguyên nhân**: SQLAlchemy async không hỗ trợ lazy loading attribute access sau khi flush trong greenlet context. `setattr` rồi `flush` rồi `refresh` gây conflict.

**Fix** trong `students.py`: Dùng `UPDATE` statement trực tiếp rồi re-query:
```python
await db.execute(
    update(Student).where(Student.id == student_id).values(**update_data)
)
await db.commit()
# Re-query để trả về object mới
result = await db.execute(select(Student).where(Student.id == student_id))
return result.scalar_one()
```

---

### 🐛 Bug 5: Pydantic v2 — `"Config" and "model_config" cannot be used together`

**Nguyên nhân**: Pydantic v2 không cho phép dùng cả `model_config = ConfigDict(...)` và `class Config: ...` trong cùng một model.

**Fix** trong `schemas/device.py`: Chỉ dùng `model_config`:
```python
from pydantic import ConfigDict

class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    # Bỏ class Config: ...
```

---

### 🐛 Bug 6: `DeviceResponse` field mismatch

**Nguyên nhân**: Schema có fields `name`, `token`, `is_active` nhưng ORM model thực tế có `device_name`, `device_token` (không có `is_active`).

**Fix**: Đồng bộ schema với model:
```python
class DeviceResponse(BaseModel):
    id: int
    device_name: str
    device_token: str
    ip_address: Optional[str]
    location: Optional[str]
    class_id: Optional[int]
    status: str
    last_heartbeat: Optional[datetime]
```

---

### 🐛 Bug 7: Frontend build fail — duplicate login paths

**Nguyên nhân**: Tồn tại cả `src/app/(auth)/login/page.tsx` VÀ `src/app/login/page.tsx`. Next.js App Router resolve cả hai về cùng route `/login` → conflict.

**Fix**: Xóa `src/app/login/page.tsx`, chỉ giữ `src/app/(auth)/login/page.tsx`.

---

### 🐛 Bug 8: Frontend login dùng `username` thay vì `email`

**Nguyên nhân**: Login form ban đầu gửi `{"username": "...", "password": "..."}` nhưng backend `LoginRequest` schema yêu cầu `email`.

**Fix** trong `(auth)/login/page.tsx`:
```tsx
body: JSON.stringify({ email, password }), // ← email, không phải username
```

---

### 🐛 Bug 9: Frontend vẫn gọi `/api/v1/` sau khi đổi prefix

**Nguyên nhân**: Next.js Docker build cache giữ bundle cũ. Phải rebuild hoàn toàn.

**Fix**:
```bash
docker-compose down
docker-compose up -d --build
```

---

### 🐛 Bug 10: Duplicate `GET /` route trong `students.py`

**Nguyên nhân**: Có 2 `@router.get("/")` trong cùng file. FastAPI dùng cái đầu tiên, cái sau bị shadow.

**Fix**: Xóa route thứ hai (duplicate).

---

## 12. Lưu ý quan trọng

### ⚠️ AES Key phải nhất quán

Key mã hóa embedding **phải giống nhau** trên Backend và Edge Device. Nếu khác nhau:
- Edge không decrypt được embedding từ Cloud
- Server không verify được embedding từ Edge
- Toàn bộ face recognition sẽ fail silently

### ⚠️ InsightFace model tự download lần đầu

InsightFace tự download model `buffalo_sc` vào `/app/models` (Docker volume `insightface_models`) khi khởi động lần đầu. Cần Internet và mất khoảng 2-3 phút.

### ⚠️ `_enrollment_sessions` là in-memory

Session buffer của enrollment flow lưu trong RAM (`_enrollment_sessions` dict). Nếu backend restart trong lúc đang enrollment, session bị mất. Sinh viên cần bắt đầu lại từ đầu.

**TODO**: Migrate sang Redis để persist enrollment sessions.

### ⚠️ JWT Secret key

`settings.SECRET_KEY` và `settings.JWT_SECRET_KEY` mặc định dùng `secrets.token_urlsafe(32)` — **random mỗi lần restart**. Nghĩa là mọi token đều invalid sau khi restart backend!

**Fix cho production**: Set cố định trong `backend/.env`:
```env
JWT_SECRET_KEY=your-fixed-256-bit-secret-key
```

### ⚠️ CORS đang để `allow_origins=["*"]`

Chỉ phù hợp development. Production phải restrict:
```python
allow_origins=["https://yourdomain.com"]
```

### ⚠️ Enrollment cần ≥5 frames

Nếu gửi ít hơn 5 frames chất lượng tốt trước khi finalize, server trả lỗi 422. Đảm bảo:
- Ánh sáng đủ
- Khuôn mặt không bị che
- Không bị blur (threshold: 60.0 Laplacian variance)

---

## 13. Hướng phát triển tiếp theo

### 🚀 Ngắn hạn (1-2 tuần)

- [x] **Migrate enrollment sessions sang Redis** — ✅ DONE (session 2026-03-01)
- [x] **Fix JWT secret** — ✅ DONE (session 2026-03-01)
- [ ] **Test WebSocket** — xác nhận real-time update dashboard
- [ ] **Test bulk-sync** — simulate offline scenario
- [x] **Frontend pages** — ✅ DONE — toàn bộ UI đã dịch sang tiếng Anh
- [ ] **Face enrollment UI** — hoàn thiện flow webcam capture trên browser (endpoint ready, cần test end-to-end)
- [ ] **Liveness UI** — hiển thị hướng dẫn (nháy mắt, quay đầu) cho người dùng

### 🏗️ Trung hạn (1-2 tháng)

- [ ] **AWS Deployment**
  - EC2 (t3.medium) cho Backend + Frontend
  - RDS PostgreSQL (db.t3.micro)
  - ElastiCache Redis
  - ECR + ECS hoặc EKS
  - CloudFront CDN cho Frontend
  - Application Load Balancer + HTTPS (ACM)

- [ ] **Edge Firmware thực tế**
  - Test trên Raspberry Pi 4
  - Camera stream với CSI Camera Module
  - Watchdog để auto-restart
  - OTA firmware update qua Cloud

- [ ] **ESP32 Integration** (optional)
  - ESP32-CAM capture frame → gửi lên Pi qua UART/WiFi
  - LED indicator (xanh: present, đỏ: not recognized)
  - LCD hiển thị tên sinh viên sau khi nhận diện

- [ ] **Alembic Migrations**
  - Thay `create_all` bằng Alembic cho production DB migrations
  - Version control schema changes

### 🎯 Dài hạn

- [ ] **Mobile App** (React Native)
  - Admin app: xem báo cáo real-time
  - Sinh viên app: xem lịch sử điểm danh cá nhân
  - Push notification khi vắng mặt

- [ ] **Advanced Analytics**
  - Báo cáo tỷ lệ chuyên cần theo tuần/tháng/kỳ
  - Phát hiện pattern bất thường
  - Export Excel/PDF

- [ ] **Multi-camera Support**
  - Nhiều camera/thiết bị trong cùng 1 phòng
  - Camera RTSP stream từ IP Camera

- [ ] **Model Upgrade**
  - Switch từ `buffalo_sc` → `buffalo_l` (accuracy cao hơn, cần GPU)
  - Fine-tune ArcFace trên dataset sinh viên Việt Nam
  - Upgrade liveness: FAS (Face Anti-Spoofing) model chuyên dụng

- [ ] **Privacy & Compliance**
  - Xin phép sinh viên trước khi thu thập biometric
  - Định kỳ xóa embedding cũ
  - Audit log cho mọi truy cập embedding

---

## 📊 Trạng thái hiện tại (Development)

| Component | Status | Ghi chú |
|---|---|---|
| Backend API | ✅ Hoạt động | Tất cả endpoints tested |
| PostgreSQL | ✅ Hoạt động | Có test data |
| Redis | ✅ Hoạt động | Rate limiting active |
| Frontend | ✅ Build thành công | Login, Students pages verified |
| InsightFace | ✅ Load được | buffalo_sc model |
| Face Enrollment (browser) | ⚠️ Endpoint ready | UI chưa fully tested |
| WebSocket | ⚠️ Code ready | Chưa test end-to-end |
| Edge Device | ⚠️ Code ready | Cần hardware để test |
| AES Encryption | ✅ Hoạt động | AES-256-GCM |
| JWT Auth | ✅ Hoạt động | Email-based |
| Device Heartbeat | ✅ Hoạt động | Tested |
| Bulk Sync | ⚠️ Code ready | Chưa test offline scenario |
| Alembic Migrations | ❌ Chưa | Dùng `create_all` tạm |

---

## 🔧 Các lệnh hữu ích

```bash
# Xem logs backend real-time
docker-compose logs -f backend

# Vào container backend (debug)
docker exec -it smart-attendance-aiot-backend-1 bash

# Chạy query DB trực tiếp
docker exec -it smart-attendance-aiot-postgres-1 psql -U doanbac07 -d attendance_db

# Xem tất cả sinh viên
# (trong psql): SELECT id, student_code, full_name, class_id FROM students;

# Xem tất cả thiết bị
# (trong psql): SELECT id, device_name, device_token, status FROM devices;

# Flush Redis cache
docker exec -it smart-attendance-aiot-redis-1 redis-cli FLUSHALL

# Test health endpoint
curl http://localhost:8000/health

# Test login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@school.com","password":"Admin@123"}'

# Swagger UI
# Mở http://localhost:8000/docs
```

---

## 📚 Tài liệu tham khảo

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [InsightFace GitHub](https://github.com/deepinsight/insightface)
- [SQLAlchemy Async ORM](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Next.js App Router](https://nextjs.org/docs/app)
- [Pydantic v2 Migration](https://docs.pydantic.dev/latest/migration/)
- [Paper_v2.md](./Paper_v2.md) — Tài liệu nghiên cứu & thiết kế hệ thống chi tiết

---

## 📋 Nhật ký phát triển (Session Log)

### Session 2026-03-01

**Công việc đã hoàn thành:**

#### 1. ✅ Dịch toàn bộ Frontend UI sang tiếng Anh

Tất cả các màn hình trong `frontend/src/app/` đã được dịch từ tiếng Việt sang tiếng Anh:

| File | Nội dung thay đổi |
|---|---|
| `(auth)/login/page.tsx` | "Đăng nhập" → "Sign In", labels, error messages |
| `dashboard/layout.tsx` | Nav labels: Overview, Students, Classes, Attendance, Devices, Reports; "Đăng xuất" → "Log Out" |
| `components/layout/navbar.tsx` | "Đăng xuất" → "Log Out" |
| `dashboard/page.tsx` | "Tổng quan hệ thống" → "System Overview", stat card labels |
| `students/page.tsx` | Title, table headers, status badges, empty state |
| `students/[id]/page.tsx` | Back, info labels, status values, face registration warning |
| `students/enroll/page.tsx` | POSE_STEPS, camera error, success screen, all UI text |
| `classes/page.tsx` | Title, form labels, buttons, status badges |
| `attendance/page.tsx` | Title, WS status, table headers, "Có mặt/Vắng" → "Present/Absent" |
| `devices/page.tsx` | Title, form labels, card body, empty state |
| `reports/page.tsx` | Title, stat cards, table headers, CSV headers, date locale → `en-US` |

> `components/layout/sidebar.tsx` — KHÔNG dịch vì là file legacy không được import ở đâu. Nav thật nằm trong `dashboard/layout.tsx`.

#### 2. ✅ Fix JWT Secret Key — Dual Key Rotation

**Vấn đề**: `config.py` dùng `secrets.token_urlsafe(32)` làm giá trị default → mỗi lần restart backend sinh key mới → toàn bộ token bị invalid, user bị logout.

**Fix đã thực hiện:**

- `backend/.env` đã có `JWT_SECRET_KEY` cố định (hex string 64 ký tự)
- `backend/app/config.py`: thêm field `JWT_SECRET_KEY_OLD: Optional[str] = None`
- `backend/app/core/jwt_handler.py`: `decode_token()` thử verify bằng key mới trước, nếu fail thì thử key cũ — **zero-downtime key rotation**

```python
# jwt_handler.py — decode_token() mới
keys_to_try = [settings.JWT_SECRET_KEY]
if settings.JWT_SECRET_KEY_OLD:
    keys_to_try.append(settings.JWT_SECRET_KEY_OLD)

for key in keys_to_try:
    try:
        return jwt.decode(token, key, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        continue
raise ValueError("Invalid token")
```

**Cách dùng khi cần rotation trong tương lai:**
```env
# backend/.env
JWT_SECRET_KEY=<key_mới>
JWT_SECRET_KEY_OLD=<key_cũ>   # uncomment trong thời gian transition (≥7 ngày)
```

#### 3. ✅ Migrate Enrollment Sessions từ In-Memory → Redis

**Vấn đề**: `enrollment.py` dùng `_enrollment_sessions: dict = {}` → mất sạch khi backend restart giữa chừng enrollment.

**Fix đã thực hiện:**

**File mới** `backend/app/core/redis_client.py`:
- Singleton async Redis client (`redis.asyncio`)
- `get_redis()` / `close_redis()` cho lifecycle management

**`backend/app/main.py`**:
- Warm-up Redis khi startup, close gracefully khi shutdown

**`backend/app/api/routes/enrollment.py`** — rewrite hoàn toàn:
- Bỏ `_enrollment_sessions: dict`
- Redis key: `enrollment:{student_id}` → JSON list of base64-encoded embeddings
- **TTL 30 phút** — auto-expire nếu admin bỏ giữa chừng
- Restart backend → session vẫn còn trong Redis ✅

```
TRƯỚC (in-memory):          SAU (Redis):
restart → mất sạch         restart → vẫn còn
multi-instance → fail      multi-instance → share được
không TTL → leak memory    TTL 30 phút → tự dọn
```

#### 4. ✅ Rebuild Docker

```bash
docker-compose up -d --build backend frontend
```
Backend và Frontend đã được rebuild sau tất cả thay đổi trên.

---

### Session 2026-03-02

**Công việc đã hoàn thành:**

#### 1. ✅ IP Webcam support cho Face Enrollment

Thêm chế độ **IP Webcam** vào `frontend/src/app/students/enroll/page.tsx`:
- Toggle giữa **Local Webcam** và **IP Webcam** (phone camera qua WiFi)
- Kết nối test bằng `shot.jpg` snapshot thay vì `<video>` (tránh HTTPS self-signed cert issue)
- Preview stream MJPEG qua `<img ref={imgRef}>` — browser render tốt hơn `<video>` với MJPEG
- Capture frame: fetch `/shot.jpg?t=...` → `createImageBitmap()` → canvas → base64
- Loading state "Connecting..." khi test kết nối

#### 2. ✅ Fix JWT key random → cố định

`config.py` dùng `secrets.token_urlsafe(32)` làm default → **key mới mỗi lần restart** → tất cả token invalid. Đã đổi thành key cố định.

#### 3. ✅ Fix `security.py` và `dependencies.py` — dùng `decode_token()` dual-key

Cả 2 file trước dùng `jwt.decode()` trực tiếp, bỏ qua dual-key logic trong `jwt_handler.py`. Đã sửa cả 2 dùng `decode_token()`.

#### 4. ✅ Fix WebSocket broadcast attendance

`attendance_service.py` save record nhưng không gọi `broadcast_attendance()`. Đã thêm broadcast sau mỗi `create_attendance()` — dashboard nhận event real-time.

#### 5. ✅ Fix WebSocket 403 — thiếu prefix `/ws`

Backend mount WS router không có prefix → route là `/attendance/2`, nhưng frontend kết nối `/ws/attendance/2`. Đã thêm `prefix="/ws"` vào `main.py`.

#### 6. ✅ Fix `disconnect()` bug trong WebSocket manager

`list.discard()` không tồn tại → lỗi khi client disconnect. Đã sửa thành `list.remove()` với try/except.

#### 7. ✅ Fix password hash admin

Admin password hash trong DB được tạo theo format cũ (không qua SHA256 prehash). Đã reset bằng script `reset_admin_password.py`.

#### 8. ✅ Test end-to-end đầy đủ

| Test | Kết quả |
|---|---|
| Login `admin@school.edu.vn / admin123` | ✅ 200 OK |
| Face Enrollment qua IP Webcam | ✅ Thành công |
| POST `/api/attendance/` với device token | ✅ 201 Created |
| GET `/api/attendance/class/2` với Bearer token | ✅ 200 OK |
| WebSocket `/ws/attendance/2` connect | ✅ Accepted |
| WebSocket broadcast sau attendance POST | ✅ Nhận được event real-time |

---

### Session 2026-03-02 (phần 2)

**Công việc đã hoàn thành:**

#### 1. ✅ Tạo AI Face Inference Microservice (`ai-service/`, port 9000)

**Vấn đề cũ**: InsightFace (~1GB model, CPU-heavy) chạy thẳng trong backend process → backend nặng, không thể scale AI riêng, khó test.

**Giải pháp**: Tách InsightFace sang microservice riêng:

```
TRƯỚC:                          SAU:
Backend (port 8000)             Backend (port 8000)
  └─ InsightFace (1GB)    →       └─ httpx → AI Service (port 9000)
  └─ Auth/DB/API                  └─ Auth/DB/API/AES
                                AI Service (port 9000)
                                  └─ InsightFace (1GB)
                                  └─ ArcFace extract
                                  └─ Cosine similarity
```

**Files tạo mới:**

| File | Mô tả |
|---|---|
| `ai-service/Dockerfile` | Python 3.11-slim + build-essential + curl + libGL |
| `ai-service/requirements.txt` | insightface, onnxruntime, opencv, httpx |
| `ai-service/app/main.py` | FastAPI + non-blocking model warm-up |
| `ai-service/app/config.py` | MODEL_NAME, SERVICE_SECRET_KEY, thresholds |
| `ai-service/app/core/face_model.py` | InsightFace wrapper: extract_embedding(), batch_identify() |
| `ai-service/app/api/routes/inference.py` | POST /api/v1/extract, POST /api/v1/identify |
| `backend/app/services/ai_client.py` | httpx async client gọi ai-service |

**API ai-service:**

```
POST /api/v1/extract          Header: X-Service-Key
  Body: { image_b64, min_blur }
  Resp: { embedding_b64, quality, meta }

POST /api/v1/identify         Header: X-Service-Key
  Body: { probe_b64, gallery: [{student_id, embedding_b64}], threshold }
  Resp: { matched, student_id, confidence, top_matches }

GET  /health
  Resp: { status, model_loaded, uptime_seconds }
```

**Backend refactored:**
- `face_service.py`: remove InsightFace, `extract_embedding()` → async, gọi `ai_client`
- `identify_face()`: AES decrypt local → gửi plain embeddings sang ai-service
- **AES key KHÔNG rời khỏi backend** — ai-service chỉ làm toán cosine
- Local fallback cosine similarity khi ai-service down

**docker-compose.yml**: thêm `ai-service` service, `backend` depends_on `ai-service (healthy)`

#### 2. ✅ Fix non-blocking model warm-up

InsightFace load trong background thread → uvicorn start ngay → healthcheck pass ngay.

#### 3. ✅ Test end-to-end

| Test | Kết quả |
|---|---|
| `GET http://localhost:9000/health` | ✅ model_loaded: true |
| `GET http://localhost:8000/health` | ✅ healthy |
| Login via backend | ✅ JWT token OK |
| Backend → ai-service (internal Docker network) | ✅ Connected |

---

### Session 2026-03-02 (phần 3) — Fix Pose Validation & Head Pose Estimation

**Vấn đề được báo cáo:** Sau khi fix JWT 401, enrollment vẫn thất bại với lỗi:
> "Pose 'Look straight at the camera': could not capture 5 valid frames after 60 attempts"

---

#### 1. 🔍 Root Cause Analysis — pitch ≈ ±178° (solvePnP back-of-head bug)

**Log bằng chứng từ backend:**
```
[enrollment] step=0 pose-rejected — yaw=-33.19 pitch=176.36 — Please look straight
[enrollment] step=0 pose-rejected — yaw=-1.14 pitch=-178.39 — Please look straight
[enrollment] step=0 pose-rejected — yaw=-34.05 pitch=173.57 — Please look straight
(lặp lại 60 lần)
```

**Root cause:** `cv2.solvePnP` với `SOLVEPNP_EPNP` sinh ra **"back-of-head" solution** — rotation matrix `rmat` ngược chiều 180° so với thực tế. Hệ quả: `cv2.decomposeProjectionMatrix` trả pitch ≈ ±175° thay vì ~0°. Mặt người nhìn thẳng nhưng hệ thống tính như đang "xoay đầu 180°".

**Các fix đã thử và thất bại:**
1. ❌ **RQDecomp3x3 + tvec[2] flip check** — vẫn cho pitch ≈ ±175° vì rmat đã sai trước khi decompose
2. ❌ **Đổi 3D model points (camera-centric → subject-centric)** — vẫn không giải quyết được ambiguity của EPnP với 5 điểm
3. ❌ **Dùng `cv2.decomposeProjectionMatrix`** — kết quả tương đương, cùng bị flip

**Kết luận:** Vấn đề căn bản với solvePnP: với chỉ 5 điểm frontal face, EPnP không thể tự phân biệt front/back solution một cách ổn định. Bất kỳ approach nào dựa trên solvePnP với 5 keypoints đều tiềm ẩn lỗi 180° flip.

---

#### 2. ✅ Fix cuối cùng — Geometric Landmark Method (bỏ hoàn toàn solvePnP)

**Giải pháp:** Thay toàn bộ solvePnP bằng phương pháp hình học đơn giản, tính trực tiếp yaw/pitch từ tỷ lệ vị trí landmark trong ảnh. Không có 180° ambiguity, không cần intrinsic matrix.

**File thay đổi:** `ai-service/app/core/face_model.py`

```python
def _estimate_pose_geometric(kps, img_w, img_h):
    """
    InsightFace 5-pt keypoints: [left_eye, right_eye, nose_tip, left_mouth, right_mouth]
    'left/right' = từ góc nhìn SUBJECT (không phải camera).
    """
    left_eye, right_eye, nose, left_mouth, right_mouth = kps[:5]

    # ── Yaw ──────────────────────────────────────────────────────────────────
    # eye midpoint horizontal vs nose horizontal
    eye_mid_x = (left_eye[0] + right_eye[0]) / 2.0
    eye_dist  = abs(left_eye[0] - right_eye[0]) + 1e-6  # interocular distance
    # offset nose từ đường giữa mắt, normalize
    yaw_raw = (eye_mid_x - nose[0]) / eye_dist
    yaw_deg = np.clip(yaw_raw * 90.0, -90.0, 90.0)      # 0.5 offset ≈ 45°

    # ── Pitch ────────────────────────────────────────────────────────────────
    eye_mid_y   = (left_eye[1] + right_eye[1]) / 2.0
    mouth_mid_y = (left_mouth[1] + right_mouth[1]) / 2.0
    face_height = abs(mouth_mid_y - eye_mid_y) + 1e-6
    t_raw = (nose[1] - eye_mid_y) / face_height  # neutral ≈ 0.5
    pitch_deg = np.clip((t_raw - 0.5) * 120.0, -90.0, 90.0)

    return round(yaw_deg, 2), round(pitch_deg, 2), None
```

**Convention kết quả (neutral face nhìn thẳng):**
- yaw ≈ 0°, pitch ≈ 0° ✅ (không còn ±175°)
- yaw > 0 → nose dịch trái ảnh → subject quay phải
- yaw < 0 → nose dịch phải ảnh → subject quay trái
- pitch > 0 → cúi xuống; pitch < 0 → ngẩng lên

**Lưu ý:** Hàm `_estimate_pose_solvepnp()` vẫn giữ tên nhưng chỉ gọi `_estimate_pose_geometric()` (backward compat).

---

#### 3. ✅ Cập nhật POSE_STEP_CONFIG phù hợp với geometric method

**File:** `backend/app/api/routes/enrollment.py`

| Step | Instruction | yaw_range | pitch_range |
|------|-------------|-----------|-------------|
| 0 | Look straight | (-20, 20) | (-20, 20) |
| 1 | Turn LEFT (subject left = raw frame right → yaw < 0) | (-∞, -20) | (-40, 40) |
| 2 | Turn RIGHT (yaw > 0) | (20, +∞) | (-40, 40) |
| 3 | Tilt UP (chin raised → pitch < -20) | (-35, 35) | (-∞, -20) |
| 4 | Tilt DOWN (lower chin → pitch > 20) | (-35, 35) | (20, +∞) |
| 5 | Look straight again | (-20, 20) | (-20, 20) |

**Giải thích sign convention với mirror CSS (scaleX -1):**
- User thấy trên màn hình: quay trái (mirror) → trong raw frame: quay phải → nose dịch phải → `eye_mid_x - nose_x < 0` → **yaw < 0** ✅
- User thấy trên màn hình: quay phải (mirror) → trong raw frame: quay trái → nose dịch trái → **yaw > 0** ✅

---

#### 4. ✅ Các fix bổ sung từ đầu session

**Fix 401 Unauthorized (phát hiện đầu session):**
- **Root cause:** JWT token expire sau backend rebuild → frontend dùng token cũ → 60 requests đều 401 → báo lỗi "could not capture 5 valid frames" (lỗi mơ hồ, không nói rõ là 401)
- **Fix frontend** `enroll/page.tsx`: detect `res.status === 401` → throw ngay với message rõ ràng "Session expired. Please log out and log in again"
- **Log bằng chứng:** 60 dòng liên tiếp `"POST /api/enrollment/capture-frame HTTP/1.1" 401 Unauthorized`

**Các thay đổi debug tạm thời (cần restore):**
- `MIN_BLUR_ENROLLMENT = 0.0` (trong `enrollment.py`) — đặt về 0 để loại trừ blur là nguyên nhân. **Cần restore về 15-25 sau khi enrollment chạy ổn.**
- `logger.warning("[BLUR] ...")` trong `ai-service/face_model.py` — log blur mọi frame. Có thể giữ hoặc xóa tùy ý.
- Tất cả `logger.debug()` trong `enrollment.py` đã đổi sang `logger.warning()` để xuất hiện trong log (log level mặc định = WARNING=30, debug bị ignore)

---

#### 5. ✅ yaw/pitch debug display trên Frontend

**File:** `frontend/src/app/students/enroll/page.tsx`
- Video element: `style={{ transform: "scaleX(-1)" }}` — mirror để UX tự nhiên
- State `lastQuality` mở rộng: `{blur, det, yaw, pitch}`
- Debug line hiển thị: `blur: 42, det: 0.97, yaw: -5.3°, pitch: 2.1°`
- Dùng để verify thresholds POSE_STEP_CONFIG chính xác

---

#### 6. ✅ Rebuild & Deploy

```bash
docker-compose up -d --build ai-service backend
```

**Trạng thái sau rebuild:**
- `ai-service`: geometric pose method, blur logging
- `backend`: POSE_STEP_CONFIG mới, MIN_BLUR=0, logger.warning
- `frontend`: 401 detection, mirror video, yaw/pitch debug

**⏳ Chờ verify:** User cần thử enrollment và xem debug line để confirm yaw/pitch có hợp lý không (neutral ≈ 0°, 0°). Nếu thresholds cần điều chỉnh thêm → sửa POSE_STEP_CONFIG rồi `docker-compose up -d --build backend`.

---

## 📊 Trạng thái hiện tại (Cập nhật 2026-03-02 phần 3)

| Component | Status | Ghi chú |
|---|---|---|
| Backend API | ✅ Hoạt động | POSE_STEP_CONFIG geometric convention, MIN_BLUR=0 (temp) |
| **AI Face Service** | ✅ Hoạt động | Geometric pose method, không còn solvePnP |
| PostgreSQL | ✅ Hoạt động | Có test data |
| Redis | ✅ Hoạt động | Enrollment sessions (TTL 30 phút) |
| Frontend | ✅ Build thành công | Mirror video, 401 detection, yaw/pitch debug |
| JWT Auth | ✅ Fixed | Key cố định + dual-key decode |
| Face Enrollment | ⚠️ **Cần test lại** | Geometric pose fix deployed, chờ user verify |
| Face Identify | ✅ Refactored | AES decrypt local → ai-service /identify |
| WebSocket | ✅ Fixed | prefix /ws, broadcast attendance |
| Attendance REST | ✅ Tested | POST + GET hoạt động |
| Edge Device | ⚠️ Code ready | Cần hardware để test |
| Alembic Migrations | ❌ Chưa | Vẫn dùng `create_all` tạm |

---

## 🔜 Việc cần làm tiếp theo (theo thứ tự ưu tiên)

### Ưu tiên cao — Cần làm NGAY

1. **Test enrollment sau fix geometric pose** — Chạy enrollment, nhìn debug line:
   - Straight: `yaw ≈ 0°, pitch ≈ 0°` → phải pass step 0
   - Turn LEFT (physical): `yaw < -20°` → phải pass step 1
   - Turn RIGHT: `yaw > 20°` → phải pass step 2
   - Tilt UP: `pitch < -20°` → phải pass step 3
   - Tilt DOWN: `pitch > 20°` → phải pass step 4
   - Nếu thresholds sai: điều chỉnh `POSE_STEP_CONFIG` trong `enrollment.py` → `docker-compose up -d --build backend`

2. **Restore MIN_BLUR_ENROLLMENT** — Sau khi enrollment pass, đặt lại:
   ```python
   # backend/app/api/routes/enrollment.py
   MIN_BLUR_ENROLLMENT = 15.0  # Hoặc 20.0 — test với webcam thực tế
   ```
   Rebuild: `docker-compose up -d --build backend`

3. **Commit code sau khi enrollment hoạt động ổn định.**

### Ưu tiên trung bình

4. **Test WebSocket real-time** — Mở dashboard, dùng curl/Postman gọi `POST /api/attendance/` với device token → xác nhận dashboard cập nhật tức thì.

5. **Test Bulk-sync offline** — Stop backend → edge ghi vào SQLite queue → Start backend lại → xác nhận `POST /api/attendance/bulk-sync` sync thành công.

6. **Alembic Migrations** — Thay `create_all` bằng Alembic để quản lý DB schema version cho production.

7. **CORS restrict** — Đổi `allow_origins=["*"]` → restrict về domain cụ thể trong production.

8. **Rate Limiter → Redis** — `rate_limiter.py` hiện vẫn dùng in-memory dict. Nên migrate sang Redis (tương tự enrollment sessions) để share giữa multiple backend instances.

### Ưu tiên thấp / Dài hạn

9. **AWS Deployment** — EC2 + RDS + ElastiCache + ECR/ECS + CloudFront + ALB + HTTPS

10. **Alembic** — DB schema migrations thay create_all

11. **Mobile App** — React Native cho admin và sinh viên

10. **Advanced Analytics** — Báo cáo tỷ lệ chuyên cần, export Excel/PDF

---

## 🔧 Các lệnh hữu ích

```bash
# Xem logs backend real-time
docker-compose logs -f backend

# Vào container backend (debug)
docker exec -it smart-attendance-aiot-backend-1 bash

# Chạy query DB trực tiếp
docker exec -it smart-attendance-aiot-postgres-1 psql -U doanbac07 -d attendance_db

# Xem tất cả sinh viên
# (trong psql): SELECT id, student_code, full_name, class_id FROM students;

# Xem tất cả thiết bị
# (trong psql): SELECT id, device_name, device_token, status FROM devices;

# Flush Redis cache
docker exec -it smart-attendance-aiot-redis-1 redis-cli FLUSHALL

# Xem enrollment session trong Redis (debug)
docker exec -it smart-attendance-aiot-redis-1 redis-cli KEYS "enrollment:*"
docker exec -it smart-attendance-aiot-redis-1 redis-cli GET "enrollment:1"

# Test health endpoint
curl http://localhost:8000/health

# Test login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@school.com","password":"Admin@123"}'

# Swagger UI
# Mở http://localhost:8000/docs

# Rebuild sau thay đổi code
docker-compose up -d --build backend
docker-compose up -d --build frontend
docker-compose up -d --build backend frontend
```

---

## 📚 Tài liệu tham khảo

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [InsightFace GitHub](https://github.com/deepinsight/insightface)
- [SQLAlchemy Async ORM](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Next.js App Router](https://nextjs.org/docs/app)
- [Pydantic v2 Migration](https://docs.pydantic.dev/latest/migration/)
- [Paper_v2.md](./Paper_v2.md) — Tài liệu nghiên cứu & thiết kế hệ thống chi tiết

---

*Cập nhật lần cuối: 2026-03-02 (phần 3) — Fix head pose estimation: bỏ solvePnP (back-of-head 180° bug), thay bằng geometric landmark method. Fix 401 detection trên frontend. POSE_STEP_CONFIG cập nhật theo geometric convention. Chờ verify enrollment end-to-end.*