"""Console-based ear-training flows built on top of the core package modules."""
from __future__ import annotations

from dataclasses import dataclass
import random
import time
from pathlib import Path
from typing import Optional, Sequence

from .notes import NoteFormatError, normalize_pitch_class, normalize_pitch_class_set
from .player import NotePlayer
from .sample_bank import SampleBank, SampleInfo


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
    distract_duration: float = 0.22,
    target_duration: float = 1.2,
    gap_seconds: float = 0.08,
    default_octave: int = 4,
    seed: Optional[int] = None,
) -> list[TrainRoundResult]:
    """Run the v1 absolute-pitch exercise and return per-round results.

    The exercise first plays several distractor notes, then one target note.
    The user enters a guess in the console, and correctness is decided only by
    pitch class, ignoring octave.

    Library defaults are intentionally lightweight. The CLI in ``main.py`` may
    choose different user-facing defaults, such as a larger default round count.
    """
    if rounds <= 0:
        raise ValueError("rounds 必须大于 0")

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
        _play_distractors(
            player=player,
            sample_bank=sample_bank,
            count=distract_count,
            duration=distract_duration,
            gap_seconds=gap_seconds,
            rng=rng,
        )

        target_pitch_class = rng.choice(pitch_classes)
        target_sample = sample_bank.choose_random_from_pitch_class(target_pitch_class, rng=rng)
        time.sleep(gap_seconds)
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


def _play_distractors(
    *,
    player: NotePlayer,
    sample_bank: SampleBank,
    count: int,
    duration: float,
    gap_seconds: float,
    rng: random.Random,
) -> None:
    """Play a short random sequence to disrupt the listener before the target note."""
    last_sample: Optional[SampleInfo] = None
    for _ in range(count):
        sample = sample_bank.choose_random_sample(exclude=last_sample, rng=rng)
        player.play_sample(sample, duration=duration, block=True)
        last_sample = sample
        time.sleep(gap_seconds)


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
