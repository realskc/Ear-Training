#!/usr/bin/env python3
"""Export the current Git working tree into a `.zip` or `.tar` archive.

The exported snapshot includes tracked files and, by default, untracked but
non-ignored files from the current working tree. It excludes Git history,
`.git/`, Git-ignored files, and any extra patterns from `.aiignore` or
``--exclude``.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Iterable


AIIGNORE_FILENAME = ".aiignore"


class ArchiveExportError(RuntimeError):
    """Raised when the snapshot export process cannot complete successfully."""


def ensure_pathspec_available() -> None:
    """Ensure the optional-but-required ``pathspec`` dependency is installed."""
    try:
        import pathspec  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on user environment
        raise SystemExit(
            "缺少依赖 pathspec。\n"
            "请先安装：python -m pip install pathspec"
        ) from exc


def run_git(args: list[str], cwd: Path) -> str:
    """Run one git command and return decoded stdout text."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.decode("utf-8", errors="surrogateescape")


def run_git_bytes(args: list[str], cwd: Path) -> bytes:
    """Run one git command and return raw stdout bytes."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def get_repo_root(start: Path) -> Path:
    """Return the repository root for ``start`` or exit with a friendly message."""
    try:
        out = run_git(["rev-parse", "--show-toplevel"], cwd=start).strip()
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        raise SystemExit(f"当前目录不在 Git 仓库中。\n{stderr}".rstrip()) from exc
    return Path(out).resolve()


def list_paths(repo_root: Path, tracked_only: bool) -> list[Path]:
    """List candidate files to export from the current working tree."""
    args = ["ls-files", "-z", "--cached"]
    if not tracked_only:
        args += ["--others", "--exclude-standard"]

    raw = run_git_bytes(args, cwd=repo_root)
    parts = [part for part in raw.split(b"\x00") if part]

    seen: set[Path] = set()
    paths: list[Path] = []

    for part in parts:
        rel = Path(part.decode("utf-8", errors="surrogateescape"))
        if rel in seen:
            continue
        seen.add(rel)

        abs_path = repo_root / rel
        if abs_path.is_file():
            paths.append(rel)

    paths.sort()
    return paths


def read_aiignore_patterns(repo_root: Path) -> list[str]:
    """Read gitignore-style patterns from ``.aiignore`` if present."""
    aiignore_path = repo_root / AIIGNORE_FILENAME
    if not aiignore_path.exists():
        return []
    return aiignore_path.read_text(encoding="utf-8").splitlines()


def apply_extra_excludes(
    members: list[Path],
    *,
    repo_root: Path,
    cli_patterns: list[str],
) -> list[Path]:
    """Filter members with patterns from `.aiignore` and repeated `--exclude` flags."""
    patterns = [*read_aiignore_patterns(repo_root), *cli_patterns]
    if not patterns:
        return members

    import pathspec

    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    kept: list[Path] = []
    for rel in members:
        if spec.match_file(rel.as_posix()):
            continue
        kept.append(rel)
    return kept


def default_output_path(repo_root: Path, fmt: str) -> Path:
    """Return the default archive path inside the repository root."""
    suffix = ".zip" if fmt == "zip" else ".tar"
    return repo_root / f"{repo_root.name}-snapshot{suffix}"


def remove_output_from_members(repo_root: Path, output: Path, members: list[Path]) -> list[Path]:
    """Prevent the generated archive from being included in itself."""
    try:
        rel_output = output.resolve().relative_to(repo_root)
    except ValueError:
        return members
    return [member for member in members if member != rel_output]


def write_zip(repo_root: Path, output: Path, members: Iterable[Path], prefix: str) -> None:
    """Write the selected members to a ZIP archive."""
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in members:
            abs_path = repo_root / rel
            arcname = f"{prefix}{rel.as_posix()}"
            zf.write(abs_path, arcname=arcname)


def write_tar(repo_root: Path, output: Path, members: Iterable[Path], prefix: str) -> None:
    """Write the selected members to an uncompressed TAR archive."""
    with tarfile.open(output, mode="w") as tf:
        for rel in members:
            abs_path = repo_root / rel
            arcname = f"{prefix}{rel.as_posix()}"
            tf.add(abs_path, arcname=arcname, recursive=False)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the snapshot-export utility."""
    parser = argparse.ArgumentParser(
        description=(
            "导出 Git 工作区快照到 .zip 或 .tar，排除 .git、Git ignored 文件，"
            f"并额外应用 {AIIGNORE_FILENAME} 与 --exclude 规则"
        )
    )
    parser.add_argument(
        "--format",
        choices=["zip", "tar"],
        default="zip",
        help="输出格式，默认 zip",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出文件路径。默认写到仓库根目录，如 repo-snapshot.zip",
    )
    parser.add_argument(
        "--tracked-only",
        action="store_true",
        help="只打包 tracked 文件；默认还会包含 untracked 但未被忽略的文件",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "额外排除模式，可重复传入。使用 gitignore 风格模式，例如："
            "--exclude sound/ --exclude '*.wav'"
        ),
    )
    parser.add_argument(
        "--no-prefix",
        action="store_true",
        help="归档内不添加顶层目录前缀。默认会加 repo_name/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要打包的文件，不生成归档",
    )
    return parser


def main() -> int:
    """Run the snapshot export utility and return a process exit code."""
    ensure_pathspec_available()

    parser = build_parser()
    args = parser.parse_args()

    repo_root = get_repo_root(Path.cwd())
    members = list_paths(repo_root, tracked_only=args.tracked_only)
    members = apply_extra_excludes(
        members,
        repo_root=repo_root,
        cli_patterns=args.exclude,
    )

    output = (args.output or default_output_path(repo_root, args.format)).resolve()
    members = remove_output_from_members(repo_root, output, members)

    if not members:
        print("没有可打包的文件。", file=sys.stderr)
        return 1

    if args.dry_run:
        for rel in members:
            print(rel.as_posix())
        print(f"\n共 {len(members)} 个文件。", file=sys.stderr)
        return 0

    prefix = "" if args.no_prefix else f"{repo_root.name}/"
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "zip":
        write_zip(repo_root, output, members, prefix)
    else:
        write_tar(repo_root, output, members, prefix)

    print(f"已生成: {output}")
    print(f"文件数: {len(members)}")
    print(f"仓库根目录: {repo_root}")
    print(f"模式: {'tracked-only' if args.tracked_only else 'tracked + untracked(non-ignored)'}")
    if (repo_root / AIIGNORE_FILENAME).exists():
        print(f"已应用: {repo_root / AIIGNORE_FILENAME}")
    if args.exclude:
        print(f"额外排除: {args.exclude}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
