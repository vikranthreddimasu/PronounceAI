"""
PronounceAI FastAPI backend.
Startup: loads all ML models into app.state so they're shared across requests.
"""
import logging
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# `.env.local` wins for overlapping keys; `.env.example` only supplies defaults for a fresh checkout.
load_dotenv(".env.local", override=True)
load_dotenv(".env.example", override=False)

LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()


def _cors_allow_list() -> tuple[list[str], bool]:
    """Return (origins, allow_credentials). CORS_ORIGINS=comma-separated origins, or * for any (credentials off)."""
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw == "*":
        return ["*"], False
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if origins:
            return origins, True
    return ["http://localhost:3000", "http://localhost:3001"], True


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
ASSESSMENT_SCORER_CHECKPOINT = os.getenv("ASSESSMENT_SCORER_CHECKPOINT", "checkpoints/assessment_head_best.pt")
PREWARM_MODELS = os.getenv("PREWARM_MODELS", "0") == "1"
LOAD_WHISPER = os.getenv("LOAD_WHISPER", "1") == "1"
LOAD_VOICE_CLONE = os.getenv("LOAD_VOICE_CLONE", "1") == "1"
LOAD_WAVLM = os.getenv("SCORE_WAVLM_MODE", "auto").lower() != "off"
PREWARM_PHRASES = [
    p.strip()
    for p in os.getenv("PREWARM_PHRASES", "").split("|")
    if p.strip()
]
PREWARM_ACCENTS = [
    a.strip().upper()
    for a in os.getenv("PREWARM_ACCENTS", "GA,RP").split(",")
    if a.strip()
]


async def _startup_prewarm(app: FastAPI) -> None:
    try:
        from app.api.score import warmup_score_stack
        phrases = PREWARM_PHRASES or ["Ship or sheep?"]
        await warmup_score_stack(app, phrases, PREWARM_ACCENTS)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"Startup prewarm failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Loading ML models on device={DEVICE}")

    from app.models.phoneme_engine import PhonemeEngine
    from app.models.prosody_engine import ProsodyEngine

    app.state.phoneme_engine = PhonemeEngine(
        model_id=WAV2VEC2_MODEL,
        device=DEVICE,
        checkpoint_path=PHONEME_SCORER_CHECKPOINT,
    )
    logger.info("Phoneme engine ready")

    app.state.prosody_engine = ProsodyEngine(sample_rate=16000)
    logger.info("Prosody engine ready")

    try:
        if Path(ASSESSMENT_SCORER_CHECKPOINT).exists():
            from app.models.assessment_scorer import AssessmentScorer
            app.state.assessment_scorer = AssessmentScorer(
                checkpoint_path=ASSESSMENT_SCORER_CHECKPOINT,
                device=DEVICE,
            )
            logger.info("Learned assessment scorer ready")
        else:
            app.state.assessment_scorer = None
            logger.info("No learned assessment scorer checkpoint — deterministic scorer only")
    except Exception as e:
        logger.warning(f"Learned assessment scorer unavailable: {e}")
        app.state.assessment_scorer = None

    needs_wavlm = (
        LOAD_WAVLM
        and (
            Path(ACCENT_CENTROIDS_PATH).exists()
            or app.state.assessment_scorer is not None
            or os.getenv("FORCE_WAVLM_ENGINE", "0") == "1"
        )
    )
    if needs_wavlm:
        try:
            from app.models.accent_distance import AccentDistanceEngine
            app.state.accent_engine = AccentDistanceEngine(
                model_id=WAVLM_MODEL,
                device=DEVICE,
                centroids_path=ACCENT_CENTROIDS_PATH,
            )
            logger.info("WavLM embedding/accent engine ready")
        except Exception as e:
            logger.warning(f"WavLM embedding/accent engine unavailable: {e}")
            app.state.accent_engine = None
    else:
        app.state.accent_engine = None
        if not LOAD_WAVLM:
            logger.info("Skipping WavLM embedding engine — SCORE_WAVLM_MODE=off")
        else:
            logger.info("Skipping WavLM embedding engine — no local checkpoint or centroids found")

    if LOAD_WHISPER:
        from app.models.whisper_engine import WhisperEngine
        app.state.whisper = WhisperEngine()
        logger.info("Whisper engine ready")
    else:
        app.state.whisper = None
        logger.info("Skipping Whisper engine — LOAD_WHISPER=0")

    if LOAD_VOICE_CLONE:
        try:
            from app.models.voice_clone import VoiceClone
            # Whisper engine is loaded above; pass it so VoiceClone can validate
            # instruct-mode output and fall back to VC when the LLM drifts.
            app.state.voice_clone = VoiceClone(whisper_engine=app.state.whisper)
            app.state.voice_clone.warmup()
            logger.info("Voice clone engine ready")
        except Exception as e:
            logger.warning(f"Voice clone engine unavailable: {e}")
            app.state.voice_clone = None
    else:
        app.state.voice_clone = None
        logger.info("Skipping voice clone engine — LOAD_VOICE_CLONE=0")

    try:
        from app.models.emotion_detector import EmotionDetector
        app.state.emotion_detector = EmotionDetector()
        logger.info("Emotion detector ready (lazy-loaded)")
    except Exception as e:
        logger.warning(f"Emotion detector unavailable: {e}")
        app.state.emotion_detector = None

    logger.info("All models loaded — server ready")
    app.state.startup_prewarm_task = None
    if PREWARM_MODELS:
        app.state.startup_prewarm_task = asyncio.create_task(_startup_prewarm(app))
        logger.info("Startup prewarm scheduled")
    yield

    task = getattr(app.state, "startup_prewarm_task", None)
    if task is not None and not task.done():
        task.cancel()
    logger.info("Shutting down")


_cors_origins, _cors_credentials = _cors_allow_list()
logger.info("CORS allow_origins=%r allow_credentials=%s", _cors_origins, _cors_credentials)

app = FastAPI(title="PronounceAI Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.score import router as score_router
from app.api.tts import router as tts_router
from app.api.voice_enroll import router as voice_enroll_router
from app.api.accent_clone import router as accent_clone_router
app.include_router(score_router, prefix="/api")
app.include_router(tts_router, prefix="/api")
app.include_router(voice_enroll_router, prefix="/api")
app.include_router(accent_clone_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
