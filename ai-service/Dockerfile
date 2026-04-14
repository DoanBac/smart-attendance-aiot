FROM python:3.11-slim-bookworm

# System deps:
# - build-essential + g++: compiling insightface C extensions
# - libGL + libglib: OpenCV runtime
# - libgomp: onnxruntime parallel ops
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    g++ \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python - <<'PY'
from pathlib import Path
src = Path('requirements.txt').read_text(encoding='utf-8').splitlines()
out = []
for line in src:
    if line.strip().startswith('# Training / ONNX export'):
        break
    out.append(line)
Path('requirements.runtime.txt').write_text('\n'.join(out).strip() + '\n', encoding='utf-8')
print('Generated requirements.runtime.txt')
PY
RUN pip install --no-cache-dir -r requirements.runtime.txt

# Pre-create model dir (InsightFace downloads here on first boot)
RUN mkdir -p /app/models

# Download anti-spoof MobileNetV3 ONNX model (11.7 MB) to a SEPARATE path
# IMPORTANT: /app/models is overridden by the insightface_models Docker volume
# so we store anti-spoof model in /app/antispoof/ which is NOT volume-mounted
# Source: Intel OpenVINO Open Model Zoo — MIT License
# Trained on CelebA-Spoof (625k images, 43 spoof types), ACER=3.81%
RUN mkdir -p /app/antispoof && \
    curl -fsSL \
    "https://storage.openvinotoolkit.org/repositories/open_model_zoo/public/2022.1/anti-spoof-mn3/anti-spoof-mn3.onnx" \
    -o /app/antispoof/anti-spoof-mn3.onnx && \
    echo "anti-spoof-mn3.onnx downloaded: $(du -sh /app/antispoof/anti-spoof-mn3.onnx)"

COPY . .

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
