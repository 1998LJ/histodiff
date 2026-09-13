"""Side-by-side, HTML and JSON output."""

from __future__ import annotations

import json
from html.parser import HTMLParser

import pytest

from histodiff import (
    HTML_STYLE,
    DiffOp,
    Move,
    SideBySideRow,
    diff,
    find_moves,
    from_json,
    html_diff,
    side_by_side,
    side_by_side_rows,
    to_json,
)
from histodiff.cli import (
    BOLD,
    GREEN,
    MAGENTA,
    NO_REVERSE,
    RED,
    RESET,
    REVERSE,
    main,
)
from test_cli import write
from test_readability import python_function

# --------------------------------------------------------------------------
# Side by side
# --------------------------------------------------------------------------


def test_side_by_side_rows() -> None:
    ops = diff(["a\n", "b\n", "c\n", "x\n"], ["a\n", "B\n", "C\n", "D\n", "x\n"])
    assert side_by_side_rows(ops) == [
        SideBySideRow(" ", 0, 0, "a\n", "a\n"),
        SideBySideRow("|", 1, 1, "b\n", "B\n"),
        SideBySideRow("|", 2, 2, "c\n", "C\n"),
        SideBySideRow(">", None, 3, None, "D\n"),
        SideBySideRow(" ", 3, 4, "x\n", "x\n"),
    ]


def test_side_by_side_rows_for_deletes() -> None:
    ops = diff(["a", "gone", "b"], ["a", "b"])
    assert side_by_side_rows(ops)[1] == SideBySideRow("<", 1, None, "gone", None)


SBS_OLD = ["a", "bb", "c"]
SBS_NEW = ["a", "BB", "c", "d"]
SBS_EXPECTED = [
    "a" + " " * 11 + "a",
    "bb" + " " * 8 + "| BB",
    "c" + " " * 11 + "c",
    " " * 10 + "> d",
]


def test_side_by_side_text() -> None:
    lines = list(side_by_side(diff(SBS_OLD, SBS_NEW), width=21))
    assert [line.rstrip("\n") for line in lines] == SBS_EXPECTED
    assert all(line.endswith("\n") for line in lines)


def test_side_by_side_truncates_and_expands_tabs() -> None:
    ops = diff(["0123456789abc", "\tx"], ["0123456789abc", "\ty"])
    lines = list(side_by_side(ops, width=21, lineterm=""))
    assert lines[0] == "012345678   012345678"
    assert lines[1] == "        x | " + "        y"


def test_side_by_side_uses_terminal_width_for_unicode() -> None:
    lines = list(side_by_side(diff(["界ab"], ["界ab"]), width=13, lineterm=""))
    assert lines == ["界ab" + " " * 4 + "界ab"]

    truncated = list(side_by_side(diff(["界abc"], ["界abc"]), width=11, lineterm=""))
    assert truncated == ["界ab" + " " * 3 + "界ab"]


def test_side_by_side_suppress_common_lines() -> None:
    lines = list(
        side_by_side(
            diff(SBS_OLD, SBS_NEW), width=21, lineterm="", suppress_common_lines=True
        )
    )
    assert lines == [SBS_EXPECTED[1], SBS_EXPECTED[3]]


def test_side_by_side_requires_text() -> None:
    with pytest.raises(TypeError, match="side_by_side renders text"):
        list(side_by_side(diff([1], [2])))
    with pytest.raises(ValueError, match="width"):
        list(side_by_side(diff(["a"], ["b"]), width=0))


def test_cli_side_by_side(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", SBS_OLD)
    new = write(tmp_path / "new", SBS_NEW)
    assert main([old, new, "-y", "-W", "21"]) == 1
    assert capsys.readouterr().out.splitlines() == SBS_EXPECTED

    assert (
        main([old, new, "--side-by-side", "--width", "21", "--suppress-common-lines"])
        == 1
    )
    assert capsys.readouterr().out.splitlines() == [SBS_EXPECTED[1], SBS_EXPECTED[3]]

    # Identical files: exit 0, but still print both columns, like diff -y.
    assert main([old, old, "-y", "-W", "21"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "a" + " " * 11 + "a",
        "bb" + " " * 10 + "bb",
        "c" + " " * 11 + "c",
    ]


def test_cli_side_by_side_color(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["result = process(event)"])
    new = write(tmp_path / "new", ["result = process_v2(event)"])
    assert main([old, new, "-y", "--color", "-W", "80"]) == 1
    out = capsys.readouterr().out
    assert out == (
        f"{RED}result = {REVERSE}process{NO_REVERSE}(event){RESET}"
        + " " * 15
        + f" | {GREEN}result = {REVERSE}process_v2{NO_REVERSE}(event){RESET}\n"
    )


def test_cli_side_by_side_moves(tmp_path, capsys) -> None:
    funcs = [python_function(i) for i in range(6)]
    old = write(tmp_path / "old", sum(funcs, []))
    new = write(tmp_path / "new", sum(funcs[:1] + funcs[2:] + [funcs[1]], []))
    assert main([old, new, "-y", "--color-moved"]) == 1
    out = capsys.readouterr().out
    assert f"{BOLD}{MAGENTA}def func_1(data):{RESET}" in out
    assert " < \n" not in out  # trailing spaces are stripped


def test_side_by_side_ignores_blank_only_hunks(tmp_path, capsys) -> None:
    old_lines = ["a\n", "b\n"]
    new_lines = ["a\n", "\n", "b\n"]
    rendered = list(
        side_by_side(diff(old_lines, new_lines), width=13, ignore_blank_lines=True)
    )
    assert [line.rstrip("\n") for line in rendered] == [
        "a" + " " * 7 + "a",
        "b" + " " * 7 + "b",
    ]

    old = write(tmp_path / "old", ["a", "b"])
    new = write(tmp_path / "new", ["a", "", "b"])
    assert main([old, new, "-B", "-y", "-W", "13"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "a" + " " * 7 + "a",
        "b" + " " * 7 + "b",
    ]


def test_cli_output_formats_are_exclusive(tmp_path) -> None:
    old = write(tmp_path / "old", ["a"])
    for flags in (["-y", "--json"], ["--html", "--json"], ["-y", "--color-words"]):
        with pytest.raises(SystemExit) as exc:
            main([old, old, *flags])
        assert exc.value.code == 2


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------


class TagBalance(HTMLParser):
    """Checks that every opened element is closed in order."""

    VOID = {"meta", "col", "br"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag) -> None:
        assert self.stack and self.stack[-1] == tag, (tag, self.stack)
        self.stack.pop()


def assert_balanced(markup: str) -> None:
    parser = TagBalance()
    parser.feed(markup)
    parser.close()
    assert parser.stack == []


def test_html_page() -> None:
    ops = diff(["a", "<b>", "c"], ["a", "<B>", "c", "d"])
    page = html_diff(ops, fromfile="old.txt", tofile="new.txt")
    assert page.startswith("<!DOCTYPE html>")
    assert "<title>old.txt → new.txt</title>" in page
    assert '<th colspan="2">old.txt</th>' in page
    assert '<tr class="hunk"><td colspan="4">@@ -1,3 +1,4 @@</td></tr>' in page
    assert (
        '<tr class="replace"><td class="num">2</td>'
        '<td class="line old">&lt;<del>b</del>&gt;</td>'
        '<td class="num">2</td><td class="line new">&lt;<ins>B</ins>&gt;</td></tr>'
    ) in page
    assert (
        '<tr class="insert"><td class="num"></td><td class="line empty"></td>'
        '<td class="num">4</td><td class="line new">d</td></tr>'
    ) in page
    assert '<tr class="equal"><td class="num">1</td><td class="line">a</td>' in page
    assert_balanced(page)


def test_html_escapes_everything() -> None:
    evil = '</td><script>alert("x")</script>'
    page = html_diff(diff(["safe"], [evil]), fromfile="<a>", tofile='"b"')
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "<title>&lt;a&gt; → &quot;b&quot;</title>" in page
    assert_balanced(page)


def test_html_context() -> None:
    old = [f"line {i}" for i in range(20)]
    new = list(old)
    new[10] = "changed"
    ops = diff(old, new)

    def numbers(markup: str) -> set[int]:
        found = set()
        for part in markup.split('<td class="num">')[1:]:
            text = part.split("<", 1)[0]
            if text:
                found.add(int(text))
        return found

    assert numbers(html_diff(ops, context=1)) == {10, 11, 12}
    assert numbers(html_diff(ops, context=None)) == set(range(1, 21))


def test_html_no_differences() -> None:
    page = html_diff(diff(["a"], ["a"]))
    assert "No differences" in page
    assert_balanced(page)
    old = ["x", "y"]
    ops = diff(old, ["x", "", "y"])
    assert "No differences" not in html_diff(ops)
    assert "No differences" in html_diff(ops, ignore_blank_lines=True)


def test_html_moves() -> None:
    funcs = [python_function(i) for i in range(6)]
    old = sum(funcs, [])
    new = sum(funcs[:1] + funcs[2:] + [funcs[1]], [])
    ops = diff(old, new)
    page = html_diff(ops, moves=find_moves(ops))
    assert '<td class="line old moved">def func_1(data):</td>' in page
    assert '<td class="line new moved">def func_1(data):</td>' in page
    assert "<del>" not in page


def test_html_fragment_and_style() -> None:
    table = html_diff(diff(["a"], ["b"]), full_page=False)
    assert table.startswith('<table class="histodiff">')
    assert "<html" not in table and "<style>" not in table
    assert ".histodiff" in HTML_STYLE and "prefers-color-scheme: dark" in HTML_STYLE
    assert_balanced(table)


def test_html_rejects_bad_input() -> None:
    with pytest.raises(TypeError, match="html_diff renders text"):
        html_diff(diff([1], [2]))
    with pytest.raises(ValueError, match="context"):
        html_diff(diff(["a"], ["b"]), context=-1)


def test_cli_html(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["a", "b"])
    new = write(tmp_path / "new", ["a", "c"])
    assert main([old, new, "--html"]) == 1
    page = capsys.readouterr().out
    assert page.startswith("<!DOCTYPE html>")
    assert '<td class="line new">c</td>' in page
    assert_balanced(page)

    assert main([old, old, "--html"]) == 0
    assert "No differences" in capsys.readouterr().out


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------


def test_json_schema() -> None:
    ops = diff(["a\n", "b\n"], ["a\n", "c\n", "d\n"])
    doc = json.loads(
        to_json(ops, fromfile="x.txt", tofile="y.txt", algorithm="histogram")
    )
    assert doc["version"] == 1
    assert doc["algorithm"] == "histogram"
    assert doc["old"] == {"path": "x.txt", "length": 2}
    assert doc["new"] == {"path": "y.txt", "length": 3}
    assert doc["ops"] == [
        {
            "tag": "equal",
            "a_start": 0,
            "a_end": 1,
            "b_start": 0,
            "b_end": 1,
            "a_lines": ["a\n"],
            "b_lines": ["a\n"],
        },
        {
            "tag": "replace",
            "a_start": 1,
            "a_end": 2,
            "b_start": 1,
            "b_end": 3,
            "a_lines": ["b\n"],
            "b_lines": ["c\n", "d\n"],
        },
    ]
    assert "moves" not in doc


def test_json_round_trip() -> None:
    ops = diff(["one", "two", "three"], ["zero", "one", "three", "four"])
    assert from_json(to_json(ops)) == ops
    assert from_json(to_json(ops, indent=2).encode()) == ops
    numbers = diff([1, 2, 3], [1, 3, 4])
    assert from_json(to_json(numbers)) == numbers


def test_json_without_lines() -> None:
    ops = diff(["a"], ["b"])
    doc = json.loads(to_json(ops, include_lines=False))
    assert doc["ops"] == [
        {"tag": "replace", "a_start": 0, "a_end": 1, "b_start": 0, "b_end": 1}
    ]
    with pytest.raises(ValueError, match="include_lines"):
        from_json(to_json(ops, include_lines=False))


def test_json_moves() -> None:
    long_line = "important = compute_something(alpha, beta)"
    ops = diff([long_line, "keep = 1"], ["keep = 1", long_line])
    doc = json.loads(to_json(ops, moves=find_moves(ops)))
    assert doc["moves"] == [
        {
            "a_start": 0,
            "a_end": 1,
            "b_start": 1,
            "b_end": 2,
            "a_lines": [long_line],
            "b_lines": [long_line],
        }
    ]
    doc = json.loads(
        to_json(
            ops,
            moves=[Move(0, 1, 1, 2, (long_line,), (long_line,))],
            include_lines=False,
        )
    )
    assert doc["moves"] == [{"a_start": 0, "a_end": 1, "b_start": 1, "b_end": 2}]


def test_json_keeps_unicode_readable() -> None:
    assert "café" in to_json(diff(["café"], ["cafe"]))


def test_from_json_rejects_other_documents() -> None:
    with pytest.raises(ValueError, match="histodiff JSON"):
        from_json("[]")
    with pytest.raises(ValueError, match="histodiff JSON"):
        from_json('{"version": 2, "ops": []}')
    bad = {
        "version": 1,
        "old": {"length": 0},
        "new": {"length": 0},
        "ops": [
            {
                "tag": "shuffle",
                "a_start": 0,
                "a_end": 0,
                "b_start": 0,
                "b_end": 0,
                "a_lines": [],
                "b_lines": [],
            }
        ],
    }
    with pytest.raises(ValueError, match="tag"):
        from_json(json.dumps(bad))


@pytest.mark.parametrize(
    "document",
    [
        {"version": 1},
        {"version": True, "old": {"length": 0}, "new": {"length": 0}, "ops": []},
        {"version": 1, "old": {"length": 0}, "new": {"length": 0}, "ops": None},
        {"version": 1, "old": {"length": 0}, "new": {"length": 0}, "ops": [1]},
        {"version": 1, "ops": []},
        {
            "version": 1,
            "old": {"length": 0},
            "new": {"length": 0},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": -1,
                    "a_end": 0,
                    "b_start": 0,
                    "b_end": 1,
                    "a_lines": [],
                    "b_lines": ["x"],
                }
            ],
        },
        {
            "version": 1,
            "old": {"length": 1},
            "new": {"length": 1},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": 0,
                    "a_end": 1,
                    "b_start": 0,
                    "b_end": 1,
                    "a_lines": [],
                    "b_lines": ["x"],
                }
            ],
        },
        {
            "version": 1,
            "old": {"length": 1},
            "new": {"length": 0},
            "ops": [
                {
                    "tag": "insert",
                    "a_start": 0,
                    "a_end": 1,
                    "b_start": 0,
                    "b_end": 0,
                    "a_lines": ["x"],
                    "b_lines": [],
                }
            ],
        },
        {
            "version": 1,
            "old": {"length": 2},
            "new": {"length": 1},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": 1,
                    "a_end": 2,
                    "b_start": 0,
                    "b_end": 1,
                    "a_lines": ["x"],
                    "b_lines": ["x"],
                }
            ],
        },
        {
            "version": 1,
            "old": {"length": 2},
            "new": {"length": 2},
            "ops": [
                {
                    "tag": "equal",
                    "a_start": 0,
                    "a_end": 1,
                    "b_start": 0,
                    "b_end": 1,
                    "a_lines": ["x"],
                    "b_lines": ["x"],
                },
                {
                    "tag": "equal",
                    "a_start": 1,
                    "a_end": 2,
                    "b_start": 1,
                    "b_end": 2,
                    "a_lines": ["y"],
                    "b_lines": ["y"],
                },
            ],
        },
        {"version": 1, "old": {"length": 1}, "new": {"length": 0}, "ops": []},
    ],
)
def test_from_json_rejects_malformed_operations(document) -> None:
    with pytest.raises(ValueError):
        from_json(json.dumps(document))


def test_from_json_rejects_malformed_moves() -> None:
    document = json.loads(to_json(diff(["old"], ["new"])))
    document["moves"] = "not a list"
    with pytest.raises(ValueError, match="moves"):
        from_json(json.dumps(document))

    document["moves"] = [{"a_start": 0, "a_end": 2, "b_start": 0, "b_end": 2}]
    with pytest.raises(ValueError, match="outside"):
        from_json(json.dumps(document))


def test_json_marks_blank_only_hunks_as_ignored(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["a", "b"])
    new = write(tmp_path / "new", ["a", "", "b"])
    assert main([old, new, "-B", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["ignore_blank_lines"] is True
    assert document["has_changes"] is False
    assert [entry.get("ignored", False) for entry in document["ops"]] == [
        False,
        True,
        False,
    ]


def test_cli_json(tmp_path, capsys) -> None:
    funcs = [python_function(i) for i in range(4)]
    old = write(tmp_path / "old.py", sum(funcs, []))
    new = write(tmp_path / "new.py", sum(funcs[1:] + funcs[:1], []))
    assert main([old, new, "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["old"]["path"] == old and doc["algorithm"] == "histogram"
    assert [op["tag"] for op in doc["ops"]] == ["delete", "equal", "insert"]
    assert len(doc["moves"]) == 1
    assert doc["moves"][0]["a_lines"][0] == "def func_0(data):\n"
    rebuilt = from_json(json.dumps(doc))
    assert all(isinstance(op, DiffOp) for op in rebuilt)

    assert main([old, old, "--json"]) == 0
    assert [op["tag"] for op in json.loads(capsys.readouterr().out)["ops"]] == ["equal"]
