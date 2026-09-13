"""histodiff.SequenceMatcher as a drop-in for difflib.SequenceMatcher."""

from __future__ import annotations

import difflib
import random

import pytest

from helpers import random_pairs
from histodiff import (
    SequenceMatcher,
    diff,
    histogram_diff,
    myers_diff,
    patience_diff,
    unified_diff,
)
from test_readability import python_function


def test_is_a_difflib_sequence_matcher() -> None:
    assert isinstance(SequenceMatcher(None, "a", "b"), difflib.SequenceMatcher)


@pytest.mark.parametrize("seed", range(5))
def test_opcodes_come_from_histodiff(seed: int) -> None:
    for a, b in random_pairs(seed, 40, max_len=30, alphabet="abcdef"):
        sm = SequenceMatcher(None, a, b)
        assert sm.get_opcodes() == [op.as_opcode() for op in diff(a, b)]
        assert sm.get_diff_ops() == diff(a, b)


@pytest.mark.parametrize("seed", range(5))
def test_difflib_invariants_hold(seed: int) -> None:
    for a, b in random_pairs(seed, 40, max_len=30, alphabet="abc"):
        sm = SequenceMatcher(None, a, b)
        blocks = sm.get_matching_blocks()
        assert blocks[-1] == (len(a), len(b), 0)
        assert all(isinstance(block, difflib.Match) for block in blocks)
        for (i1, j1, n1), (i2, j2, n2) in zip(blocks, blocks[1:]):
            assert n1 > 0
            assert i1 + n1 <= i2 and j1 + n1 <= j2
            # Maximal: adjacent blocks are never contiguous in both sequences.
            assert not (i1 + n1 == i2 and j1 + n1 == j2 and n2 > 0)
        for i, j, n in blocks:
            assert list(a[i : i + n]) == list(b[j : j + n])

        matched = sum(n for _, _, n in blocks)
        total = len(a) + len(b)
        assert sm.ratio() == (2.0 * matched / total if total else 1.0)
        assert sm.real_quick_ratio() >= sm.quick_ratio() >= sm.ratio()


def test_same_results_as_difflib_when_alignments_agree() -> None:
    a = [f"line {i}\n" for i in range(30)]
    b = list(a)
    b[10] = "changed\n"
    del b[20]
    ours, theirs = SequenceMatcher(None, a, b), difflib.SequenceMatcher(None, a, b)
    assert ours.get_matching_blocks() == theirs.get_matching_blocks()
    assert ours.get_opcodes() == theirs.get_opcodes()
    for n in (0, 1, 3, 5):
        assert list(ours.get_grouped_opcodes(n)) == list(theirs.get_grouped_opcodes(n))
    assert ours.ratio() == theirs.ratio()


def test_character_sequences() -> None:
    sm = SequenceMatcher(
        None, "private Thread currentThread;", "private volatile Thread currentThread;"
    )
    assert sm.get_opcodes() == [
        ("equal", 0, 8, 0, 8),
        ("insert", 8, 8, 8, 17),
        ("equal", 8, 29, 17, 38),
    ]
    assert round(sm.ratio(), 3) == 0.866


def test_non_string_items() -> None:
    a = [1, 2, (3, 4), None, 5]
    b = [1, (3, 4), None, 6, 5]
    ops = SequenceMatcher(None, a, b).get_opcodes()
    assert ops == [
        ("equal", 0, 1, 0, 1),
        ("delete", 1, 2, 1, 1),
        ("equal", 2, 4, 1, 3),
        ("insert", 4, 4, 3, 4),
        ("equal", 4, 5, 4, 5),
    ]


def test_better_ratio_on_moved_function() -> None:
    funcs = [python_function(i) for i in range(20)]
    old = sum(funcs, [])
    new = sum(funcs[:3] + funcs[4:] + [funcs[3]], [])
    ours = SequenceMatcher(None, old, new).ratio()
    theirs = difflib.SequenceMatcher(None, old, new).ratio()
    assert ours == pytest.approx(0.95)  # 228 of 240 lines kept
    assert theirs < 0.25


def test_set_seqs_invalidates_cached_results() -> None:
    sm = SequenceMatcher(None, ["a", "b"], ["a", "b"])
    assert sm.get_opcodes() == [("equal", 0, 2, 0, 2)]
    sm.set_seq2(["a", "c"])
    assert sm.get_opcodes() == [("equal", 0, 1, 0, 1), ("replace", 1, 2, 1, 2)]
    sm.set_seq1(["x"])
    assert sm.get_opcodes() == [("replace", 0, 1, 0, 2)]
    sm.set_seqs("abc", "abc")
    assert sm.ratio() == 1.0


def test_reusing_one_matcher_like_difflib_docs_suggest() -> None:
    # difflib recommends set_seq2 once and set_seq1 per candidate.
    words = ["apple", "ape", "apply", "maple", "people"]
    sm = SequenceMatcher()
    sm.set_seq2("appel")
    scores = {}
    for word in words:
        sm.set_seq1(word)
        scores[word] = sm.ratio()
    for word in words:
        assert scores[word] == SequenceMatcher(None, word, "appel").ratio()


@pytest.mark.parametrize(
    ("algorithm", "func"),
    [("myers", myers_diff), ("patience", patience_diff), ("histogram", histogram_diff)],
)
def test_algorithm_option(algorithm, func) -> None:
    rng = random.Random(algorithm)
    a = [rng.choice("abcd") for _ in range(50)]
    b = [rng.choice("abcd") for _ in range(50)]
    sm = SequenceMatcher(None, a, b, algorithm=algorithm)
    assert sm.get_opcodes() == [op.as_opcode() for op in func(a, b)]


def test_minimal_option() -> None:
    a, b = list("abcabba"), list("cbabac")
    sm = SequenceMatcher(None, a, b, algorithm="myers", minimal=True)
    assert sm.get_diff_ops() == myers_diff(a, b, minimal=True)


def test_unknown_algorithm_rejected() -> None:
    with pytest.raises(ValueError, match="unknown algorithm 'lcs'"):
        SequenceMatcher(None, "a", "b", algorithm="lcs")


@pytest.mark.parametrize("algorithm", ["patience", "histogram"])
def test_isjunk_lines_are_not_anchors(algorithm: str) -> None:
    # "---" is the only unique line, so it would normally anchor the diff.
    a = ["---", "p", "p"]
    b = ["p", "p", "---"]
    plain = SequenceMatcher(None, a, b, algorithm=algorithm)
    assert plain.get_matching_blocks() == [(0, 2, 1), (3, 3, 0)]

    junked = SequenceMatcher(lambda line: line == "---", a, b, algorithm=algorithm)
    assert junked.get_matching_blocks() == [(1, 0, 2), (3, 3, 0)]
    # difflib's own junk bookkeeping still works.
    assert junked.bjunk == {"---"}


def test_autojunk_does_not_affect_alignment() -> None:
    rows = ["0,0,0,0"] * 300
    new = rows[:150] + ["1,2,3,4"] + rows[150:]
    for autojunk in (True, False):
        sm = SequenceMatcher(None, rows, new, autojunk=autojunk)
        assert sm.get_opcodes() == [
            ("equal", 0, 150, 0, 150),
            ("insert", 150, 150, 150, 151),
            ("equal", 150, 300, 151, 301),
        ]


def test_diff_ops_feed_unified_diff() -> None:
    a = ["one\n", "two\n"]
    b = ["one\n", "2\n"]
    text = "".join(unified_diff(SequenceMatcher(None, a, b).get_diff_ops()))
    assert text == "--- \n+++ \n@@ -1,2 +1,2 @@\n one\n-two\n+2\n"
