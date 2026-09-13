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
```

### Command line

```bash
histodiff old.py new.py                           # unified diff, histogram algorithm
histodiff old.py new.py --algorithm patience
histodiff old.py new.py --color                   # green additions, red deletions
histodiff old.py new.py -U 10                     # 10 lines of context
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
| `myers` | You need the minimum number of changed lines, or you're comparing against `git diff --diff-algorithm=myers`. | Readily matches stray `}` and blank lines, which splits moved or rewritten blocks into many interleaved hunks. |

- **histogram** is Git's recommended algorithm (`git diff --diff-algorithm=histogram`).
  It works like patience but anchors on the *rarest* matching lines instead of
  demanding strictly unique ones. That keeps it readable when every line repeats
  somewhere. Lines that occur more than 64 times are never used as anchors.
- **patience** anchors on lines that occur exactly once in both files, keeps the
  longest run of them that appears in the same order, and repeats that between
  the anchors.
- **myers** is the classic O(ND) shortest-edit-script algorithm and Git's
  default. It's the right choice when diff *size* matters more than
  readability.

Because patience and histogram prefer distinctive lines over the largest
possible match, they sometimes report more changed lines than Myers, most often
when whole blocks are duplicated and shuffled. All three algorithms share a
final pass that slides ambiguous insertions and deletions to blank-line and
indentation boundaries, similar to Git's own clean-up heuristics.

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

New behavior should come with tests. For changes to how lines get matched,
add a realistic case to `tests/test_readability.py` showing the diff you
expect. CI runs all of the above on Python 3.9–3.14.

## License

MIT, see [LICENSE](LICENSE).
