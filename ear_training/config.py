"""Centralized configuration defaults for the Ear Training project.

This module is the single place where user-facing and library-facing default
parameters live. Code and documentation should prefer referring to these names
instead of duplicating literal values in multiple files.
"""
from __future__ import annotations

# -----------------------------------------------------------------------------
# Paths / generic defaults
# -----------------------------------------------------------------------------

DEFAULT_SOUND_DIR = "sound"
DEFAULT_OCTAVE = 4
DEFAULT_PLAY_DURATION = 1.0

# -----------------------------------------------------------------------------
# Training defaults
# -----------------------------------------------------------------------------

# Library-level defaults used when ``absolute_train1`` is called directly.
DEFAULT_LIBRARY_ROUNDS = 1
DEFAULT_LIBRARY_DISTRACT_COUNT_RANGE = (6, 10)

# CLI-level defaults used by ``main.py``.
DEFAULT_CLI_ROUNDS = 5
DEFAULT_CLI_DISTRACT_MIN = 10
DEFAULT_CLI_DISTRACT_MAX = 15

# -----------------------------------------------------------------------------
# Sequence rendering / playback defaults
# -----------------------------------------------------------------------------

DEFAULT_DISTRACT_DURATION = 0.32
DEFAULT_DISTRACT_OVERLAP = 0.05
DEFAULT_DISTRACT_FADE_OUT = 0.03
DEFAULT_DISTRACT_FINAL_TAIL = 0.10
DEFAULT_PRE_TARGET_GAP = 0.50
DEFAULT_TARGET_DURATION = 1.80
DEFAULT_SEQUENCE_PEAK_LIMIT = 0.98
