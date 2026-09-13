"""Render :class:`DiffOp` lists as text: unified, side by side, and JSON."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from ._core import DiffOp
from .moves import Move
from .whitespace import is_blank

__all__ = [
    "JSON_VERSION",
    "SideBySideRow",
    "from_json",
    "side_by_side",
    "side_by_side_rows",
    "to_json",
    "unified_diff",
]

_Opcode = tuple[str, int, int, int, int]

#: ``(text, changed)`` pieces of one line, as from
#: :func:`histodiff.highlight_words`.
Segments = list[tuple[str, bool]]

#: Version of the document written by :func:`to_json`.
JSON_VERSION = 1

_TAGS = ("equal", "insert", "delete", "replace")


def _require_text(ops: Iterable[DiffOp[Any]], name: str) -> None:
    for op in ops:
        for item in op.a_lines + op.b_lines:
            if not isinstance(item, str):
                raise TypeError(
                    f"{name} renders text, but the ops contain a "
                    f"{type(item).__name__} item; diff strings, or convert "
                    "items with str() first"
                )


def _strip_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith("\n"):
        return line[:-1]
    return line


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


def _is_blank_group(group: list[_Opcode], a: Sequence[str], b: Sequence[str]) -> bool:
    """Whether every change in a hunk only adds or removes blank lines."""
    return all(
        tag == "equal"
        or (
            all(is_blank(line) for line in a[i1:i2])
            and all(is_blank(line) for line in b[j1:j2])
        )
        for tag, i1, i2, j1, j2 in group
    )


# --------------------------------------------------------------------------
# Unified diff
# --------------------------------------------------------------------------


def unified_diff(
    ops: Iterable[DiffOp[str]],
    context: int = 3,
    *,
    fromfile: str = "",
    tofile: str = "",
    fromfiledate: str = "",
    tofiledate: str = "",
    lineterm: str = "\n",
    ignore_blank_lines: bool = False,
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

    Unchanged lines are printed from ``a``. That matters when the ops come
    from a ``key`` such as :func:`histodiff.ignore_space_change`, where the
    two sides of an unchanged line may differ in whitespace: like GNU diff,
    the old file's version is shown.

    :param ops: the result of :func:`histodiff.diff` or an algorithm function.
    :param context: number of unchanged lines shown around each change.
    :param ignore_blank_lines: skip hunks whose changes only add or remove
        blank (empty or whitespace-only) lines, like ``diff -B``. A hunk that
        also contains a real change is shown in full, blank lines included,
        so every hunk's line counts stay consistent.
    :raises ValueError: if ``context`` is negative.
    :raises TypeError: if the ops hold anything but strings; unified diff is
        a text format, so convert other items first (e.g. with ``str``).
    """
    if context < 0:
        raise ValueError(f"context must be >= 0, got {context}")
    ops = list(ops)
    _require_text(ops, "unified_diff")
    return _unified_diff(
        ops,
        context,
        fromfile,
        tofile,
        fromfiledate,
        tofiledate,
        lineterm,
        ignore_blank_lines,
    )


def _unified_diff(
    ops: list[DiffOp[str]],
    context: int,
    fromfile: str,
    tofile: str,
    fromfiledate: str,
    tofiledate: str,
    lineterm: str,
    ignore_blank_lines: bool,
) -> Iterator[str]:
    a = [line for op in ops for line in op.a_lines]
    b = [line for op in ops for line in op.b_lines]
    started = False
    for group in _group([op.as_opcode() for op in ops], context):
        if ignore_blank_lines and _is_blank_group(group, a, b):
            continue
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


# --------------------------------------------------------------------------
# Side by side
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SideBySideRow:
    """One row of a side-by-side diff.

    ``mark`` is ``" "`` for unchanged lines, ``"|"`` for a changed pair,
    ``"<"`` for a line only on the left (deleted) and ``">"`` for a line only
    on the right (inserted), as in ``diff -y``. The indices are 0-based
    positions in the old/new sequences and the texts are the original items
    (line endings included); both are ``None`` on the empty side.
    """

    mark: str
    a_index: int | None
    b_index: int | None
    left: str | None
    right: str | None


def _rows(
    tag: str,
    a_start: int,
    a_lines: Sequence[str],
    b_start: int,
    b_lines: Sequence[str],
) -> Iterator[SideBySideRow]:
    """Rows for one opcode, given its lines on each side. A replaced block
    is paired line by line; the longer side's extra lines become one-sided
    rows."""
    for k in range(max(len(a_lines), len(b_lines))):
        has_old = k < len(a_lines)
        has_new = k < len(b_lines)
        if tag == "equal":
            mark = " "
        elif has_old and has_new:
            mark = "|"
        else:
            mark = "<" if has_old else ">"
        yield SideBySideRow(
            mark,
            a_start + k if has_old else None,
            b_start + k if has_new else None,
            a_lines[k] if has_old else None,
            b_lines[k] if has_new else None,
        )


def side_by_side_rows(ops: Iterable[DiffOp[str]]) -> list[SideBySideRow]:
    """Pair up the lines of a diff for side-by-side display.

    Use this to lay out your own columns; :func:`side_by_side` renders them
    as plain text.
    """
    rows: list[SideBySideRow] = []
    for op in ops:
        rows.extend(_rows(op.tag, op.a_start, op.a_lines, op.b_start, op.b_lines))
    return rows


def side_by_side(
    ops: Iterable[DiffOp[str]],
    *,
    width: int = 130,
    suppress_common_lines: bool = False,
    tabsize: int = 8,
    lineterm: str = "\n",
) -> Iterator[str]:
    """Render diff ops in two columns, like ``diff -y``.

    Each column is ``(width - 3) // 2`` characters wide; longer lines are cut
    off and tabs are expanded so the columns line up. The gutter between
    them holds the row's mark (see :class:`SideBySideRow`).

    :param width: total line width (``diff -W``).
    :param suppress_common_lines: leave out unchanged lines.
    :param tabsize: tab stop for expanding tabs.
    :param lineterm: appended to each output line.
    :raises TypeError: if the ops hold anything but strings.
    :raises ValueError: if ``width`` is less than 1.
    """
    if width < 1:
        raise ValueError(f"width must be >= 1, got {width}")
    ops = list(ops)
    _require_text(ops, "side_by_side")
    return _side_by_side(ops, width, suppress_common_lines, tabsize, lineterm)


def _side_by_side(
    ops: list[DiffOp[str]],
    width: int,
    suppress_common_lines: bool,
    tabsize: int,
    lineterm: str,
) -> Iterator[str]:
    column = max((width - 3) // 2, 1)

    def cell(text: str | None) -> str:
        if text is None:
            return ""
        return _strip_ending(text).expandtabs(tabsize)[:column]

    for row in side_by_side_rows(ops):
        if suppress_common_lines and row.mark == " ":
            continue
        line = f"{cell(row.left):<{column}} {row.mark} {cell(row.right)}"
        yield line.rstrip(" ") + lineterm


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------


def to_json(
    ops: Iterable[DiffOp[Any]],
    *,
    fromfile: str | None = None,
    tofile: str | None = None,
    algorithm: str | None = None,
    moves: Iterable[Move] | None = None,
    include_lines: bool = True,
    indent: int | None = None,
) -> str:
    """Serialize diff ops (and optionally moved blocks) as JSON.

    The document looks like::

        {"version": 1, "algorithm": "histogram",
         "old": {"path": "a.py", "length": 10},
         "new": {"path": "b.py", "length": 11},
         "ops": [{"tag": "equal", "a_start": 0, "a_end": 4,
                  "b_start": 0, "b_end": 4, "a_lines": [...], "b_lines": [...]},
                 ...],
         "moves": [{"a_start": ..., "a_end": ..., "b_start": ..., "b_end": ...,
                    "a_lines": [...], "b_lines": [...]}]}

    Indices are 0-based and ranges half-open, as in :class:`DiffOp`. Items
    must be JSON-serializable; lines keep their line endings.

    :param moves: moved blocks to include under ``"moves"`` (omitted if None).
    :param include_lines: include ``a_lines``/``b_lines``; without them the
        document is smaller but :func:`from_json` can't rebuild the ops.
    :param indent: passed to :func:`json.dumps`.
    """
    ops = list(ops)
    entries = []
    for op in ops:
        entry: dict[str, Any] = {
            "tag": op.tag,
            "a_start": op.a_start,
            "a_end": op.a_end,
            "b_start": op.b_start,
            "b_end": op.b_end,
        }
        if include_lines:
            entry["a_lines"] = list(op.a_lines)
            entry["b_lines"] = list(op.b_lines)
        entries.append(entry)

    doc: dict[str, Any] = {
        "version": JSON_VERSION,
        "algorithm": algorithm,
        "old": {"path": fromfile, "length": sum(op.a_end - op.a_start for op in ops)},
        "new": {"path": tofile, "length": sum(op.b_end - op.b_start for op in ops)},
        "ops": entries,
    }
    if moves is not None:
        move_entries = []
        for move in moves:
            move_entry: dict[str, Any] = {
                "a_start": move.a_start,
                "a_end": move.a_end,
                "b_start": move.b_start,
                "b_end": move.b_end,
            }
            if include_lines:
                move_entry["a_lines"] = list(move.a_lines)
                move_entry["b_lines"] = list(move.b_lines)
            move_entries.append(move_entry)
        doc["moves"] = move_entries
    return json.dumps(doc, indent=indent, ensure_ascii=False)


def from_json(data: str | bytes) -> list[DiffOp[Any]]:
    """Rebuild :class:`DiffOp` objects from :func:`to_json` output.

    :raises ValueError: if the document isn't histodiff JSON of a supported
        version, has an unknown tag, or was written without lines.
    """
    doc = json.loads(data)
    if not isinstance(doc, dict) or doc.get("version") != JSON_VERSION:
        raise ValueError(f"not histodiff JSON (expected version {JSON_VERSION})")
    ops: list[DiffOp[Any]] = []
    for entry in doc.get("ops", []):
        if entry.get("tag") not in _TAGS:
            raise ValueError(f"unknown op tag {entry.get('tag')!r}")
        if "a_lines" not in entry or "b_lines" not in entry:
            raise ValueError(
                "the JSON has no lines (written with include_lines=False), "
                "so the ops can't be rebuilt"
            )
        ops.append(
            DiffOp(
                entry["tag"],
                entry["a_start"],
                entry["a_end"],
                entry["b_start"],
                entry["b_end"],
                tuple(entry["a_lines"]),
                tuple(entry["b_lines"]),
            )
        )
    return ops
