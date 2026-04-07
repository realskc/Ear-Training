"""Sample indexing and lookup for locally stored piano WAV files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random
from typing import Dict, Iterable, List, Optional, Tuple

from .notes import (
    CANONICAL_PITCH_CLASSES,
    NoteFormatError,
    canonical_to_filename_token,
    format_concrete_note,
    normalize_pitch_class,
    parse_note_name,
)


@dataclass(frozen=True)
class SampleInfo:
    """Immutable description of one concrete WAV sample in the sound directory."""

    path: Path
    octave: int
    pitch_class: str

    @property
    def concrete_name(self) -> str:
        """Return the note name in ``C4``-style form."""
        return format_concrete_note(self.pitch_class, self.octave)

    @property
    def local_filename_style(self) -> str:
        """Return the filename stem in local ``4-cs`` style."""
        return f"{self.octave}-{canonical_to_filename_token(self.pitch_class)}"


class SampleBank:
    """Index and resolve local piano samples stored under one sound directory."""

    def __init__(self, sound_dir: str | Path = "sound") -> None:
        self.sound_dir = Path(sound_dir)
        if not self.sound_dir.exists():
            raise FileNotFoundError(f"未找到 sound 目录: {self.sound_dir}")
        if not self.sound_dir.is_dir():
            raise NotADirectoryError(f"sound 路径不是目录: {self.sound_dir}")

        self._by_concrete: Dict[Tuple[int, str], SampleInfo] = {}
        self._by_pitch_class: Dict[str, List[SampleInfo]] = {pc: [] for pc in CANONICAL_PITCH_CLASSES}
        self._all_samples: List[SampleInfo] = []
        self._scan()

    def _scan(self) -> None:
        """Scan ``sound_dir`` and build in-memory indexes for all recognized samples."""
        wav_files = sorted(self.sound_dir.glob("*.wav"))
        if not wav_files:
            raise FileNotFoundError(f"在 {self.sound_dir} 下未找到任何 .wav 文件")

        for wav_path in wav_files:
            try:
                pitch_class, octave = parse_note_name(wav_path.stem)
            except NoteFormatError:
                continue
            if octave is None:
                continue

            info = SampleInfo(path=wav_path, octave=octave, pitch_class=pitch_class)
            self._by_concrete[(octave, pitch_class)] = info
            self._by_pitch_class[pitch_class].append(info)
            self._all_samples.append(info)

        if not self._all_samples:
            raise RuntimeError(
                f"{self.sound_dir} 中存在 wav 文件，但没有一个符合形如 4-cs.wav 的命名规则"
            )

        for items in self._by_pitch_class.values():
            items.sort(key=lambda s: s.octave)

    def resolve_sample(
        self,
        note: str,
        *,
        default_octave: int = 4,
        nearest_octave_if_missing: bool = True,
    ) -> SampleInfo:
        """Resolve one user-supplied note string into the best matching sample."""
        pitch_class, octave = parse_note_name(note, default_octave=default_octave)
        candidates = self._by_pitch_class.get(pitch_class, [])
        if not candidates:
            raise KeyError(f"音高类别 {pitch_class} 在样本库中不存在")

        if octave is None:
            octave = default_octave

        exact = self._by_concrete.get((octave, pitch_class))
        if exact is not None:
            return exact

        if not nearest_octave_if_missing:
            raise KeyError(f"未找到精确样本: {pitch_class}{octave}")

        return min(candidates, key=lambda s: (abs(s.octave - octave), s.octave))

    def choose_random_sample(
        self,
        *,
        exclude: Optional[SampleInfo] = None,
        rng: Optional[random.Random] = None,
    ) -> SampleInfo:
        """Choose one random sample, optionally avoiding the previous sample."""
        items = self._all_samples
        if exclude is None:
            return (rng or random).choice(items)

        filtered = [sample for sample in items if sample != exclude]
        if not filtered:
            return exclude
        return (rng or random).choice(filtered)

    def choose_random_from_pitch_class(
        self,
        pitch_class: str,
        *,
        rng: Optional[random.Random] = None,
    ) -> SampleInfo:
        """Choose a random sample from one pitch class across all available octaves."""
        canonical = normalize_pitch_class(pitch_class)
        items = self._by_pitch_class.get(canonical, [])
        if not items:
            raise KeyError(f"音高类别 {canonical} 在样本库中不存在")
        return (rng or random).choice(items)

    def validate_pitch_class_subset(self, pitch_classes: Iterable[str]) -> list[str]:
        """Ensure every requested pitch class exists in the sample bank."""
        validated: list[str] = []
        missing: list[str] = []
        for pitch_class in pitch_classes:
            canonical = normalize_pitch_class(pitch_class)
            if self._by_pitch_class.get(canonical):
                validated.append(canonical)
            else:
                missing.append(canonical)
        if missing:
            missing_text = ", ".join(missing)
            raise ValueError(f"样本库里没有这些音高类别: {missing_text}")
        return validated
