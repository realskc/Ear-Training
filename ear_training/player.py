"""Audio playback helpers built on top of soundfile and sounddevice.

The module reads local WAV samples into NumPy arrays, trims them to the
requested duration and plays them through the system audio device.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from .sample_bank import SampleBank, SampleInfo


class UnsupportedWavFormatError(RuntimeError):
    """Backward-compatible error type kept for API stability."""


class InvalidWavFileError(RuntimeError):
    """Raised when a sample file cannot be opened or contains no audio frames."""


class NotePlayer:
    """Play samples from a ``SampleBank`` by note name or by resolved sample."""

    def __init__(self, sample_bank: SampleBank, default_octave: int = 4) -> None:
        self.sample_bank = sample_bank
        self.default_octave = default_octave
        self._async_buffer: np.ndarray | None = None
        self._async_samplerate: int | None = None

    def play_note(self, note: str, duration: float, *, block: bool = True) -> SampleInfo:
        """Resolve a note string, play the matching sample and return its metadata."""
        sample = self.sample_bank.resolve_sample(note, default_octave=self.default_octave)
        self.play_sample(sample, duration=duration, block=block)
        return sample

    def play_sample(self, sample: SampleInfo, duration: float, *, block: bool = True) -> None:
        """Play one already-resolved sample for the requested duration."""
        data, sample_rate = _read_trimmed_audio(sample.path, duration)

        if not block:
            self._async_buffer = data
            self._async_samplerate = sample_rate
        else:
            self._async_buffer = None
            self._async_samplerate = None

        sd.play(data, sample_rate, blocking=block)

        if block:
            self._async_buffer = None
            self._async_samplerate = None

    def stop(self) -> None:
        """Stop the current playback, if any."""
        self._async_buffer = None
        self._async_samplerate = None
        sd.stop()


class LazyPlayer:
    """Convenience wrapper that constructs ``SampleBank`` and ``NotePlayer`` lazily."""

    def __init__(self, sound_dir: str | Path = "sound", default_octave: int = 4) -> None:
        self.sample_bank = SampleBank(sound_dir)
        self.player = NotePlayer(self.sample_bank, default_octave=default_octave)

    def play_note(self, note: str, duration: float, *, block: bool = True) -> SampleInfo:
        """Play one note through the internally managed ``NotePlayer``."""
        return self.player.play_note(note, duration, block=block)


# -----------------------------------------------------------------------------
# WAV helpers
# -----------------------------------------------------------------------------


def build_trimmed_wav_bytes(wav_path: str | Path, duration: float) -> bytes:
    """Read, trim and re-encode a WAV file as in-memory PCM-16 bytes."""
    data, sample_rate = _read_trimmed_audio(wav_path, duration)

    with io.BytesIO() as buffer:
        buffer.name = "trimmed.wav"
        sf.write(buffer, data, sample_rate, format="WAV", subtype="PCM_16")
        buffer.seek(0)
        return buffer.read()



def get_wav_duration(wav_path: str | Path) -> float:
    """Return the duration of a WAV file in seconds."""
    wav_path = Path(wav_path)

    try:
        with sf.SoundFile(str(wav_path)) as f:
            if f.samplerate <= 0:
                raise InvalidWavFileError(f"无效采样率: {wav_path}")
            return f.frames / f.samplerate
    except Exception as exc:  # pragma: no cover - depends on local files/backend
        raise InvalidWavFileError(f"无法读取音频时长: {wav_path}") from exc



def _read_trimmed_audio(wav_path: str | Path, duration: float) -> tuple[np.ndarray, int]:
    """Load a WAV file, trim it to ``duration`` seconds and return ``(data, sr)``."""
    if duration <= 0:
        raise ValueError("duration 必须大于 0")

    wav_path = Path(wav_path)

    try:
        with sf.SoundFile(str(wav_path)) as f:
            if f.samplerate <= 0:
                raise InvalidWavFileError(f"无效采样率: {wav_path}")
            if f.frames <= 0:
                raise InvalidWavFileError(f"音频文件为空: {wav_path}")

            frames_to_read = max(1, min(f.frames, int(round(duration * f.samplerate))))
            data = f.read(frames=frames_to_read, dtype="float32", always_2d=False)
            sample_rate = int(f.samplerate)
    except InvalidWavFileError:
        raise
    except Exception as exc:  # pragma: no cover - depends on local files/backend
        raise InvalidWavFileError(f"无法读取 WAV 文件: {wav_path}") from exc

    if getattr(data, "size", 0) == 0:
        raise InvalidWavFileError(f"未读取到任何音频帧: {wav_path}")

    if data.ndim == 2 and data.shape[1] == 1:
        data = data[:, 0]

    data = np.ascontiguousarray(data, dtype=np.float32)
    return data, sample_rate
