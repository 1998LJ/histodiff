# Changelog

All notable changes to histodiff will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/). During the
`0.x` series, minor releases may include documented changes to ambiguous diff
alignment while preserving the public data model and valid edit operations.

## [Unreleased]

## [0.1.0] - Unreleased

### Added

- Histogram, patience, and Myers sequence-diff algorithms.
- Readability cleanup for ambiguous insertion and deletion boundaries.
- Unified, side-by-side, HTML, and versioned JSON output.
- Word-level highlighting and moved-block detection.
- Whitespace-aware comparison and blank-line filtering.
- A `difflib.SequenceMatcher`-compatible API and support for generic sequences.
- A dependency-free command-line interface.
- A `git-histodiff` adapter for repository, staged, and commit diffs.

[Unreleased]: https://github.com/rmnvg/histodiff/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/rmnvg/histodiff/releases/tag/v0.1.0
