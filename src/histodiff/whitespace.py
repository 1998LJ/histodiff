"""Whitespace-insensitive diffs, like ``diff -b``, ``diff -w`` and ``diff -B``.

:func:`ignore_space_change` and :func:`ignore_all_space` are ``key``
functions: diff with them and lines are *matched* on their normalized form,
while the ops (and so the printed diff) still hold the original lines::

    ops = histodiff.diff(old, new, key=histodiff.ignore_space_change)

Ignoring blank lines is different: it hides whole changes rather than
changing how lines compare, so it is an option of
:func:`histodiff.unified_diff` (``ignore_blank_lines=True``).
"""

from __future__ import annotations

__all__ = ["ignore_all_space", "ignore_space_change", "is_blank"]


def ignore_space_change(line: str) -> str:
    """Key that ignores changes in the *amount* of whitespace (``diff -b``).

    Trailing whitespace (including the line ending) is ignored and every
    other run of whitespace counts as a single space. Having whitespace
    still differs from having none, so ``"    x"`` equals ``"\\tx"`` but not
    ``"x"``, and ``"a b"`` equals ``"a   b"`` but not ``"ab"``.
    """
    stripped = line.rstrip()
    indented = stripped[:1].isspace()
    return (" " if indented else "") + " ".join(stripped.split())


def ignore_all_space(line: str) -> str:
    """Key that ignores all whitespace (``diff -w``).

    ``"a b\\n"``, ``"ab"`` and ``"  a\\tb  "`` all compare equal.
    """
    return "".join(line.split())


def is_blank(line: str) -> bool:
    """Whether a line is empty or contains only whitespace."""
    return not line.strip()
