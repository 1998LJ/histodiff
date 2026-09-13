"""Command-line interface: ``histodiff old.txt new.txt``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import datetime

from . import ALGORITHMS, __version__, diff
from .format import unified_diff

RED = "\x1b[31m"
GREEN = "\x1b[32m"
CYAN = "\x1b[36m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"
NO_NEWLINE = "\\ No newline at end of file\n"


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {value}")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="histodiff",
        description="Compare two files line by line and print a unified diff.",
        epilog="Exit status is 0 if the inputs are identical, 1 if they differ, "
        "2 on error.",
    )
    parser.add_argument("file1", help="original file ('-' reads stdin)")
    parser.add_argument("file2", help="changed file ('-' reads stdin)")
    parser.add_argument(
        "--algorithm",
        choices=list(ALGORITHMS),
        default="histogram",
        help="diff algorithm to use (default: %(default)s)",
    )
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="always find the smallest diff, even if that is very slow on large, "
        "very different files",
    )
    parser.add_argument(
        "--color",
        action="store_true",
        help="color the output with ANSI escapes (green additions, red deletions)",
    )
    parser.add_argument(
        "-U",
        "--unified",
        dest="context",
        type=_non_negative_int,
        default=3,
        metavar="N",
        help="lines of context around each change (default: %(default)s)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def split_lines(text: str) -> list[str]:
    """Split on ``\\n`` only, keeping line endings (like ``diff``).

    Unlike :meth:`str.splitlines` this does not break on form feeds or other
    Unicode line separators, and a final line without a newline is kept.
    """
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _read(path: str) -> tuple[list[str], str]:
    """Return the file's lines and its modification time for the header."""
    if path == "-":
        return split_lines(sys.stdin.read()), ""
    with open(path, encoding="utf-8", errors="replace", newline="") as handle:
        text = handle.read()
    mtime = datetime.fromtimestamp(os.stat(path).st_mtime).astimezone()
    return split_lines(text), mtime.strftime("%Y-%m-%d %H:%M:%S.%f %z")


def _render(index: int, line: str, color: bool) -> str:
    if line.endswith("\r\n"):
        body, ending = line[:-2], "\r\n"
    elif line.endswith("\n"):
        body, ending = line[:-1], "\n"
    else:
        body, ending = line, ""

    if color:
        # The first two lines are always the ---/+++ file headers; checking
        # the index avoids mistaking a deleted "-- comment" line for one.
        if index < 2:
            body = f"{BOLD}{body}{RESET}"
        elif body.startswith("@@"):
            body = f"{CYAN}{body}{RESET}"
        elif body.startswith("+"):
            body = f"{GREEN}{body}{RESET}"
        elif body.startswith("-"):
            body = f"{RED}{body}{RESET}"

    if not ending:  # last line of a file that lacks a trailing newline
        return f"{body}\n{NO_NEWLINE}"
    return body + ending


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        a, a_date = _read(args.file1)
        b, b_date = _read(args.file2)
    except OSError as exc:
        name = exc.filename if exc.filename is not None else ""
        print(f"histodiff: {name}: {exc.strerror or exc}", file=sys.stderr)
        return 2

    ops = diff(a, b, algorithm=args.algorithm, minimal=args.minimal)
    if all(op.tag == "equal" for op in ops):
        return 0

    lines = unified_diff(
        ops,
        args.context,
        fromfile=args.file1,
        tofile=args.file2,
        fromfiledate=a_date,
        tofiledate=b_date,
    )
    try:
        for index, line in enumerate(lines):
            sys.stdout.write(_render(index, line, args.color))
        sys.stdout.flush()
    except BrokenPipeError:
        # The reader went away (e.g. `histodiff a b | head`). Point stdout at
        # devnull so the interpreter's final flush doesn't raise again.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    return 1


if __name__ == "__main__":
    sys.exit(main())
