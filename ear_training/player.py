"""Audio playback and sequence-rendering helpers for Ear Training.

This module is responsible for loading local WAV samples into NumPy arrays and
playing them with ``sounddevice``. In addition to single-note playback, it can
render a short legato-style sequence by placing multiple note clips on one
timeline with a small overlap and a fade-out, then playing the whole phrase in
one call. That approach sounds more natural than repeatedly starting and
stopping the output device for every distractor note.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Sequence

import numpy as np
import sounddevice as sd
import soundfile as sf

from .sample_bank import SampleBank, SampleInfo

DEFAULT_LEGATO_OVERLAP = 0.05
DEFAULT_LEGATO_FADE_OUT = 0.03
DEFAULT_LEGATO_FINAL_TAIL = 0.10
DEFAULT_SEQUENCE_PEAK_LIMIT = 0.98


class UnsupportedWavFormatError(RuntimeError):
    """Backward-compatible error type kept for API stability."""


class InvalidWavFileError(RuntimeError):
    """Raised when a sample file cannot be opened or contains no audio frames."""


class NotePlayer:
    """Play samples from a :class:`~ear_training.sample_bank.SampleBank`.

    The class supports both one-off single-note playback and rendering/playing a
    short legato sequence. The latter is mainly used by the training flow to
    make distractor notes sound more continuous and less mechanically chopped.
    """

    def __init__(self, sample_bank: SampleBank, default_octave: int = 4) -> None:
        """Create a player bound to one sample bank."""
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
        self._play_array(data, sample_rate, block=block)

    def render_legato_sequence(
        self,
        notes: Sequence[str],
        note_duration: float,
        *,
        overlap: float = DEFAULT_LEGATO_OVERLAP,
        fade_out: float = DEFAULT_LEGATO_FADE_OUT,
        final_tail: float = DEFAULT_LEGATO_FINAL_TAIL,
    ) -> tuple[np.ndarray, int, list[SampleInfo]]:
        """Resolve note names and render them as one legato-style phrase.

        Args:
            notes: Note names such as ``["C4", "E4", "G4"]``.
            note_duration: Nominal duration of each note inside the sequence.
            overlap: Amount of time in seconds during which adjacent notes overlap.
            fade_out: Linear fade-out applied to the end of every clip.
            final_tail: Extra ring-out added only to the last note.

        Returns:
            A tuple of ``(audio, sample_rate, resolved_samples)`` where ``audio``
            is ready for playback with ``sounddevice``.
        """
        resolved_samples = [
            self.sample_bank.resolve_sample(note, default_octave=self.default_octave)
            for note in notes
        ]
        audio, sample_rate = self.render_sample_sequence(
            resolved_samples,
            note_duration,
            overlap=overlap,
            fade_out=fade_out,
            final_tail=final_tail,
        )
        return audio, sample_rate, resolved_samples

    def play_legato_sequence(
        self,
        notes: Sequence[str],
        note_duration: float,
        *,
        overlap: float = DEFAULT_LEGATO_OVERLAP,
        fade_out: float = DEFAULT_LEGATO_FADE_OUT,
        final_tail: float = DEFAULT_LEGATO_FINAL_TAIL,
        block: bool = True,
    ) -> list[SampleInfo]:
        """Render and play a legato-style phrase from note names."""
        audio, sample_rate, resolved_samples = self.render_legato_sequence(
            notes,
            note_duration,
            overlap=overlap,
            fade_out=fade_out,
            final_tail=final_tail,
        )
        self._play_array(audio, sample_rate, block=block)
        return resolved_samples

    def render_sample_sequence(
        self,
        samples: Sequence[SampleInfo],
        note_duration: float,
        *,
        overlap: float = DEFAULT_LEGATO_OVERLAP,
        fade_out: float = DEFAULT_LEGATO_FADE_OUT,
        final_tail: float = DEFAULT_LEGATO_FINAL_TAIL,
    ) -> tuple[np.ndarray, int]:
        """Render resolved samples into one legato-style phrase.

        Formal timing semantics:

        - For non-final samples, the clip length is ``note_duration``.
        - For the final sample, the clip length is
          ``note_duration + final_tail``.
        - Adjacent clip starts are spaced by ``note_duration - overlap``.
          Therefore ``overlap`` is *contained inside* the nominal note duration;
          it is not an extra tail appended after the slot.
        - ``fade_out`` only shapes the end of each clip. It does not extend any
          clip and does not change the clip start times.

        Ignoring frame-rounding effects, a sequence of ``N`` samples has the
        theoretical total duration::

            N * note_duration - (N - 1) * overlap + final_tail
        """
        _validate_legato_params(
            note_duration=note_duration,
            overlap=overlap,
            fade_out=fade_out,
            final_tail=final_tail,
        )

        if not samples:
            raise ValueError("samples 不能为空")

        prepared: list[tuple[np.ndarray, int]] = []
        target_sample_rate: int | None = None

        for index, sample in enumerate(samples):
            clip_duration = note_duration + (final_tail if index == len(samples) - 1 else 0.0)
            data, sample_rate = _read_trimmed_audio(sample.path, clip_duration)
            data = _ensure_2d(data)
            data = _apply_fade_out(data, sample_rate, fade_out)

            if target_sample_rate is None:
                target_sample_rate = sample_rate
            elif sample_rate != target_sample_rate:
                data = _resample_audio_linear(data, sample_rate, target_sample_rate)
                sample_rate = target_sample_rate

            prepared.append((data, sample_rate))

        assert target_sample_rate is not None

        target_channels = max(data.shape[1] for data, _ in prepared)
        prepared = [(_match_channel_count(data, target_channels), sample_rate) for data, sample_rate in prepared]

        step_seconds = note_duration - overlap
        step_frames = max(1, int(round(step_seconds * target_sample_rate)))

        total_frames = 0
        for index, (data, _sample_rate) in enumerate(prepared):
            start_frame = index * step_frames
            total_frames = max(total_frames, start_frame + data.shape[0])

        phrase = np.zeros((total_frames, target_channels), dtype=np.float32)

        for index, (data, _sample_rate) in enumerate(prepared):
            start_frame = index * step_frames
            end_frame = start_frame + data.shape[0]
            phrase[start_frame:end_frame] += data

        phrase = _limit_peak(phrase, peak_limit=DEFAULT_SEQUENCE_PEAK_LIMIT)
        phrase = np.ascontiguousarray(_squeeze_if_mono(phrase), dtype=np.float32)
        return phrase, target_sample_rate

    def play_sample_sequence(
        self,
        samples: Sequence[SampleInfo],
        note_duration: float,
        *,
        overlap: float = DEFAULT_LEGATO_OVERLAP,
        fade_out: float = DEFAULT_LEGATO_FADE_OUT,
        final_tail: float = DEFAULT_LEGATO_FINAL_TAIL,
        block: bool = True,
    ) -> None:
        """Render resolved samples into a phrase and play it."""
        audio, sample_rate = self.render_sample_sequence(
            samples,
            note_duration,
            overlap=overlap,
            fade_out=fade_out,
            final_tail=final_tail,
        )
        self._play_array(audio, sample_rate, block=block)

    def stop(self) -> None:
        """Stop the current playback, if any."""
        self._async_buffer = None
        self._async_samplerate = None
        sd.stop()

    def _play_array(self, data: np.ndarray, sample_rate: int, *, block: bool) -> None:
        """Play an already-prepared audio array."""
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


class LazyPlayer:
    """Convenience wrapper that constructs :class:`SampleBank` and :class:`NotePlayer`."""

    def __init__(self, sound_dir: str | Path = "sound", default_octave: int = 4) -> None:
        """Create the underlying sample bank and player lazily for one-off usage."""
        self.sample_bank = SampleBank(sound_dir)
        self.player = NotePlayer(self.sample_bank, default_octave=default_octave)

    def play_note(self, note: str, duration: float, *, block: bool = True) -> SampleInfo:
        """Play one note through the internally managed :class:`NotePlayer`."""
        return self.player.play_note(note, duration, block=block)

    def play_legato_sequence(
        self,
        notes: Sequence[str],
        note_duration: float,
        *,
        overlap: float = DEFAULT_LEGATO_OVERLAP,
        fade_out: float = DEFAULT_LEGATO_FADE_OUT,
        final_tail: float = DEFAULT_LEGATO_FINAL_TAIL,
        block: bool = True,
    ) -> list[SampleInfo]:
        """Play a legato-style phrase through the internally managed player."""
        return self.player.play_legato_sequence(
            notes,
            note_duration,
            overlap=overlap,
            fade_out=fade_out,
            final_tail=final_tail,
            block=block,
        )


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


def _validate_legato_params(
    *,
    note_duration: float,
    overlap: float,
    fade_out: float,
    final_tail: float,
) -> None:
    """Validate parameters shared by the legato sequence helpers."""
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
    """Convert a mono array to ``(frames, 1)`` and keep stereo arrays unchanged."""
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


def _resample_audio_linear(data: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Resample audio with simple linear interpolation.

    The piano samples in this project are usually stored at one sample rate, so
    this path is mainly a small compatibility fallback. It avoids introducing a
    heavier dependency just for occasional mismatches.
    """
    if source_rate == target_rate:
        return data

    if source_rate <= 0 or target_rate <= 0:
        raise InvalidWavFileError("采样率必须为正整数")

    arr = _ensure_2d(data)
    source_frames = arr.shape[0]
    if source_frames == 1:
        return np.repeat(arr, max(1, int(round(target_rate / source_rate))), axis=0)

    target_frames = max(1, int(round(source_frames * target_rate / source_rate)))
    positions = np.arange(target_frames, dtype=np.float64) * (source_rate / target_rate)
    left = np.floor(positions).astype(np.int64)
    right = np.clip(left + 1, 0, source_frames - 1)
    frac = (positions - left).astype(np.float32)[:, None]

    left = np.clip(left, 0, source_frames - 1)
    resampled = arr[left] * (1.0 - frac) + arr[right] * frac
    return np.ascontiguousarray(resampled, dtype=np.float32)


def _match_channel_count(data: np.ndarray, target_channels: int) -> np.ndarray:
    """Expand mono audio to the requested channel count."""
    arr = _ensure_2d(data)
    channels = arr.shape[1]
    if channels == target_channels:
        return arr
    if channels == 1 and target_channels > 1:
        return np.repeat(arr, target_channels, axis=1)
    raise InvalidWavFileError(
        f"不支持的声道数混合: 当前 {channels} 声道, 目标 {target_channels} 声道"
    )


def _limit_peak(data: np.ndarray, *, peak_limit: float) -> np.ndarray:
    """Scale the phrase down if overlap summing would otherwise clip."""
    if peak_limit <= 0:
        raise ValueError("peak_limit 必须大于 0")

    arr = np.asarray(data, dtype=np.float32)
    max_abs = float(np.max(np.abs(arr))) if arr.size else 0.0
    if max_abs <= peak_limit or max_abs == 0.0:
        return arr
    return np.ascontiguousarray(arr * (peak_limit / max_abs), dtype=np.float32)
