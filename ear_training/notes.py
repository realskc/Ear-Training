"""Utilities for parsing and normalizing note names.

This module is the single source of truth for how user input maps to canonical
pitch classes and local sample-file naming tokens.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Tuple

CANONICAL_PITCH_CLASSES = [
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
]

_ALIAS_TO_CANONICAL = {
    "c": "C",
    "b#": "C",
    "cs": "C#",
    "c#": "C#",
    "db": "C#",
    "d": "D",
    "ds": "D#",
    "d#": "D#",
    "eb": "D#",
    "e": "E",
    "fb": "E",
    "f": "F",
    "e#": "F",
    "fs": "F#",
    "f#": "F#",
    "gb": "F#",
    "g": "G",
    "gs": "G#",
    "g#": "G#",
    "ab": "G#",
    "a": "A",
    "as": "A#",
    "a#": "A#",
    "bb": "A#",
    "b": "B",
    "cb": "B",
}

_CANONICAL_TO_FILENAME = {
    "C": "c",
    "C#": "cs",
    "D": "d",
    "D#": "ds",
    "E": "e",
    "F": "f",
    "F#": "fs",
    "G": "g",
    "G#": "gs",
    "A": "a",
    "A#": "as",
    "B": "b",
}


class NoteFormatError(ValueError):
    """Raised when a note name cannot be parsed into a supported format."""


_STANDARD_NOTE_RE = re.compile(r"^([A-Ga-g])([#bBsS]?)(-?\d+)?$")
_FILENAME_STYLE_RE = re.compile(r"^(\d+)-([a-g](?:s)?)$", re.IGNORECASE)


def normalize_pitch_class(name: str) -> str:
    """Normalize one note-like input into a canonical sharp-based pitch class."""
    pitch_class, _ = parse_note_name(name)
    return pitch_class



def parse_note_name(note: str, default_octave: Optional[int] = None) -> Tuple[str, Optional[int]]:
    """Parse a note string and return ``(pitch_class, octave_or_none)``.

    Supported forms include ``C4``, ``C#4``, ``Db4``, ``C``, ``cs`` and the
    local filename style ``4-cs``.
    """
    if not isinstance(note, str):
        raise NoteFormatError(f"音名必须是字符串，收到: {type(note)!r}")

    raw = note.strip().replace("♯", "#").replace("♭", "b")
    if not raw:
        raise NoteFormatError("音名不能为空")

    filename_match = _FILENAME_STYLE_RE.fullmatch(raw)
    if filename_match:
        octave_text, token = filename_match.groups()
        pitch_class = _normalize_token(token)
        return pitch_class, int(octave_text)

    compact = raw.replace(" ", "")
    match = _STANDARD_NOTE_RE.fullmatch(compact)
    if not match:
        raise NoteFormatError(
            f"无法识别音名: {note!r}。支持示例: C4, C#4, Db4, C, cs, 4-cs"
        )

    letter, accidental, octave_text = match.groups()
    token = letter.lower() + accidental.lower().replace("s", "#")
    pitch_class = _normalize_token(token)
    octave = int(octave_text) if octave_text is not None else default_octave
    return pitch_class, octave


def canonical_to_filename_token(pitch_class: str) -> str:
    """Convert a canonical pitch class into the filename token used by samples."""
    canonical = normalize_pitch_class(pitch_class)
    return _CANONICAL_TO_FILENAME[canonical]


def normalize_pitch_class_set(values: Iterable[str]) -> list[str]:
    """Normalize a sequence of note-like values into a de-duplicated pitch-class list."""
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        pitch_class = normalize_pitch_class(value)
        if pitch_class not in seen:
            seen.add(pitch_class)
            normalized.append(pitch_class)
    if not normalized:
        raise ValueError("音集合 S 不能为空")
    return normalized


def format_concrete_note(pitch_class: str, octave: int) -> str:
    """Format a canonical pitch class and octave as a user-facing note name."""
    return f"{pitch_class}{octave}"


def _normalize_token(token: str) -> str:
    """Normalize one pitch token such as ``db`` or ``fs`` to canonical form."""
    normalized = token.strip().lower().replace("♯", "#").replace("♭", "b")
    normalized = normalized.replace("s", "#") if normalized.endswith("s") else normalized
    canonical = _ALIAS_TO_CANONICAL.get(normalized)
    if canonical is None:
        raise NoteFormatError(f"无法识别音名: {token!r}")
    return canonical
