# Roadmap

histodiff is `0.1.x`: the alignment engine, output formats, and CLI are
stable and in real use, but the project is young. This is a short,
honest list of what's likely next - not a promise of dates, and not
exhaustive. Priorities shift based on what real usage turns up; see
[issue #4](https://github.com/rmnvg/histodiff/issues/4) for the single
best way to influence it.

## Now: small, well-scoped gaps

Tracked as individual issues, several tagged
[`good first issue`](https://github.com/rmnvg/histodiff/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22):

- `NO_COLOR` support ([#1](https://github.com/rmnvg/histodiff/issues/1))
- Case-insensitive comparison, `-i`/`--ignore-case`
  ([#2](https://github.com/rmnvg/histodiff/issues/2))
- A `--stat` summary mode ([#3](https://github.com/rmnvg/histodiff/issues/3))

## Next: driven by real examples

- A regression suite built from real, submitted diffs
  ([#4](https://github.com/rmnvg/histodiff/issues/4)) - concrete cases
  where an existing tool produced a poor alignment, turned into permanent
  tests. This is the main way the alignment heuristics improve from here:
  from cases that actually happened, not more synthetic ones.
- Sourcing a few of the [real-world corpus](examples/real_world_corpus.py)
  scenarios from actual open-source history (with attribution and a
  compatible license), rather than hand-written fixtures, once that's worth
  the added maintenance.

## Later, and less certain

- **1.0.** Once the data model (`DiffOp`, the JSON schema) has held up
  against real-world use for a while with no breaking changes needed, a
  1.0 mostly just means committing to that stability explicitly - see
  [API stability](README.md#api-stability) for what's already promised
  during `0.x`.
- **Structural / AST-aware diffing** for specific languages, as an
  opt-in mode - a much bigger undertaking than anything above, and not
  started. Line-based diffing (what histodiff does today) has a ceiling;
  this would be for going past it. No design work yet.
- **A pluggable algorithm interface**, if a third algorithm request ever
  comes in that doesn't fit alongside Myers/patience/histogram - not
  designed, and not needed until that actually happens.

## Explicitly not planned

- **Binary diffing.** Out of scope - histodiff is for text.
- **Merging or patch application.** histodiff generates and renders
  differences; it doesn't apply them (see
  [Limitations](README.md#limitations)). `patch`/`git apply` already do
  this well against unified-diff output.
- **Matching Git's output byte-for-byte.** histodiff is Git-*inspired*
  (histogram alignment, similar cleanup heuristics), not a
  reimplementation; see [Limitations](README.md#limitations).

Have a use case that doesn't fit here? Open an issue - roadmaps like this
one are supposed to be argued with.
