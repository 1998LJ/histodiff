"""Shared data types and helpers used by every diff algorithm."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

#: The item type of the sequences being diffed.
T = TypeVar("T")

Tag = Literal["equal", "insert", "delete", "replace"]

#: A single matched item: ``(index_in_a, index_in_b)``.
Match = tuple[int, int]


@dataclass(frozen=True)
class DiffOp(Generic[T]):
    """One diff operation.

    ``a[a_start:a_end]`` in the old sequence corresponds to
    ``b[b_start:b_end]`` in the new one, and ``tag`` says how:

    * ``"equal"``   - the two slices are identical.
    * ``"delete"``  - ``a[a_start:a_end]`` was removed (``b`` slice is empty).
    * ``"insert"``  - ``b[b_start:b_end]`` was added (``a`` slice is empty).
    * ``"replace"`` - ``a[a_start:a_end]`` was replaced by ``b[b_start:b_end]``.

    ``a_lines`` and ``b_lines`` hold the items of those slices. They are
    usually lines of text, but can be any items that were diffed: words,
    tokens, records. When a ``key`` function was used, "identical" means
    identical keys, so the two sides of an ``equal`` op can differ in ways
    the key ignores.

    The index fields use the same conventions as the tuples returned by
    :meth:`difflib.SequenceMatcher.get_opcodes`.
    """

    tag: Tag
    a_start: int
    a_end: int
    b_start: int
    b_end: int
    a_lines: tuple[T, ...]
    b_lines: tuple[T, ...]

    def as_opcode(self) -> tuple[str, int, int, int, int]:
        """Return a ``difflib``-style ``(tag, i1, i2, j1, j2)`` tuple."""
        return (self.tag, self.a_start, self.a_end, self.b_start, self.b_end)


def intern_items(
    a: Sequence[T],
    b: Sequence[T],
    key: Callable[[T], Hashable] | None = None,
) -> tuple[list[int], list[int]]:
    """Map every distinct item (or ``key(item)``) to a small integer.

    The algorithms only ever need equality, and comparing ints is much
    cheaper than comparing strings or records. Items are compared the way a
    ``dict`` compares keys - by hash and ``==`` - exactly like difflib.
    ``key`` is called once per item.

    :raises TypeError: if an item (or its key) is unhashable.
    """
    ids: dict[Hashable, int] = {}
    try:
        if key is None:
            ia = [ids.setdefault(item, len(ids)) for item in a]  # type: ignore[arg-type]
            ib = [ids.setdefault(item, len(ids)) for item in b]  # type: ignore[arg-type]
        else:
            ia = [ids.setdefault(key(item), len(ids)) for item in a]
            ib = [ids.setdefault(key(item), len(ids)) for item in b]
    except TypeError as exc:
        if "unhashable" not in str(exc):
            raise  # e.g. an unrelated error inside the key function
        what = "keys must be hashable" if key else "items must be hashable"
        raise TypeError(
            f"{what} to be compared ({exc}); pass key= to compare items by a "
            "hashable value, e.g. key=tuple for lists or "
            "key=lambda row: tuple(sorted(row.items())) for dicts"
        ) from exc
    return ia, ib


def build_ops(
    a: Sequence[T],
    b: Sequence[T],
    matches: list[Match],
    ia: Sequence[int],
    ib: Sequence[int],
) -> list[DiffOp[T]]:
    """Turn a sorted list of matched item pairs into a list of :class:`DiffOp`.

    ``matches`` must be strictly increasing in both coordinates; ``ia`` and
    ``ib`` are the interned ids from :func:`intern_items`. Runs of adjacent
    matches become one ``equal`` op; the gaps between them become
    ``delete``, ``insert`` or ``replace`` ops. Pure insertions and deletions
    are then slid to the most readable equivalent position
    (see :func:`_slide_groups`).
    """
    codes: list[list[Any]] = []

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
    _slide_groups(codes, a, b, ia, ib)
    return [
        DiffOp(tag, i1, i2, j1, j2, tuple(a[i1:i2]), tuple(b[j1:j2]))
        for tag, i1, i2, j1, j2 in codes
        if not (tag == "equal" and i1 == i2)
    ]


def _is_blank(item: object) -> bool:
    # Only text has blank lines; other items never count as boundaries.
    return isinstance(item, str) and not item.strip()


def _position_score(seq: Sequence[object], start: int, end: int) -> tuple[int, int]:
    """Readability score for placing a changed group at ``seq[start:end]``.

    Higher is better: group edges on blank lines (so whole paragraphs or
    functions are added/removed), then a less-indented first line (so the
    group starts at a ``def`` rather than in the middle of its body). Items
    that aren't strings all score the same, so ties go to Git's default.
    """
    boundary = int(start == 0 or _is_blank(seq[start - 1])) + int(
        _is_blank(seq[end - 1])
    )
    first = seq[start]
    if not isinstance(first, str):
        indent = 0
    elif _is_blank(first):
        indent = 1 << 30
    else:
        indent = len(first) - len(first.lstrip())
    return boundary, -indent


def _slide_groups(
    codes: list[list[Any]],
    a: Sequence[object],
    b: Sequence[object],
    ia: Sequence[int],
    ib: Sequence[int],
) -> None:
    """Move ambiguous insert/delete groups to their most readable position.

    A group of inserted items ``b[s:e]`` can shift down by one when
    ``b[s] == b[e]`` (or up when ``b[s-1] == b[e-1]``) without changing the
    size of the diff - e.g. adding a function between two others that both
    end in ``return 0`` and a blank line. Every algorithm has to pick one of
    these equivalent positions arbitrarily; Git resolves them afterwards
    with its "compaction" and indent heuristics, and this is a simplified
    version of that. Groups never absorb the only equal item separating
    them from another change, so no hunks are merged or split.

    Equality is checked on the interned ids ``ia``/``ib``, so it agrees
    with the diff's own notion of equal (including any ``key``); the raw
    items are only used to score positions.

    ``codes`` must alternate equal and non-equal ops and start and end with
    an equal op (possibly empty). Modifies ``codes`` in place; emptied equal
    ops are left for the caller to drop.
    """
    last = len(codes) - 1
    for idx, code in enumerate(codes):
        tag = code[0]
        if tag == "insert":
            seq, ids, lo, hi = b, ib, 3, 4
        elif tag == "delete":
            seq, ids, lo, hi = a, ia, 1, 2
        else:
            continue
        start, end = code[lo], code[hi]
        prev, nxt = codes[idx - 1], codes[idx + 1]

        # The outermost equal ops may be consumed entirely; inner ones must
        # keep one item so this group stays separate from its neighbours.
        up_limit = prev[2] - prev[1] - (1 if idx - 1 > 0 else 0)
        down_limit = nxt[2] - nxt[1] - (1 if idx + 1 < last else 0)
        up = 0
        while up < up_limit and ids[start - 1 - up] == ids[end - 1 - up]:
            up += 1
        down = 0
        while down < down_limit and ids[start + down] == ids[end + down]:
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
