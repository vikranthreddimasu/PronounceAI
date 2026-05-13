import asyncio
import io
import unittest
from types import SimpleNamespace

import numpy as np
import soundfile as sf

import app.api.score as score_mod
import app.scoring.pipeline as pipeline_mod
from app.models.phoneme_engine import PhonemeResult


class _FakeUpload:
    def __init__(self, payload: bytes):
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _FakePhonemeEngine:
    def __init__(self):
        self.prepared = []

    def prepare_phrase(self, phrase):
        self.prepared.append(phrase)
        return [1]

    def score(self, wav, phrase, include_diagnostics=False):
        results = [
            PhonemeResult(
                phoneme="sh",
                expected="sh",
                gop=-0.2,
                correct=True,
                substitution=None,
                start_ms=0,
                end_ms=120,
            )
        ]
        diagnostics = {
            "expected_phone_count": 1,
            "predicted_phone_count": 1,
            "phone_error_rate": 0.0,
            "ctc_sequence_score": 100.0,
            "predicted_phones": ["sh"],
        }
        return (results, diagnostics) if include_diagnostics else results

    def accuracy_score(self, results):
        return 93.0


class _FakeProsodyEngine:
    def analyze(self, wav_np, phoneme_dicts, reference_f0=None, include_formants=True):
        return {
            "intonation": 88.0,
            "stress_rhythm": 90.0,
            "rate_score": 90.0,
            "npvi": 50.0,
            "f0_contour": [100.0, 110.0, 0.0, 120.0],
            "formants": {},
            "speech_rate_sps": 4.0,
        }


class _FakeAccentEngine:
    def distance_score(self, wav_np, accent):
        return None


class _FakeWhisper:
    def transcribe_fast(self, wav_np):
        return "Ship or sheep?"


def _wav_bytes() -> bytes:
    sr = 16_000
    t = np.arange(sr, dtype=np.float32) / sr
    wav = np.zeros(sr, dtype=np.float32)
    wav[int(0.2 * sr):] = 0.1 * np.sin(2 * np.pi * 220 * t[int(0.2 * sr):])
    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class ScoreRouteAsyncTests(unittest.TestCase):
    def test_score_route_returns_grounding_debug_with_fake_engines(self):
        app = SimpleNamespace(
            state=SimpleNamespace(
                phoneme_engine=_FakePhonemeEngine(),
                prosody_engine=_FakeProsodyEngine(),
                accent_engine=_FakeAccentEngine(),
                whisper=_FakeWhisper(),
            )
        )
        request = SimpleNamespace(app=app)

        original_native_f0 = pipeline_mod.get_native_f0
        pipeline_mod.get_native_f0 = lambda phrase, accent, prosody: (
            np.array([100.0, 110.0, 0.0, 120.0], dtype=np.float32),
            1000,
        )
        try:
            result = asyncio.run(
                score_mod.score_recording(
                    request=request,
                    audio=_FakeUpload(_wav_bytes()),
                    phrase="Ship or sheep?",
                    accent="GA",
                    l1="unknown",
                )
            )
        finally:
            pipeline_mod.get_native_f0 = original_native_f0

        self.assertEqual(result["wer"], 0.0)
        self.assertEqual(result["debug"]["phrase_match"]["phrase_match"], 100.0)
        self.assertIn("stage_ms", result["debug"])
        self.assertEqual(result["debug"]["score_gates"], [])
        self.assertFalse(result["debug"]["cache_hit"])

    def test_prewarm_schedules_phrase_context(self):
        engine = _FakePhonemeEngine()
        app = SimpleNamespace(
            state=SimpleNamespace(
                phoneme_engine=engine,
                prosody_engine=_FakeProsodyEngine(),
            )
        )
        original_native_f0 = pipeline_mod.get_native_f0
        pipeline_mod.get_native_f0 = lambda phrase, accent, prosody: (
            np.array([100.0], dtype=np.float32),
            100,
        )
        try:
            asyncio.run(score_mod._prewarm_context(app, "Ship or sheep?", "GA"))
        finally:
            pipeline_mod.get_native_f0 = original_native_f0
        self.assertEqual(engine.prepared, ["Ship or sheep?"])


if __name__ == "__main__":
    unittest.main()
