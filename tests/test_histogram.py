from __future__ import annotations

import pytest

from helpers import check_valid, hunks, lcs_length, matched_lines, random_pairs
from histodiff import (
    DiffOp,
    diff,
    histogram_diff,
    myers_diff,
    patience_diff,
)
from histodiff.histogram import MAX_CHAIN
from samples import FROBNITZ_NEW, FROBNITZ_OLD


def test_trivial_cases() -> None:
    assert histogram_diff([], []) == []
    assert histogram_diff(["a"], ["a"]) == [DiffOp("equal", 0, 1, 0, 1, ("a",), ("a",))]
    assert [op.tag for op in histogram_diff(["a"], [])] == ["delete"]
    assert [op.tag for op in histogram_diff([], ["a"])] == ["insert"]
    assert [op.tag for op in histogram_diff(["a", "b"], ["c"])] == ["replace"]


@pytest.mark.parametrize("seed", range(20))
def test_random_inputs_are_valid(seed: int) -> None:
    for a, b in random_pairs(seed, 50):
        ops = histogram_diff(a, b)
        check_valid(a, b, ops)
        assert matched_lines(ops) <= lcs_length(a, b)


def test_prefers_rarest_lines_over_longest_match() -> None:
    # "}" occurs 3 times, "key" twice. Myers maximises matches ("}" x3);
    # patience finds no unique line and falls back to Myers; histogram
    # anchors on the rarer "key" lines.
    a = ["}", "}", "}", "key", "key"]
    b = ["key", "key", "}", "}", "}"]
    assert matched_lines(myers_diff(a, b)) == 3
    assert patience_diff(a, b) == myers_diff(a, b)

    ops = histogram_diff(a, b)
    check_valid(a, b, ops)
    assert [op for op in ops if op.tag == "equal"] == [
        DiffOp("equal", 3, 5, 0, 2, ("key", "key"), ("key", "key"))
    ]


def test_anchors_without_any_unique_line() -> None:
    # load/save/load/save -> save/load/save/load. Every line repeats, so
    # patience has no anchors and degrades to Myers, which "renames" each
    # function in four one-line hunks while keeping the identical bodies.
    # Histogram anchors on the rarer def lines and reports what actually
    # happened: the first `load` moved to the end.
    def func(name: str) -> list[str]:
        return [
            f"def {name}():",
            "    try:",
            "        pass",
            "    except Exception:",
            "        pass",
            "}",
            "",
        ]

    a = func("load") + func("save") + func("load") + func("save")
    b = func("save") + func("load") + func("save") + func("load")

    myers = myers_diff(a, b)
    assert hunks(myers) == 4
    assert all(op.tag in ("equal", "replace") for op in myers)
    assert patience_diff(a, b) == myers

    ops = histogram_diff(a, b)
    check_valid(a, b, ops)
    assert [op.as_opcode() for op in ops] == [
        ("delete", 0, 7, 0, 0),
        ("equal", 7, 28, 0, 21),
        ("insert", 28, 28, 21, 28),
    ]
    assert ops[0].a_lines == tuple(func("load"))
    assert ops[2].b_lines == tuple(func("load"))


def test_frobnitz_matches_patience() -> None:
    ops = histogram_diff(FROBNITZ_OLD, FROBNITZ_NEW)
    check_valid(FROBNITZ_OLD, FROBNITZ_NEW, ops)
    assert hunks(ops) == 4 < hunks(myers_diff(FROBNITZ_OLD, FROBNITZ_NEW))
    assert ops == patience_diff(FROBNITZ_OLD, FROBNITZ_NEW)


def test_overly_common_lines_fall_back_to_myers() -> None:
    n = MAX_CHAIN + 6
    a = ["head"] + ["x"] * n
    b = ["x"] * n + ["tail"]
    ops = histogram_diff(a, b)
    assert ops == myers_diff(a, b)
    assert matched_lines(ops) == n


def test_no_common_lines_is_a_single_replace() -> None:
    a = [f"old {i}" for i in range(3000)]
    b = [f"new {i}" for i in range(3000)]
    assert [op.tag for op in histogram_diff(a, b)] == ["replace"]


def test_large_file_small_edits() -> None:
    a = [f"line {i % 500}" for i in range(20_000)]
    b = list(a)
    b[100:100] = ["inserted"]
    del b[15_000:15_010]
    ops = histogram_diff(a, b)
    check_valid(a, b, ops)


@pytest.mark.parametrize("algorithm", ["myers", "patience", "histogram"])
def test_diff_dispatches(algorithm: str) -> None:
    a, b = FROBNITZ_OLD, FROBNITZ_NEW
    expected = {"myers": myers_diff, "patience": patience_diff}.get(
        algorithm, histogram_diff
    )(a, b)
    assert diff(a, b, algorithm=algorithm) == expected


def test_diff_defaults_to_histogram() -> None:
    a = ["}", "}", "}", "key", "key"]
    b = ["key", "key", "}", "}", "}"]
    assert diff(a, b) == histogram_diff(a, b)


def test_diff_rejects_unknown_algorithm() -> None:
    with pytest.raises(ValueError, match="unknown algorithm 'lcs'"):
        diff([], [], algorithm="lcs")
