"""Myers' O(ND) shortest-edit-script diff.

This is the linear-space, divide-and-conquer variant from Eugene Myers'
1986 paper *"An O(ND) Difference Algorithm and Its Variations"*: each step
searches forwards from the top-left and backwards from the bottom-right of
the edit graph at the same time until the two frontiers overlap. The
overlapping diagonal ("middle snake") lies on an optimal path, so the
problem splits into two smaller boxes on either side of it.

Time is O((N+M)·D) and memory is O(N+M), where D is the size of the
minimal edit script. When D is large - two big, mostly unrelated inputs -
that is quadratic, so by default the search is capped the way Git caps it
(``xdl_split`` in ``xdiffi.c``): once a split has cost more than
:func:`max_cost` edits, it stops looking for the optimal split and cuts at
the furthest point either search has reached. The result is still a
correct diff, just not always the smallest one. Pass ``minimal=True`` to
disable the cap.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from math import isqrt

from ._core import DiffOp, Match, T, build_ops, intern_items, trim_common

__all__ = ["MIN_COST", "max_cost", "myers_diff"]

#: Lower bound for the per-split edit budget; see :func:`max_cost`.
MIN_COST = 256


def max_cost(size: int) -> int:
    """Edit budget per split for a region with ``size`` lines in total.

    Same shape as Git's: the square root of the input size, but never less
    than :data:`MIN_COST`, so ordinary diffs never hit the cap.
    """
    return max(isqrt(size + 3), MIN_COST)


def _middle_snake(
    a: Sequence[int],
    alo: int,
    ahi: int,
    b: Sequence[int],
    blo: int,
    bhi: int,
    cost: int,
) -> tuple[int, int, int, int]:
    """Find a split point for the box ``a[alo:ahi]`` x ``b[blo:bhi]``.

    Returns ``(x_start, y_start, x_end, y_end)`` in absolute indices: a run
    of matching lines (possibly empty) to keep, with the two sub-boxes on
    either side still to be diffed. Normally this is the middle snake of an
    optimal path; if the search needs ``cost`` or more edits, it is instead
    an empty run at the furthest-reaching point of either search.

    The box must be non-empty on both sides with differing first and last
    lines (see :func:`trim_common`).

    Coordinates below are relative to the box. ``x`` indexes ``a``, ``y``
    indexes ``b`` and diagonal ``k = x - y``. ``vf[k]`` is the furthest
    ``x`` reached on diagonal ``k`` by the forward search; ``vb[c]`` is the
    smallest ``y`` reached on diagonal ``c = k - delta`` by the backward
    search. Negative diagonals rely on Python's negative list indexing.
    """
    n = ahi - alo
    m = bhi - blo
    delta = n - m
    odd = delta & 1
    max_d = (n + m + 1) // 2
    size = 2 * min(max_d, cost) + 1
    vf = [0] * size
    vb = [0] * size
    vf[1] = 0
    vb[1] = m

    for d in range(max_d + 1):
        # Forward search: extend every d-path by one edit, then follow the snake.
        for k in range(d, -d - 1, -2):
            if k == -d or (k != d and vf[k - 1] < vf[k + 1]):
                x = vf[k + 1]  # move down (insertion)
            else:
                x = vf[k - 1] + 1  # move right (deletion)
            y = x - k
            x0, y0 = x, y
            while x < n and y < m and a[alo + x] == b[blo + y]:
                x += 1
                y += 1
            vf[k] = x
            c = k - delta
            if odd and -(d - 1) <= c <= d - 1 and y >= vb[c]:
                return alo + x0, blo + y0, alo + x, blo + y

        # Backward search, mirrored.
        for c in range(d, -d - 1, -2):
            if c == -d or (c != d and vb[c - 1] > vb[c + 1]):
                y = vb[c + 1]  # move left
            else:
                y = vb[c - 1] - 1  # move up
            k = c + delta
            x = y + k
            x1, y1 = x, y
            while x > 0 and y > 0 and a[alo + x - 1] == b[blo + y - 1]:
                x -= 1
                y -= 1
            vb[c] = y
            if not odd and -d <= k <= d and x <= vf[k]:
                return alo + x, blo + y, alo + x1, blo + y1

        if d >= cost:
            # Too expensive: split at whichever frontier point has covered
            # the most ground. Diagonals near the edge can overshoot the
            # box, so only in-bounds points count.
            best = bx = by = 0
            for k in range(d, -d - 1, -2):
                x = vf[k]
                y = x - k
                if 0 <= x <= n and 0 <= y <= m and x + y > best:
                    best, bx, by = x + y, x, y
            for c in range(d, -d - 1, -2):
                y = vb[c]
                x = y + c + delta
                if 0 <= x <= n and 0 <= y <= m and n + m - x - y > best:
                    best, bx, by = n + m - x - y, x, y
            # A point strictly inside the box makes both halves smaller.
            if 0 < bx + by < n + m:
                return alo + bx, blo + by, alo + bx, blo + by

    raise AssertionError("unreachable: Myers search found no middle snake")


def myers_matches(
    a: Sequence[int],
    alo: int,
    ahi: int,
    b: Sequence[int],
    blo: int,
    bhi: int,
    minimal: bool = False,
) -> list[Match]:
    """Return the matched ``(i, j)`` pairs of a diff of two regions.

    The result is *not* sorted; callers sort once at the end. With
    ``minimal=False`` the per-split search is capped at :func:`max_cost`.
    """
    total = (ahi - alo) + (bhi - blo)
    # No sub-box can need more than `total` edits, so that disables the cap.
    cost = total + 1 if minimal else max_cost(total)
    matches: list[Match] = []
    stack = [(alo, ahi, blo, bhi)]
    while stack:
        alo, ahi, blo, bhi = stack.pop()
        alo, ahi, blo, bhi = trim_common(a, alo, ahi, b, blo, bhi, matches)
        if alo == ahi or blo == bhi:
            continue
        # After trimming, both regions are non-empty and start/end with
        # different lines, so both sub-boxes are strictly smaller.
        xs, ys, xe, ye = _middle_snake(a, alo, ahi, b, blo, bhi, cost)
        matches.extend((xs + i, ys + i) for i in range(xe - xs))
        stack.append((alo, xs, blo, ys))
        stack.append((xe, ahi, ye, bhi))
    return matches


def myers_diff(
    a: Sequence[T],
    b: Sequence[T],
    *,
    minimal: bool = False,
    key: Callable[[T], Hashable] | None = None,
) -> list[DiffOp[T]]:
    """Diff two sequences with Myers' algorithm.

    Items are usually lines, but can be any hashable values; ``key`` works
    as in :func:`histodiff.diff`.

    Produces the smallest edit script (fewest inserted plus deleted lines)
    unless the inputs are large and very different, where the search is
    capped like Git's to avoid quadratic run time; pass ``minimal=True`` to
    always get the smallest script, however long it takes.

    Small is not always readable: Myers will happily match stray ``}`` or
    blank lines, which can shred a moved block into many small hunks. See
    :func:`histodiff.patience_diff` and :func:`histodiff.histogram_diff`.
    """
    ia, ib = intern_items(a, b, key)
    matches = myers_matches(ia, 0, len(ia), ib, 0, len(ib), minimal)
    matches.sort()
    return build_ops(a, b, matches, ia, ib)
