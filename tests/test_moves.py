"""Moved-block detection and --color-moved."""

from __future__ import annotations

import random
import re

import pytest

from histodiff import (
    DiffOp,
    Move,
    diff,
    find_moves,
    ignore_all_space,
    unified_diff,
)
from histodiff.cli import (
    BLUE,
    BOLD,
    CYAN,
    DIM,
    GREEN,
    MAGENTA,
    NO_REVERSE,
    RED,
    RESET,
    REVERSE,
    YELLOW,
    main,
    render,
)
from test_cli import write
from test_readability import python_function

LONG1 = "important = compute_something(alpha, beta)"
LONG2 = "other_value = transform(gamma, delta)"
LONG3 = "final_result = combine(important, other_value)"
KEEP1 = "config = load_configuration(path)"
KEEP2 = "logger = make_logger(config.level)"


# --------------------------------------------------------------------------
# find_moves
# --------------------------------------------------------------------------


def test_moved_function() -> None:
    funcs = [python_function(i) for i in range(20)]
    old = sum(funcs, [])
    new = sum(funcs[:3] + funcs[4:] + [funcs[3]], [])
    assert find_moves(diff(old, new)) == [
        Move(36, 48, 228, 240, tuple(funcs[3]), tuple(funcs[3]))
    ]


def test_swapped_lines() -> None:
    assert find_moves(diff([LONG1, LONG2], [LONG2, LONG1])) == [
        Move(0, 1, 1, 2, (LONG1,), (LONG1,))
    ]


def test_short_blocks_are_not_moves() -> None:
    old = ["}", LONG1, LONG2]
    new = [LONG1, LONG2, "}"]
    ops = diff(old, new)
    assert find_moves(ops) == []
    assert find_moves(ops, min_alnum=0) == [Move(0, 1, 2, 3, ("}",), ("}",))]


def test_unrelated_changes_are_not_moves() -> None:
    old = [KEEP1, LONG1, LONG2]
    new = [KEEP1, "completely = different(code)", "nothing_in_common = True"]
    assert find_moves(diff(old, new)) == []


def test_edited_block_only_moves_its_unchanged_parts() -> None:
    funcs = [python_function(i) for i in range(6)]
    moved = list(funcs[1])
    moved[4] = "    result.append(data[1] * 100)"  # edited on the way
    old = sum(funcs, [])
    new = sum(funcs[:1] + funcs[2:], []) + moved
    moves = find_moves(diff(old, new))
    assert moves, "the untouched parts of the function still moved"
    for move in moves:
        assert "    result.append(data[1] * 1)" not in move.a_lines
        assert "    result.append(data[1] * 100)" not in move.b_lines


def test_each_inserted_line_moves_at_most_once() -> None:
    old = [LONG1, LONG2, KEEP1, KEEP2]
    new = [KEEP1, KEEP2, LONG1, LONG2, "separator = 1", LONG1, LONG2]
    moves = find_moves(diff(old, new))
    assert moves == [Move(0, 2, 2, 4, (LONG1, LONG2), (LONG1, LONG2))]


def test_longest_match_wins() -> None:
    sep = "unrelated = 0"
    ops = [
        DiffOp("delete", 0, 3, 0, 0, (LONG1, LONG2, LONG3), ()),
        DiffOp("equal", 3, 4, 0, 1, (KEEP1,), (KEEP1,)),
        DiffOp("insert", 4, 4, 1, 6, (), (LONG1, sep, LONG1, LONG2, LONG3)),
    ]
    assert find_moves(ops) == [
        Move(0, 3, 3, 6, (LONG1, LONG2, LONG3), (LONG1, LONG2, LONG3))
    ]


def test_matches_never_span_two_insertions() -> None:
    ops = [
        DiffOp("delete", 0, 2, 0, 0, (LONG1, LONG2), ()),
        DiffOp("equal", 2, 3, 0, 1, (KEEP1,), (KEEP1,)),
        DiffOp("insert", 3, 3, 1, 2, (), (LONG1,)),
        DiffOp("equal", 3, 4, 2, 3, (KEEP2,), (KEEP2,)),
        DiffOp("insert", 4, 4, 3, 4, (), (LONG2,)),
    ]
    assert find_moves(ops) == [
        Move(0, 1, 1, 2, (LONG1,), (LONG1,)),
        Move(1, 2, 3, 4, (LONG2,), (LONG2,)),
    ]


def test_key_matches_reindented_moves() -> None:
    body = ["def helper(value):", "    return value * 2"]
    indented = ["    " + line for line in body]
    old = body + [KEEP1, KEEP2]
    new = [KEEP1, KEEP2, *indented]
    ops = diff(old, new)
    assert find_moves(ops) == []
    assert find_moves(ops, key=ignore_all_space) == [
        Move(0, 2, 2, 4, tuple(body), tuple(indented))
    ]


POOL = [f"line number {n} with some words" for n in range(8)]


@pytest.mark.parametrize("seed", range(25))
def test_moves_are_consistent(seed: int) -> None:
    rng = random.Random(seed)
    old = [rng.choice(POOL) for _ in range(rng.randint(0, 30))]
    new = list(old)
    for _ in range(rng.randint(0, 3)):  # move a few chunks around
        if not new:
            break
        start = rng.randrange(len(new))
        chunk = new[start : start + rng.randint(1, 5)]
        del new[start : start + len(chunk)]
        pos = rng.randint(0, len(new))
        new[pos:pos] = chunk
    if rng.random() < 0.5 and new:
        new[rng.randrange(len(new))] = "edited = True"

    ops = diff(old, new)
    min_alnum = rng.choice([0, 20, 50])
    moves = find_moves(ops, min_alnum=min_alnum)
    assert moves == sorted(moves, key=lambda m: m.a_start)
    used_a: set[int] = set()
    used_b: set[int] = set()
    for move in moves:
        assert move.a_end - move.a_start == move.b_end - move.b_start > 0
        assert list(move.a_lines) == old[move.a_start : move.a_end]
        assert list(move.b_lines) == new[move.b_start : move.b_end]
        assert move.a_lines == move.b_lines
        assert sum(c.isalnum() for line in move.a_lines for c in line) >= min_alnum
        # Each side lies within a single changed op, and lines aren't reused.
        assert any(
            op.tag in ("delete", "replace")
            and op.a_start <= move.a_start and move.a_end <= op.a_end
            for op in ops
        )
        assert any(
            op.tag in ("insert", "replace")
            and op.b_start <= move.b_start and move.b_end <= op.b_end
            for op in ops
        )
        span_a = set(range(move.a_start, move.a_end))
        span_b = set(range(move.b_start, move.b_end))
        assert not span_a & used_a and not span_b & used_b
        used_a |= span_a
        used_b |= span_b


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def test_render_colors_moves_and_alternates_adjacent_blocks() -> None:
    lines = [
        "--- a\n", "+++ b\n",
        "@@ -1,2 +1,0 @@\n", f"-{LONG1}\n", f"-{LONG2}\n",
        "@@ -5,0 +3,2 @@\n", f"+{LONG2}\n", f"+{LONG1}\n",
    ]
    moves = [
        Move(0, 1, 3, 4, (LONG1,), (LONG1,)),
        Move(1, 2, 2, 3, (LONG2,), (LONG2,)),
    ]
    out = list(render(lines, "color", moves=moves))
    assert f"{BOLD}{MAGENTA}-{LONG1}{RESET}\n" in out
    assert f"{BOLD}{BLUE}-{LONG2}{RESET}\n" in out
    assert f"{BOLD}{CYAN}+{LONG2}{RESET}\n" in out
    assert f"{BOLD}{YELLOW}+{LONG1}{RESET}\n" in out

    dimmed = list(render(lines, "color", moves=moves, dim_moved=True))
    assert f"{DIM}{MAGENTA}-{LONG1}{RESET}\n" in dimmed
    assert f"{DIM}{YELLOW}+{LONG1}{RESET}\n" in dimmed


@pytest.mark.parametrize("seed", range(15))
def test_render_tracks_line_numbers_across_hunks(seed: int) -> None:
    rng = random.Random(seed)
    old = [f"old {i}\n" for i in range(rng.randint(0, 25))]
    new: list[str] = []
    for line in old:
        roll = rng.random()
        if roll < 0.6:
            new.append(line)
        elif roll < 0.8:
            new.append(f"new {len(new)}\n")
        if rng.random() < 0.15:
            new.append(f"extra {len(new)}\n")

    ops = diff(old, new)
    moves, marked_a, marked_b = [], set(), set()
    for op in ops:
        if op.tag == "equal":
            continue
        a0 = rng.randint(op.a_start, op.a_end)
        a1 = rng.randint(a0, op.a_end)
        b0 = rng.randint(op.b_start, op.b_end)
        b1 = rng.randint(b0, op.b_end)
        moves.append(Move(a0, a1, b0, b1, tuple(old[a0:a1]), tuple(new[b0:b1])))
        marked_a |= set(range(a0, a1))
        marked_b |= set(range(b0, b1))

    lines = list(unified_diff(ops, context=rng.randint(0, 3)))
    moved_old = (BOLD + MAGENTA, BOLD + BLUE)
    moved_new = (BOLD + CYAN, BOLD + YELLOW)
    for chunk in list(render(lines, "color", moves=moves))[2:]:
        text = re.sub(r"\x1b\[\d+m", "", chunk)
        if text.startswith("-"):
            assert chunk.startswith(moved_old) == (old.index(text[1:]) in marked_a)
        elif text.startswith("+"):
            assert chunk.startswith(moved_new) == (new.index(text[1:]) in marked_b)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


@pytest.fixture
def moved_files(tmp_path) -> tuple[str, str]:
    funcs = [python_function(i) for i in range(6)]
    old = sum(funcs, [])
    edited = list(funcs[4])
    edited[3] = "    result.append(data[0] * 40)"
    new = sum(funcs[:1] + funcs[2:4] + [edited] + funcs[5:] + [funcs[1]], [])
    return write(tmp_path / "old.py", old), write(tmp_path / "new.py", new)


def test_cli_color_moved(moved_files, capsys) -> None:
    assert main([*moved_files, "--color-moved"]) == 1
    out = capsys.readouterr().out
    assert f"{BOLD}{MAGENTA}-def func_1(data):{RESET}\n" in out
    assert f"{BOLD}{CYAN}+def func_1(data):{RESET}\n" in out
    # The real edit is still a normal, word-highlighted change.
    assert (f"{RED}-    result.append(data[0] * {REVERSE}4{NO_REVERSE}){RESET}\n"
            in out)
    assert (f"{GREEN}+    result.append(data[0] * {REVERSE}40{NO_REVERSE}){RESET}\n"
            in out)


def test_cli_dim_moved(moved_files, capsys) -> None:
    assert main([*moved_files, "--dim-moved"]) == 1
    out = capsys.readouterr().out
    assert f"{DIM}{MAGENTA}-def func_1(data):{RESET}\n" in out
    assert f"{DIM}{CYAN}+def func_1(data):{RESET}\n" in out


def test_cli_moves_not_colored_by_default(moved_files, capsys) -> None:
    main([*moved_files, "--color"])
    out = capsys.readouterr().out
    assert MAGENTA not in out and CYAN + "+" not in out
    assert f"{RED}-def func_1(data):{RESET}\n" in out


def test_cli_color_words_with_moves(moved_files, capsys) -> None:
    assert main([*moved_files, "--color-words", "--color-moved"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert f"{BOLD}{MAGENTA}def func_1(data):{RESET}" in out
    assert f"{BOLD}{CYAN}def func_1(data):{RESET}" in out
    assert f"    result.append(data[0] * {RED}4{RESET}{GREEN}40{RESET})" in out
