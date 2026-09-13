from __future__ import annotations

import pytest

from helpers import check_valid, hunks, lcs_length, matched_lines, random_pairs
from histodiff import DiffOp, myers_diff, patience_diff
from histodiff.patience import _longest_increasing
from samples import FROBNITZ_NEW, FROBNITZ_OLD


def test_trivial_cases() -> None:
    assert patience_diff([], []) == []
    assert patience_diff(["a"], ["a"]) == [DiffOp("equal", 0, 1, 0, 1, ("a",), ("a",))]
    assert [op.tag for op in patience_diff(["a"], [])] == ["delete"]
    assert [op.tag for op in patience_diff([], ["a"])] == ["insert"]
    assert [op.tag for op in patience_diff(["a"], ["b"])] == ["replace"]


def test_longest_increasing() -> None:
    pairs = [(0, 3), (1, 0), (2, 1), (3, 4), (4, 2), (5, 5)]
    result = _longest_increasing(pairs)
    # Several subsequences of length 4 exist; any one is correct.
    assert len(result) == 4
    assert all(p in pairs for p in result)
    assert all(x[0] < y[0] and x[1] < y[1] for x, y in zip(result, result[1:]))
    assert _longest_increasing([]) == []


@pytest.mark.parametrize("seed", range(20))
def test_random_inputs_are_valid(seed: int) -> None:
    for a, b in random_pairs(seed, 50):
        ops = patience_diff(a, b)
        check_valid(a, b, ops)
        assert matched_lines(ops) <= lcs_length(a, b)


def test_no_unique_lines_falls_back_to_myers() -> None:
    # Every line repeats, so there are no anchors: result must equal Myers.
    a = ["x", "y", "x", "y", "z", "z"]
    b = ["y", "x", "z", "y", "x", "z"]
    assert patience_diff(a, b) == myers_diff(a, b)


def test_unique_lines_anchor_the_diff() -> None:
    # Myers prefers matching the two repeated "}" lines (2 matches) over the
    # single unique "def keep" line; patience anchors on the unique line.
    a = ["}", "}", "def keep"]
    b = ["def keep", "}", "}"]
    assert matched_lines(myers_diff(a, b)) == 2
    ops = patience_diff(a, b)
    check_valid(a, b, ops)
    kept = [op for op in ops if op.tag == "equal"]
    assert kept == [DiffOp("equal", 2, 3, 0, 1, ("def keep",), ("def keep",))]


def test_frobnitz_keeps_functions_whole() -> None:
    myers = myers_diff(FROBNITZ_OLD, FROBNITZ_NEW)
    ops = patience_diff(FROBNITZ_OLD, FROBNITZ_NEW)
    check_valid(FROBNITZ_OLD, FROBNITZ_NEW, ops)

    assert hunks(ops) == 4 < hunks(myers)
    changes = [op for op in ops if op.tag != "equal"]
    # fib() is one contiguous insertion...
    assert changes[0].tag == "insert"
    assert changes[0].b_lines[0] == "int fib(int n)"
    assert len(changes[0].b_lines) == 9
    # ...one line removed from frobnitz...
    assert changes[1].a_lines == ('        printf("Your answer is: ");',)
    # ...fact() is one contiguous deletion...
    assert changes[2].tag == "delete"
    assert changes[2].a_lines[0] == "int fact(int n)"
    assert len(changes[2].a_lines) == 9
    # ...and the call site changes.
    assert changes[3].tag == "replace"


def test_fully_reversed_input() -> None:
    # Only one anchor can survive the ordering constraint.
    n = 5000
    a = [f"u{i}" for i in range(n)]
    b = list(reversed(a))
    ops = patience_diff(a, b)
    check_valid(a, b, ops)
