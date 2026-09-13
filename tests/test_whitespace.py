"""Whitespace options: -b / -w keys and -B blank-line filtering."""

from __future__ import annotations

import random
import re

import pytest

from histodiff import diff, ignore_all_space, ignore_space_change, unified_diff
from histodiff.cli import main
from histodiff.whitespace import is_blank
from test_cli import write
from test_readability import handler

# (left, right, equal under -b, equal under -w)
PAIRS = [
    ("x", "x", True, True),
    ("a b", "a   b", True, True),
    ("a b", "a\tb", True, True),
    ("a b", "ab", False, True),
    ("x  ", "x", True, True),
    ("x\n", "x", True, True),
    ("x\r\n", "x\n", True, True),
    ("    x", "\tx", True, True),
    ("    x", "        x", True, True),
    ("  x", "x", False, True),
    ("", "   \n", True, True),
    ("a", "b", False, False),
    ("a  b", " a b", False, True),
]


@pytest.mark.parametrize(("left", "right", "eq_b", "eq_w"), PAIRS)
def test_normalization_rules(left: str, right: str, eq_b: bool, eq_w: bool) -> None:
    assert (ignore_space_change(left) == ignore_space_change(right)) is eq_b
    assert (ignore_all_space(left) == ignore_all_space(right)) is eq_w


def test_is_blank() -> None:
    assert is_blank("") and is_blank(" \t\n") and not is_blank(" x ")


def wrapped_module() -> tuple[list[str], list[str]]:
    """35 handlers; one body gets wrapped in an `if`, another gets a real edit."""
    old = sum((handler(i) for i in range(35)), [])
    new = list(old)
    start = old.index("def handle_4(event):") + 1
    body = old[start : start + 5]
    new[start : start + 5] = ["    if ENABLED:"] + ["    " + x for x in body]
    k = new.index("    result = process(event, 20)")
    new[k] = "    result = process_v2(event, 20)"
    return old, new


@pytest.mark.parametrize("key", [ignore_space_change, ignore_all_space])
@pytest.mark.parametrize("algorithm", ["myers", "patience", "histogram"])
def test_reindented_block_shows_only_the_real_changes(key, algorithm: str) -> None:
    old, new = wrapped_module()
    plain = diff(old, new, algorithm)
    assert sum(op.a_end - op.a_start for op in plain if op.tag != "equal") == 6

    ops = diff(old, new, algorithm, key=key)
    assert [op.as_opcode() for op in ops if op.tag != "equal"] == [
        ("insert", 29, 29, 29, 30),
        ("replace", 143, 144, 144, 145),
    ]
    assert ops[1].b_lines == ("    if ENABLED:",)
    # The re-indented lines are matched but keep their original text.
    body = ops[2]
    assert body.a_lines[0] == "    if event is None:"
    assert body.b_lines[0] == "        if event is None:"


def test_unified_diff_prints_old_side_for_matched_lines() -> None:
    old = ["def f():", "    x = 1", "    return x"]
    new = ["def f():", "  x = 1", "  return x", "# done"]
    ops = diff(old, new, key=ignore_space_change)
    assert list(unified_diff(ops, lineterm="")) == [
        "--- ",
        "+++ ",
        "@@ -1,3 +1,4 @@",
        " def f():",
        "     x = 1",
        "     return x",
        "+# done",
    ]


# --------------------------------------------------------------------------
# ignore_blank_lines
# --------------------------------------------------------------------------


def body(n: int, tag: str = "line") -> list[str]:
    return [f"{tag} {i}" for i in range(n)]


def test_blank_only_changes_are_hidden() -> None:
    old = body(10)
    new = old[:5] + ["", "   "] + old[5:]
    ops = diff(old, new)
    assert list(unified_diff(ops))  # shown by default
    assert list(unified_diff(ops, ignore_blank_lines=True)) == []


def test_real_hunks_survive_and_blank_hunks_elsewhere_do_not() -> None:
    old = body(40)
    new = list(old)
    new.insert(5, "")  # blank-only change, its own hunk
    new[30] = "changed"  # real change, far away
    lines = list(unified_diff(diff(old, new), lineterm="", ignore_blank_lines=True))
    assert lines[:2] == ["--- ", "+++ "]
    assert [line for line in lines if line.startswith("@@")] == ["@@ -27,7 +28,7 @@"]
    assert "+changed" in lines
    assert "+" not in lines


def test_blank_change_inside_a_real_hunk_is_kept() -> None:
    old = body(10)
    new = old[:4] + [""] + old[4:5] + ["changed"] + old[6:]
    lines = list(unified_diff(diff(old, new), lineterm="", ignore_blank_lines=True))
    assert "+" in lines and "+changed" in lines
    assert_hunks_consistent(lines)


def assert_hunks_consistent(lines: list[str]) -> None:
    """Every @@ header's line counts match the lines that follow it."""
    header = re.compile(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
    i = 0
    while i < len(lines):
        match = header.match(lines[i])
        i += 1
        if not match:
            continue
        expected = (int(match[1] or 1), int(match[2] or 1))
        old = new = 0
        while i < len(lines) and not lines[i].startswith("@@"):
            first = lines[i][:1]
            old += first in " -"
            new += first in " +"
            i += 1
        assert (old, new) == expected, lines


VOCAB = ["", "  ", "\t", "x = 1", "  x = 1", "x  = 1", "y", "\ty", "z", "return"]


@pytest.mark.parametrize("seed", range(20))
def test_random_whitespace_edits(seed: int) -> None:
    rng = random.Random(seed)
    old = [rng.choice(VOCAB) for _ in range(rng.randint(0, 40))]
    new = list(old)
    for _ in range(rng.randint(0, 8)):
        pos = rng.randint(0, len(new))
        roll = rng.random()
        if roll < 0.4:
            new.insert(pos, rng.choice(VOCAB))
        elif new and roll < 0.7:
            del new[min(pos, len(new) - 1)]
        elif new:
            new[min(pos, len(new) - 1)] = rng.choice(VOCAB)

    for key in (None, ignore_space_change, ignore_all_space):
        ops = diff(old, new, key=key)
        for ignore_blank in (False, True):
            lines = list(
                unified_diff(
                    ops,
                    context=rng.randint(0, 3),
                    lineterm="",
                    ignore_blank_lines=ignore_blank,
                )
            )
            assert_hunks_consistent(lines)
            if not ignore_blank:
                continue
            # Every real change is still printed; hidden hunks were blank-only.
            printed = [
                line[1:]
                for line in lines[2:]
                if line[:1] in "+-" and not is_blank(line[1:])
            ]
            real = [
                line
                for op in ops
                if op.tag != "equal"
                for line in op.a_lines + op.b_lines
                if not is_blank(line)
            ]
            assert sorted(printed) == sorted(real)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


@pytest.fixture
def wrapped_files(tmp_path) -> tuple[str, str]:
    old, new = wrapped_module()
    return write(tmp_path / "old.py", old), write(tmp_path / "new.py", new)


@pytest.mark.parametrize(
    "flag", ["-b", "--ignore-space-change", "-w", "--ignore-all-space"]
)
def test_cli_whitespace_flags(wrapped_files, capsys, flag: str) -> None:
    assert main([*wrapped_files, flag]) == 1
    out = capsys.readouterr().out.splitlines()
    changed = [
        line for line in out if line[:1] in "+-" and not line.startswith(("---", "+++"))
    ]
    assert changed == [
        "+    if ENABLED:",
        "-    result = process(event, 20)",
        "+    result = process_v2(event, 20)",
    ]


def test_cli_whitespace_only_differences_exit_0(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["def f():", "    return 1"])
    new = write(tmp_path / "new", ["def f():", "\treturn  1   "])
    assert main([old, new]) == 1
    capsys.readouterr()
    assert main([old, new, "-b"]) == 0
    assert main([old, new, "-w"]) == 0
    assert capsys.readouterr().out == ""


def test_cli_w_overrides_b(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["a b"])
    new = write(tmp_path / "new", ["ab"])
    assert main([old, new, "-b"]) == 1
    capsys.readouterr()
    assert main([old, new, "-b", "-w"]) == 0


def test_cli_ignore_blank_lines(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", body(20))
    blank_only = write(tmp_path / "blank", body(10) + ["", ""] + body(20)[10:])
    assert main([old, blank_only]) == 1
    capsys.readouterr()
    assert main([old, blank_only, "-B"]) == 0
    assert main([old, blank_only, "--ignore-blank-lines"]) == 0
    assert capsys.readouterr().out == ""

    mixed = write(tmp_path / "mixed", body(3) + [""] + body(20)[3:15] + ["new"])
    assert main([old, mixed, "-B", "-U", "1"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert "+new" in out
    assert "+" not in out  # the far-away blank line isn't shown


def test_cli_combines_b_and_blank_lines(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["a", "  b", "c"])
    new = write(tmp_path / "new", ["a", "", "\tb   ", "c"])
    assert main([old, new, "-b", "-B"]) == 0
    assert main([old, new, "-b"]) == 1
