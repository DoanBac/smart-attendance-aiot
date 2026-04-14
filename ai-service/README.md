# Hướng dẫn AI Service, chống spoofing và huấn luyện CNN

Tài liệu này mô tả phần **deep learning / anti-spoof** của dự án theo đúng logic đang chạy trong codebase.

---

## 1. Vai trò của `ai-service`

`ai-service` là tầng AI chuyên trách cho nhận diện khuôn mặt và kiểm tra giả mạo:

- **ArcFace / InsightFace**: trích xuất embedding 512 chiều để trả lời câu hỏi **"đây là ai?"**
- **CNN anti-spoof / liveness**: ước lượng `liveness_score` để trả lời câu hỏi **"đây có phải người thật trước camera không?"**

> Điểm quan trọng: **ArcFace không có nhiệm vụ chống spoof**. Nếu chỉ dùng embedding, ảnh của chính người đó vẫn có thể match rất tốt. Vì vậy hệ thống phải thêm một lớp **anti-spoof CNN** và **pose challenge** để chặn ảnh tĩnh / màn hình / replay video.

---

## 2. Logic deep learning hiện tại hoạt động như thế nào?

### 2.1 Tách thành 2 bài toán độc lập

#### A. Nhận dạng danh tính (Identity Recognition)

- Input: ảnh khuôn mặt đã detect
- Model: `InsightFace` / `ArcFace`
- Output: vector embedding 512-dim đã L2-normalize
- Mục tiêu: so sánh cosine similarity với embeddings đã lưu trong DB

#### B. Chống giả mạo (Anti-Spoof / Liveness)

- Input: crop khuôn mặt từ camera
- Model: CNN ONNX (`custom_cnn` hoặc `anti-spoof-mn3`)
- Output:
  - `liveness_score`: xác suất / điểm tin cậy khuôn mặt là **người thật**
  - `is_live`: quyết định cuối cùng theo `ANTISPOOF_THRESHOLD`
- Mục tiêu: chặn
  - ảnh in
  - ảnh hiển thị trên điện thoại / laptop / tablet
  - replay video cơ bản

### 2.2 Vì sao trước đây ảnh vẫn qua được?

Về mặt machine learning, điều này là **bình thường** nếu chỉ nhìn vào identity:

- ảnh thật của bạn và ảnh chụp bạn đều có **đặc trưng khuôn mặt giống nhau**
- ArcFace thấy cả hai đều là “cùng một người”
- nếu không có liveness gate, backend vẫn coi frame đó là hợp lệ

Do đó pipeline đúng phải là:

```text
camera frame
  → face detection
  → ArcFace embedding
  → anti-spoof CNN
  → nếu is_live=True mới cho phép enroll / attendance
```

Trong repo hiện tại, việc chặn spoof được áp dụng ở:

- `backend/app/api/routes/enrollment.py` — chặn spoof khi đăng ký khuôn mặt
- `backend/app/services/attendance_service.py` — chặn spoof khi kiosk / điểm danh
- `ai-service/app/core/face_model.py` — tính `liveness_score` và `is_live`

---

## 3. Luồng runtime khi hệ thống chạy

### 3.1 Luồng đăng ký khuôn mặt (Enrollment)

```text
Webcam (6 góc × nhiều frame)
  → /api/enrollment/capture-frame
  → ai-service /api/v1/extract
  → blur check + face size check
  → ArcFace embedding
  → yaw / pitch estimation
  → anti-spoof CNN
  → nếu live: buffer frame
  → nếu spoof: reject ngay
  → /finalize → average embedding → AES encrypt → lưu DB
```

### 3.2 Luồng điểm danh / kiosk

```text
Camera frame
  → /api/attendance/verify-face
  → ai-service /api/v1/extract
  → ArcFace embedding + liveness_score
  → pose challenge trái / phải (active liveness)
  → cosine similarity với gallery
  → ghi attendance nếu vừa đúng người vừa là người thật
```

### 3.3 Các lớp bảo vệ hiện có

1. **Blur check**: ảnh quá mờ bị loại trước
2. **Face size check**: mặt quá nhỏ bị loại
3. **Pose check**: phải nhìn đúng góc (front / left / right / up / down)
4. **Passive anti-spoof CNN**: phát hiện texture, ánh sáng, độ phẳng, moiré của ảnh / màn hình
5. **Active liveness**: quay đầu theo hướng yêu cầu để giảm khả năng qua mặt bằng ảnh tĩnh

---

## 4. Thu thập dữ liệu `train / dev(val) / test`

### 4.1 Ý nghĩa của từng tập

| Tập | Mục đích |
|---|---|
| `train` | dùng để cập nhật trọng số model |
| `dev` / `val` | dùng để chọn epoch tốt nhất, tune augmentation, tune `ANTISPOOF_THRESHOLD` |
| `test` | giữ riêng hoàn toàn để đánh giá cuối cùng, không dùng để tinh chỉnh |

> Trong code hiện tại, script `train_cnn_antispoof.py` dùng trực tiếp `train/` và `val/`. Tập `test/` nên được giữ riêng để đánh giá ngoài (manual / script riêng) sau khi đã chốt model.

### 4.2 Quy tắc chia dữ liệu đúng

Đây là phần rất quan trọng để model “thật sự có tác dụng”, không bị ảo tưởng kết quả tốt:

1. **Không trộn frame từ cùng một video vào nhiều tập**
   - nếu video A đã vào `train` thì toàn bộ frame của video A phải ở `train`
2. **Ưu tiên tách theo session / device / attack medium**
   - ví dụ: replay trên iPhone ở `train`, replay trên laptop ở `test`
3. **Nếu có thể, tách theo người / buổi chụp**
   - giúp kiểm tra khả năng tổng quát hóa tốt hơn
4. **Giữ cân bằng live / spoof tương đối**
   - tránh model học lệch một lớp
5. **Có đủ hard negatives**
   - ảnh toàn màn hình
   - video replay trên điện thoại
   - ảnh in bóng / mờ / có phản sáng

### 4.3 Nên thu dữ liệu live như thế nào?

Đối với lớp **`live`**, nên thu ở nhiều điều kiện:

- nhiều người khác nhau
- nhiều góc mặt: thẳng, trái, phải, ngẩng, cúi
- nhiều ánh sáng: sáng phòng, tối phòng, ánh sáng lệch, ngược sáng nhẹ
- nhiều thiết bị: webcam laptop, camera điện thoại, webcam rời
- có / không đeo kính
- khoảng cách gần / vừa / xa

### 4.4 Nên thu dữ liệu spoof như thế nào?

Đối với lớp **`spoof`**, nên có ít nhất 3 nhóm:

1. **Ảnh tĩnh**
   - ảnh hiển thị trên điện thoại
   - ảnh hiển thị trên laptop / tablet
   - ảnh in trên giấy

2. **Replay video**
   - video quay người thật rồi phát lại trên điện thoại
   - video phát trên màn hình laptop / tablet

3. **Hard spoof cases**
   - thay đổi độ sáng màn hình
   - zoom ảnh full-face / half-face
   - thêm phản chiếu / nghiêng màn hình / khoảng cách khác nhau

> Nếu model chỉ học từ ảnh tĩnh mà không có replay video thật, nó thường **chặn được ảnh nhưng vẫn dễ bị qua mặt bởi video replay**.

---

## 5. Cấu trúc thư mục dataset đề xuất

```text
ai-service/
  data/
    antispoof/
      train/
        live/
          images/
          videos/
        spoof/
          images/
          videos/
      val/
        live/
          images/
        spoof/
          images/
      test/
        live/
          images/
        spoof/
          images/
```

Ghi chú:

- `train/` và `val/` được script huấn luyện dùng trực tiếp
- `test/` nên giữ ngoài luồng train để benchmark cuối cùng
- `ImageFolder` của PyTorch sẽ đọc ảnh bên trong các thư mục con như `images/`

---

## 6. Chuẩn hóa và dựng dataset bằng các script trong repo

### 6.1 Sắp xếp dữ liệu từ các thư mục lồng nhau

Nếu dữ liệu gốc đang ở dạng nhiều folder nhỏ như:

```text
samples/
  0001.../
    live_selfie.jpg
    live_video.mp4
  0002.../
    replay_video.mp4
```

chạy:

```powershell
cd ai-service
python .\training\organize_antispoof_samples.py `
  --source "C:\path\to\raw_samples" `
  --output .\data\antispoof
```

Script này sẽ **copy** dữ liệu về cấu trúc dễ huấn luyện hơn. Nếu muốn di chuyển thay vì copy, dùng `--move`.

### 6.2 Trích frame từ video spoof

Nếu phần lớn dữ liệu spoof là video replay, dùng:

```powershell
python .\training\extract_spoof_frames.py `
  --source .\data\raw_spoof_videos `
  --output .\data\antispoof `
  --every-n-frames 15 `
  --max-frames-per-video 100 `
  --val-ratio 0.2
```

Ý nghĩa:

- `--every-n-frames 15`: lấy 1 frame mỗi 15 frame video
- `--max-frames-per-video 100`: tránh một video chiếm quá nhiều trọng số
- `--val-ratio 0.2`: chia một phần sang `val/`

> Nên chia theo **video**, không chia ngẫu nhiên từng frame, để tránh rò rỉ dữ liệu giữa `train` và `val`.

---

## 7. Huấn luyện CNN anti-spoof

### 7.1 Tạo môi trường train

```powershell
cd ai-service
py -3.11 -m venv .venv-train
.\.venv-train\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 7.2 Kiến trúc baseline hiện tại

Script `training/train_cnn_antispoof.py` dùng một CNN nhỏ, phù hợp làm baseline:

- `Conv2d(3→32) + BN + ReLU + MaxPool`
- `Conv2d(32→64) + BN + ReLU + MaxPool`
- `Conv2d(64→128) + BN + ReLU + MaxPool`
- `Conv2d(128→256) + BN + ReLU + AdaptiveAvgPool`
- `FC(256→64→2)`

Ưu điểm:

- train được trên CPU
- export ONNX dễ
- tốc độ inference nhanh
- phù hợp để kiểm tra pipeline đầu-cuối trước khi nâng cấp sang model mạnh hơn

### 7.3 Augmentation đang dùng

- resize về `128×128`
- `RandomHorizontalFlip`
- `ColorJitter` nhẹ

Các augmentation này giúp model bớt overfit vào một điều kiện ánh sáng / góc chụp duy nhất.

### 7.4 Lệnh train

```powershell
python .\training\train_cnn_antispoof.py `
  --data-dir .\data\antispoof `
  --epochs 15 `
  --batch-size 32 `
  --image-size 128 `
  --export-onnx
```

Output chính (được ghi cố định về `ai-service/checkpoints/` kể cả khi chạy script từ thư mục gốc của repo):

- `ai-service/checkpoints/best_cnn_antispoof.pt`
- `ai-service/checkpoints/training_summary.json`
- `ai-service/checkpoints/custom-cnn-antispoof.onnx`
- đôi khi có thêm `ai-service/checkpoints/custom-cnn-antispoof.onnx.data`

---

## 8. Đưa model vào runtime

Sau khi train xong, copy model sang thư mục runtime:

```powershell
Copy-Item .\checkpoints\custom-cnn-antispoof.onnx* .\antispoof\ -Force
```

> **Quan trọng**: nếu export tạo ra cả file `.onnx.data`, phải copy **cả hai file**. Nếu thiếu `.onnx.data`, `ai-service` có thể lên `health=healthy` nhưng `/api/v1/extract` vẫn lỗi khi chạy thật.

Cập nhật `ai-service/ai-service.env`:

```env
ANTISPOOF_MODEL_PATH=/app/antispoof/custom-cnn-antispoof.onnx
ANTISPOOF_MODEL_TYPE=custom_cnn
ANTISPOOF_INPUT_SIZE=128
ANTISPOOF_THRESHOLD=0.80
```

Sau đó rebuild:

```powershell
cd ..
docker compose up -d --build ai-service backend
```

Kiểm tra health:

```powershell
Invoke-WebRequest http://localhost:9000/health
```

---

## 9. Đánh giá model sau khi train

### 9.1 Nên đo những gì?

Ngoài accuracy, với anti-spoof nên quan tâm thêm:

| Metric | Ý nghĩa |
|---|---|
| `APCER` | tỉ lệ spoof lọt qua được |
| `BPCER` | tỉ lệ người thật bị chặn nhầm |
| `ACER` | trung bình của APCER và BPCER |

Mục tiêu thực tế:

- `APCER` thấp: ảnh / video giả khó qua mặt
- `BPCER` không quá cao: người thật vẫn đăng ký / điểm danh được ổn định

### 9.2 Chọn threshold như thế nào?

Không nên đoán tay. Nên làm như sau:

1. chạy model trên tập `val/live` và `val/spoof`
2. thu các giá trị `liveness_score`
3. tìm threshold sao cho:
   - spoof bị chặn tốt
   - live vẫn pass đủ nhiều
4. chốt threshold cuối cùng rồi mới đem thử trên `test/`

> Nếu threshold quá cao, người thật dễ bị reject. Nếu quá thấp, spoof dễ lọt. Vì vậy `ANTISPOOF_THRESHOLD` phải được chọn từ dữ liệu validation, không chọn cảm tính.

---

## 10. Những cách giúp anti-spoof hoạt động tốt hơn

Nếu muốn hệ thống mạnh hơn với replay video thật, đây là các hướng hiệu quả nhất:

1. **Thêm nhiều dữ liệu spoof kiểu replay video thật**
   - điện thoại
   - laptop
   - tablet
   - các mức sáng màn hình khác nhau

2. **Bổ sung hard negatives**
   - ảnh full-screen chất lượng cao
   - video có đúng góc trái / phải / ngẩng / cúi
   - ảnh / video ở khoảng cách gần với camera

3. **Giữ split sạch giữa train / val / test**
   - không để cùng một video xuất hiện ở nhiều tập

4. **Kết hợp passive + active liveness**
   - passive: CNN anti-spoof
   - active: random turn-left / turn-right / blink / open-mouth challenge

5. **Test bằng tấn công thật, không chỉ test bằng ảnh mẫu trong code**
   - ảnh trên điện thoại
   - ảnh in
   - video replay của chính người đã enroll

---

## 11. Ghi chú về tốc độ build Docker

Để tránh việc container runtime phải cài cả `torch` và các gói phục vụ huấn luyện, `Dockerfile` hiện chỉ cài **phần runtime** được tách tự động từ `requirements.txt`.

Điều này có nghĩa là:

- khi **train / dev local**: dùng `pip install -r requirements.txt`
- khi **build Docker runtime**: image chỉ cài các gói cần để chạy API inference

Nhờ đó:

- build `ai-service` nhanh hơn rõ rệt
- image nhỏ hơn
- vẫn giữ được **một nguồn dependency duy nhất**

## 12. Run toàn bộ hệ thống

Từ thư mục gốc của repo:

```powershell
cd "c:\Users\Lam Nguyen\OneDrive\Desktop\DeepLearning_Final\smart-attendance-aiot"
Copy-Item backend\.env.example backend\.env -Force
Copy-Item ai-service\ai-service.env.example ai-service\ai-service.env -Force

docker compose up -d --build
```

Các URL chính:

| Service | URL |
|---|---|
| Frontend | `http://localhost:3000` |
| Backend API | `http://localhost:8000` |
| Backend docs | `http://localhost:8000/docs` |
| AI service health | `http://localhost:9000/health` |

Dừng hệ thống:

```powershell
docker compose down
```

---

## 13. Tóm tắt ngắn

- **ArcFace** dùng để nhận ra **đúng người nào**
- **CNN anti-spoof** dùng để kiểm tra **có phải người thật hay không**
- **Pose challenge** tăng khả năng chống ảnh tĩnh và replay attack
- **train / val / test** phải tách đúng để tránh kết quả ảo
- muốn chống replay video tốt hơn thì **data spoof thực tế** và **active liveness** là hai yếu tố quan trọng nhất
