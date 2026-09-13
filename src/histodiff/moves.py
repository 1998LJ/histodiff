"""Detect blocks of lines that were moved rather than changed.

A diff reports a moved function as a deletion in one place and an insertion
somewhere else. :func:`find_moves` pairs those up: every deleted run of
lines that reappears unchanged among the inserted lines becomes a
:class:`Move`. ``histodiff --color-moved`` uses it to color moved lines
differently, like ``git diff --color-moved``.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass

from ._core import DiffOp

__all__ = ["MIN_ALNUM", "Move", "find_moves"]

#: A block needs at least this many letters or digits to count as moved, so
#: stray ``}`` or blank lines are never reported (Git uses the same rule).
MIN_ALNUM = 20

# How many unused copies of a line to try as the start of a match.
_MAX_CANDIDATES = 64


@dataclass(frozen=True)
class Move:
    """A block deleted from ``a[a_start:a_end]`` and inserted, unchanged, as
    ``b[b_start:b_end]``.

    ``a_lines`` and ``b_lines`` are identical unless a ``key`` was used, in
    which case they are equal under that key.
    """

    a_start: int
    a_end: int
    b_start: int
    b_end: int
    a_lines: tuple[str, ...]
    b_lines: tuple[str, ...]


def find_moves(
    ops: Iterable[DiffOp[str]],
    *,
    min_alnum: int = MIN_ALNUM,
    key: Callable[[str], Hashable] | None = None,
) -> list[Move]:
    """Find deleted blocks that reappear unchanged as insertions.

    Each deleted run (from ``delete`` and ``replace`` ops) is matched
    greedily, from its top, against the longest identical run of inserted
    lines (from ``insert`` and ``replace`` ops). Every line takes part in at
    most one move, so a block pasted twice is only matched once.

    :param ops: the result of :func:`histodiff.diff`.
    :param min_alnum: minimum number of letters and digits in a block for it
        to count as moved; ``0`` reports every match.
    :param key: compare ``key(line)`` rather than the lines, e.g. the same
        whitespace key the diff was made with.
    :returns: moves ordered by position in ``a``.
    """
    ops = list(ops)

    # Every inserted line, flattened, with the run it belongs to so matches
    # never span two separate insertions.
    ins_keys: list[Hashable] = []
    ins_lines: list[str] = []
    ins_index: list[int] = []
    ins_run: list[int] = []
    positions: dict[Hashable, list[int]] = {}
    run = 0
    for op in ops:
        if op.tag not in ("insert", "replace"):
            continue
        for offset, line in enumerate(op.b_lines):
            line_key = line if key is None else key(line)
            positions.setdefault(line_key, []).append(len(ins_keys))
            ins_keys.append(line_key)
            ins_lines.append(line)
            ins_index.append(op.b_start + offset)
            ins_run.append(run)
        run += 1
    used = [False] * len(ins_keys)

    moves: list[Move] = []
    for op in ops:
        if op.tag not in ("delete", "replace"):
            continue
        lines = op.a_lines
        keys = [line if key is None else key(line) for line in lines]
        i = 0
        while i < len(lines):
            best_len, best = 0, -1
            tried = 0
            for flat in positions.get(keys[i], ()):
                if used[flat]:
                    continue
                tried += 1
                if tried > _MAX_CANDIDATES:
                    break
                length = 0
                while (
                    i + length < len(lines)
                    and flat + length < len(ins_keys)
                    and ins_run[flat + length] == ins_run[flat]
                    and not used[flat + length]
                    and ins_keys[flat + length] == keys[i + length]
                ):
                    length += 1
                if length > best_len:
                    best_len, best = length, flat

            block = lines[i : i + best_len]
            alnum = sum(char.isalnum() for line in block for char in line)
            if best_len and alnum >= min_alnum:
                used[best : best + best_len] = [True] * best_len
                b_start = ins_index[best]
                moves.append(
                    Move(
                        op.a_start + i,
                        op.a_start + i + best_len,
                        b_start,
                        b_start + best_len,
                        tuple(block),
                        tuple(ins_lines[best : best + best_len]),
                    )
                )
                i += best_len
            else:
                i += 1
    return moves
