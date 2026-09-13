"""Command-line interface: ``histodiff old.txt new.txt``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime

from . import ALGORITHMS, __version__, diff
from .format import unified_diff
from .whitespace import ignore_all_space, ignore_space_change
from .words import highlight_words, inline_word_diff

RED = "\x1b[31m"
GREEN = "\x1b[32m"
CYAN = "\x1b[36m"
BOLD = "\x1b[1m"
REVERSE = "\x1b[7m"
NO_REVERSE = "\x1b[27m"
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
    whitespace = parser.add_argument_group("whitespace")
    whitespace.add_argument(
        "-b",
        "--ignore-space-change",
        action="store_true",
        help="ignore changes in the amount of whitespace (trailing whitespace, "
        "and runs of spaces/tabs, compare as one space)",
    )
    whitespace.add_argument(
        "-w",
        "--ignore-all-space",
        action="store_true",
        help="ignore all whitespace when comparing lines (overrides -b)",
    )
    whitespace.add_argument(
        "-B",
        "--ignore-blank-lines",
        action="store_true",
        help="ignore changes whose lines are all blank",
    )
    parser.add_argument(
        "--color",
        action="store_true",
        help="color the output with ANSI escapes (green additions, red deletions, "
        "changed words within replaced lines highlighted)",
    )
    parser.add_argument(
        "--color-words",
        action="store_true",
        help="show replaced lines as one line with the deleted and inserted words "
        "colored inline, like git diff --color-words (implies --color)",
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


def _split_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _finish(body: str, ending: str) -> str:
    if not ending:  # last line of a file that lacks a trailing newline
        return f"{body}\n{NO_NEWLINE}"
    return body + ending


def _paint(color: str, text: str) -> str:
    return f"{color}{text}{RESET}" if text else ""


def render(
    lines: Sequence[str], mode: str = "plain", algorithm: str = "histogram"
) -> Iterator[str]:
    """Turn unified diff lines into terminal output.

    :param mode: ``"plain"``; ``"color"`` - red/green lines, with the changed
        words of replaced lines in reverse video; or ``"words"`` - replaced
        lines merged into one with words colored inline, like
        ``git diff --color-words``.
    :param algorithm: algorithm for the word-level diff.
    """
    i = 0
    while i < len(lines):
        body, ending = _split_ending(lines[i])
        if mode == "plain":
            yield _finish(body, ending)
            i += 1
        elif i < 2:
            # The first two lines are always the ---/+++ file headers; checking
            # the index avoids mistaking a deleted "-- comment" line for one.
            yield _finish(_paint(BOLD, body), ending)
            i += 1
        elif body.startswith("@@"):
            yield _finish(_paint(CYAN, body), ending)
            i += 1
        elif body[:1] in ("-", "+"):
            # Inside a hunk, '-' lines directly followed by '+' lines are
            # always a single replaced block.
            j = i
            while j < len(lines) and lines[j].startswith("-"):
                j += 1
            k = j
            while k < len(lines) and lines[k].startswith("+"):
                k += 1
            yield from _render_change(lines[i:j], lines[j:k], mode, algorithm)
            i = k
        else:  # context line
            if mode == "words":
                yield body[1:] + (ending or "\n")
            else:
                yield _finish(body, ending)
            i += 1


def _render_change(
    old: Sequence[str], new: Sequence[str], mode: str, algorithm: str
) -> Iterator[str]:
    old_parts = [_split_ending(line[1:]) for line in old]
    new_parts = [_split_ending(line[1:]) for line in new]
    old_bodies = [body for body, _ in old_parts]
    new_bodies = [body for body, _ in new_parts]

    if mode == "words":
        if old_bodies and new_bodies:
            pieces = []
            for tag, text in inline_word_diff(old_bodies, new_bodies,
                                              algorithm=algorithm):
                color = {"equal": "", "delete": RED, "insert": GREEN}[tag]
                # Color each physical line separately so pagers stay tidy.
                pieces.append("\n".join(
                    _paint(color, part) if color else part
                    for part in text.split("\n")
                ))
            yield "".join(pieces) + "\n"
        else:
            color = RED if old_bodies else GREEN
            for body in old_bodies or new_bodies:
                yield _paint(color, body) + "\n"
        return

    highlights = highlight_words(old_bodies, new_bodies, algorithm=algorithm)
    for sign, color, parts, side in (
        ("-", RED, old_parts, 0),
        ("+", GREEN, new_parts, 1),
    ):
        for number, (body, ending) in enumerate(parts):
            if highlights is None:
                text = body
            else:
                text = "".join(
                    f"{REVERSE}{piece}{NO_REVERSE}" if changed else piece
                    for piece, changed in highlights[side][number]
                )
            yield _finish(f"{color}{sign}{text}{RESET}", ending)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        a, a_date = _read(args.file1)
        b, b_date = _read(args.file2)
    except OSError as exc:
        name = exc.filename if exc.filename is not None else ""
        print(f"histodiff: {name}: {exc.strerror or exc}", file=sys.stderr)
        return 2

    key: Callable[[str], str] | None = None
    if args.ignore_all_space:
        key = ignore_all_space
    elif args.ignore_space_change:
        key = ignore_space_change

    ops = diff(a, b, algorithm=args.algorithm, minimal=args.minimal, key=key)
    lines = list(
        unified_diff(
            ops,
            args.context,
            fromfile=args.file1,
            tofile=args.file2,
            fromfiledate=a_date,
            tofiledate=b_date,
            ignore_blank_lines=args.ignore_blank_lines,
        )
    )
    # Like GNU diff, differences that were all ignored count as no difference.
    if not lines:
        return 0

    mode = "words" if args.color_words else "color" if args.color else "plain"
    try:
        for chunk in render(lines, mode, args.algorithm):
            sys.stdout.write(chunk)
        sys.stdout.flush()
    except BrokenPipeError:
        # The reader went away (e.g. `histodiff a b | head`). Point stdout at
        # devnull so the interpreter's final flush doesn't raise again.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    return 1


if __name__ == "__main__":
    sys.exit(main())
