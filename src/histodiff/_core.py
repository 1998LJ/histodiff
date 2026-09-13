"""Shared data types and helpers used by every diff algorithm."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Tag = Literal["equal", "insert", "delete", "replace"]

#: A single matched line: ``(index_in_a, index_in_b)``.
Match = tuple[int, int]


@dataclass(frozen=True)
class DiffOp:
    """One diff operation.

    ``a[a_start:a_end]`` in the old sequence corresponds to
    ``b[b_start:b_end]`` in the new one, and ``tag`` says how:

    * ``"equal"``   - the two slices are identical.
    * ``"delete"``  - ``a[a_start:a_end]`` was removed (``b`` slice is empty).
    * ``"insert"``  - ``b[b_start:b_end]`` was added (``a`` slice is empty).
    * ``"replace"`` - ``a[a_start:a_end]`` was replaced by ``b[b_start:b_end]``.

    The index fields use the same conventions as the tuples returned by
    :meth:`difflib.SequenceMatcher.get_opcodes`.
    """

    tag: Tag
    a_start: int
    a_end: int
    b_start: int
    b_end: int
    a_lines: tuple[str, ...]
    b_lines: tuple[str, ...]

    def as_opcode(self) -> tuple[str, int, int, int, int]:
        """Return a ``difflib``-style ``(tag, i1, i2, j1, j2)`` tuple."""
        return (self.tag, self.a_start, self.a_end, self.b_start, self.b_end)


def intern_lines(a: Sequence[str], b: Sequence[str]) -> tuple[list[int], list[int]]:
    """Map every distinct line to a small integer.

    Comparing and hashing ints is much cheaper than strings, and the
    algorithms only ever need equality.
    """
    ids: dict[str, int] = {}
    ia = [ids.setdefault(line, len(ids)) for line in a]
    ib = [ids.setdefault(line, len(ids)) for line in b]
    return ia, ib


def build_ops(a: Sequence[str], b: Sequence[str], matches: list[Match]) -> list[DiffOp]:
    """Turn a sorted list of matched line pairs into a list of :class:`DiffOp`.

    ``matches`` must be strictly increasing in both coordinates. Runs of
    adjacent matches become one ``equal`` op; the gaps between them become
    ``delete``, ``insert`` or ``replace`` ops. Pure insertions and deletions
    are then slid to the most readable equivalent position
    (see :func:`_slide_groups`).
    """
    codes: list[list] = []

    def emit_gap(i1: int, i2: int, j1: int, j2: int) -> None:
        if i1 < i2 and j1 < j2:
            codes.append(["replace", i1, i2, j1, j2])
        elif i1 < i2:
            codes.append(["delete", i1, i2, j1, j2])
        elif j1 < j2:
            codes.append(["insert", i1, i2, j1, j2])

    i = j = 0
    k = 0
    while k < len(matches):
        mi, mj = matches[k]
        emit_gap(i, mi, j, mj)
        run = 1
        while (
            k + run < len(matches)
            and matches[k + run][0] == mi + run
            and matches[k + run][1] == mj + run
        ):
            run += 1
        codes.append(["equal", mi, mi + run, mj, mj + run])
        i, j = mi + run, mj + run
        k += run
    emit_gap(i, len(a), j, len(b))

    # Pad with empty equal ops so every change has an equal op on both sides
    # for _slide_groups to grow or shrink. Empty ones are dropped below.
    if not codes or codes[0][0] != "equal":
        codes.insert(0, ["equal", 0, 0, 0, 0])
    if codes[-1][0] != "equal":
        codes.append(["equal", len(a), len(a), len(b), len(b)])
    _slide_groups(codes, a, b)
    return [
        DiffOp(tag, i1, i2, j1, j2, tuple(a[i1:i2]), tuple(b[j1:j2]))
        for tag, i1, i2, j1, j2 in codes
        if not (tag == "equal" and i1 == i2)
    ]


def _is_blank(line: str) -> bool:
    return not line.strip()


def _position_score(seq: Sequence[str], start: int, end: int) -> tuple[int, int]:
    """Readability score for placing a changed group at ``seq[start:end]``.

    Higher is better: group edges on blank lines (so whole paragraphs or
    functions are added/removed), then a less-indented first line (so the
    group starts at a ``def`` rather than in the middle of its body).
    """
    boundary = int(start == 0 or _is_blank(seq[start - 1])) + int(
        _is_blank(seq[end - 1])
    )
    first = seq[start]
    indent = 1 << 30 if _is_blank(first) else len(first) - len(first.lstrip())
    return boundary, -indent


def _slide_groups(codes: list[list], a: Sequence[str], b: Sequence[str]) -> None:
    """Move ambiguous insert/delete groups to their most readable position.

    A group of inserted lines ``b[s:e]`` can shift down by one when
    ``b[s] == b[e]`` (or up when ``b[s-1] == b[e-1]``) without changing the
    size of the diff - e.g. adding a function between two others that both
    end in ``return 0`` and a blank line. Every algorithm has to pick one of
    these equivalent positions arbitrarily; Git resolves them afterwards
    with its "compaction" and indent heuristics, and this is a simplified
    version of that. Groups never absorb the only equal line separating
    them from another change, so no hunks are merged or split.

    ``codes`` must alternate equal and non-equal ops and start and end with
    an equal op (possibly empty). Modifies ``codes`` in place; emptied equal
    ops are left for the caller to drop.
    """
    last = len(codes) - 1
    for idx, code in enumerate(codes):
        tag = code[0]
        if tag == "insert":
            seq, lo, hi = b, 3, 4
        elif tag == "delete":
            seq, lo, hi = a, 1, 2
        else:
            continue
        start, end = code[lo], code[hi]
        prev, nxt = codes[idx - 1], codes[idx + 1]

        # The outermost equal ops may be consumed entirely; inner ones must
        # keep one line so this group stays separate from its neighbours.
        up_limit = prev[2] - prev[1] - (1 if idx - 1 > 0 else 0)
        down_limit = nxt[2] - nxt[1] - (1 if idx + 1 < last else 0)
        up = 0
        while up < up_limit and seq[start - 1 - up] == seq[end - 1 - up]:
            up += 1
        down = 0
        while down < down_limit and seq[start + down] == seq[end + down]:
            down += 1
        if not (up or down):
            continue

        # Ties go to the lowest position, as in Git.
        shift = max(
            range(-up, down + 1),
            key=lambda t: (*_position_score(seq, start + t, end + t), t),
        )
        if shift:
            for field in (1, 2, 3, 4):
                code[field] += shift
            prev[2] += shift
            prev[4] += shift
            nxt[1] += shift
            nxt[3] += shift


def trim_common(
    a: Sequence[int], alo: int, ahi: int, b: Sequence[int], blo: int, bhi: int,
    matches: list[Match],
) -> tuple[int, int, int, int]:
    """Match the common prefix and suffix of a region; return the shrunk bounds."""
    while alo < ahi and blo < bhi and a[alo] == b[blo]:
        matches.append((alo, blo))
        alo += 1
        blo += 1
    while alo < ahi and blo < bhi and a[ahi - 1] == b[bhi - 1]:
        ahi -= 1
        bhi -= 1
        matches.append((ahi, bhi))
    return alo, ahi, blo, bhi
