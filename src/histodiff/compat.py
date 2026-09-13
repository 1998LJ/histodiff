"""A drop-in replacement for :class:`difflib.SequenceMatcher`."""

from __future__ import annotations

import difflib
from collections.abc import Callable, Hashable, Sequence
from typing import Any

from ._core import DiffOp, build_ops, intern_lines
from .histogram import histogram_matches
from .myers import myers_matches
from .patience import patience_matches

__all__ = ["SequenceMatcher"]

_ALGORITHMS = ("myers", "patience", "histogram")


def _align(
    a: Sequence[Hashable],
    b: Sequence[Hashable],
    algorithm: str,
    minimal: bool,
    isjunk: Callable[[Any], bool] | None,
) -> list[DiffOp]:
    ia, ib = intern_lines(a, b)  # type: ignore[arg-type]
    if algorithm == "myers":
        # Myers has no anchors, so junk makes no difference to it.
        matches = myers_matches(ia, 0, len(ia), ib, 0, len(ib), minimal)
    else:
        junk: frozenset[int] = frozenset()
        if isjunk is not None:
            junk = frozenset(i for item, i in dict(zip(b, ib)).items() if isjunk(item))
        func = patience_matches if algorithm == "patience" else histogram_matches
        matches = func(ia, 0, len(ia), ib, 0, len(ib), minimal, junk)
    matches.sort()
    return build_ops(a, b, matches)  # type: ignore[arg-type]


class SequenceMatcher(difflib.SequenceMatcher):  # type: ignore[type-arg]
    """:class:`difflib.SequenceMatcher`, aligned with histodiff's algorithms.

    Change ``from difflib import SequenceMatcher`` to
    ``from histodiff import SequenceMatcher`` and everything built on the
    alignment - :meth:`get_matching_blocks`, :meth:`get_opcodes`,
    :meth:`get_grouped_opcodes`, :meth:`ratio` - uses histogram diff (or
    ``algorithm=``) instead of difflib's longest-match heuristic. It is a
    real subclass, so ``isinstance(m, difflib.SequenceMatcher)`` holds and
    the other methods behave as documented for difflib.

    As with difflib, ``a`` and ``b`` can be any sequences of hashable items:
    lists of lines, strings (compared character by character), tokens...

    Differences from difflib:

    * ``isjunk`` items are never used as anchors by patience or histogram,
      but can still be matched when they fall between anchors - in the same
      spirit as difflib, where junk only matches next to a real match.
      Myers ignores ``isjunk``.
    * ``autojunk`` is accepted for compatibility but does not affect the
      alignment: histodiff copes with frequent lines on its own, and
      difflib's popularity heuristic is what makes its large diffs poor.
    * :meth:`find_longest_match` is inherited unchanged, so it still answers
      difflib's question (longest contiguous block, with ``autojunk``).
    * Opcodes can differ from difflib's - that's the point - but always
      describe a valid transformation of ``a`` into ``b``, and ``ratio()``
      reflects the better alignment.

    :param algorithm: ``"histogram"`` (default), ``"patience"`` or ``"myers"``.
    :param minimal: see :func:`histodiff.diff`.
    """

    def __init__(
        self,
        isjunk: Callable[[Any], bool] | None = None,
        a: Sequence[Any] = "",
        b: Sequence[Any] = "",
        autojunk: bool = True,
        *,
        algorithm: str = "histogram",
        minimal: bool = False,
    ) -> None:
        if algorithm not in _ALGORITHMS:
            choices = ", ".join(repr(name) for name in _ALGORITHMS)
            raise ValueError(
                f"unknown algorithm {algorithm!r}; expected one of {choices}"
            )
        self.algorithm = algorithm
        self.minimal = minimal
        self._diff_ops: list[DiffOp] | None = None
        super().__init__(isjunk, a, b, autojunk)

    def set_seq1(self, a: Sequence[Any]) -> None:
        super().set_seq1(a)
        self._diff_ops = None

    def set_seq2(self, b: Sequence[Any]) -> None:
        super().set_seq2(b)
        self._diff_ops = None

    def get_diff_ops(self) -> list[DiffOp]:
        """The alignment as histodiff :class:`~histodiff.DiffOp` objects.

        Useful for :func:`histodiff.unified_diff`, which takes ops.
        """
        if self._diff_ops is None:
            self._diff_ops = _align(
                self.a, self.b, self.algorithm, self.minimal, self.isjunk
            )
        return self._diff_ops

    def get_matching_blocks(self) -> list[difflib.Match]:
        """Return maximal matching blocks, ending with ``(len(a), len(b), 0)``.

        Same format as difflib's; every other alignment method is derived
        from this one, exactly as in difflib.
        """
        if self.matching_blocks is not None:
            return self.matching_blocks
        blocks = [
            difflib.Match(op.a_start, op.b_start, op.a_end - op.a_start)
            for op in self.get_diff_ops()
            if op.tag == "equal"
        ]
        blocks.append(difflib.Match(len(self.a), len(self.b), 0))
        self.matching_blocks = blocks
        return blocks
