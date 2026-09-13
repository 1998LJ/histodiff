"""Render diffs as a standalone HTML page (or just the table)."""

from __future__ import annotations

from collections.abc import Iterable
from html import escape

from ._core import DiffOp
from .format import (
    Segments,
    _format_range,
    _group,
    _is_blank_group,
    _require_text,
    _rows,
    _strip_ending,
)
from .moves import Move
from .words import highlight_words

__all__ = ["HTML_STYLE", "html_diff"]

#: The stylesheet :func:`html_diff` embeds. Everything is scoped to
#: ``table.histodiff``, so it can be dropped into another page as-is.
HTML_STYLE = """\
.histodiff {
  --hd-fg: #1f2328; --hd-muted: #6e7781; --hd-border: #d0d7de;
  --hd-hunk: #f6f8fa; --hd-old: #ffebe9; --hd-old-strong: #ffc1bc;
  --hd-new: #e6ffec; --hd-new-strong: #a6f0b8;
  --hd-moved-old: #f3ebff; --hd-moved-new: #ddf4ff;
  width: 100%; border-collapse: collapse; table-layout: fixed;
  font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--hd-fg);
}
@media (prefers-color-scheme: dark) {
  .histodiff {
    --hd-fg: #e6edf3; --hd-muted: #8b949e; --hd-border: #30363d;
    --hd-hunk: #161b22; --hd-old: rgba(248, 81, 73, .15);
    --hd-old-strong: rgba(248, 81, 73, .45); --hd-new: rgba(46, 160, 67, .15);
    --hd-new-strong: rgba(46, 160, 67, .45);
    --hd-moved-old: rgba(163, 113, 247, .18);
    --hd-moved-new: rgba(56, 139, 253, .18);
  }
}
.histodiff col.num { width: 4.5em; }
.histodiff th { text-align: left; padding: 6px 8px; font-weight: 600;
  border-bottom: 1px solid var(--hd-border); overflow-wrap: anywhere; }
.histodiff td { padding: 0 8px; vertical-align: top; }
.histodiff td.num { text-align: right; color: var(--hd-muted); user-select: none; }
.histodiff td.line { white-space: pre-wrap; overflow-wrap: anywhere; tab-size: 4; }
.histodiff td.old { background: var(--hd-old); }
.histodiff td.new { background: var(--hd-new); }
.histodiff td.old.moved { background: var(--hd-moved-old); }
.histodiff td.new.moved { background: var(--hd-moved-new); }
.histodiff td.empty { background: var(--hd-hunk); }
.histodiff del { background: var(--hd-old-strong); text-decoration: none; }
.histodiff ins { background: var(--hd-new-strong); text-decoration: none; }
.histodiff tr.hunk td { background: var(--hd-hunk); color: var(--hd-muted);
  padding: 4px 8px; }
.histodiff tr.no-changes td { padding: 16px; text-align: center;
  color: var(--hd-muted); }
"""

_ROW_CLASS = {" ": "equal", "|": "replace", "<": "delete", ">": "insert"}


def _cell(
    text: str | None,
    index: int | None,
    side: str,
    changed: bool,
    moved: set[int],
    segments: Segments | None,
) -> str:
    if text is None or index is None:
        return '<td class="num"></td><td class="line empty"></td>'
    classes = "line"
    if changed:
        classes += f" {side}"
    if index in moved:
        classes += " moved"
        segments = None  # moved lines are shown whole
    if segments is None:
        content = escape(_strip_ending(text), quote=False)
    else:
        mark = "del" if side == "old" else "ins"
        content = "".join(
            f"<{mark}>{escape(piece, quote=False)}</{mark}>"
            if piece_changed
            else escape(piece, quote=False)
            for piece, piece_changed in segments
        )
    return f'<td class="num">{index + 1}</td><td class="{classes}">{content}</td>'


def html_diff(
    ops: Iterable[DiffOp[str]],
    *,
    fromfile: str = "",
    tofile: str = "",
    context: int | None = 3,
    moves: Iterable[Move] = (),
    ignore_blank_lines: bool = False,
    algorithm: str = "histogram",
    title: str | None = None,
    full_page: bool = True,
) -> str:
    """Render diff ops as a side-by-side HTML table.

    Changed lines are paired side by side with their line numbers, the words
    that changed inside a replaced line are wrapped in ``<del>``/``<ins>``,
    and lines in ``moves`` get a ``moved`` class instead. The embedded
    :data:`HTML_STYLE` follows the reader's light/dark preference.

    :param ops: the result of :func:`histodiff.diff`; items must be strings.
    :param context: unchanged lines shown around each change, or ``None`` to
        show the whole file.
    :param moves: moved blocks, e.g. from :func:`histodiff.find_moves`.
    :param ignore_blank_lines: skip hunks whose changes are all blank lines.
    :param algorithm: algorithm for the word-level highlighting.
    :param title: page title; defaults to ``"fromfile → tofile"``.
    :param full_page: return a complete HTML document; with ``False`` just the
        ``<table class="histodiff">``, to embed with :data:`HTML_STYLE`.
    :raises TypeError: if the ops hold anything but strings.
    :raises ValueError: if ``context`` is negative.
    """
    ops = list(ops)
    _require_text(ops, "html_diff")
    if context is not None and context < 0:
        raise ValueError(f"context must be >= 0 or None, got {context}")
    a = [line for op in ops for line in op.a_lines]
    b = [line for op in ops for line in op.b_lines]
    codes = [op.as_opcode() for op in ops]
    if context is None:
        groups = [codes] if any(code[0] != "equal" for code in codes) else []
    else:
        groups = list(_group(codes, context))
    if ignore_blank_lines:
        groups = [group for group in groups if not _is_blank_group(group, a, b)]

    moves = list(moves)
    old_moved = {i for move in moves for i in range(move.a_start, move.a_end)}
    new_moved = {j for move in moves for j in range(move.b_start, move.b_end)}

    rows: list[str] = []
    for group in groups:
        first, last = group[0], group[-1]
        header = (
            f"@@ -{_format_range(first[1], last[2])} "
            f"+{_format_range(first[3], last[4])} @@"
        )
        rows.append(f'<tr class="hunk"><td colspan="4">{escape(header)}</td></tr>')
        for tag, i1, i2, j1, j2 in group:
            highlights = None
            if (
                tag == "replace"
                and old_moved.isdisjoint(range(i1, i2))
                and new_moved.isdisjoint(range(j1, j2))
            ):
                highlights = highlight_words(
                    [_strip_ending(line) for line in a[i1:i2]],
                    [_strip_ending(line) for line in b[j1:j2]],
                    algorithm=algorithm,
                )
            for row in _rows(tag, i1, a[i1:i2], j1, b[j1:j2]):
                changed = row.mark != " "
                old_segments = new_segments = None
                if highlights is not None:
                    if row.a_index is not None:
                        old_segments = highlights[0][row.a_index - i1]
                    if row.b_index is not None:
                        new_segments = highlights[1][row.b_index - j1]
                left = _cell(row.left, row.a_index, "old", changed, old_moved,
                             old_segments)
                right = _cell(row.right, row.b_index, "new", changed, new_moved,
                              new_segments)
                rows.append(f'<tr class="{_ROW_CLASS[row.mark]}">{left}{right}</tr>')
    if not groups:
        rows.append('<tr class="no-changes"><td colspan="4">No differences</td></tr>')

    table = (
        '<table class="histodiff">\n'
        '<colgroup><col class="num"><col><col class="num"><col></colgroup>\n'
        f'<thead><tr><th colspan="2">{escape(fromfile)}</th>'
        f'<th colspan="2">{escape(tofile)}</th></tr></thead>\n'
        "<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>\n"
    )
    if not full_page:
        return table

    if title is None:
        title = f"{fromfile} → {tofile}" if fromfile or tofile else "histodiff"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f"<title>{escape(title)}</title>\n"
        "<style>\nbody { margin: 0; padding: 16px; background: Canvas; "
        "color: CanvasText; }\n"
        f"{HTML_STYLE}</style>\n</head>\n<body>\n{table}</body>\n</html>\n"
    )
