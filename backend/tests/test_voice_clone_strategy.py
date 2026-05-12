import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from app.models.voice_clone import VoiceClone


class _StrategyVoiceClone(VoiceClone):
    def __init__(self):
        super().__init__(whisper_engine=None)
        self.calls = []

    def _make_audio(self) -> Path:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        sf.write(tmp.name, np.zeros(1600, dtype=np.float32), 16_000)
        return Path(tmp.name)

    def _speak_vc(self, text, ref_audio_path, accent):
        self.calls.append("vc")
        return self._make_audio()

    def _speak_zero_shot(self, text, ref_audio_path, ref_text):
        self.calls.append("zero_shot")
        return self._make_audio()

    def _speak_instruct(self, text, ref_audio_path, accent):
        self.calls.append("instruct")
        return self._make_audio()

    def _transcribe_with_words(self, audio_path):
        return {
            "text": "Hello world",
            "words": [
                {"word": "Hello", "start_ms": 0, "end_ms": 250},
                {"word": "world", "start_ms": 250, "end_ms": 500},
            ],
        }


class VoiceCloneStrategyTests(unittest.TestCase):
    def _ref_path(self) -> Path:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        sf.write(tmp.name, np.zeros(16_000, dtype=np.float32), 16_000)
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def test_target_accent_strategy_uses_vc_first(self):
        clone = _StrategyVoiceClone()
        result = clone.speak(
            text="Hello world",
            ref_audio_path=self._ref_path(),
            accent="GA",
            ref_text="Reference text",
            strategy="target_accent",
        )
        self.addCleanup(lambda: result.path.unlink(missing_ok=True))

        self.assertEqual(result.mode, "vc")
        self.assertEqual(result.strategy, "target_accent")
        self.assertEqual(clone.calls, ["vc"])

    def test_natural_strategy_uses_zero_shot_first(self):
        clone = _StrategyVoiceClone()
        result = clone.speak(
            text="Hello world",
            ref_audio_path=self._ref_path(),
            accent="GA",
            ref_text="Reference text",
            strategy="natural",
        )
        self.addCleanup(lambda: result.path.unlink(missing_ok=True))

        self.assertEqual(result.mode, "zero_shot")
        self.assertEqual(result.strategy, "natural")
        self.assertEqual(clone.calls, ["zero_shot"])

    def test_cosyvoice3_zero_shot_ref_text_uses_prompt_prefix(self):
        clone = VoiceClone(model_id="mlx-community/Fun-CosyVoice3-0.5B-2512-fp16")
        formatted = clone._zero_shot_ref_text("This is my voice sample.")

        self.assertEqual(
            formatted,
            "You are a helpful assistant.<|endofprompt|>This is my voice sample.",
        )


if __name__ == "__main__":
    unittest.main()
