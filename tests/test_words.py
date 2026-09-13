"""Word-level highlighting inside replaced lines."""

from __future__ import annotations

import random

import pytest

import histodiff.words
from histodiff import highlight_words, inline_word_diff, split_words
from histodiff.cli import (
    GREEN,
    NO_NEWLINE,
    NO_REVERSE,
    RED,
    RESET,
    REVERSE,
    main,
    render,
)
from test_cli import write

# --------------------------------------------------------------------------
# split_words
# --------------------------------------------------------------------------


def test_split_words() -> None:
    assert split_words("result = process(event)") == [
        "result",
        " ",
        "=",
        " ",
        "process",
        "(",
        "event",
        ")",
    ]
    assert split_words("  a->b\t") == ["  ", "a", "-", ">", "b", "\t"]
    assert split_words("") == []
    assert split_words("naïve café_1") == ["naïve", " ", "café_1"]


def test_split_words_round_trips() -> None:
    rng = random.Random(0)
    alphabet = "ab_ 1\t(),.-=é\"'"
    for _ in range(500):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
        assert "".join(split_words(text)) == text


# --------------------------------------------------------------------------
# highlight_words
# --------------------------------------------------------------------------


def test_highlight_single_changed_word() -> None:
    old, new = highlight_words(
        ["    result = process(event)"], ["    result = process_v2(event)"]
    )
    assert old == [[("    result = ", False), ("process", True), ("(event)", False)]]
    assert new == [[("    result = ", False), ("process_v2", True), ("(event)", False)]]


def test_highlight_across_lines() -> None:
    # The call was joined onto one line: only the line break/indent changed.
    old, new = highlight_words(["foo(a,", "    b)"], ["foo(a, b)"])
    assert old == [[("foo(a,", False)], [("    ", True), ("b)", False)]]
    assert new == [[("foo(a,", False), (" ", True), ("b)", False)]]


def test_highlight_segments_rebuild_lines() -> None:
    rng = random.Random(1)
    words = ["x", "y", "=", "(", ")", " ", "  ", "foo", "bar", ","]
    for _ in range(200):
        old = [
            "".join(rng.choice(words) for _ in range(rng.randint(1, 8)))
            for _ in range(rng.randint(1, 3))
        ]
        new = [
            "".join(rng.choice(words) for _ in range(rng.randint(1, 8)))
            for _ in range(rng.randint(1, 3))
        ]
        result = highlight_words(old, new, min_similarity=0)
        assert result is not None
        for lines, segments in zip((old, new), result):
            assert ["".join(text for text, _ in line) for line in segments] == lines


def test_unrelated_lines_are_not_highlighted() -> None:
    assert highlight_words(["alpha beta"], ["gamma delta"]) is None
    # Forced: only the shared space between the words is left unmarked.
    assert highlight_words(["alpha beta"], ["gamma delta"], min_similarity=0) == (
        [[("alpha", True), (" ", False), ("beta", True)]],
        [[("gamma", True), (" ", False), ("delta", True)]],
    )


def test_whitespace_only_change_is_highlighted() -> None:
    old, new = highlight_words(["x = 1"], ["x  = 1"])
    assert old == [[("x", False), (" ", True), ("= 1", False)]]
    assert new == [[("x", False), ("  ", True), ("= 1", False)]]


def test_highlight_needs_both_sides() -> None:
    assert highlight_words([], ["x"]) is None
    assert highlight_words(["x"], []) is None


def test_highlight_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="newlines"):
        highlight_words(["a\n"], ["b\n"])
    with pytest.raises(ValueError, match="unknown algorithm"):
        highlight_words(["a"], ["b"], algorithm="lcs")


def test_huge_blocks_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(histodiff.words, "MAX_TOKENS", 4)
    assert highlight_words(["a b c"], ["a b d"]) is None
    assert inline_word_diff(["a b", "c"], ["a b d"]) == [
        ("delete", "a b c"),
        ("insert", "a b d"),
    ]


@pytest.mark.parametrize("algorithm", ["myers", "patience", "histogram"])
def test_every_algorithm_works(algorithm: str) -> None:
    old, new = highlight_words(["a = f(x)"], ["a = g(x)"], algorithm=algorithm)
    assert [text for text, changed in old[0] if changed] == ["f"]
    assert [text for text, changed in new[0] if changed] == ["g"]


# --------------------------------------------------------------------------
# inline_word_diff
# --------------------------------------------------------------------------


def test_inline_single_word() -> None:
    assert inline_word_diff(
        ["result = process(event)"], ["result = process_v2(event)"]
    ) == [
        ("equal", "result = "),
        ("delete", "process"),
        ("insert", "process_v2"),
        ("equal", "(event)"),
    ]


def test_inline_deleted_newline_becomes_space() -> None:
    assert inline_word_diff(["foo(a,", "    b)"], ["foo(a, b)"]) == [
        ("equal", "foo(a,"),
        ("delete", "     "),
        ("insert", " "),
        ("equal", "b)"),
    ]


def test_inline_follows_new_line_structure() -> None:
    runs = inline_word_diff(["one two three"], ["one two", "three"])
    assert "".join(text for tag, text in runs if tag != "delete") == "one two\nthree"
    assert "".join(text for tag, text in runs if tag != "insert") == "one two three"


def test_inline_one_side_empty() -> None:
    assert inline_word_diff([], ["new line"]) == [("insert", "new line")]
    assert inline_word_diff(["old", "lines"], []) == [("delete", "old lines")]
    assert inline_word_diff([], []) == []


# --------------------------------------------------------------------------
# CLI rendering
# --------------------------------------------------------------------------

OLD = ["def handle(event):", "    result = process(event)", "    return result"]
NEW = [
    "def handle(event):",
    "    result = process_v2(event)",
    "    return result",
    "# totally unrelated trailer",
]


@pytest.fixture
def files(tmp_path) -> tuple[str, str]:
    return write(tmp_path / "old.py", OLD), write(tmp_path / "new.py", NEW)


def test_color_highlights_changed_words(files, capsys) -> None:
    assert main([*files, "--color"]) == 1
    out = capsys.readouterr().out
    assert f"{RED}-    result = {REVERSE}process{NO_REVERSE}(event){RESET}\n" in out
    assert (
        f"{GREEN}+    result = {REVERSE}process_v2{NO_REVERSE}(event){RESET}\n" in out
    )
    # A pure insertion has nothing to compare against: no highlighting.
    assert f"{GREEN}+# totally unrelated trailer{RESET}\n" in out


def test_color_words_inline(files, capsys) -> None:
    assert main([*files, "--color-words"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert f"    result = {RED}process{RESET}{GREEN}process_v2{RESET}(event)" in out
    # Context lines lose the diff's leading space; insertions are plain green.
    assert "def handle(event):" in out
    assert "    return result" in out
    assert "     return result" not in out
    assert f"{GREEN}# totally unrelated trailer{RESET}" in out
    assert not any(line.startswith(("+", "-")) for line in out[2:])


def test_plain_output_is_unchanged(files, capsys) -> None:
    assert main(list(files)) == 1
    out = capsys.readouterr().out
    assert "\x1b[" not in out
    assert "-    result = process(event)\n+    result = process_v2(event)\n" in out


def test_render_unrelated_replacement_has_no_highlight() -> None:
    lines = ["--- a\n", "+++ b\n", "@@ -1 +1 @@\n", "-alpha beta\n", "+gamma delta\n"]
    out = "".join(render(lines, "color"))
    assert REVERSE not in out
    assert f"{RED}-alpha beta{RESET}\n{GREEN}+gamma delta{RESET}\n" in out


def test_render_keeps_no_newline_marker_and_crlf() -> None:
    lines = ["--- a\n", "+++ b\n", "@@ -1 +1 @@\n", "-x = 1\r\n", "+x = 2"]
    out = "".join(render(lines, "color"))
    assert out.endswith(
        f"{RED}-x = {REVERSE}1{NO_REVERSE}{RESET}\r\n"
        f"{GREEN}+x = {REVERSE}2{NO_REVERSE}{RESET}\n{NO_NEWLINE}"
    )


def test_color_words_keeps_no_newline_markers(tmp_path, capsys) -> None:
    old = write(tmp_path / "old", ["alpha beta"], trailing_newline=False)
    new = write(tmp_path / "new", ["alpha gamma"], trailing_newline=False)
    assert main([old, new, "--color-words"]) == 1
    assert capsys.readouterr().out.count(NO_NEWLINE) == 2

    with_newline = write(tmp_path / "with-newline", ["same"])
    without_newline = write(
        tmp_path / "without-newline", ["same"], trailing_newline=False
    )
    assert main([with_newline, without_newline, "--color-words"]) == 1
    assert capsys.readouterr().out.endswith(f"same\n{NO_NEWLINE}")


def test_render_does_not_treat_deleted_dashes_as_headers() -> None:
    lines = [
        "--- a\n",
        "+++ b\n",
        "@@ -1 +1 @@\n",
        "--- old sql comment\n",
        "+-- new sql comment\n",
    ]
    out = "".join(render(lines, "color"))
    assert f"{RED}--- {REVERSE}old{NO_REVERSE} sql comment{RESET}\n" in out
