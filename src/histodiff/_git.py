"""Adapter for Git's external-diff protocol."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Sequence

from . import __version__
from .cli import main as cli_main

_SCORE = re.compile(r"^(?:dis)?similarity index \d+%$")
_TRUE = frozenset({"1", "true", "yes", "on"})

_HELP = """\
usage: git-histodiff <path> <old-file> <old-hex> <old-mode> \\
                     <new-file> <new-hex> <new-mode> [<new-path> <score>]

Adapter for Git's external-diff protocol. Configure it in a repository with:

    git config diff.external git-histodiff

Run `git diff`, `git diff --cached`, or `git show --ext-diff` normally after
configuration. This command is invoked by Git and is not a two-file interface;
use `histodiff OLD NEW` for direct comparisons.
"""


def _missing(path: str, mode: str) -> bool:
    return path == "/dev/null" or mode in {".", "000000"}


def _contains_nul(path: str, missing: bool) -> bool:
    if missing:
        return False
    with open(path, "rb") as handle:
        return b"\0" in handle.read(8192)


def _git_status(status: int) -> int:
    """Translate normal diff status to Git's external-helper convention."""
    if status == 2:
        return 2
    trusted = os.environ.get("GIT_EXTERNAL_DIFF_TRUST_EXIT_CODE", "").lower()
    return status if trusted in _TRUE else 0


def _os_error(exc: OSError) -> int:
    name = exc.filename if exc.filename is not None else ""
    print(f"git-histodiff: {name}: {exc.strerror or exc}", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    """Render one file pair supplied through Git's external-diff protocol."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--help"]:
        print(_HELP, end="")
        return 0
    if args == ["--version"]:
        print(f"git-histodiff {__version__}")
        return 0
    if len(args) == 1:
        print(f"Unmerged path: {args[0]}")
        return 0
    if len(args) not in {7, 9}:
        print(_HELP, file=sys.stderr, end="")
        return 2

    path, old_file, _old_hex, old_mode, new_file, _new_hex, new_mode = args[:7]
    if len(args) == 9:
        new_path, score = args[7:]
        if not _SCORE.fullmatch(score):
            print("git-histodiff: invalid rename/copy score from Git", file=sys.stderr)
            return 2
    else:
        new_path, score = path, None

    old_missing = _missing(old_file, old_mode)
    new_missing = _missing(new_file, new_mode)
    old_input = os.devnull if old_missing else old_file
    new_input = os.devnull if new_missing else new_file
    old_label = "/dev/null" if old_missing else f"a/{path}"
    new_label = "/dev/null" if new_missing else f"b/{new_path}"

    print(f"diff --histodiff {old_label} {new_label}")
    if old_missing:
        print(f"new file mode {new_mode}")
    elif new_missing:
        print(f"deleted file mode {old_mode}")
    elif old_mode != new_mode:
        print(f"old mode {old_mode}")
        print(f"new mode {new_mode}")
    if score is not None:
        print(score)
        print(f"path from {path}")
        print(f"path to {new_path}")

    try:
        binary = _contains_nul(old_file, old_missing) or _contains_nul(
            new_file, new_missing
        )
    except OSError as exc:
        return _os_error(exc)
    if binary:
        print(f"Binary files {old_label} and {new_label} differ")
        return _git_status(1)

    status = cli_main([old_input, new_input], _labels=(old_label, new_label))
    return _git_status(status)


if __name__ == "__main__":  # pragma: no cover
    # The installed `git-histodiff` console script calls main() directly, not
    # through this guard; tests/test_git.py exercises that real entry point
    # via a subprocess (test_documented_git_workflow), which coverage.py
    # can't see into. Running this file directly as a script would take the
    # same path, so this line stays untested rather than untestable.
    sys.exit(main())
