"""histodiff - alignment-aware diffing using Myers, patience and histogram."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Callable

from ._core import DiffOp
from .format import unified_diff
from .histogram import histogram_diff
from .myers import myers_diff
from .patience import patience_diff

__all__ = [
    "ALGORITHMS",
    "DiffOp",
    "diff",
    "histogram_diff",
    "myers_diff",
    "patience_diff",
    "unified_diff",
]
__version__ = "0.1.0"

#: Algorithm name -> implementation, for :func:`diff` and the CLI.
ALGORITHMS: dict[str, Callable[..., list[DiffOp]]] = {
    "myers": myers_diff,
    "patience": patience_diff,
    "histogram": histogram_diff,
}


def diff(
    a: Sequence[str],
    b: Sequence[str],
    algorithm: str = "histogram",
    *,
    minimal: bool = False,
) -> list[DiffOp]:
    """Diff two sequences of lines.

    :param a: the old lines.
    :param b: the new lines.
    :param algorithm: ``"histogram"`` (default), ``"patience"`` or ``"myers"``.
    :param minimal: never trade diff size for speed. By default Myers (and
        the Myers fallback inside patience and histogram) caps its search on
        large, very different inputs, like ``git diff`` does; with
        ``minimal=True`` it always finds the smallest edit script, which can
        take quadratic time.
    :returns: :class:`DiffOp` objects that together cover all of ``a`` and ``b``.
    :raises ValueError: if ``algorithm`` is not recognised.
    """
    try:
        func = ALGORITHMS[algorithm]
    except KeyError:
        choices = ", ".join(repr(name) for name in ALGORITHMS)
        raise ValueError(
            f"unknown algorithm {algorithm!r}; expected one of {choices}"
        ) from None
    return func(a, b, minimal=minimal)
