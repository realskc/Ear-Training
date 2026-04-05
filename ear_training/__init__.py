"""Public package exports for the Ear Training project.

The package keeps most logic in dedicated modules and only re-exports a small,
stable surface here for convenience.
"""
from __future__ import annotations

from pathlib import Path

from .notes import CANONICAL_PITCH_CLASSES, normalize_pitch_class, normalize_pitch_class_set
from .player import LazyPlayer, NotePlayer
from .sample_bank import SampleBank
from .trainer import absolute_train1

__all__ = [
    "CANONICAL_PITCH_CLASSES",
    "SampleBank",
    "NotePlayer",
    "LazyPlayer",
    "play_note",
    "absolute_train1",
    "normalize_pitch_class",
    "normalize_pitch_class_set",
]



def play_note(
    note: str,
    duration: float,
    *,
    sound_dir: str | Path = "sound",
    default_octave: int = 4,
) -> None:
    """Play one note immediately without manually constructing helper objects."""
    player = LazyPlayer(sound_dir=sound_dir, default_octave=default_octave)
    player.play_note(note, duration, block=True)
