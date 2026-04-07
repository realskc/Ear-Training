"""Public exports for the Ear Training package.

The package keeps most logic in dedicated modules and exposes only a small,
stable surface here. There are intentionally no convenience wrappers that build
temporary objects behind the scenes; callers should construct ``SampleBank`` and
``NotePlayer`` explicitly when they need playback.
"""
from __future__ import annotations

from . import config
from .notes import CANONICAL_PITCH_CLASSES, normalize_pitch_class, normalize_pitch_class_set
from .player import InvalidWavFileError, NotePlayer
from .sample_bank import SampleBank, SampleInfo
from .trainer import TrainRoundResult, absolute_train1

__all__ = [
    "CANONICAL_PITCH_CLASSES",
    "config",
    "SampleBank",
    "SampleInfo",
    "NotePlayer",
    "InvalidWavFileError",
    "TrainRoundResult",
    "absolute_train1",
    "normalize_pitch_class",
    "normalize_pitch_class_set",
]
