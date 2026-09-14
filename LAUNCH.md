# histodiff: readable diffs for code that moves, repeats, or reformats

`difflib` is the diff engine behind most Python tooling, and it has a known
weak spot: it aligns files by greedily grabbing the longest matching run it
can find and working outward from there. That's fast, and it's usually
fine. It falls over on three ordinary situations: a function that moved
without changing, a file with a lot of repeated lines (config files,
generated code, CSV exports), and its own `autojunk` heuristic, which
silently stops trusting any line that repeats "too often" once a file
crosses 200 lines - exactly the files where that line mattered most.

Git ran into the same problem years ago and shipped two alternative
algorithms for it: **patience diff** and **histogram diff** (Git's current
default). Both anchor on a file's *distinctive* lines first - the ones that
appear once or rarely - and fit everything else around those anchors,
instead of matching greedily from the start. `histodiff` is a pure-Python,
zero-dependency implementation of both, plus Myers' algorithm (what
`difflib` itself approximates) as a third option, behind one small API.

## What it looks like

A function moves from the top of a 240-line file to the bottom, with no
other changes:

```
difflib: 448 changed lines, 2 hunks
histodiff (histogram): 16 changed lines, 2 hunks
```

difflib doesn't just report a larger diff here - past its 200-line
autojunk cutoff it starts distrusting lines that repeat too often, and the
move looks like the whole file was rewritten. histodiff anchors on each
function's distinctive body and reports exactly what happened: one
function removed here, the same one added there.

Three more before/after cases - including one where histogram alignment
starts a hunk cleanly on a config-section boundary instead of three lines
into the wrong section - are online here: **[Before/after
showcase](https://claude.ai/code/artifact/cde0b91d-c33e-4392-905d-fdd43e6c63a4)**.

## Trying it

```bash
pip install histodiff
```

```python
import histodiff

ops = histodiff.diff(old_lines, new_lines)  # histogram by default
print("".join(histodiff.unified_diff(ops, fromfile="old.py", tofile="new.py")))
```

Already using `difflib.SequenceMatcher`? `histodiff.SequenceMatcher` is a
real subclass - same `get_opcodes()`, `get_grouped_opcodes()`, `ratio()` -
aligned with histodiff's algorithms instead of difflib's. Changing the
import is usually the whole migration; there's a runnable, side-by-side
example of both migration paths in
[`examples/migrate_from_difflib.py`](https://github.com/rmnvg/histodiff/blob/main/examples/migrate_from_difflib.py).

The CLI covers the rest of what you'd expect from a modern diff tool:
side-by-side and HTML output, JSON for feeding other tools, word-level
highlighting for changed lines (`--color-words`, like `git diff`), moved-block
detection, whitespace-insensitive comparisons, and a `git-histodiff` adapter
so `git diff` itself can use it with one `git config` line.

## What it isn't

histodiff doesn't apply patches, doesn't diff binaries, and doesn't promise
byte-identical output to Git - it's Git-inspired, not a reimplementation.
It's line-oriented, like difflib and like `git diff`; it does not do
AST-aware structural diffing. Full list, along with what's actually planned
next, in [ROADMAP.md](https://github.com/rmnvg/histodiff/blob/main/ROADMAP.md).

## Where this goes next

The project is `0.1.x` - the algorithms, formats, and CLI are stable and
already in use, but young. The most useful thing anyone can do right now is
send a real diff that came out looking wrong - from `difflib`, from `git
diff`, from anything - as
[a real example](https://github.com/rmnvg/histodiff/issues/4). Those become
permanent regression tests, which is a better source of truth than more
synthetic fixtures at this stage.

- Source, issues, full docs: <https://github.com/rmnvg/histodiff>
- PyPI: <https://pypi.org/project/histodiff/>
- License: MIT
