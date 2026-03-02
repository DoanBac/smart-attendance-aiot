FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    libpq-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/models

COPY . .

EXPOSE 8000

# Make the startup script executable
RUN chmod +x /app/start.sh

# start.sh runs: alembic upgrade head → uvicorn
CMD ["/app/start.sh"]
