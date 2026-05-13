FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    DEVICE=cpu \
    LOG_LEVEL=info \
    WAV2VEC2_MODEL=slplab/wav2vec2-large-robust-L2-english-phoneme-recognition \
    WAVLM_MODEL=microsoft/wavlm-large \
    WHISPER_MODEL=small.en \
    WHISPER_FALLBACK_MODEL=small.en \
    KOKORO_REPO_ID=hexgrad/Kokoro-82M \
    KOKORO_DEVICE=cpu \
    EMOTION_MODEL=j-hartmann/emotion-english-distilroberta-base \
    LOAD_WHISPER=0 \
    LOAD_VOICE_CLONE=0 \
    PREWARM_MODELS=0 \
    SCORE_ASR_MODE=off \
    SCORE_INCLUDE_FORMANTS=0 \
    SCORE_WAVLM_MODE=off \
    PRELOAD_ACCENT_CONVERTER=0 \
    HF_HOME=/app/.cache/huggingface \
    NLTK_DATA=/usr/local/share/nltk_data \
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

COPY requirements.prod.txt requirements.txt
RUN pip install --upgrade "pip<26" "setuptools<80" wheel \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchaudio==2.5.1 \
    && pip install -r requirements.txt \
    && python -m nltk.downloader -d /usr/local/share/nltk_data \
        punkt punkt_tab averaged_perceptron_tagger averaged_perceptron_tagger_eng cmudict

COPY app ./app
COPY checkpoints ./checkpoints
COPY models ./models

RUN mkdir -p /app/cache/native_f0 /app/data/enrollments /app/.cache/huggingface

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
