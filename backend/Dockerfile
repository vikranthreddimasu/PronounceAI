FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    DEVICE=cpu \
    LOG_LEVEL=info \
    PREWARM_MODELS=0 \
    SCORE_ASR_MODE=off \
    SCORE_INCLUDE_FORMANTS=0 \
    PRELOAD_ACCENT_CONVERTER=0 \
    HF_HOME=/app/.cache/huggingface \
    XDG_CACHE_HOME=/app/.cache \
    ENROLLMENT_DIR=/app/data/enrollments \
    NATIVE_F0_CACHE_DIR=/app/cache/native_f0 \
    ESPEAK_NG_LIB=/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        git \
        libsndfile1 \
        espeak-ng \
        libespeak-ng1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app ./app
COPY checkpoints ./checkpoints

RUN mkdir -p /app/cache/native_f0 /app/data/enrollments /app/.cache/huggingface

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
