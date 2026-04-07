"""Audio playback and phrase-rendering helpers for Ear Training.

This module loads local WAV samples with ``soundfile`` and plays them with
``sounddevice``. It supports two core operations:

- play one concrete sample or note name for a requested duration
- render a distractor phrase by placing several sample clips on one shared
  timeline, then play the whole phrase in one output call

The renderer deliberately assumes that the local piano sample set is internally
consistent. In particular, all samples are expected to use the same sample rate
and the same channel count. If that assumption is broken, the renderer raises an
error instead of silently resampling or reshaping channels.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import sounddevice as sd
import soundfile as sf

from .config import (
    DEFAULT_DISTRACT_FADE_OUT,
    DEFAULT_DISTRACT_FINAL_TAIL,
    DEFAULT_DISTRACT_OVERLAP,
    DEFAULT_OCTAVE,
    DEFAULT_SEQUENCE_PEAK_LIMIT,
)
from .sample_bank import SampleBank, SampleInfo


class InvalidWavFileError(RuntimeError):
    """Raised when a sample file cannot be opened or violates project assumptions."""


class NotePlayer:
    """Play samples from one :class:`~ear_training.sample_bank.SampleBank`.

    ``NotePlayer`` is intentionally small. It does not try to be a generic audio
    engine; it only implements the playback behavior needed by this project.
    """

    def __init__(self, sample_bank: SampleBank, default_octave: int = DEFAULT_OCTAVE) -> None:
        """Create a player bound to one sample bank."""
        self.sample_bank = sample_bank
        self.default_octave = default_octave
        self._async_buffer: np.ndarray | None = None
        self._async_samplerate: int | None = None

    def play_note(self, note: str, duration: float, *, block: bool = True) -> SampleInfo:
        """Resolve one note string, play the matching sample and return its metadata."""
        sample = self.sample_bank.resolve_sample(note, default_octave=self.default_octave)
        self.play_sample(sample, duration=duration, block=block)
        return sample

    def play_sample(self, sample: SampleInfo, duration: float, *, block: bool = True) -> None:
        """Play one already-resolved sample for the requested duration."""
        data, sample_rate = _read_trimmed_audio(sample.path, duration)
        self._play_array(data, sample_rate, block=block)

    def render_sample_sequence(
        self,
        samples: Sequence[SampleInfo],
        note_duration: float,
        *,
        overlap: float = DEFAULT_DISTRACT_OVERLAP,
        fade_out: float = DEFAULT_DISTRACT_FADE_OUT,
        final_tail: float = DEFAULT_DISTRACT_FINAL_TAIL,
    ) -> tuple[np.ndarray, int]:
        """Render resolved samples into one legato-style phrase.

        Formal timing semantics, ignoring frame-rounding effects:

        - every non-final clip has length ``note_duration``
        - the final clip has length ``note_duration + final_tail``
        - adjacent clip starts are spaced by ``note_duration - overlap``
        - therefore ``overlap`` is *contained inside* the nominal duration; it
          is not an extra tail appended afterward
        - ``fade_out`` only shapes the end of each clip and does not change any
          clip start time or clip length

        For ``N >= 1`` samples, the theoretical total phrase duration is::

            N * note_duration - (N - 1) * overlap + final_tail

        This method requires at least one sample. Higher-level code that wants to
        allow zero distractors should short-circuit before calling it.
        """
        _validate_legato_params(
            note_duration=note_duration,
            overlap=overlap,
            fade_out=fade_out,
            final_tail=final_tail,
        )

        if not samples:
            raise ValueError("render_sample_sequence 需要至少一个 sample")

        prepared: list[np.ndarray] = []
        target_sample_rate: int | None = None
        target_channels: int | None = None

        for index, sample in enumerate(samples):
            clip_duration = note_duration + (final_tail if index == len(samples) - 1 else 0.0)
            data, sample_rate = _read_trimmed_audio(sample.path, clip_duration)
            clip = _ensure_2d(data)
            clip = _apply_fade_out(clip, sample_rate, fade_out)

            if target_sample_rate is None:
                target_sample_rate = sample_rate
                target_channels = clip.shape[1]
            else:
                if sample_rate != target_sample_rate:
                    raise InvalidWavFileError(
                        f"样本采样率不一致: 期望 {target_sample_rate}, 实际 {sample_rate}, 文件 {sample.path}"
                    )
                if clip.shape[1] != target_channels:
                    raise InvalidWavFileError(
                        f"样本声道数不一致: 期望 {target_channels}, 实际 {clip.shape[1]}, 文件 {sample.path}"
                    )

            prepared.append(clip)

        assert target_sample_rate is not None
        assert target_channels is not None

        step_frames = max(1, int(round((note_duration - overlap) * target_sample_rate)))
        total_frames = 0
        for index, clip in enumerate(prepared):
            start_frame = index * step_frames
            total_frames = max(total_frames, start_frame + clip.shape[0])

        phrase = np.zeros((total_frames, target_channels), dtype=np.float32)
        for index, clip in enumerate(prepared):
            start_frame = index * step_frames
            end_frame = start_frame + clip.shape[0]
            phrase[start_frame:end_frame] += clip

        phrase = _limit_peak(phrase, peak_limit=DEFAULT_SEQUENCE_PEAK_LIMIT)
        return _squeeze_if_mono(phrase), target_sample_rate

    def play_sample_sequence(
        self,
        samples: Sequence[SampleInfo],
        note_duration: float,
        *,
        overlap: float = DEFAULT_DISTRACT_OVERLAP,
        fade_out: float = DEFAULT_DISTRACT_FADE_OUT,
        final_tail: float = DEFAULT_DISTRACT_FINAL_TAIL,
        block: bool = True,
    ) -> None:
        """Render and play a legato-style phrase from already-resolved samples."""
        if not samples:
            return
        audio, sample_rate = self.render_sample_sequence(
            samples,
            note_duration,
            overlap=overlap,
            fade_out=fade_out,
            final_tail=final_tail,
        )
        self._play_array(audio, sample_rate, block=block)

    def stop(self) -> None:
        """Stop current playback."""
        self._async_buffer = None
        self._async_samplerate = None
        sd.stop()

    def _play_array(self, data: np.ndarray, sample_rate: int, *, block: bool) -> None:
        """Play one prepared NumPy audio buffer."""
        audio = np.ascontiguousarray(data, dtype=np.float32)
        sd.stop()
        if not block:
            self._async_buffer = audio
            self._async_samplerate = sample_rate
        else:
            self._async_buffer = None
            self._async_samplerate = None
        sd.play(audio, sample_rate, blocking=block)


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


def _validate_legato_params(
    *,
    note_duration: float,
    overlap: float,
    fade_out: float,
    final_tail: float,
) -> None:
    """Validate parameters shared by the phrase renderer."""
    if note_duration <= 0:
        raise ValueError("note_duration 必须大于 0")
    if overlap < 0:
        raise ValueError("overlap 不能小于 0")
    if overlap >= note_duration:
        raise ValueError("overlap 必须小于 note_duration")
    if fade_out < 0:
        raise ValueError("fade_out 不能小于 0")
    if final_tail < 0:
        raise ValueError("final_tail 不能小于 0")


def _ensure_2d(data: np.ndarray) -> np.ndarray:
    """Convert mono audio to ``(frames, 1)`` and keep 2-D audio unchanged."""
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 1:
        return np.ascontiguousarray(arr[:, None], dtype=np.float32)
    if arr.ndim == 2:
        return np.ascontiguousarray(arr, dtype=np.float32)
    raise InvalidWavFileError(f"不支持的音频维度: {arr.ndim}")


def _squeeze_if_mono(data: np.ndarray) -> np.ndarray:
    """Convert ``(frames, 1)`` back to a 1-D mono array."""
    if data.ndim == 2 and data.shape[1] == 1:
        return data[:, 0]
    return data


def _apply_fade_out(data: np.ndarray, sample_rate: int, fade_out: float) -> np.ndarray:
    """Apply a linear fade-out to the end of one clip."""
    if fade_out <= 0:
        return data

    arr = np.array(data, dtype=np.float32, copy=True)
    frames = arr.shape[0]
    fade_frames = min(frames, max(1, int(round(fade_out * sample_rate))))
    ramp = np.linspace(1.0, 0.0, num=fade_frames, endpoint=True, dtype=np.float32)
    arr[-fade_frames:] *= ramp[:, None]
    return arr


def _limit_peak(data: np.ndarray, *, peak_limit: float) -> np.ndarray:
    """Scale the phrase down if overlap summing would otherwise clip."""
    if peak_limit <= 0:
        raise ValueError("peak_limit 必须大于 0")

    arr = np.asarray(data, dtype=np.float32)
    max_abs = float(np.max(np.abs(arr))) if arr.size else 0.0
    if max_abs <= peak_limit or max_abs == 0.0:
        return arr
    return np.ascontiguousarray(arr * (peak_limit / max_abs), dtype=np.float32)
