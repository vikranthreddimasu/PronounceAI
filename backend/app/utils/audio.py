"""
Audio preprocessing utilities: VAD, resampling, quality gate.
All functions return 16 kHz mono float32 tensors.
"""
import io
import numpy as np
import soundfile as sf
import torch
import torchaudio

TARGET_SR = 16_000
MIN_DURATION_S = 0.5
MAX_DURATION_S = 30.0
MIN_SNR_DB = 5.0


class AudioError(ValueError):
    pass


def load_audio(data: bytes) -> tuple[torch.Tensor, int]:
    """
    Load raw audio bytes → (waveform [1, T], sample_rate).
    Handles any format the browser can produce (webm/opus, ogg, mp4, wav)
    by piping through FFmpeg when torchaudio/soundfile can't decode directly.
    """
    buf = io.BytesIO(data)

    # 1. Try torchaudio with ffmpeg backend (handles webm/opus natively)
    try:
        buf.seek(0)
        wav, sr = torchaudio.load(buf, backend="ffmpeg")
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)
        return wav, sr
    except Exception:
        pass

    # 2. Try torchaudio default backend (works for wav/flac)
    try:
        buf.seek(0)
        wav, sr = torchaudio.load(buf)
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)
        return wav, sr
    except Exception:
        pass

    # 3. Subprocess FFmpeg: decode anything → 16kHz mono PCM f32le → soundfile
    try:
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", "pipe:0",
                    "-ac", "1", "-ar", "16000",
                    "-f", "wav", tmp_path,
                ],
                input=data,
                capture_output=True,
                timeout=15,
            )
            if proc.returncode == 0:
                arr, sr = sf.read(tmp_path, always_2d=False)
                wav = torch.from_numpy(arr.astype("float32")).unsqueeze(0)
                return wav, sr
        finally:
            os.unlink(tmp_path)
    except Exception:
        pass

    raise RuntimeError("Could not decode audio — unsupported format.")


def resample(wav: torch.Tensor, src_sr: int, tgt_sr: int = TARGET_SR) -> torch.Tensor:
    if src_sr == tgt_sr:
        return wav
    resampler = torchaudio.transforms.Resample(src_sr, tgt_sr)
    return resampler(wav)


def quality_gate(wav: torch.Tensor, sr: int) -> None:
    """Raise AudioError if the recording fails basic quality checks."""
    duration = wav.shape[-1] / sr
    if duration < MIN_DURATION_S:
        raise AudioError(f"Recording too short ({duration:.1f}s). Please record at least 0.5 seconds.")
    if duration > MAX_DURATION_S:
        raise AudioError(f"Recording too long ({duration:.1f}s). Please keep it under 30 seconds.")

    # Clipping detection: > 1% of samples saturated
    clipped = (wav.abs() > 0.98).float().mean().item()
    if clipped > 0.01:
        raise AudioError("Recording is clipped. Please move back from the microphone or reduce volume.")

    # SNR estimate: signal power vs noise floor (first 0.2s)
    noise_samples = int(0.2 * sr)
    if wav.shape[-1] > noise_samples * 2:
        noise_power = wav[..., :noise_samples].pow(2).mean().item()
        signal_power = wav.pow(2).mean().item()
        if noise_power > 0 and signal_power > 0:
            snr = 10 * np.log10(signal_power / noise_power)
            if snr < MIN_SNR_DB:
                raise AudioError(f"Too much background noise (SNR {snr:.0f} dB). Please record in a quieter environment.")


SILENCE_FRAME_MS = 20
SILENCE_PREROLL_MS = 80
SILENCE_RMS_FLOOR = 0.012


def trim_leading_silence(wav: torch.Tensor, sr: int) -> torch.Tensor:
    """
    Strip leading silence so downstream alignment / pitch contour starts at speech
    onset rather than button-press timestamp. Uses short-window RMS with a small
    pre-roll buffer so we don't bite into the first phoneme attack.
    """
    if wav.ndim != 2 or wav.shape[-1] < sr // 5:
        return wav
    frame = max(1, int(sr * SILENCE_FRAME_MS / 1000))
    pcm = wav[0]
    if pcm.shape[0] < frame * 2:
        return wav
    # Trim to multiple of frame to vectorise RMS
    usable = pcm.shape[0] - (pcm.shape[0] % frame)
    frames = pcm[:usable].view(-1, frame)
    rms = frames.pow(2).mean(dim=1).sqrt()
    if rms.numel() == 0:
        return wav
    peak = float(rms.max().item())
    threshold = max(SILENCE_RMS_FLOOR, peak * 0.18)
    voiced = (rms >= threshold).nonzero(as_tuple=False)
    if voiced.numel() == 0:
        return wav
    onset_frame = int(voiced[0].item())
    preroll_frames = max(1, int(SILENCE_PREROLL_MS / SILENCE_FRAME_MS))
    onset_frame = max(0, onset_frame - preroll_frames)
    onset_sample = onset_frame * frame
    if onset_sample <= frame:
        return wav
    return wav[..., onset_sample:].contiguous()


def preprocess(data: bytes) -> tuple[torch.Tensor, int]:
    """
    Full preprocessing pipeline:
      load → mono → quality gate → resample to 16kHz → trim leading silence
    Returns (wav_16k [1, T], 16000)
    """
    wav, sr = load_audio(data)
    quality_gate(wav, sr)
    wav = resample(wav, sr, TARGET_SR)
    wav = trim_leading_silence(wav, TARGET_SR)
    # Peak-normalise
    peak = wav.abs().max()
    if peak > 0:
        wav = wav / peak * 0.95
    return wav, TARGET_SR
