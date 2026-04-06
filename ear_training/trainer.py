"""Console-based ear-training flows built on top of the core package modules."""
from __future__ import annotations

from dataclasses import dataclass
import random
import time
from pathlib import Path
from typing import Optional, Sequence

from .notes import NoteFormatError, normalize_pitch_class, normalize_pitch_class_set
from .player import (
    DEFAULT_LEGATO_FADE_OUT,
    DEFAULT_LEGATO_FINAL_TAIL,
    DEFAULT_LEGATO_OVERLAP,
    NotePlayer,
)
from .sample_bank import SampleBank, SampleInfo

DEFAULT_DISTRACT_DURATION = 0.42
DEFAULT_TARGET_DURATION = 1.2
DEFAULT_PRE_TARGET_GAP = 0.50


@dataclass
class TrainRoundResult:
    """Result of one completed training round."""

    round_index: int
    target_pitch_class: str
    target_sample_name: str
    guess_pitch_class: Optional[str]
    correct: bool


def absolute_train1(
    S: Sequence[str],
    *,
    sound_dir: str | Path = "sound",
    rounds: int = 1,
    distract_count_range: tuple[int, int] = (6, 10),
    distract_duration: float = DEFAULT_DISTRACT_DURATION,
    target_duration: float = DEFAULT_TARGET_DURATION,
    gap_seconds: float | None = None,
    distract_overlap: float = DEFAULT_LEGATO_OVERLAP,
    distract_fade_out: float = DEFAULT_LEGATO_FADE_OUT,
    distract_final_tail: float = DEFAULT_LEGATO_FINAL_TAIL,
    pre_target_gap: float = DEFAULT_PRE_TARGET_GAP,
    default_octave: int = 4,
    seed: Optional[int] = None,
) -> list[TrainRoundResult]:
    """Run the v1 absolute-pitch exercise and return per-round results.

    The exercise first renders the distractor notes into one legato-style
    phrase, then waits for a short silence, then plays one target note. The
    user enters a guess in the console, and correctness is decided only by
    pitch class, ignoring octave.

    Timing model, ignoring tiny frame-rounding effects:

    - Each distractor note uses ``distract_duration`` as its nominal slot
      duration.
    - Adjacent distractor note starts are separated by
      ``distract_duration - distract_overlap``.
    - Only the final distractor note receives the extra
      ``distract_final_tail`` ring-out.
    - After the distractor phrase finishes, the program waits exactly
      ``pre_target_gap`` seconds before playing the target note.

    Args:
        S: Target pitch-class subset used to draw the question note.
        sound_dir: Directory that contains local WAV samples.
        rounds: Number of rounds to run.
        distract_count_range: Inclusive range for the number of distractor notes.
        distract_duration: Nominal duration of each distractor note.
        target_duration: Playback duration of the target note.
        gap_seconds: Deprecated compatibility alias for ``pre_target_gap``.
        distract_overlap: Overlap between adjacent distractor notes.
        distract_fade_out: Fade-out applied to the end of each distractor note.
        distract_final_tail: Extra ring-out added to the final distractor note.
        pre_target_gap: Silence between the distractor phrase and the target note.
        default_octave: Fallback octave when note strings omit octave information.
        seed: Optional random seed for reproducible experiments.

    Returns:
        One :class:`TrainRoundResult` per completed round.

    Raises:
        ValueError: If any duration/count parameter is invalid.
    """
    if rounds <= 0:
        raise ValueError("rounds 必须大于 0")
    if distract_duration <= 0:
        raise ValueError("distract_duration 必须大于 0")
    if target_duration <= 0:
        raise ValueError("target_duration 必须大于 0")
    if pre_target_gap < 0:
        raise ValueError("pre_target_gap 不能小于 0")
    if distract_overlap < 0:
        raise ValueError("distract_overlap 不能小于 0")
    if distract_overlap >= distract_duration:
        raise ValueError("distract_overlap 必须小于 distract_duration")
    if distract_fade_out < 0:
        raise ValueError("distract_fade_out 不能小于 0")
    if distract_final_tail < 0:
        raise ValueError("distract_final_tail 不能小于 0")

    if gap_seconds is not None:
        # Backward-compatible alias from the earlier CLI/library version.
        pre_target_gap = gap_seconds

    rng = random.Random(seed)
    sample_bank = SampleBank(sound_dir)
    player = NotePlayer(sample_bank, default_octave=default_octave)

    pitch_classes = normalize_pitch_class_set(S)
    pitch_classes = sample_bank.validate_pitch_class_subset(pitch_classes)

    low, high = distract_count_range
    if low <= 0 or high <= 0 or low > high:
        raise ValueError("distract_count_range 必须形如 (较小正整数, 较大正整数)")

    results: list[TrainRoundResult] = []

    print("=" * 56)
    print("absolute_train1 已启动")
    print(f"目标音集合 S: {', '.join(pitch_classes)}")
    print("答题时只比较十二半音，不看八度。")
    print("支持输入: C, C#, Db, cs, A#, Bb, 4-cs, C4 等格式。")
    print("输入 quit / exit 可以提前结束。")
    print("=" * 56)

    for round_index in range(1, rounds + 1):
        print(f"\n[Round {round_index}/{rounds}] 请听音...")

        distract_count = rng.randint(low, high)
        distractor_samples = _choose_distractors(
            sample_bank=sample_bank,
            count=distract_count,
            rng=rng,
        )
        player.play_sample_sequence(
            distractor_samples,
            note_duration=distract_duration,
            overlap=distract_overlap,
            fade_out=distract_fade_out,
            final_tail=distract_final_tail,
            block=True,
        )

        if pre_target_gap > 0:
            time.sleep(pre_target_gap)

        target_pitch_class = rng.choice(pitch_classes)
        target_sample = sample_bank.choose_random_from_pitch_class(target_pitch_class, rng=rng)
        player.play_sample(target_sample, duration=target_duration, block=True)

        guess = _prompt_guess()
        if guess in {"quit", "exit"}:
            print("训练已提前结束。")
            break

        correct = guess == target_pitch_class
        if correct:
            print(f"✅ 正确，答案是 {target_pitch_class}（实际播放样本: {target_sample.local_filename_style}.wav）")
        else:
            guessed_text = guess if guess is not None else "<未作答>"
            print(
                f"❌ 不对。你答的是 {guessed_text}，"
                f"正确答案是 {target_pitch_class}（实际播放样本: {target_sample.local_filename_style}.wav）"
            )

        results.append(
            TrainRoundResult(
                round_index=round_index,
                target_pitch_class=target_pitch_class,
                target_sample_name=target_sample.concrete_name,
                guess_pitch_class=guess,
                correct=correct,
            )
        )

    if results:
        total = len(results)
        correct_count = sum(1 for item in results if item.correct)
        accuracy = 100.0 * correct_count / total
        print("\n" + "-" * 56)
        print(f"训练结束：{correct_count}/{total} 正确，正确率 {accuracy:.1f}%")
        print("-" * 56)
    else:
        print("本次没有完成任何题目。")

    return results


def _choose_distractors(
    *,
    sample_bank: SampleBank,
    count: int,
    rng: random.Random,
) -> list[SampleInfo]:
    """Choose a short distractor sequence while avoiding immediate exact repeats."""
    if count <= 0:
        raise ValueError("count 必须大于 0")

    chosen: list[SampleInfo] = []
    last_sample: Optional[SampleInfo] = None
    for _ in range(count):
        sample = sample_bank.choose_random_sample(exclude=last_sample, rng=rng)
        chosen.append(sample)
        last_sample = sample
    return chosen


def _prompt_guess() -> Optional[str]:
    """Read and normalize one user guess from stdin."""
    while True:
        raw = input("请输入音名 > ").strip()
        if not raw:
            print("请输入一个音名，例如 C / C# / Db / fs / 4-cs")
            continue

        if raw.lower() in {"quit", "exit"}:
            return raw.lower()

        try:
            return normalize_pitch_class(raw)
        except NoteFormatError as exc:
            print(f"输入无法识别：{exc}")
