"""Public package exports for the Ear Training project.

The package keeps most logic in dedicated modules and only re-exports a small,
stable surface here for convenience.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .notes import CANONICAL_PITCH_CLASSES, normalize_pitch_class, normalize_pitch_class_set
from .player import (
    DEFAULT_LEGATO_FADE_OUT,
    DEFAULT_LEGATO_FINAL_TAIL,
    DEFAULT_LEGATO_OVERLAP,
    LazyPlayer,
    NotePlayer,
)
from .sample_bank import SampleBank
from .trainer import absolute_train1

__all__ = [
    "CANONICAL_PITCH_CLASSES",
    "SampleBank",
    "NotePlayer",
    "LazyPlayer",
    "play_note",
    "play_legato_sequence",
    "absolute_train1",
    "normalize_pitch_class",
    "normalize_pitch_class_set",
    "DEFAULT_LEGATO_OVERLAP",
    "DEFAULT_LEGATO_FADE_OUT",
    "DEFAULT_LEGATO_FINAL_TAIL",
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


def play_legato_sequence(
    notes: Sequence[str],
    note_duration: float,
    *,
    sound_dir: str | Path = "sound",
    default_octave: int = 4,
    overlap: float = DEFAULT_LEGATO_OVERLAP,
    fade_out: float = DEFAULT_LEGATO_FADE_OUT,
    final_tail: float = DEFAULT_LEGATO_FINAL_TAIL,
) -> None:
    """Play a short legato-style phrase without manually constructing helper objects."""
    player = LazyPlayer(sound_dir=sound_dir, default_octave=default_octave)
    player.play_legato_sequence(
        notes,
        note_duration,
        overlap=overlap,
        fade_out=fade_out,
        final_tail=final_tail,
        block=True,
    )
