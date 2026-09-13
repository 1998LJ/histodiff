# histodiff

histodiff produces clean, human-readable diffs even when content shifts position — using the same patience/histogram algorithms Git uses internally, unlike Python's built-in difflib.

## Why

A diff tool has to decide which lines in the old file "are" which lines in
the new one. Python's `difflib` grabs the longest stretch of identical lines
it can find and works outward from there. In files of 200 lines or more it
also refuses to line up on lines that appear often, such as blank lines or
repeated boilerplate. `difflib.unified_diff` gives you no way to turn that
off. Move one function to the bottom of a file, and difflib can end up
reporting that almost the whole file was deleted and re-added.

histodiff lines files up on their *distinctive* lines first: a function
name, a section header, the one row of data that changed. Everything else
falls into place around those. Moved code shows up as moved, a one-line
change stays a one-line change, and change blocks start and end at natural
boundaries such as blank lines rather than halfway through a block.

## Before and after

A function moved from the top of a 240-line module to the bottom, from
[`examples/before_after.py`](examples/before_after.py). Both columns use the
same unified-diff formatter, so every difference comes from how the lines
were matched up:

```
difflib                                              | histodiff (histogram)
-----------------------------------------------------+-----------------------------------------------------
@@ -6,6 +6,230 @@                                    | @@ -6,14 +6,6 @@
     return results                                  |      return results
                                                     |  
                                                     |  
+def fetch_invoices(client, limit=100):              | -def fetch_orders(client, limit=100):
+    """Return up to `limit` invoices from the API.~ | -    """Return up to `limit` orders from the API."""
+    results = []                                    | -    results = []
+    for page in client.paginate("/invoices", limit~ | -    for page in client.paginate("/orders", limit=l~
+        results.extend(page)                        | -        results.extend(page)
+    return results                                  | -    return results
+                                                    | -
+                                                    | -
+def fetch_payments(client, limit=100):              |  def fetch_invoices(client, limit=100):
+    """Return up to `limit` payments from the API.~ |      """Return up to `limit` invoices from the API.~
+    results = []                                    |      results = []
+    for page in client.paginate("/payments", limit~ | @@ -238,3 +230,11 @@
+        results.extend(page)                        |      return results
+    return results                                  |  
+                                                    |  
+                                                    | +def fetch_orders(client, limit=100):
+def fetch_refunds(client, limit=100):               | +    """Return up to `limit` orders from the API."""
+    """Return up to `limit` refunds from the API."~ | +    results = []
+    results = []                                    | +    for page in client.paginate("/orders", limit=l~
+    for page in client.paginate("/refunds", limit=~ | +        results.extend(page)
... 435 more lines                                   | ... 3 more lines

                   difflib   histodiff
hunks                    2           2
changed lines          448          16
```

Run `python examples/before_after.py` for this and two more scenarios: a
single changed row in a repetitive CSV file (difflib: 301 changed lines,
histodiff: 1), and a small config file where both report the same number of
changes but difflib's change block begins in the middle of a section.

## Installation

```bash
pip install histodiff
```

Requires Python 3.9+. No dependencies.

## Usage

### Python

```python
from histodiff import diff, unified_diff

old = open("old.py").readlines()
new = open("new.py").readlines()

ops = diff(old, new)                      # algorithm="histogram" by default
for op in ops:
    if op.tag != "equal":
        print(op.tag, op.a_start, op.a_end, op.b_start, op.b_end)

print("".join(unified_diff(ops, context=3, fromfile="old.py", tofile="new.py")))
```

`diff` returns a list of `DiffOp` dataclasses. Each op covers
`a[a_start:a_end]` and `b[b_start:b_end]`, carries those lines in `a_lines`
and `b_lines`, and has a `tag` of `"equal"`, `"insert"`, `"delete"` or
`"replace"`. Indices follow `difflib.SequenceMatcher.get_opcodes()`, and
`op.as_opcode()` returns the same tuple. `unified_diff` renders the same
text `difflib.unified_diff` would for that alignment.

Each algorithm is also available directly, with the same return type:

```python
from histodiff import histogram_diff, myers_diff, patience_diff

ops = patience_diff(old, new)
ops = diff(old, new, algorithm="myers")   # equivalent to myers_diff(old, new)
ops = diff(old, new, minimal=True)        # never trade diff size for speed
```

### Words, tokens and records

`diff` works on any sequence of hashable items, not just lines:

```python
from histodiff import diff

old = "the quick brown fox jumps".split()
new = "the quick red fox jumped".split()
[(op.tag, op.a_lines, op.b_lines) for op in diff(old, new) if op.tag != "equal"]
# [('replace', ('brown',), ('red',)), ('replace', ('jumps',), ('jumped',))]

diff([1, 2, 3, 4], [1, 3, 4, 5])          # numbers, tuples, named tuples,
                                          # frozen dataclasses...
```

Pass `key` to compare items by a derived value, as with `sorted(key=...)`.
The ops still hold your original items:

```python
diff(old_lines, new_lines, key=str.strip)       # ignore indentation/trailing spaces
diff(old_words, new_words, key=str.casefold)    # ignore case

# dicts aren't hashable, so compare them by their contents
diff(old_rows, new_rows, key=lambda row: tuple(sorted(row.items())))
```

The algorithm functions (`myers_diff` and the rest) take the same `key`.
`unified_diff` is a text format, so it only accepts ops whose items are
strings.

### Coming from difflib

`histodiff.SequenceMatcher` is a drop-in subclass of
`difflib.SequenceMatcher`. Change the import and your existing code gets
histodiff's alignment:

```python
# from difflib import SequenceMatcher
from histodiff import SequenceMatcher

sm = SequenceMatcher(None, old, new)      # same signature as difflib
sm.get_opcodes()                          # [('equal', 0, 5, 0, 5), ...]
sm.get_grouped_opcodes(3)                 # hunks, as in difflib
sm.ratio()                                # similarity from the better alignment

SequenceMatcher(None, old, new, algorithm="patience")   # pick an algorithm
```

Like difflib's, it works on any sequences of hashable items, including
strings compared character by character. `get_diff_ops()` returns the same
alignment as `DiffOp`s, which you can pass to `unified_diff`. A few
deliberate differences:

- `isjunk` items are never used as anchors, but can still be matched between
  anchors.
- `autojunk` is accepted but has no effect, because difflib's
  frequent-line heuristic is what makes its large diffs poor.
- `find_longest_match()` keeps difflib's behavior.

To replace `difflib.unified_diff(a, b)`, use `unified_diff(diff(a, b))`.

### Command line

```bash
histodiff old.py new.py                           # unified diff, histogram algorithm
histodiff old.py new.py --algorithm patience
histodiff old.py new.py --color                   # green additions, red deletions
histodiff old.py new.py -U 10                     # 10 lines of context
histodiff old.py new.py --minimal                 # smallest diff, however long it takes
cat new.py | histodiff old.py -                   # '-' reads stdin
```

As with `diff`, the exit status is 0 when the files are identical, 1 when
they differ, and 2 on error. Try it on the classic patience-diff example:
`histodiff examples/frobnitz_old.c examples/frobnitz_new.c`, then the same
with `--algorithm myers`.

## Choosing an algorithm

| Algorithm | Use it when | Trade-off |
| --- | --- | --- |
| `histogram` (default) | You want readable diffs of real files: code, config, data. | Not guaranteed to be the smallest possible diff. |
| `patience` | Code with plenty of unique lines, where you want strict "only anchor on lines that appear exactly once" behavior. | If no line is unique, for example when blocks are duplicated, it falls back to Myers. |
| `myers` | You need the minimum number of changed lines (with `minimal=True` on big, very different inputs), or you're comparing against `git diff --diff-algorithm=myers`. | Readily matches stray `}` and blank lines, which splits moved or rewritten blocks into many interleaved hunks. |

- **histogram** is Git's recommended algorithm (`git diff --diff-algorithm=histogram`).
  It works like patience but anchors on the *rarest* matching lines instead of
  demanding strictly unique ones. That keeps it readable when every line repeats
  somewhere. Lines that occur more than 64 times are never used as anchors.
- **patience** anchors on lines that occur exactly once in both files, keeps the
  longest run of them that appears in the same order, and repeats that between
  the anchors.
- **myers** is the classic O(ND) shortest-edit-script algorithm and Git's
  default. It's the right choice when diff *size* matters more than
  readability. On large, very different inputs its run time grows with the
  square of the file size, so, like Git, histodiff caps the search there and
  accepts a slightly larger diff (see [Performance](#performance)). Patience
  and histogram use Myers for the stretches they can't anchor, so the cap
  protects them too. Pass `minimal=True` or `--minimal` to turn it off.

Because patience and histogram prefer distinctive lines over the largest
possible match, they sometimes report more changed lines than Myers, most often
when whole blocks are duplicated and shuffled. All three algorithms share a
final pass that slides ambiguous insertions and deletions to blank-line and
indentation boundaries, similar to Git's own clean-up heuristics.

## Performance

histodiff is pure Python. These numbers come from
[`benchmarks/bench.py`](benchmarks/bench.py) on an Apple M3 Pro with
Python 3.14, using 20,000-line files and keeping the best of 3 runs. Each
cell shows the time, then the number of lines the diff marks as changed:

| Scenario | difflib | myers | patience | histogram |
| --- | --- | --- | --- | --- |
| One line changed | 6 ms (2) | 4 ms (2) | 4 ms (2) | 4 ms (2) |
| Function moved | 6 ms (39,968) | 6 ms (16) | 8 ms (16) | 6 ms (16) |
| 5% of lines edited | 830 ms (2,094) | 119 ms (1,950) | 10 ms (1,950) | 31 ms (1,950) |
| Row inserted in repeated rows | 3 ms (20,001) | 4 ms (1) | 4 ms (1) | 4 ms (1) |
| Unrelated files (worst case) | 3 ms (40,000) | 1.67 s (30,232) | 1.66 s (30,232) | 1.71 s (30,232) |

- **Everyday edits:** histodiff is about as fast as difflib or faster, and
  its diffs are never larger. With many scattered edits, histogram is about
  25× faster than difflib here.
- **Unrelated files:** difflib is far faster, because on large files it
  effectively gives up and marks every line as changed. histodiff still
  lines up the lines the files share, which takes longer.
- **The search cap:** without it, the worst case grows with the square of
  the file size. On 8,000-line unrelated files, histogram takes 0.67 s
  capped and 10.5 s with `minimal=True`, while the capped diff is only 0.8%
  larger (12,092 changed lines instead of 12,000). At 16,000 lines the
  uncapped search took 42 s.

Run `python benchmarks/bench.py --help` for sizes, repeats and a Markdown
output mode.

## Contributing

Issues and pull requests are welcome. To set up a development environment:

```bash
git clone https://github.com/rmnvg/histodiff
cd histodiff
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Before opening a pull request, make sure the tests and linter pass:

```bash
pytest                          # unit, readability and CLI tests
ruff check .                    # lint
python examples/before_after.py # the README comparison still holds
```

If you touch the algorithms, run `python benchmarks/bench.py` before and
after your change and include both tables in the pull request.

New behavior should come with tests. For changes to how lines get matched,
add a realistic case to `tests/test_readability.py` showing the diff you
expect. CI runs all of the above on Python 3.9–3.14.

## License

MIT, see [LICENSE](LICENSE).
