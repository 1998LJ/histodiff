from __future__ import annotations

import difflib

import pytest

from helpers import random_pairs
from histodiff import diff, unified_diff


@pytest.fixture
def difflib_with_our_alignment(monkeypatch: pytest.MonkeyPatch):
    """Make difflib.unified_diff use histodiff's alignment.

    That isolates the formatter: for any input, our unified_diff must then
    produce exactly the same text as difflib's.
    """
    real = difflib.SequenceMatcher

    class HistodiffMatcher(real):  # type: ignore[misc, valid-type]
        def get_opcodes(self):  # type: ignore[no-untyped-def]
            return [op.as_opcode() for op in diff(self.a, self.b)]

    monkeypatch.setattr(difflib, "SequenceMatcher", HistodiffMatcher)


@pytest.mark.parametrize("context", [0, 1, 3])
@pytest.mark.parametrize("seed", range(5))
def test_matches_difflib_byte_for_byte(
    difflib_with_our_alignment: None, seed: int, context: int
) -> None:
    for a, b in random_pairs(seed, 40, max_len=40, alphabet="abcdef"):
        a = [line + "\n" for line in a]
        b = [line + "\n" for line in b]
        expected = list(
            difflib.unified_diff(a, b, "old.txt", "new.txt", "d1", "d2", n=context)
        )
        actual = list(
            unified_diff(
                diff(a, b),
                context,
                fromfile="old.txt",
                tofile="new.txt",
                fromfiledate="d1",
                tofiledate="d2",
            )
        )
        assert actual == expected


def test_simple_change() -> None:
    a = ["one\n", "two\n", "three\n", "four\n", "five\n"]
    b = ["one\n", "two\n", "3\n", "four\n", "five\n"]
    text = "".join(unified_diff(diff(a, b), context=1, fromfile="a", tofile="b"))
    assert text == ("--- a\n+++ b\n@@ -2,3 +2,3 @@\n two\n-three\n+3\n four\n")


def test_separate_hunks_and_lineterm() -> None:
    a = [f"line {i}" for i in range(20)]
    b = list(a)
    b[2] = "changed 2"
    b[15] = "changed 15"
    lines = list(unified_diff(diff(a, b), lineterm=""))
    assert [line for line in lines if line.startswith("@@")] == [
        "@@ -1,6 +1,6 @@",
        "@@ -13,7 +13,7 @@",
    ]
    assert lines[:2] == ["--- ", "+++ "]


def test_insert_into_empty_and_delete_everything() -> None:
    assert list(unified_diff(diff([], ["x\n"]))) == [
        "--- \n",
        "+++ \n",
        "@@ -0,0 +1 @@\n",
        "+x\n",
    ]
    assert list(unified_diff(diff(["x\n", "y\n"], []))) == [
        "--- \n",
        "+++ \n",
        "@@ -1,2 +0,0 @@\n",
        "-x\n",
        "-y\n",
    ]


def test_no_changes_yields_nothing() -> None:
    assert list(unified_diff(diff(["a\n"], ["a\n"]))) == []
    assert list(unified_diff([])) == []


def test_accepts_any_iterable() -> None:
    ops = diff(["a\n"], ["b\n"])
    assert list(unified_diff(iter(ops))) == list(unified_diff(ops))


def test_negative_context_rejected_immediately() -> None:
    with pytest.raises(ValueError, match="context"):
        unified_diff([], context=-1)
