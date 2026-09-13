"""Shared assertions for algorithm tests."""

from __future__ import annotations

import random
from collections.abc import Sequence
from functools import cache

from histodiff import DiffOp


def apply_ops(a: Sequence[str], ops: list[DiffOp]) -> list[str]:
    """Rebuild ``b`` from ``a`` and the ops, checking they tile both sequences."""
    out: list[str] = []
    i = j = 0
    for op in ops:
        assert op.a_start == i, (op, i)
        assert op.b_start == j, (op, j)
        assert list(op.a_lines) == list(a[op.a_start : op.a_end])
        if op.tag == "equal":
            assert op.a_lines == op.b_lines
            assert op.a_end - op.a_start == op.b_end - op.b_start > 0
        elif op.tag == "delete":
            assert op.a_end > op.a_start and op.b_end == op.b_start
        elif op.tag == "insert":
            assert op.b_end > op.b_start and op.a_end == op.a_start
        elif op.tag == "replace":
            assert op.a_end > op.a_start and op.b_end > op.b_start
        else:
            raise AssertionError(f"bad tag {op.tag!r}")
        out.extend(op.b_lines)
        i, j = op.a_end, op.b_end
    assert i == len(a)
    return out


def check_valid(a: Sequence[str], b: Sequence[str], ops: list[DiffOp]) -> None:
    assert apply_ops(a, ops) == list(b)
    # Adjacent ops never share a tag (runs are merged, gaps are one op).
    for prev, cur in zip(ops, ops[1:]):
        assert not (prev.tag == cur.tag == "equal")
        assert prev.tag == "equal" or cur.tag == "equal"


def matched_lines(ops: list[DiffOp]) -> int:
    return sum(op.a_end - op.a_start for op in ops if op.tag == "equal")


def changed_lines(ops: list[DiffOp]) -> int:
    return sum(
        (op.a_end - op.a_start) + (op.b_end - op.b_start)
        for op in ops
        if op.tag != "equal"
    )


def hunks(ops: list[DiffOp]) -> int:
    return sum(op.tag != "equal" for op in ops)


def lcs_length(a: Sequence[str], b: Sequence[str]) -> int:
    @cache
    def go(i: int, j: int) -> int:
        if i == len(a) or j == len(b):
            return 0
        if a[i] == b[j]:
            return 1 + go(i + 1, j + 1)
        return max(go(i + 1, j), go(i, j + 1))

    return go(0, 0)


def random_pairs(seed: int, count: int, max_len: int = 12, alphabet: str = "abcd"):
    rng = random.Random(seed)
    for _ in range(count):
        a = [rng.choice(alphabet) for _ in range(rng.randint(0, max_len))]
        b = [rng.choice(alphabet) for _ in range(rng.randint(0, max_len))]
        yield a, b
