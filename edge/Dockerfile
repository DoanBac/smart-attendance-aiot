FROM python:3.11-slim-bookworm

# System deps for OpenCV + ONNX Runtime ARM
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy into /app/edge/ so that "from edge.src.x import y" works with PYTHONPATH=/app
COPY . /app/edge/

ENV PYTHONPATH=/app
# Suppress ONNX Runtime C++ verbosity (log level 3 = ERROR only)
ENV ORT_LOG_LEVEL=3

CMD ["python", "-m", "edge.src.main"]