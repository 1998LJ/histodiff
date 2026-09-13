"""Word-level diffs inside changed lines.

When a block of lines is replaced, a second diff over the *words* of the
old and new lines shows which parts actually changed. The whole block is
tokenized at once (with a separator between lines), so a word that moved to
the next line still matches.

* :func:`highlight_words` keeps the line structure and marks the changed
  parts of each line - what ``histodiff --color`` highlights.
* :func:`inline_word_diff` merges both sides into one stream of equal,
  deleted and inserted text - what ``histodiff --color-words`` prints, like
  ``git diff --color-words``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any, Literal

from ._core import DiffOp
from .histogram import histogram_diff
from .myers import myers_diff
from .patience import patience_diff

__all__ = [
    "MAX_TOKENS",
    "Segment",
    "highlight_words",
    "inline_word_diff",
    "split_words",
]

#: Blocks with more tokens than this (both sides together) are not
#: word-diffed; they are shown as whole changed lines instead.
MAX_TOKENS = 10_000

#: ``(text, changed)`` - one piece of a line.
Segment = tuple[str, bool]

# Words, whitespace runs, and single punctuation characters. Together they
# cover every character, so the tokens always join back into the input.
_TOKEN = re.compile(r"\w+|\s+|[^\w\s]")

# Placed between lines; lines passed in never contain a newline.
_SEP = "\n"

_ALGORITHMS: dict[str, Callable[..., list[DiffOp[Any]]]] = {
    "myers": myers_diff,
    "patience": patience_diff,
    "histogram": histogram_diff,
}


def split_words(text: str) -> list[str]:
    """Split text into words, whitespace runs and punctuation characters.

    >>> split_words("result = process(event)")
    ['result', ' ', '=', ' ', 'process', '(', 'event', ')']

    ``"".join(split_words(text)) == text`` always holds.
    """
    return _TOKEN.findall(text)


def _tokenize(lines: Sequence[str]) -> tuple[list[str], list[int]]:
    """Tokens of all lines, plus the line each belongs to (-1 = separator)."""
    tokens: list[str] = []
    owners: list[int] = []
    for number, line in enumerate(lines):
        if number:
            tokens.append(_SEP)
            owners.append(-1)
        for token in split_words(line):
            tokens.append(token)
            owners.append(number)
    return tokens, owners


def _token_diff(
    old_lines: Sequence[str], new_lines: Sequence[str], algorithm: str
) -> tuple[list[str], list[int], list[str], list[int], list[DiffOp[str]]] | None:
    try:
        func = _ALGORITHMS[algorithm]
    except KeyError:
        choices = ", ".join(repr(name) for name in _ALGORITHMS)
        raise ValueError(
            f"unknown algorithm {algorithm!r}; expected one of {choices}"
        ) from None
    for line in (*old_lines, *new_lines):
        if "\n" in line:
            raise ValueError("lines must not contain newlines; strip line endings")
    old_tokens, old_owners = _tokenize(old_lines)
    new_tokens, new_owners = _tokenize(new_lines)
    if len(old_tokens) + len(new_tokens) > MAX_TOKENS:
        return None
    ops = func(old_tokens, new_tokens)
    return old_tokens, old_owners, new_tokens, new_owners, ops


def _segments(
    tokens: list[str], owners: list[int], changed: list[bool], n_lines: int
) -> list[list[Segment]]:
    lines: list[list[Segment]] = [[] for _ in range(n_lines)]
    for token, owner, flag in zip(tokens, owners, changed):
        if owner < 0:
            continue
        pieces = lines[owner]
        if pieces and pieces[-1][1] == flag:
            pieces[-1] = (pieces[-1][0] + token, flag)
        else:
            pieces.append((token, flag))
    return lines


def _visible_chars(tokens: Sequence[str]) -> int:
    return sum(len(token) for token in tokens if not token.isspace())


def highlight_words(
    old_lines: Sequence[str],
    new_lines: Sequence[str],
    *,
    algorithm: str = "histogram",
    min_similarity: float = 0.5,
) -> tuple[list[list[Segment]], list[list[Segment]]] | None:
    """Mark which parts of a replaced block of lines changed.

    Returns ``(old_segments, new_segments)``: for every line, a list of
    ``(text, changed)`` pieces that join back into the line. Returns
    ``None`` when highlighting wouldn't help - either side is empty, the
    block exceeds :data:`MAX_TOKENS`, or less than ``min_similarity`` of the
    non-whitespace text is shared (so highlighting would mark nearly
    everything).

    >>> highlight_words(["x = process(a)"], ["x = process_v2(a)"])
    ([[('x = ', False), ('process', True), ('(a)', False)]], \
[[('x = ', False), ('process_v2', True), ('(a)', False)]])

    :param old_lines: the removed lines, without line endings.
    :param new_lines: the added lines, without line endings.
    :param algorithm: algorithm for the word diff.
    :param min_similarity: from 0 (always highlight) to 1 (only highlight
        whitespace-only changes).
    """
    if not old_lines or not new_lines:
        return None
    result = _token_diff(old_lines, new_lines, algorithm)
    if result is None:
        return None
    old_tokens, old_owners, new_tokens, new_owners, ops = result

    old_changed = [True] * len(old_tokens)
    new_changed = [True] * len(new_tokens)
    kept = 0
    for op in ops:
        if op.tag == "equal":
            old_changed[op.a_start : op.a_end] = [False] * (op.a_end - op.a_start)
            new_changed[op.b_start : op.b_end] = [False] * (op.b_end - op.b_start)
            kept += 2 * _visible_chars(op.a_lines)

    total = _visible_chars(old_tokens) + _visible_chars(new_tokens)
    if total and kept / total < min_similarity:
        return None
    return (
        _segments(old_tokens, old_owners, old_changed, len(old_lines)),
        _segments(new_tokens, new_owners, new_changed, len(new_lines)),
    )


def inline_word_diff(
    old_lines: Sequence[str],
    new_lines: Sequence[str],
    *,
    algorithm: str = "histogram",
) -> list[tuple[Literal["equal", "delete", "insert"], str]]:
    """Merge a replaced block into one stream of equal/deleted/inserted text.

    Returns ``(tag, text)`` runs. Lines are joined with ``"\\n"``; a newline
    that exists only in the old text is shown as a space, so the result
    follows the new text's line structure. Blocks over :data:`MAX_TOKENS`
    come back as one deleted and one inserted run.

    >>> inline_word_diff(["x = process(a)"], ["x = process_v2(a)"])
    [('equal', 'x = '), ('delete', 'process'), ('insert', 'process_v2'), \
('equal', '(a)')]
    """
    result = _token_diff(old_lines, new_lines, algorithm)
    if result is None:
        runs: list[tuple[Literal["equal", "delete", "insert"], str]] = []
        if old_lines:
            runs.append(("delete", " ".join(old_lines)))
        if new_lines:
            runs.append(("insert", "\n".join(new_lines)))
        return runs
    ops = result[4]

    runs = []

    def add(tag: Literal["equal", "delete", "insert"], text: str) -> None:
        if not text:
            return
        if runs and runs[-1][0] == tag:
            runs[-1] = (tag, runs[-1][1] + text)
        else:
            runs.append((tag, text))

    for op in ops:
        if op.tag == "equal":
            add("equal", "".join(op.a_lines))
        else:
            add("delete", "".join(" " if t == _SEP else t for t in op.a_lines))
            add("insert", "".join(op.b_lines))
    return runs
