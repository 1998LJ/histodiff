"""Diffing sequences of arbitrary hashable items, and the ``key`` option."""

from __future__ import annotations

import difflib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple

import pytest

from helpers import random_pairs
from histodiff import (
    DiffOp,
    diff,
    histogram_diff,
    myers_diff,
    patience_diff,
    unified_diff,
)

FUNCS = [myers_diff, patience_diff, histogram_diff]


def identity(item: Any) -> Any:
    return item


def check(
    a: Sequence[Any],
    b: Sequence[Any],
    ops: list[DiffOp[Any]],
    key: Callable[[Any], Any] = identity,
) -> None:
    """Ops tile both sequences, hold the original items, and equal means
    equal keys."""
    i = j = 0
    for op in ops:
        assert (op.a_start, op.b_start) == (i, j)
        assert list(op.a_lines) == list(a[op.a_start : op.a_end])
        assert list(op.b_lines) == list(b[op.b_start : op.b_end])
        if op.tag == "equal":
            assert [key(x) for x in op.a_lines] == [key(x) for x in op.b_lines]
        i, j = op.a_end, op.b_end
    assert (i, j) == (len(a), len(b))


def changes(ops: list[DiffOp[Any]]) -> list[tuple[str, tuple, tuple]]:
    return [(op.tag, op.a_lines, op.b_lines) for op in ops if op.tag != "equal"]


# --------------------------------------------------------------------------
# Plain hashable items
# --------------------------------------------------------------------------


@pytest.mark.parametrize("func", FUNCS)
def test_words(func) -> None:
    a = ["the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
    b = ["the", "quick", "red", "fox", "jumped", "over", "the", "lazy", "dog"]
    ops = func(a, b)
    check(a, b, ops)
    assert changes(ops) == [
        ("replace", ("brown",), ("red",)),
        ("replace", ("jumps",), ("jumped",)),
    ]


@pytest.mark.parametrize("func", FUNCS)
def test_integers(func) -> None:
    ops = func([1, 2, 3, 4], [1, 3, 4, 5])
    assert [op.as_opcode() for op in ops] == [
        ("equal", 0, 1, 0, 1),
        ("delete", 1, 2, 1, 1),
        ("equal", 2, 4, 1, 3),
        ("insert", 4, 4, 3, 4),
    ]


class Row(NamedTuple):
    id: int
    name: str


@dataclass(frozen=True)
class Event:
    kind: str
    at: int


@pytest.mark.parametrize("func", FUNCS)
def test_records(func) -> None:
    a = [Row(1, "ann"), Row(2, "bob"), Row(3, "cy")]
    b = [Row(1, "ann"), Row(2, "bobby"), Row(3, "cy"), Row(4, "di")]
    ops = func(a, b)
    check(a, b, ops)
    assert changes(ops) == [
        ("replace", (Row(2, "bob"),), (Row(2, "bobby"),)),
        ("insert", (), (Row(4, "di"),)),
    ]

    events_a = [Event("start", 0), Event("tick", 1), Event("stop", 2)]
    events_b = [Event("start", 0), Event("stop", 2)]
    assert changes(func(events_a, events_b)) == [
        ("delete", (Event("tick", 1),), ())
    ]


@pytest.mark.parametrize("func", FUNCS)
def test_character_strings(func) -> None:
    ops = func("kitten", "sitting")
    check("kitten", "sitting", ops)
    assert changes(ops) == [
        ("replace", ("k",), ("s",)),
        ("replace", ("e",), ("i",)),
        ("insert", (), ("g",)),
    ]


@pytest.mark.parametrize("func", FUNCS)
def test_mixed_types(func) -> None:
    a = [1, "1", 1.5, None, (1, 2), frozenset({3})]
    b = [None, 1, "1", (1, 2), b"bytes", frozenset({3})]
    check(a, b, func(a, b))


@pytest.mark.parametrize("func", FUNCS)
def test_random_integer_sequences(func) -> None:
    for a, b in random_pairs(11, 100, max_len=25, alphabet="abcde"):
        ints_a, ints_b = [ord(c) for c in a], [ord(c) for c in b]
        ops = func(ints_a, ints_b)
        check(ints_a, ints_b, ops)
        # Same alignment as the equivalent strings.
        assert [op.as_opcode() for op in ops] == [
            op.as_opcode() for op in func(a, b)
        ]


def test_equality_is_hash_and_eq_like_difflib() -> None:
    # 1, 1.0 and True are equal dict keys; difflib treats them the same way.
    a, b = [1, 2.0], [True, 2]
    assert [op.as_opcode() for op in diff(a, b)] == [("equal", 0, 2, 0, 2)]
    assert difflib.SequenceMatcher(None, a, b).get_opcodes() == [("equal", 0, 2, 0, 2)]


# --------------------------------------------------------------------------
# key=
# --------------------------------------------------------------------------


@pytest.mark.parametrize("func", FUNCS)
def test_key_ignores_whitespace(func) -> None:
    a = ["def f():", "    return 1", ""]
    b = ["def f():", "  return 1  ", ""]
    assert [op.tag for op in func(a, b)] == ["equal", "replace", "equal"]

    ops = func(a, b, key=str.strip)
    check(a, b, ops, key=str.strip)
    assert len(ops) == 1 and ops[0].tag == "equal"
    # The ops keep the original items from each side.
    assert ops[0].a_lines[1] == "    return 1"
    assert ops[0].b_lines[1] == "  return 1  "


@pytest.mark.parametrize("func", FUNCS)
def test_key_casefold_random(func) -> None:
    for a, b in random_pairs(5, 100, max_len=25, alphabet="aAbBc"):
        ops = func(a, b, key=str.casefold)
        check(a, b, ops, key=str.casefold)
        folded = func([c.casefold() for c in a], [c.casefold() for c in b])
        assert [op.as_opcode() for op in ops] == [op.as_opcode() for op in folded]


def test_unhashable_records_need_a_key() -> None:
    a = [{"id": 1, "name": "ann"}, {"id": 2, "name": "bob"}]
    b = [{"id": 1, "name": "ann"}, {"id": 2, "name": "bobby"}]
    with pytest.raises(TypeError, match=r"unhashable.*pass key="):
        diff(a, b)

    ops = diff(a, b, key=lambda row: tuple(sorted(row.items())))
    assert [op.tag for op in ops] == ["equal", "replace"]
    # Original dicts, not the keys.
    assert ops[1].a_lines[0] is a[1]
    assert ops[1].b_lines[0] is b[1]


def test_unhashable_key_result_is_reported() -> None:
    with pytest.raises(TypeError, match="keys must be hashable"):
        diff(["a"], ["b"], key=list)


def test_errors_inside_key_are_not_rewritten() -> None:
    def bad_key(item: str) -> str:
        return item + 1  # type: ignore[operator]

    with pytest.raises(TypeError) as exc:
        diff(["a"], ["b"], key=bad_key)
    assert "key=" not in str(exc.value)


def test_key_is_called_once_per_item() -> None:
    calls = []

    def key(item: str) -> str:
        calls.append(item)
        return item.lower()

    a, b = list("abcdef"), list("ABXDEF")
    diff(a, b, key=key)
    assert sorted(calls) == sorted(a + b)


def test_changes_slide_using_key_equality() -> None:
    # Under key=str.strip, "x" and " x" are equal, so the inserted item can
    # slide to the top - but only because sliding uses the diff's equality.
    ops = diff(["x"], ["x", " x"], key=str.strip)
    check(["x"], ["x", " x"], ops, key=str.strip)
    assert ops == [
        DiffOp("insert", 0, 0, 0, 1, (), ("x",)),
        DiffOp("equal", 0, 1, 1, 2, ("x",), (" x",)),
    ]


@pytest.mark.parametrize("algorithm", ["myers", "patience", "histogram"])
def test_diff_passes_key_through(algorithm: str) -> None:
    a, b = ["A", "b"], ["a", "B", "c"]
    ops = diff(a, b, algorithm, key=str.lower)
    assert [op.as_opcode() for op in ops] == [
        ("equal", 0, 2, 0, 2),
        ("insert", 2, 2, 2, 3),
    ]


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def test_unified_diff_requires_text() -> None:
    with pytest.raises(TypeError, match="renders text.*int"):
        unified_diff(diff([1, 2], [1, 3]))
    # Converting first works.
    ops = diff([str(x) for x in (1, 2)], [str(x) for x in (1, 3)])
    assert list(unified_diff(ops, lineterm=""))[-2:] == ["-2", "+3"]
