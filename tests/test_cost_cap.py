"""The Myers cost cap: bounded run time on large, very different inputs."""

from __future__ import annotations

import random
import time

import pytest

import histodiff.myers
from helpers import changed_lines, check_valid, lcs_length, random_pairs
from histodiff import diff, histogram_diff, myers_diff, patience_diff
from histodiff.cli import main

ALGORITHMS = [myers_diff, patience_diff, histogram_diff]


def unrelated_with_blanks(n: int, seed: int) -> list[str]:
    """A file sharing nothing with another but blank lines, which are too
    common for patience/histogram to anchor on, so everything goes to Myers."""
    rng = random.Random(seed)
    return ["" if i % 4 == 3 else f"code {rng.random()}" for i in range(n)]


def test_max_cost_has_a_floor_and_grows_with_size() -> None:
    assert histodiff.myers.max_cost(0) == histodiff.myers.MIN_COST
    big = 10 * histodiff.myers.MIN_COST
    assert histodiff.myers.max_cost(big * big) == big


@pytest.mark.parametrize("budget", [1, 2, 5])
@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_capped_search_still_produces_valid_diffs(
    monkeypatch: pytest.MonkeyPatch, algorithm, budget: int
) -> None:
    # Force the cap to trigger on tiny inputs to exercise the split path.
    monkeypatch.setattr(histodiff.myers, "max_cost", lambda size: budget)
    capped = 0
    for seed in range(10):
        for a, b in random_pairs(seed, 40, max_len=30, alphabet="abcdef"):
            ops = algorithm(a, b)
            check_valid(a, b, ops)
            if algorithm is myers_diff:
                minimum = len(a) + len(b) - 2 * lcs_length(a, b)
                assert changed_lines(ops) >= minimum
                capped += changed_lines(ops) > minimum
    if algorithm is myers_diff:
        assert capped, "the cap should have cost some diff size"


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_minimal_ignores_the_cap(monkeypatch: pytest.MonkeyPatch, algorithm) -> None:
    monkeypatch.setattr(histodiff.myers, "max_cost", lambda size: 1)
    for a, b in random_pairs(7, 60, max_len=20, alphabet="abc"):
        ops = algorithm(a, b, minimal=True)
        check_valid(a, b, ops)
        if algorithm is myers_diff:
            assert changed_lines(ops) == len(a) + len(b) - 2 * lcs_length(a, b)


def test_diff_and_cli_pass_minimal_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(histodiff.myers, "max_cost", lambda size: 1)
    # Pick an input where the cap costs diff size, so the flag is observable.
    a, b = next(
        (a, b)
        for a, b in random_pairs(0, 200, max_len=30, alphabet="abcdef")
        if changed_lines(myers_diff(a, b))
        > changed_lines(myers_diff(a, b, minimal=True))
    )
    assert diff(a, b, "myers", minimal=True) == myers_diff(a, b, minimal=True)
    assert diff(a, b, "myers") == myers_diff(a, b)

    old, new = tmp_path / "old", tmp_path / "new"
    old.write_bytes("".join(x + "\n" for x in a).encode())
    new.write_bytes("".join(x + "\n" for x in b).encode())
    counts = []
    for flag in ([], ["--minimal"]):
        main([str(old), str(new), "--algorithm", "myers", "-U", "0", *flag])
        counts.append(
            sum(
                1
                for line in capsys.readouterr().out.splitlines()
                if line[:1] in "+-" and not line.startswith(("---", "+++"))
            )
        )
    assert counts == [
        changed_lines(myers_diff(a, b)),
        changed_lines(myers_diff(a, b, minimal=True)),
    ]
    assert counts[0] > counts[1]


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_unrelated_large_files_finish_quickly(algorithm) -> None:
    # Uncapped, this takes ~10s on a fast laptop and grows 4x per doubling.
    a, b = unrelated_with_blanks(8000, 1), unrelated_with_blanks(8000, 2)
    start = time.perf_counter()
    ops = algorithm(a, b)
    elapsed = time.perf_counter() - start
    check_valid(a, b, ops)
    # Generous bound for slow CI machines; locally this is well under 1s.
    assert elapsed < 5
