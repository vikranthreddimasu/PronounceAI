"""Pitch contour shaping for the frontend overlay.

Both learner and native F0 series are trimmed to phonation onset, resampled to
a fixed length, z-scored on voiced frames only, then encoded with ``None``
sentinels for unvoiced frames so the SVG path breaks cleanly.
"""
from __future__ import annotations

import numpy as np

PITCH_CONTOUR_FRAMES = 80


def _resample_f0(f0: np.ndarray, n_out: int) -> np.ndarray:
    if len(f0) == 0:
        return np.zeros(n_out, dtype=np.float32)
    src_idx = np.linspace(0, len(f0) - 1, n_out)
    return np.interp(src_idx, np.arange(len(f0)), f0).astype(np.float32)


def _voiced_segment_bounds(f0: np.ndarray) -> tuple[int, int]:
    voiced = np.where(f0 > 0)[0]
    if voiced.size == 0:
        return 0, len(f0)
    return int(voiced[0]), int(voiced[-1]) + 1


def _f0_segment_onset_aligned(f0: np.ndarray) -> np.ndarray:
    """Trim leading/trailing unvoiced frames so we compare from phonation onset."""
    f0 = np.asarray(f0, dtype=np.float64)
    if f0.size == 0:
        return f0.astype(np.float32)
    i0, i1 = _voiced_segment_bounds(f0)
    seg = f0[i0:i1]
    if seg.size < 2:
        return f0.astype(np.float32)
    return seg.astype(np.float32)


def _segment_wall_ms(full_len: int, seg_len: int, clip_ms: int) -> int:
    if full_len <= 1:
        return max(int(clip_ms), 1)
    return max(
        1,
        int(round(int(clip_ms) * max(int(seg_len) - 1, 1) / max(full_len - 1, 1))),
    )


def _zscore_voiced(arr: np.ndarray) -> np.ndarray:
    voiced = arr[arr > 0]
    if len(voiced) < 2:
        return arr - arr.mean()
    mean = voiced.mean()
    std = voiced.std()
    if std <= 1e-6:
        return arr - mean
    out = (arr - mean) / std
    out[arr <= 0] = 0.0
    return out


def _contour_to_json(arr: np.ndarray) -> list[float | None]:
    return [None if v == 0.0 else round(float(v), 3) for v in arr]


def build_pitch_contour(
    user_f0: np.ndarray,
    native_f0: np.ndarray,
    *,
    user_duration_ms: int,
    native_duration_ms: int,
) -> dict:
    """Z-scored, equal-length, null-unvoiced pitch contour pair."""
    user_full = np.asarray(user_f0, dtype=np.float32)
    native_full = np.asarray(native_f0, dtype=np.float32)
    user_seg = _f0_segment_onset_aligned(user_full)
    native_seg = _f0_segment_onset_aligned(native_full)

    user_r = _resample_f0(user_seg, PITCH_CONTOUR_FRAMES)
    native_r = _resample_f0(native_seg, PITCH_CONTOUR_FRAMES)

    visual_ms = max(
        _segment_wall_ms(len(user_full), len(user_seg), user_duration_ms),
        _segment_wall_ms(len(native_full), len(native_seg), native_duration_ms),
    )

    return {
        "user": _contour_to_json(_zscore_voiced(user_r)),
        "native": _contour_to_json(_zscore_voiced(native_r)),
        "duration_ms": int(visual_ms),
    }
