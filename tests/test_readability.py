"""Scenarios where diff *readability* matters, not just diff size.

The difflib comparisons use ``difflib.SequenceMatcher`` with its defaults,
which is what ``difflib.unified_diff`` and most callers use. Its greedy
longest-block matching plus the "autojunk" heuristic (lines making up more
than 1% of a 200+ line file cannot anchor a match) fall apart on real files
full of blank lines and boilerplate.
"""

from __future__ import annotations

import difflib

import pytest

from helpers import changed_lines, check_valid
from histodiff import DiffOp, diff

ALGORITHMS = ["myers", "patience", "histogram"]


def difflib_changed(a: list[str], b: list[str]) -> int:
    return sum(
        (i2 - i1) + (j2 - j1)
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes()
        if tag != "equal"
    )


def changes(ops: list[DiffOp]) -> list[tuple[str, int, int, int, int]]:
    return [op.as_opcode() for op in ops if op.tag != "equal"]


# --------------------------------------------------------------------------
# 1. A block of lines moved elsewhere in the file
# --------------------------------------------------------------------------


def python_function(i: int) -> list[str]:
    return (
        [f"def func_{i}(data):", '    """Process the data."""', "    result = []"]
        + [f"    result.append(data[{k}] * {i})" for k in range(6)]
        + ["    return result", "", ""]
    )


def test_function_moved_to_bottom_of_module() -> None:
    funcs = [python_function(i) for i in range(20)]
    old = sum(funcs, [])
    new = sum(funcs[:3] + funcs[4:] + [funcs[3]], [])

    ops = diff(old, new)
    check_valid(old, new, ops)
    # One clean deletion of func_3 and one clean insertion at the bottom.
    assert changes(ops) == [
        ("delete", 36, 48, 36, 36),
        ("insert", 240, 240, 228, 240),
    ]
    assert list(ops[1].a_lines) == funcs[3]
    assert list(ops[-1].b_lines) == funcs[3]

    # difflib rewrites most of the file (384 changed lines) to express it.
    assert changed_lines(ops) == 24
    assert difflib_changed(old, new) >= 10 * changed_lines(ops)


# --------------------------------------------------------------------------
# 2. A unique line inserted into otherwise repeated content
# --------------------------------------------------------------------------


def test_unique_line_in_repeated_rows() -> None:
    # e.g. a CSV of sensor readings that are mostly the default value.
    old = ["0,0,0,0"] * 300
    new = old[:150] + ["1,2,3,4"] + old[150:]

    ops = diff(old, new)
    assert changes(ops) == [("insert", 150, 150, 150, 151)]
    # difflib cannot anchor on the repeated row and replaces the second half.
    assert difflib_changed(old, new) > 300


def test_unique_block_in_repeated_yaml() -> None:
    worker = ["- name: worker", "  replicas: 1", "  image: app:latest", ""]
    special = ["- name: special", "  replicas: 3", "  image: app:latest", ""]
    old = worker * 60
    new = worker * 30 + special + worker * 30

    ops = diff(old, new)
    check_valid(old, new, ops)
    assert changes(ops) == [("insert", 120, 120, 120, 124)]
    assert list(ops[1].b_lines) == special
    assert difflib_changed(old, new) > 200


# --------------------------------------------------------------------------
# 3. Reordered blocks whose lines are duplicated elsewhere in the file
# --------------------------------------------------------------------------


def config_section(i: int) -> list[str]:
    # Every section repeats `enabled`, `timeout`, `retries` and a blank line,
    # so only the header and port are unique.
    return [
        f"[svc{i}]",
        "enabled = true",
        f"port = {8000 + i}",
        "timeout = 30",
        "retries = 3",
        "",
    ]


@pytest.mark.parametrize("algorithm", ["patience", "histogram"])
def test_config_section_moved_to_end(algorithm: str) -> None:
    sections = [config_section(i) for i in range(45)]
    old = sum(sections, [])
    new = sum(sections[:3] + sections[4:] + [sections[3]], [])

    ops = diff(old, new, algorithm=algorithm)
    check_valid(old, new, ops)
    assert changes(ops) == [
        ("delete", 18, 24, 18, 18),
        ("insert", 270, 270, 264, 270),
    ]
    assert ops[1].a_lines[0] == "[svc3]"
    assert ops[-1].b_lines[0] == "[svc3]"
    # difflib: one giant hunk touching ~490 lines.
    assert difflib_changed(old, new) >= 10 * changed_lines(ops)


def test_swapped_sections_show_only_the_differing_lines() -> None:
    sections = [config_section(i) for i in range(45)]
    old = sum(sections, [])
    new = sum(
        sections[:5] + [sections[30]] + sections[6:30] + [sections[5]] + sections[31:],
        [],
    )

    ops = diff(old, new)
    check_valid(old, new, ops)
    # The sections only differ in header and port, so that's all we report.
    assert [(op.a_lines, op.b_lines) for op in ops if op.tag != "equal"] == [
        (("[svc5]",), ("[svc30]",)),
        (("port = 8005",), ("port = 8030",)),
        (("[svc30]",), ("[svc5]",)),
        (("port = 8030",), ("port = 8005",)),
    ]
    assert difflib_changed(old, new) >= 30 * changed_lines(ops)


def test_test_function_moved() -> None:
    def test_func(name: str) -> list[str]:
        return [
            f"def test_{name}(client):",
            f'    resp = client.get("/{name}")',
            "    assert resp.status_code == 200",
            "    assert resp.json() is not None",
            "",
            "",
        ]

    names = [f"endpoint_{i}" for i in range(40)]
    old = sum((test_func(n) for n in names), [])
    new = sum(
        (test_func(n) for n in names[:2] + names[3:25] + [names[2]] + names[25:]), []
    )

    ops = diff(old, new)
    check_valid(old, new, ops)
    assert changes(ops) == [
        ("delete", 12, 18, 12, 12),
        ("insert", 150, 150, 144, 150),
    ]
    assert ops[1].a_lines[0] == "def test_endpoint_2(client):"
    assert ops[-2].b_lines[0] == "def test_endpoint_2(client):"
    assert difflib_changed(old, new) >= 10 * changed_lines(ops)


# --------------------------------------------------------------------------
# 4. Whitespace/indentation changes mixed with real content changes
# --------------------------------------------------------------------------


def handler(i: int) -> list[str]:
    return [
        f"def handle_{i}(event):",
        "    if event is None:",
        "        return None",
        f"    result = process(event, {i})",
        "    log(result)",
        "    return result",
        "",
    ]


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_reindent_and_edit_stay_separate_and_tight(algorithm: str) -> None:
    old = sum((handler(i) for i in range(35)), [])
    new = list(old)
    # Wrap one handler's body in an `if` (whitespace-only change to 5 lines
    # plus one new line)...
    start = old.index("def handle_4(event):") + 1
    body = old[start : start + 5]
    new[start : start + 5] = ["    if ENABLED:"] + ["    " + x for x in body]
    # ...and make an unrelated one-line content change far away.
    k = new.index("    result = process(event, 20)")
    new[k] = "    result = process_v2(event, 20)"

    ops = diff(old, new, algorithm=algorithm)
    check_valid(old, new, ops)
    assert changes(ops) == [
        ("replace", 29, 34, 29, 35),
        ("replace", 143, 144, 144, 145),
    ]
    # Indentation is significant: re-indented lines are real changes.
    assert ops[1].a_lines[0] == "    if event is None:"
    assert ops[1].b_lines[:2] == ("    if ENABLED:", "        if event is None:")
    assert ops[3].b_lines == ("    result = process_v2(event, 20)",)


def test_whitespace_only_line_change_is_detected() -> None:
    old = ["def f():", "    return 1", ""]
    new = ["def f():", "    return 1  ", ""]
    assert changes(diff(old, new)) == [("replace", 1, 2, 1, 2)]


# --------------------------------------------------------------------------
# 5. Large insertions/deletions around a small unchanged anchor
# --------------------------------------------------------------------------

ANCHOR = ["def main():", "    config = load()", "    run(config)", "    return 0", ""]


def helpers_block(count: int) -> list[str]:
    out: list[str] = []
    for i in range(count):
        # Shares `config = load()`, `return 0` and blank lines with ANCHOR.
        out += [
            f"def helper_{i}():",
            "    config = load()",
            f"    step_{i}(config)",
            "    return 0",
            "",
        ]
    return out


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_insertions_around_anchor_keep_anchor_whole(algorithm: str) -> None:
    helpers = helpers_block(12)
    old = ANCHOR
    new = helpers[:30] + ANCHOR + helpers[30:]

    ops = diff(old, new, algorithm=algorithm)
    check_valid(old, new, ops)
    # Without histodiff's slider pass, `return 0` and the blank line of
    # main() get matched to the *last* helper instead, splitting main().
    assert [op.as_opcode() for op in ops] == [
        ("insert", 0, 0, 0, 30),
        ("equal", 0, 5, 30, 35),
        ("insert", 5, 5, 35, 65),
    ]


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_deletions_around_anchor_keep_anchor_whole(algorithm: str) -> None:
    helpers = helpers_block(60)
    old = ["import app", ""] + helpers[:150] + ANCHOR + helpers[150:]
    new = ["import app", ""] + ANCHOR

    ops = diff(old, new, algorithm=algorithm)
    check_valid(old, new, ops)
    assert [op.as_opcode() for op in ops] == [
        ("equal", 0, 2, 0, 2),
        ("delete", 2, 152, 2, 2),
        ("equal", 152, 157, 2, 7),
        ("delete", 157, 307, 7, 7),
    ]
