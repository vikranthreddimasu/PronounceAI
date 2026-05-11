"""
PronounceAI FastAPI backend.
Startup: loads all ML models into app.state so they're shared across requests.
"""
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(".env.local", override=True)
load_dotenv(".env.example")

LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()

# Set espeak-ng library path for phonemizer (Homebrew on macOS puts it here)
_ESPEAK_LIB = os.getenv("ESPEAK_NG_LIB", "/opt/homebrew/lib/libespeak-ng.dylib")
try:
    from phonemizer.backend import EspeakBackend
    EspeakBackend.set_library(_ESPEAK_LIB)
except Exception:
    pass  # phonemizer unavailable — engine falls back to tokenizer
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DEVICE = os.getenv("DEVICE", "mps")
WAV2VEC2_MODEL = os.getenv("WAV2VEC2_MODEL", "slplab/wav2vec2-large-robust-L2-english-phoneme-recognition")
WAVLM_MODEL = os.getenv("WAVLM_MODEL", "microsoft/wavlm-large")
PHONEME_SCORER_CHECKPOINT = os.getenv("PHONEME_SCORER_CHECKPOINT", "checkpoints/phoneme_scorer_best.pt")
ACCENT_CENTROIDS_PATH = os.getenv("ACCENT_CENTROIDS_PATH", "checkpoints/accent_centroids.pt")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Loading ML models on device={DEVICE}")

    from app.models.phoneme_engine import PhonemeEngine
    from app.models.prosody_engine import ProsodyEngine
    from app.models.accent_distance import AccentDistanceEngine
    from app.models.feedback_generator import FeedbackGenerator

    app.state.phoneme_engine = PhonemeEngine(
        model_id=WAV2VEC2_MODEL,
        device=DEVICE,
        checkpoint_path=PHONEME_SCORER_CHECKPOINT,
    )
    logger.info("Phoneme engine ready")

    app.state.prosody_engine = ProsodyEngine(sample_rate=16000)
    logger.info("Prosody engine ready")

    app.state.accent_engine = AccentDistanceEngine(
        model_id=WAVLM_MODEL,
        device=DEVICE,
        centroids_path=ACCENT_CENTROIDS_PATH,
    )
    logger.info("Accent distance engine ready")

    app.state.feedback_gen = FeedbackGenerator()
    logger.info("Feedback generator ready")

    from app.models.whisper_engine import WhisperEngine
    app.state.whisper = WhisperEngine()
    logger.info("Whisper engine ready")

    logger.info("All models loaded — server ready")
    yield

    logger.info("Shutting down")


app = FastAPI(title="PronounceAI Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.score import router as score_router
from app.api.tts import router as tts_router
app.include_router(score_router, prefix="/api")
app.include_router(tts_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
