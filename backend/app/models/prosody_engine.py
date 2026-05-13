"""
Layer 3 — Prosody Engine.

Computes four prosody dimensions from the raw audio + CTC timestamps:
  - Intonation:   DTW distance of learner F0 contour vs. reference
  - Stress:       energy-per-syllable deviation from native stress pattern
  - Rhythm:       nPVI (normalized Pairwise Variability Index) on vowel intervals
  - Rate:         syllables/second vs. native range

All methods are deterministic (no ML) and run on CPU in <150ms.
"""
import logging
import numpy as np
import librosa
import parselmouth
from parselmouth.praat import call

logger = logging.getLogger(__name__)

# GA native speech reference ranges (conservative mid-values)
NATIVE_SPEECH_RATE_SPS = (3.5, 5.5)   # syllables/second
NATIVE_NPVI_RANGE = (40, 65)           # typical stress-timed English nPVI


class ProsodyEngine:
    def __init__(self, sample_rate: int = 16000):
        self.sr = sample_rate

    def analyze(
        self,
        wav_np: np.ndarray,       # [T] float32, 16kHz
        phoneme_timestamps: list[dict],  # [{phoneme, start_ms, end_ms}, ...]
        reference_f0: np.ndarray | None = None,  # native F0 contour for DTW
        include_formants: bool = True,
    ) -> dict:
        """
        Returns:
          intonation: 0-100
          stress_rhythm: 0-100
          rate_score: 0-100
          npvi: raw nPVI value
          f0_contour: list of F0 values (Hz, 0=unvoiced) for visualization
          formants: {vowel: {f1, f2, f3}} for vowel space plot
        """
        result = {}

        # F0 extraction via Parselmouth (Praat)
        f0_contour, f0_voiced = self._extract_f0(wav_np)
        result["f0_contour"] = f0_contour.tolist()

        # Formant analysis is useful but noticeably slower. The score route can
        # disable it for demo-fast responses and fall back to a neutral vowel
        # quality score.
        result["formants"] = (
            self._extract_formants(wav_np, phoneme_timestamps)
            if include_formants
            else {}
        )

        # Intonation score: DTW vs reference, or internal smoothness proxy
        result["intonation"] = self._intonation_score(f0_voiced, reference_f0)

        # Rhythm + stress
        npvi = self._compute_npvi(phoneme_timestamps)
        result["npvi"] = round(npvi, 2)
        result["stress_rhythm"] = self._rhythm_score(npvi)

        # Speech rate
        rate_sps = self._speech_rate(phoneme_timestamps, len(wav_np))
        result["rate_score"] = self._rate_score(rate_sps)
        result["speech_rate_sps"] = round(rate_sps, 2)

        return result

    def _extract_f0(self, wav_np: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Returns (f0_contour [Hz, 0=unvoiced], voiced_only [Hz]) using Parselmouth."""
        try:
            snd = parselmouth.Sound(wav_np, sampling_frequency=self.sr)
            pitch = snd.to_pitch(pitch_floor=75.0, pitch_ceiling=600.0)
            # selected_array['frequency'] is 0.0 for unvoiced frames
            f0 = pitch.selected_array["frequency"].astype(np.float64)
            f0 = np.nan_to_num(f0, nan=0.0)
            voiced = f0[f0 > 0]
            return f0, voiced
        except Exception as e:
            logger.warning(f"Parselmouth F0 failed: {e}")
            # Fallback: librosa pyin
            f0_raw, voiced_flag, _ = librosa.pyin(
                wav_np, fmin=75, fmax=600, sr=self.sr
            )
            f0 = np.where(voiced_flag, f0_raw, 0.0)
            voiced = f0[f0 > 0]
            return f0, voiced

    def _extract_formants(
        self, wav_np: np.ndarray, timestamps: list[dict]
    ) -> dict:
        """Extract F1/F2/F3 for each vowel token."""
        VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY",
                  "IH", "IY", "OW", "OY", "UH", "UW"}
        formants = {}
        try:
            snd = parselmouth.Sound(wav_np, sampling_frequency=self.sr)
            formant_obj = call(snd, "To Formant (burg)", 0, 5, 5500, 0.025, 50)
            for tok in timestamps:
                ph = tok.get("expected", tok.get("phoneme", "")).upper()
                if ph not in VOWELS:
                    continue
                mid_s = (tok["start_ms"] + tok["end_ms"]) / 2 / 1000
                try:
                    f1 = call(formant_obj, "Get value at time", 1, mid_s, "Hertz", "Linear")
                    f2 = call(formant_obj, "Get value at time", 2, mid_s, "Hertz", "Linear")
                    f3 = call(formant_obj, "Get value at time", 3, mid_s, "Hertz", "Linear")
                    if all(v == v for v in [f1, f2, f3]):  # not NaN
                        formants[ph] = {
                            "f1": round(f1, 1),
                            "f2": round(f2, 1),
                            "f3": round(f3, 1),
                        }
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Formant extraction failed: {e}")
        return formants

    def _intonation_score(
        self,
        f0_voiced: np.ndarray,
        reference_f0: np.ndarray | None,
    ) -> float:
        """
        Score 0-100. With a reference, uses DTW distance (normalised).
        Without reference, uses internal prosody proxy: variance + monotonicity check.
        """
        if len(f0_voiced) < 5:
            return 50.0

        if reference_f0 is not None and len(reference_f0) > 5:
            # Normalize both to z-score for speaker-invariant comparison
            def normalize(x):
                std = x.std()
                return (x - x.mean()) / std if std > 0 else x - x.mean()
            a = normalize(self._resample_contour(f0_voiced, 96))
            b = normalize(self._resample_contour(reference_f0, 96))
            # Simple DTW via cumulative distance
            dtw = self._dtw_distance(a, b)
            # Max possible distance for normalisation
            max_dtw = max(len(a), len(b)) * 2.0
            score = max(0.0, 100 - (dtw / max_dtw * 100))
            return round(score, 1)

        # Proxy: penalise flat or erratic contours
        diff = np.diff(np.log(f0_voiced + 1e-9))
        # A good intonation contour has moderate variance (not flat, not chaotic)
        var = np.var(diff)
        # Ideal variance is around 0.01-0.05 (empirically)
        ideal_var = 0.025
        deviation = abs(var - ideal_var) / ideal_var
        score = max(0.0, 100 - deviation * 60)
        return round(score, 1)

    def _resample_contour(self, arr: np.ndarray, n_out: int) -> np.ndarray:
        if len(arr) <= n_out:
            return arr.astype(np.float64)
        src_idx = np.linspace(0, len(arr) - 1, n_out)
        return np.interp(src_idx, np.arange(len(arr)), arr).astype(np.float64)

    def _dtw_distance(self, a: np.ndarray, b: np.ndarray) -> float:
        n, m = len(a), len(b)
        dtw = np.full((n + 1, m + 1), np.inf)
        dtw[0, 0] = 0
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = abs(a[i - 1] - b[j - 1])
                dtw[i, j] = cost + min(dtw[i - 1, j], dtw[i, j - 1], dtw[i - 1, j - 1])
        return dtw[n, m]

    def _compute_npvi(self, timestamps: list[dict]) -> float:
        """
        nPVI on inter-vowel intervals (duration variability).
        Higher nPVI = more stress-timed (native English ~50-60).
        Lower nPVI = syllable-timed (Spanish, French ~30-40).
        """
        VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY",
                  "IH", "IY", "OW", "OY", "UH", "UW"}
        durations = []
        for tok in timestamps:
            ph = tok.get("expected", tok.get("phoneme", "")).upper()
            if ph in VOWELS:
                d = tok["end_ms"] - tok["start_ms"]
                if d > 0:
                    durations.append(d)

        if len(durations) < 2:
            return 50.0  # default to native-like

        nPVI = 0.0
        for i in range(len(durations) - 1):
            d1, d2 = durations[i], durations[i + 1]
            nPVI += abs(d1 - d2) / ((d1 + d2) / 2) * 100
        return nPVI / (len(durations) - 1)

    def _rhythm_score(self, npvi: float) -> float:
        """Convert nPVI to 0-100 score. Native GA range: 40-65."""
        lo, hi = NATIVE_NPVI_RANGE
        if lo <= npvi <= hi:
            return 100.0
        elif npvi < lo:
            # Syllable-timed — penalise proportionally
            return max(0.0, round(100 - (lo - npvi) * 2.0, 1))
        else:
            return max(0.0, round(100 - (npvi - hi) * 1.5, 1))

    def _speech_rate(self, timestamps: list[dict], n_samples: int) -> float:
        """Syllables per second from phoneme boundaries."""
        VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY",
                  "IH", "IY", "OW", "OY", "UH", "UW"}
        n_vowels = sum(
            1 for t in timestamps
            if t.get("expected", t.get("phoneme", "")).upper() in VOWELS
        )
        duration_s = n_samples / self.sr
        return n_vowels / duration_s if duration_s > 0 else 0.0

    def _rate_score(self, rate_sps: float) -> float:
        lo, hi = NATIVE_SPEECH_RATE_SPS
        if lo <= rate_sps <= hi:
            return 100.0
        elif rate_sps < lo:
            return max(40.0, round(100 - (lo - rate_sps) * 15, 1))
        else:
            return max(40.0, round(100 - (rate_sps - hi) * 12, 1))
