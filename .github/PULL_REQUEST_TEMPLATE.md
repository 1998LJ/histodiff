## What does this change do?

<!-- A short description of the change and why it's needed. -->

Closes #<!-- issue number, if any -->

## How was this tested?

<!-- pytest output, a new/updated test, manual verification, etc. -->

## Checklist

- [ ] `pytest` passes
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] `mypy src` passes
- [ ] New behavior has a test (see
      [CONTRIBUTING.md](https://github.com/rmnvg/histodiff/blob/main/CONTRIBUTING.md#tests))
- [ ] If this changes how lines get matched, `tests/test_readability.py`
      and/or `tests/test_properties.py` were updated
- [ ] If this affects performance, `python benchmarks/bench.py` was run
      before/after and the tables are included below
- [ ] Documentation (README, docstrings) updated if behavior changed

## Benchmark results (if applicable)

<!-- Paste before/after tables from benchmarks/bench.py here, or delete this section. -->
