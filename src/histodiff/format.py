"""Render :class:`DiffOp` lists as text."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from ._core import DiffOp

__all__ = ["unified_diff"]

_Opcode = tuple[str, int, int, int, int]


def _format_range(start: int, stop: int) -> str:
    """Convert a half-open range to unified-diff ``start,length`` (1-based)."""
    beginning = start + 1
    length = stop - start
    if length == 1:
        return str(beginning)
    if not length:
        beginning -= 1  # empty ranges point at the line before
    return f"{beginning},{length}"


def _group(codes: list[_Opcode], context: int) -> Iterator[list[_Opcode]]:
    """Split opcodes into hunks with ``context`` lines around each change.

    Same rules as :meth:`difflib.SequenceMatcher.get_grouped_opcodes`.
    """
    if not codes:
        return
    tag, i1, i2, j1, j2 = codes[0]
    if tag == "equal":
        codes[0] = (tag, max(i1, i2 - context), i2, max(j1, j2 - context), j2)
    tag, i1, i2, j1, j2 = codes[-1]
    if tag == "equal":
        codes[-1] = (tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context))

    group: list[_Opcode] = []
    for tag, i1, i2, j1, j2 in codes:
        # A long unchanged stretch ends one hunk and starts the next.
        if tag == "equal" and i2 - i1 > 2 * context:
            group.append((tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context)))
            yield group
            group = []
            i1, j1 = max(i1, i2 - context), max(j1, j2 - context)
        group.append((tag, i1, i2, j1, j2))
    if group and not (len(group) == 1 and group[0][0] == "equal"):
        yield group


def unified_diff(
    ops: Iterable[DiffOp],
    context: int = 3,
    *,
    fromfile: str = "",
    tofile: str = "",
    fromfiledate: str = "",
    tofiledate: str = "",
    lineterm: str = "\n",
) -> Iterator[str]:
    """Render diff ops in unified diff format.

    Works like :func:`difflib.unified_diff`, except it takes the ops from
    :func:`histodiff.diff` instead of the two sequences, so the output is
    byte-for-byte what difflib would print for the same alignment::

        ops = histodiff.diff(old.splitlines(True), new.splitlines(True))
        sys.stdout.writelines(histodiff.unified_diff(ops, fromfile="old"))

    As with difflib, ``lineterm`` only applies to the ``---``/``+++``/``@@``
    header lines; content lines are yielded exactly as given (so pass lines
    with their newlines, or use ``lineterm=""`` for lines without them).
    Yields nothing when there are no changes.

    :param ops: the result of :func:`histodiff.diff` or an algorithm function.
    :param context: number of unchanged lines shown around each change.
    :raises ValueError: if ``context`` is negative.
    """
    if context < 0:
        raise ValueError(f"context must be >= 0, got {context}")
    return _unified_diff(
        list(ops), context, fromfile, tofile, fromfiledate, tofiledate, lineterm
    )


def _unified_diff(
    ops: list[DiffOp],
    context: int,
    fromfile: str,
    tofile: str,
    fromfiledate: str,
    tofiledate: str,
    lineterm: str,
) -> Iterator[str]:
    a = [line for op in ops for line in op.a_lines]
    b = [line for op in ops for line in op.b_lines]
    started = False
    for group in _group([op.as_opcode() for op in ops], context):
        if not started:
            started = True
            fromdate = f"\t{fromfiledate}" if fromfiledate else ""
            todate = f"\t{tofiledate}" if tofiledate else ""
            yield f"--- {fromfile}{fromdate}{lineterm}"
            yield f"+++ {tofile}{todate}{lineterm}"

        first, last = group[0], group[-1]
        old_range = _format_range(first[1], last[2])
        new_range = _format_range(first[3], last[4])
        yield f"@@ -{old_range} +{new_range} @@{lineterm}"

        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for line in a[i1:i2]:
                    yield " " + line
                continue
            if tag in ("replace", "delete"):
                for line in a[i1:i2]:
                    yield "-" + line
            if tag in ("replace", "insert"):
                for line in b[j1:j2]:
                    yield "+" + line
