# Contributing to histodiff

Thanks for considering a contribution. This guide covers environment setup,
testing, formatting and type checking, what's expected of property tests and
benchmarks, and how the pull-request process works. For what histodiff *is*
and how its pieces fit together, see the [README](README.md) first.

## Environment setup

histodiff has no runtime dependencies, but the development tools (pytest,
ruff, mypy, hypothesis, build) are declared in the `dev` extra:

```bash
git clone https://github.com/rmnvg/histodiff
cd histodiff
python -m venv .venv
source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

This installs histodiff itself in editable mode, so `import histodiff` and
the `histodiff`/`git-histodiff` commands immediately reflect your changes to
`src/histodiff/`.

Supported Python versions are 3.9 through 3.14; CI runs the full test suite
on all of them on Linux, plus macOS and Windows on the newest supported
version. If you can, test locally on at least the oldest (3.9) and newest
supported version before opening a pull request - a language feature
available in one may not exist in the other.

## Tests

```bash
pytest
```

This runs the unit tests, the readability regression cases
(`tests/test_readability.py`), the property tests (`tests/test_properties.py`),
and the CLI/format/compat tests. It should complete in a few seconds.

New behavior needs a new test:

- **Bug fixes:** add a regression test that fails before your fix and
  passes after it.
- **Changes to how lines get matched** (any of the three algorithms, the
  readability cleanup pass, or move detection): add a realistic case to
  `tests/test_readability.py` that shows the diff you expect, not just an
  assertion on line counts - a future reader should be able to see *why*
  the alignment is correct by reading the test.
- **New public API:** add tests under the relevant `tests/test_*.py`
  module, following the existing naming and structure.

## Property-test expectations

`tests/test_properties.py` uses [Hypothesis](https://hypothesis.readthedocs.io/)
to check invariants that should hold for *any* input, not just the fixed
examples elsewhere - for example, that every algorithm's output ops tile the
two input sequences exactly, that `unified_diff` output round-trips, or that
`from_json(to_json(ops)) == ops`.

If you touch an algorithm or a data format, check whether an existing
property already covers it before adding another fixed example. A property
that Hypothesis can shrink to a minimal failing case is usually more
valuable than a hand-written regression, because it keeps testing your
change against inputs nobody thought to write by hand. Add a new property
when you introduce a new invariant (a new output format, an option that
should never change the total line count, and so on); extend an existing
one when your change is a variation on something already covered.

Hypothesis examples it has found failing are cached under `.hypothesis/`
(gitignored). That cache isn't needed to reproduce a bug report - include
the failing input directly in the report or as a test instead.

## Formatting and type checking

```bash
ruff check .            # lint
ruff format --check .   # formatting (drop --check to fix in place)
mypy src                # type checking of the public and internal API
```

All three run in CI and must pass. `mypy` only checks `src/`; `examples/`,
`benchmarks/`, and `tests/` are not type-checked, so prioritize clarity over
strict typing there.

## Benchmark expectations

```bash
python benchmarks/bench.py --help
```

If your change touches an algorithm's *performance* (not just its output),
run `python benchmarks/bench.py` before and after the change and include
both tables in the pull request description. This is how regressions get
caught before release rather than after. `benchmarks/bench.py` itself is
not run by CI, since its numbers are machine-dependent; CI only runs
`python benchmarks/bench.py --quick` as a smoke test that it still executes.

If your change could affect diff *quality* rather than speed, also run:

```bash
python examples/before_after.py
python examples/real_world_corpus.py
```

Both compare histodiff against difflib on realistic inputs and assert on
the comparison, so if a change makes histodiff's output measurably worse on
any of these scenarios, the assertion fails and the script explains why.

## Pull-request process

1. **For anything beyond a small, obvious fix, open an issue first**
   describing the problem or the feature, so the approach can be agreed on
   before you invest time in an implementation. Small fixes - typos, a bug
   with an obviously correct fix - can go straight to a pull request.
2. **Keep pull requests focused.** One logical change per PR is easier to
   review and to revert if something goes wrong. Put unrelated formatting
   or refactoring changes in a separate PR.
3. **Run the full local check before pushing:**

   ```bash
   pytest
   ruff check .
   ruff format --check .
   mypy src
   python -m build
   ```

   All of these run in CI too; running them locally first saves a
   round-trip.
4. **Write a clear PR description:** what changed, why, and how you tested
   it. Link the issue it addresses, if any. The
   [pull request template](.github/PULL_REQUEST_TEMPLATE.md) that appears
   when you open a PR has a checklist covering the above.
5. **CI must be green** before a PR is merged. If a failure looks unrelated
   to your change, say so in the PR - it may be a flake or a pre-existing
   issue rather than something you introduced.
6. Maintainers review for correctness, test coverage, and fit with the
   project's own design trade-offs (see
   [Choosing an algorithm](README.md#choosing-an-algorithm) and
   [Limitations](README.md#limitations) in the README). Expect at least one
   round of review comments on anything beyond a trivial fix.
7. Once approved, a maintainer merges the PR. There's no required commit
   style, but a short, descriptive commit message or PR title helps anyone
   reading `git log` later.

## Reporting bugs, requesting features, and security issues

- **Bugs and feature requests:** open a
  [GitHub issue](https://github.com/rmnvg/histodiff/issues/new/choose)
  using the bug report or feature request template.
- **Performance regressions:** use the performance regression issue
  template, and include `benchmarks/bench.py` output before and after, if
  you have it.
- **Security vulnerabilities:** do **not** open a public issue for these.
  See [SECURITY.md](SECURITY.md) for how to report one privately.

## Code of conduct

Participation in this project, including issues and pull requests, is
governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
