"""Console-based ear-training flow built on top of the core package modules."""
from __future__ import annotations

from dataclasses import dataclass
import random
import time
from pathlib import Path
from typing import Optional, Sequence

from .config import (
    DEFAULT_DISTRACT_COUNT,
    DEFAULT_DISTRACT_DURATION,
    DEFAULT_DISTRACT_FADE_OUT,
    DEFAULT_DISTRACT_FINAL_TAIL,
    DEFAULT_DISTRACT_OVERLAP,
    DEFAULT_LIBRARY_ROUNDS,
    DEFAULT_OCTAVE,
    DEFAULT_PRE_TARGET_GAP,
    DEFAULT_SOUND_DIR,
    DEFAULT_TARGET_DURATION,
)
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
    sound_dir: str | Path = DEFAULT_SOUND_DIR,
    rounds: int = DEFAULT_LIBRARY_ROUNDS,
    distract_count: int = DEFAULT_DISTRACT_COUNT,
    distract_duration: float = DEFAULT_DISTRACT_DURATION,
    target_duration: float = DEFAULT_TARGET_DURATION,
    distract_overlap: float = DEFAULT_DISTRACT_OVERLAP,
    distract_fade_out: float = DEFAULT_DISTRACT_FADE_OUT,
    distract_final_tail: float = DEFAULT_DISTRACT_FINAL_TAIL,
    pre_target_gap: float = DEFAULT_PRE_TARGET_GAP,
    default_octave: int = DEFAULT_OCTAVE,
    seed: Optional[int] = None,
) -> list[TrainRoundResult]:
    """Run the v1 absolute-pitch exercise and return per-round results.

    One round proceeds as follows:

    1. choose ``distract_count`` random concrete samples
    2. render them into one legato-style phrase
    3. wait for ``pre_target_gap`` seconds of silence
    4. choose and play one target note from the requested pitch-class subset
    5. read the user's guess and compare only pitch class, ignoring octave

    The distractor phrase uses the timing model implemented by
    :meth:`ear_training.player.NotePlayer.render_sample_sequence`. For ``N >= 1``
    distractors, the theoretical phrase duration is::

        N * distract_duration - (N - 1) * distract_overlap + distract_final_tail

    A round may also use ``distract_count = 0``. In that case the phrase stage is
    skipped and the round becomes::

        pre_target_gap -> target note -> user input
    """
    if rounds <= 0:
        raise ValueError("rounds 必须大于 0")
    if distract_count < 0:
        raise ValueError("distract_count 不能小于 0")
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

    rng = random.Random(seed)
    sample_bank = SampleBank(sound_dir)
    player = NotePlayer(sample_bank, default_octave=default_octave)

    pitch_classes = normalize_pitch_class_set(S)
    pitch_classes = sample_bank.validate_pitch_class_subset(pitch_classes)

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

        distractor_samples = _choose_distractors(
            sample_bank=sample_bank,
            count=distract_count,
            rng=rng,
        )
        if distractor_samples:
            player.play_sample_sequence(
                distractor_samples,
                note_duration=distract_duration,
                overlap=distract_overlap,
                fade_out=distract_fade_out,
                final_tail=distract_final_tail,
                block=True,
            )
        else:
            print("本轮不播放干扰音。")

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
    if count < 0:
        raise ValueError("count 不能小于 0")
    if count == 0:
        return []

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
