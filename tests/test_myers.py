from __future__ import annotations

import pytest

from helpers import changed_lines, check_valid, lcs_length, random_pairs
from histodiff import DiffOp, myers_diff


def test_both_empty() -> None:
    assert myers_diff([], []) == []


def test_identical() -> None:
    a = ["x", "y", "z"]
    lines = ("x", "y", "z")
    assert myers_diff(a, list(a)) == [DiffOp("equal", 0, 3, 0, 3, lines, lines)]


def test_all_inserted() -> None:
    assert myers_diff([], ["a", "b"]) == [DiffOp("insert", 0, 0, 0, 2, (), ("a", "b"))]


def test_all_deleted() -> None:
    assert myers_diff(["a", "b"], []) == [DiffOp("delete", 0, 2, 0, 0, ("a", "b"), ())]


def test_completely_different_is_one_replace() -> None:
    ops = myers_diff(["a", "b"], ["c", "d", "e"])
    assert [op.tag for op in ops] == ["replace"]


def test_single_change_in_middle() -> None:
    a = ["1", "2", "3", "4", "5"]
    b = ["1", "2", "X", "4", "5"]
    ops = myers_diff(a, b)
    assert [op.as_opcode() for op in ops] == [
        ("equal", 0, 2, 0, 2),
        ("replace", 2, 3, 2, 3),
        ("equal", 3, 5, 3, 5),
    ]


def test_paper_example() -> None:
    # The worked example from Myers' paper: ABCABBA -> CBABAC has D = 5.
    a, b = list("ABCABBA"), list("CBABAC")
    ops = myers_diff(a, b)
    check_valid(a, b, ops)
    assert changed_lines(ops) == 5


@pytest.mark.parametrize("seed", range(20))
def test_random_inputs_are_minimal(seed: int) -> None:
    for a, b in random_pairs(seed, 50):
        ops = myers_diff(a, b)
        check_valid(a, b, ops)
        # Minimal edit script <=> matched lines equal the LCS length.
        assert changed_lines(ops) == len(a) + len(b) - 2 * lcs_length(a, b)


def test_larger_input_is_minimal() -> None:
    for a, b in random_pairs(99, 5, max_len=80, alphabet="abcdefgh"):
        ops = myers_diff(a, b)
        check_valid(a, b, ops)
        assert changed_lines(ops) == len(a) + len(b) - 2 * lcs_length(a, b)


def test_long_inputs_run_quickly() -> None:
    a = [f"line {i}" for i in range(20_000)]
    b = list(a)
    del b[5000:5100]
    b[12000:12000] = ["new"] * 50
    ops = myers_diff(a, b)
    check_valid(a, b, ops)
    assert changed_lines(ops) == 150
