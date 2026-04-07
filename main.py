"""Command-line entry point for the Ear Training project.

This module owns argument parsing, user-facing validation and error reporting.
It deliberately keeps audio parsing and training logic in the package modules
under ``ear_training`` and imports its default values from ``ear_training.config``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from ear_training import absolute_train1, play_note
from ear_training.config import (
    DEFAULT_CLI_ROUNDS,
    DEFAULT_DISTRACT_COUNT,
    DEFAULT_DISTRACT_DURATION,
    DEFAULT_DISTRACT_FADE_OUT,
    DEFAULT_DISTRACT_FINAL_TAIL,
    DEFAULT_DISTRACT_OVERLAP,
    DEFAULT_OCTAVE,
    DEFAULT_PLAY_DURATION,
    DEFAULT_PRE_TARGET_GAP,
    DEFAULT_SOUND_DIR,
    DEFAULT_TARGET_DURATION,
)
from ear_training.notes import NoteFormatError


class CliInputError(ValueError):
    """用户可以自行修正的命令行输入错误。"""


# -----------------------------------------------------------------------------
# argparse type helpers
# -----------------------------------------------------------------------------


def positive_float(value: str) -> float:
    """Parse a strictly positive float for CLI arguments."""
    try:
        x = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"必须是数字: {value!r}") from exc
    if x <= 0:
        raise argparse.ArgumentTypeError(f"必须大于 0: {value!r}")
    return x


def non_negative_float(value: str) -> float:
    """Parse a non-negative float for CLI arguments."""
    try:
        x = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"必须是数字: {value!r}") from exc
    if x < 0:
        raise argparse.ArgumentTypeError(f"不能小于 0: {value!r}")
    return x


def positive_int(value: str) -> int:
    """Parse a strictly positive integer for CLI arguments."""
    try:
        x = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"必须是整数: {value!r}") from exc
    if x <= 0:
        raise argparse.ArgumentTypeError(f"必须大于 0: {value!r}")
    return x


def non_negative_int(value: str) -> int:
    """Parse a non-negative integer for CLI arguments."""
    try:
        x = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"必须是整数: {value!r}") from exc
    if x < 0:
        raise argparse.ArgumentTypeError(f"不能小于 0: {value!r}")
    return x


def octave_int(value: str) -> int:
    """Parse an octave limited to the sample bank's supported range."""
    x = non_negative_int(value)
    if not 0 <= x <= 8:
        raise argparse.ArgumentTypeError(f"八度必须在 0 到 8 之间: {value!r}")
    return x


# -----------------------------------------------------------------------------
# parser
# -----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        description="本地钢琴 wav 样本驱动的绝对音感训练小项目",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sound-dir",
        default=DEFAULT_SOUND_DIR,
        help="sound 目录路径，默认是项目根目录下的 sound",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="显示完整 traceback，便于调试",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    play_parser = subparsers.add_parser(
        "play",
        help="播放一个单音",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    play_parser.add_argument("note", help="音名，如 C4 / C#4 / Db4 / fs / 4-cs")
    play_parser.add_argument(
        "--duration",
        type=positive_float,
        default=DEFAULT_PLAY_DURATION,
        help="播放时长（秒）",
    )
    play_parser.add_argument(
        "--default-octave",
        type=octave_int,
        default=DEFAULT_OCTAVE,
        help="当 note 不带八度时默认使用的八度",
    )

    train_parser = subparsers.add_parser(
        "absolute_train1",
        help="开始绝对音感训练 v1",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    train_parser.add_argument(
        "--set",
        nargs="+",
        required=True,
        help="目标音集合 S，例如: C D# F# A 或 C Ds Fs A",
    )
    train_parser.add_argument("--rounds", type=positive_int, default=DEFAULT_CLI_ROUNDS, help="训练轮数")
    train_parser.add_argument(
        "--distract-count",
        type=non_negative_int,
        default=DEFAULT_DISTRACT_COUNT,
        help="每轮固定干扰音个数，可为 0",
    )
    train_parser.add_argument(
        "--distract-duration",
        type=positive_float,
        default=DEFAULT_DISTRACT_DURATION,
        help="每个干扰音的标称时长（秒）",
    )
    train_parser.add_argument(
        "--distract-overlap",
        type=non_negative_float,
        default=DEFAULT_DISTRACT_OVERLAP,
        help="相邻干扰音的重合时长（秒）",
    )
    train_parser.add_argument(
        "--distract-fade-out",
        type=non_negative_float,
        default=DEFAULT_DISTRACT_FADE_OUT,
        help="每个干扰音结尾的淡出时长（秒）",
    )
    train_parser.add_argument(
        "--distract-final-tail",
        type=non_negative_float,
        default=DEFAULT_DISTRACT_FINAL_TAIL,
        help="最后一个干扰音额外保留的尾音时长（秒）",
    )
    train_parser.add_argument(
        "--pre-target-gap",
        type=non_negative_float,
        default=DEFAULT_PRE_TARGET_GAP,
        help="干扰音序列结束到目标音开始前的停顿（秒）",
    )
    train_parser.add_argument(
        "--gap",
        dest="legacy_gap",
        type=non_negative_float,
        default=None,
        help=argparse.SUPPRESS,
    )
    train_parser.add_argument(
        "--target-duration",
        type=positive_float,
        default=DEFAULT_TARGET_DURATION,
        help="目标音播放时长（秒）",
    )
    train_parser.add_argument(
        "--default-octave",
        type=octave_int,
        default=DEFAULT_OCTAVE,
        help="当集合里的音名不带八度时，用于解析/回退的默认八度",
    )
    train_parser.add_argument("--seed", type=int, default=None, help="随机种子，便于复现实验")

    return parser


# -----------------------------------------------------------------------------
# validation / execution
# -----------------------------------------------------------------------------


def validate_args(args: argparse.Namespace) -> Path:
    """Validate cross-argument constraints and return the resolved sound dir."""
    sound_dir = Path(args.sound_dir).expanduser()

    if not sound_dir.exists():
        raise CliInputError(f"sound 目录不存在: {sound_dir}")
    if not sound_dir.is_dir():
        raise CliInputError(f"sound 目录不是文件夹: {sound_dir}")

    if args.command == "absolute_train1":
        if not args.set:
            raise CliInputError("--set 不能为空")
        if args.distract_overlap >= args.distract_duration:
            raise CliInputError("--distract-overlap 必须小于 --distract-duration")
        if args.legacy_gap is not None:
            if (
                args.pre_target_gap != DEFAULT_PRE_TARGET_GAP
                and args.pre_target_gap != args.legacy_gap
            ):
                raise CliInputError("不要同时传不同值的 --pre-target-gap 和旧别名 --gap")
            args.pre_target_gap = args.legacy_gap

    return sound_dir


def run(argv: Sequence[str] | None = None) -> int:
    """Execute the requested subcommand and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    sound_dir = validate_args(args)

    if args.command == "play":
        play_note(
            args.note,
            args.duration,
            sound_dir=sound_dir,
            default_octave=args.default_octave,
        )
        return 0

    if args.command == "absolute_train1":
        absolute_train1(
            args.set,
            sound_dir=sound_dir,
            rounds=args.rounds,
            distract_count=args.distract_count,
            distract_duration=args.distract_duration,
            target_duration=args.target_duration,
            distract_overlap=args.distract_overlap,
            distract_fade_out=args.distract_fade_out,
            distract_final_tail=args.distract_final_tail,
            pre_target_gap=args.pre_target_gap,
            default_octave=args.default_octave,
            seed=args.seed,
        )
        return 0

    raise AssertionError(f"未处理的命令: {args.command}")


# -----------------------------------------------------------------------------
# entry point
# -----------------------------------------------------------------------------


def eprint(message: str) -> None:
    """Print a message to stderr."""
    print(message, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the CLI with friendly error handling for expected user mistakes."""
    actual_argv = list(argv) if argv is not None else sys.argv[1:]
    debug = "--debug" in actual_argv

    try:
        raise SystemExit(run(actual_argv))
    except KeyboardInterrupt:
        if debug:
            raise
        eprint("已取消。")
        raise SystemExit(130)
    except NoteFormatError as exc:
        if debug:
            raise
        eprint(f"输入错误: {exc}")
        raise SystemExit(2)
    except CliInputError as exc:
        if debug:
            raise
        eprint(f"参数错误: {exc}")
        raise SystemExit(2)
    except FileNotFoundError as exc:
        if debug:
            raise
        eprint(f"文件错误: {exc}")
        raise SystemExit(2)
    except ValueError as exc:
        if debug:
            raise
        eprint(f"输入值错误: {exc}")
        raise SystemExit(2)
    except Exception as exc:
        if debug:
            raise
        eprint(f"未处理的运行错误: {exc}")
        eprint("如需查看完整 traceback，请加上 --debug")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
