"""Myers' O(ND) shortest-edit-script diff.

This is the linear-space, divide-and-conquer variant from Eugene Myers'
1986 paper *"An O(ND) Difference Algorithm and Its Variations"*: each step
searches forwards from the top-left and backwards from the bottom-right of
the edit graph at the same time until the two frontiers overlap. The
overlapping diagonal ("middle snake") lies on an optimal path, so the
problem splits into two smaller boxes on either side of it.

Time is O((N+M)·D) and memory is O(N+M), where D is the size of the
minimal edit script.
"""

from __future__ import annotations

from collections.abc import Sequence

from ._core import DiffOp, Match, build_ops, intern_lines, trim_common

__all__ = ["myers_diff"]


def _middle_snake(
    a: Sequence[int], alo: int, ahi: int, b: Sequence[int], blo: int, bhi: int
) -> tuple[int, int, int, int]:
    """Find the middle snake of the box ``a[alo:ahi]`` x ``b[blo:bhi]``.

    Returns ``(x_start, y_start, x_end, y_end)`` in absolute indices: a run
    of matching lines (possibly empty) that lies on a shortest edit path.

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
    size = 2 * max_d + 1
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

    raise AssertionError("unreachable: Myers search found no middle snake")


def myers_matches(
    a: Sequence[int], alo: int, ahi: int, b: Sequence[int], blo: int, bhi: int
) -> list[Match]:
    """Return the matched ``(i, j)`` pairs of a minimal diff of two regions.

    The result is *not* sorted; callers sort once at the end.
    """
    matches: list[Match] = []
    stack = [(alo, ahi, blo, bhi)]
    while stack:
        alo, ahi, blo, bhi = stack.pop()
        alo, ahi, blo, bhi = trim_common(a, alo, ahi, b, blo, bhi, matches)
        if alo == ahi or blo == bhi:
            continue
        # After trimming, both regions are non-empty and start/end with
        # different lines, so D >= 2 and both sub-boxes are strictly smaller.
        xs, ys, xe, ye = _middle_snake(a, alo, ahi, b, blo, bhi)
        matches.extend((xs + i, ys + i) for i in range(xe - xs))
        stack.append((alo, xs, blo, ys))
        stack.append((xe, ahi, ye, bhi))
    return matches


def myers_diff(a: Sequence[str], b: Sequence[str]) -> list[DiffOp]:
    """Diff two sequences of lines with Myers' algorithm.

    Produces a minimal edit script (the fewest inserted plus deleted lines).
    Minimal is not always readable: Myers will happily match stray ``}`` or
    blank lines, which can shred a moved block into many small hunks. See
    :func:`histodiff.patience_diff` and :func:`histodiff.histogram_diff`.
    """
    ia, ib = intern_lines(a, b)
    matches = myers_matches(ia, 0, len(ia), ib, 0, len(ib))
    matches.sort()
    return build_ops(a, b, matches)
