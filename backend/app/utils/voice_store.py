"""
Multi-take voice enrollment store.

Each user owns `data/enrollments/{user_id}/` containing:
  take_001.wav, take_002.wav, ...   — individual 16 kHz mono PCM_16 takes
  meta.json                          — list of takes with text + quality stats
  bundle.wav                         — lazy-cached concat at 24 kHz mono,
                                       capped at BUNDLE_MAX_S, used directly
                                       by CosyVoice 3 as ref_audio
  bundle.json                        — bundle build manifest (source ids etc.)

Why bundle: CosyVoice 3 accepts up to 30 s of reference audio and uses it
to compute both the speaker embedding AND the prompt mel-spectrogram /
prompt speech tokens that anchor the flow model. Longer + varied reference
audio = stronger speaker fidelity and better push-back against accent drift.

`user_id` is an opaque client-generated UUID stored in the browser's
localStorage. No accounts, no PII.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

import numpy as np
import resampy
import soundfile as sf

logger = logging.getLogger(__name__)

ENROLL_ROOT = Path(os.getenv("ENROLLMENT_DIR", "data/enrollments")).resolve()
ENROLL_ROOT.mkdir(parents=True, exist_ok=True)

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_TAKE_ID_RE = re.compile(r"^take_\d{3,4}$")

# Per-take limits (raw 16 kHz mono float32 from the browser)
MIN_TAKE_S = 4.0
MAX_TAKE_S = 25.0

# Quality gates
MAX_PEAK = 0.985    # absolute peak above this = clipping
MIN_RMS = 0.01      # below this = whisper / dead mic
TARGET_RMS = 0.075  # consistent prompt loudness helps zero-shot cloning

# Bundle target — CosyVoice 3 native rate, 30 s hard cap with margin
TARGET_SR = 24_000
BUNDLE_MAX_S = 28.0
INTER_TAKE_SILENCE_MS = 200
TRIM_PAD_MS = 120
FADE_MS = 12


class VoiceStoreError(ValueError):
    pass


def _validate_id(user_id: str) -> None:
    if not _ID_RE.match(user_id):
        raise VoiceStoreError("Invalid user id format.")


def _user_dir(user_id: str) -> Path:
    _validate_id(user_id)
    return ENROLL_ROOT / user_id


def _meta_path(user_id: str) -> Path:
    return _user_dir(user_id) / "meta.json"


def _read_meta(user_id: str) -> dict:
    p = _meta_path(user_id)
    if not p.exists():
        return {"takes": []}
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError:
        return {"takes": []}

    # Migrate legacy single-ref schema → multi-take schema.
    if "takes" not in data and "ref_text" in data:
        ud = _user_dir(user_id)
        legacy_wav = ud / "ref.wav"
        if legacy_wav.exists():
            new_take = ud / "take_001.wav"
            try:
                legacy_wav.rename(new_take)
            except Exception:
                pass
            data = {
                "takes": [{
                    "id": "take_001",
                    "ref_text": data.get("ref_text", ""),
                    "duration_s": data.get("duration_s", 0.0),
                    "created_at": data.get("created_at", time.time()),
                    "peak": None,
                    "rms": None,
                }],
            }
            p.write_text(json.dumps(data, indent=2))
            logger.info(f"voice_store: migrated legacy enrollment to multi-take ({user_id})")
        else:
            data = {"takes": []}
    return data


def _write_meta(user_id: str, data: dict) -> None:
    _meta_path(user_id).write_text(json.dumps(data, indent=2))


def _next_take_id(meta: dict) -> str:
    max_n = 0
    for t in meta.get("takes", []):
        m = re.match(r"^take_(\d+)$", t.get("id", ""))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"take_{max_n+1:03d}"


def _invalidate_bundle(user_id: str) -> None:
    ud = _user_dir(user_id)
    for name in ("bundle.wav", "bundle.json"):
        p = ud / name
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def _quality_check(wav_16k_mono: np.ndarray, ref_text: str) -> dict:
    duration = len(wav_16k_mono) / 16_000
    if not (MIN_TAKE_S <= duration <= MAX_TAKE_S):
        raise VoiceStoreError(
            f"Take duration {duration:.1f}s out of range "
            f"({MIN_TAKE_S:.0f}-{MAX_TAKE_S:.0f}s)."
        )
    peak = float(np.abs(wav_16k_mono).max())
    rms = float(np.sqrt(np.mean(np.square(wav_16k_mono))))
    if peak > MAX_PEAK:
        raise VoiceStoreError(
            f"Audio is clipping (peak {peak:.3f}). Lower your input volume and re-record."
        )
    if rms < MIN_RMS:
        raise VoiceStoreError(
            f"Audio is too quiet (rms {rms:.4f}). Move closer to the mic and re-record."
        )
    if len(ref_text.strip()) < 3:
        raise VoiceStoreError("Reference text too short.")
    return {"duration_s": round(duration, 2), "peak": round(peak, 3), "rms": round(rms, 4)}


def _condition_take(wav_16k_mono: np.ndarray) -> np.ndarray:
    """Trim obvious silence and normalize prompt loudness before storage."""
    wav = np.asarray(wav_16k_mono, dtype=np.float32).reshape(-1)
    wav = np.nan_to_num(wav, nan=0.0, posinf=0.0, neginf=0.0)
    if wav.size == 0:
        return wav

    raw_peak = float(np.abs(wav).max())
    if raw_peak > MAX_PEAK:
        raise VoiceStoreError(
            f"Audio is clipping (peak {raw_peak:.3f}). Lower your input volume and re-record."
        )

    wav = wav - float(np.mean(wav))
    peak = float(np.abs(wav).max())
    if peak > 0:
        threshold = max(0.006, peak * 0.04)
        voiced = np.flatnonzero(np.abs(wav) >= threshold)
        if voiced.size > 0:
            pad = int(16_000 * TRIM_PAD_MS / 1000)
            start = max(0, int(voiced[0]) - pad)
            end = min(len(wav), int(voiced[-1]) + pad + 1)
            wav = wav[start:end]

    if wav.size == 0:
        return wav

    rms = float(np.sqrt(np.mean(np.square(wav))))
    peak = float(np.abs(wav).max())
    if rms > 1e-6 and peak > 0:
        gain = TARGET_RMS / rms
        gain = min(gain, 0.92 / peak)
        wav = (wav * gain).astype(np.float32)

    fade_n = min(int(16_000 * FADE_MS / 1000), len(wav) // 2)
    if fade_n > 1:
        fade = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
        wav[:fade_n] *= fade
        wav[-fade_n:] *= fade[::-1]
    return wav.astype(np.float32)


# ── Mutators ──────────────────────────────────────────────────────────

def add_take(user_id: str, wav_16k_mono: np.ndarray, ref_text: str) -> dict:
    """Append a new take. Returns the take record."""
    conditioned = _condition_take(wav_16k_mono)
    metrics = _quality_check(conditioned, ref_text)
    user_dir = _user_dir(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    meta = _read_meta(user_id)
    take_id = _next_take_id(meta)
    take_path = user_dir / f"{take_id}.wav"
    sf.write(str(take_path), conditioned, 16_000, subtype="PCM_16")

    take = {
        "id": take_id,
        "ref_text": ref_text.strip(),
        "duration_s": metrics["duration_s"],
        "peak": metrics["peak"],
        "rms": metrics["rms"],
        "created_at": time.time(),
    }
    meta.setdefault("takes", []).append(take)
    _write_meta(user_id, meta)
    _invalidate_bundle(user_id)
    logger.info(
        f"voice_store: take added {user_id}/{take_id} "
        f"({metrics['duration_s']:.1f}s, peak={metrics['peak']:.2f}, "
        f"rms={metrics['rms']:.3f})"
    )
    return take


def delete_take(user_id: str, take_id: str) -> bool:
    if not _TAKE_ID_RE.match(take_id):
        raise VoiceStoreError("Invalid take id.")
    meta = _read_meta(user_id)
    takes = meta.get("takes", [])
    new_takes = [t for t in takes if t.get("id") != take_id]
    if len(new_takes) == len(takes):
        return False
    take_path = _user_dir(user_id) / f"{take_id}.wav"
    if take_path.exists():
        try:
            take_path.unlink()
        except Exception:
            pass
    meta["takes"] = new_takes
    _write_meta(user_id, meta)
    _invalidate_bundle(user_id)
    logger.info(f"voice_store: take deleted {user_id}/{take_id}")
    return True


def delete_enrollment(user_id: str) -> bool:
    user_dir = _user_dir(user_id)
    if not user_dir.exists():
        return False
    for p in user_dir.iterdir():
        try:
            p.unlink()
        except IsADirectoryError:
            pass
    try:
        user_dir.rmdir()
    except Exception:
        pass
    logger.info(f"voice_store: deleted enrollment {user_id}")
    return True


# ── Bundle (lazy) ─────────────────────────────────────────────────────

def _build_bundle(user_id: str) -> tuple[Path, str]:
    """Concat all takes into one 24kHz mono reference clip up to BUNDLE_MAX_S."""
    user_dir = _user_dir(user_id)
    meta = _read_meta(user_id)
    takes = sorted(meta.get("takes", []), key=lambda t: t.get("created_at", 0))
    if not takes:
        raise VoiceStoreError("No takes to bundle.")

    silence = np.zeros(int(TARGET_SR * INTER_TAKE_SILENCE_MS / 1000), dtype=np.float32)
    parts: list[np.ndarray] = []
    ref_texts: list[str] = []
    used_ids: list[str] = []
    total_cap_samples = int(TARGET_SR * BUNDLE_MAX_S)
    running = 0

    for t in takes:
        tp = user_dir / f"{t['id']}.wav"
        if not tp.exists():
            continue
        wav, sr = sf.read(str(tp), dtype="float32")
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        if sr != TARGET_SR:
            wav = resampy.resample(wav, sr, TARGET_SR).astype(np.float32)

        # Insert silence between takes (skip before the first)
        if running > 0 and running + len(silence) < total_cap_samples:
            parts.append(silence)
            running += len(silence)

        room = total_cap_samples - running
        if room <= 0:
            break
        if len(wav) > room:
            wav = wav[:room]
        parts.append(wav)
        running += len(wav)
        ref_texts.append(t["ref_text"])
        used_ids.append(t["id"])
        if running >= total_cap_samples:
            break

    if not parts:
        raise VoiceStoreError("No valid take files on disk.")

    bundle = np.concatenate(parts).astype(np.float32)
    bundle_path = user_dir / "bundle.wav"
    sf.write(str(bundle_path), bundle, TARGET_SR, subtype="PCM_16")

    ref_text = " ".join(ref_texts)
    (user_dir / "bundle.json").write_text(json.dumps({
        "source_take_ids": used_ids,
        "total_duration_s": round(len(bundle) / TARGET_SR, 2),
        "ref_text": ref_text,
        "sample_rate": TARGET_SR,
        "built_at": time.time(),
    }, indent=2))
    logger.info(
        f"voice_store: bundle built {user_id} "
        f"({len(bundle)/TARGET_SR:.1f}s from {len(used_ids)} take(s))"
    )
    return bundle_path, ref_text


def _bundle_paths(user_id: str) -> tuple[Path, Path]:
    ud = _user_dir(user_id)
    return ud / "bundle.wav", ud / "bundle.json"


def _profile_revision(
    user_id: str,
    takes: list[dict],
    bundle_wav: Path,
    bundle_json: Path,
) -> tuple[str, float]:
    """Return a stable-enough client cache revision for the current profile."""
    stamps = [t.get("created_at", 0.0) for t in takes]
    for p in (_meta_path(user_id), bundle_wav, bundle_json):
        try:
            stamps.append(p.stat().st_mtime)
        except OSError:
            pass
    updated_at = max(stamps) if stamps else time.time()
    revision = f"{int(updated_at * 1000)}-{len(takes)}"
    return revision, updated_at


# ── Read ──────────────────────────────────────────────────────────────

def get_enrollment(user_id: str) -> dict | None:
    """Returns enrollment summary + bundled ref-audio path. Builds bundle on demand."""
    user_dir = _user_dir(user_id)
    if not user_dir.exists():
        return None
    meta = _read_meta(user_id)
    takes = meta.get("takes", [])
    if not takes:
        return None

    bundle_wav, bundle_json = _bundle_paths(user_id)
    if not bundle_wav.exists() or not bundle_json.exists():
        _build_bundle(user_id)
    try:
        binfo = json.loads(bundle_json.read_text())
    except Exception:
        bundle_wav, _ = _build_bundle(user_id)
        binfo = json.loads(bundle_json.read_text())

    ordered = sorted(takes, key=lambda t: t.get("created_at", 0))
    total_raw_s = sum(t.get("duration_s", 0.0) for t in takes)
    revision, updated_at = _profile_revision(user_id, ordered, bundle_wav, bundle_json)
    return {
        "user_id": user_id,
        "takes": [
            {
                "id": t["id"],
                "ref_text": t["ref_text"],
                "duration_s": t.get("duration_s", 0.0),
                "created_at": t.get("created_at", 0.0),
            }
            for t in ordered
        ],
        "ref_path": str(bundle_wav),
        "ref_text": binfo.get("ref_text", ""),
        "duration_s": round(total_raw_s, 2),
        "bundle_duration_s": binfo.get("total_duration_s", 0.0),
        "created_at": ordered[0].get("created_at", time.time()),
        "updated_at": updated_at,
        "revision": revision,
    }


# ── Legacy shim: replace-all behaviour for callers that still rely on it ──

def save_enrollment(user_id: str, wav_16k_mono: np.ndarray, ref_text: str) -> dict:
    """Deprecated single-take replace. Kept for backwards compatibility."""
    delete_enrollment(user_id)
    take = add_take(user_id, wav_16k_mono, ref_text)
    return {
        "user_id": user_id,
        "ref_text": take["ref_text"],
        "duration_s": take["duration_s"],
        "created_at": take["created_at"],
    }
