#!/usr/bin/env python3
"""Compare diff tools on ten realistic change scenarios.

    python examples/real_world_corpus.py            # full run
    python examples/real_world_corpus.py --quick     # shrink the large
                                                      # scenarios (CI smoke test)
    python examples/real_world_corpus.py --repeat 10 # more timing samples

For each scenario this prints, per tool: how many lines the diff marks as
changed, how many hunks that becomes with 3 lines of context, the best-of-N
wall-clock time, and (for the four scenarios built at a scale where it's
worth measuring) peak memory during the diff call.

Tools compared: `difflib.SequenceMatcher`, histodiff's `histogram`,
`patience` and `myers` algorithms, and - if installed - the third-party
`patiencediff` package (`pip install patiencediff`), an independent
implementation of the same patience idea. That package is optional and not
a histodiff dependency; the script runs without it and says so.

Design notes, read before citing these numbers:

* Every fixture below was written for this script to look like real code,
  config, and data - none of it is copied from an external repository, so
  there is no separate attribution or license to track. Sourcing genuine
  pairs from live repositories and pinning their commits was judged not
  worth the added risk (license review, upstream churn) for what a
  hand-written realistic fixture already demonstrates just as well.
* Timings are wall-clock, best of `--repeat` runs, on whatever machine you
  run this on - treat them as order-of-magnitude, not a benchmark suite.
  See benchmarks/bench.py for that.
* There is no universal winner here by design. Each scenario's note explains
  why *one* alignment tends to read more naturally for that shape of change;
  several scenarios are included specifically because the tools tie.
"""

from __future__ import annotations

import argparse
import difflib
import sys
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

try:
    import histodiff
except ImportError:  # not installed: use the checkout's src/ directory
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import histodiff

try:
    import patiencediff

    HAVE_PATIENCEDIFF = True
except ImportError:
    HAVE_PATIENCEDIFF = False

Lines = list[str]
Opcode = tuple[str, int, int, int, int]
Opcodes = list[Opcode]
ToolFunc = Callable[[Lines, Lines], Opcodes]

RULE = "=" * 78


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


def changed_lines(codes: Opcodes) -> int:
    return sum((i2 - i1) + (j2 - j1) for tag, i1, i2, j1, j2 in codes if tag != "equal")


def group_hunks(codes: Opcodes, context: int = 3) -> list[Opcodes]:
    """Split opcodes into hunks with ``context`` lines of padding.

    The same grouping ``difflib.SequenceMatcher.get_grouped_opcodes`` and
    ``histodiff.unified_diff`` use, reimplemented here so this script only
    needs a plain opcode list - it works the same for difflib, histodiff and
    patiencediff output.
    """
    codes = list(codes)
    if not codes:
        return []
    tag, i1, i2, j1, j2 = codes[0]
    if tag == "equal":
        codes[0] = (tag, max(i1, i2 - context), i2, max(j1, j2 - context), j2)
    tag, i1, i2, j1, j2 = codes[-1]
    if tag == "equal":
        codes[-1] = (tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context))

    groups: list[Opcodes] = []
    group: Opcodes = []
    for tag, i1, i2, j1, j2 in codes:
        if tag == "equal" and i2 - i1 > 2 * context:
            group.append((tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context)))
            groups.append(group)
            group = []
            i1, j1 = max(i1, i2 - context), max(j1, j2 - context)
        group.append((tag, i1, i2, j1, j2))
    if group and not (len(group) == 1 and group[0][0] == "equal"):
        groups.append(group)
    return groups


def hunk_count(codes: Opcodes, context: int = 3) -> int:
    return len(group_hunks(codes, context))


def best_time(fn: Callable[[], object], repeat: int) -> float:
    best = float("inf")
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def peak_memory(fn: Callable[[], object]) -> int:
    tracemalloc.start()
    try:
        fn()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def format_time(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.1f} ms" if seconds >= 0.0001 else "<0.1 ms"
    return f"{seconds:.2f} s"


def format_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} MB"  # pragma: no cover - unreachable, keeps mypy happy


# --------------------------------------------------------------------------
# Tools under comparison
# --------------------------------------------------------------------------


def _difflib_opcodes(a: Lines, b: Lines) -> Opcodes:
    return difflib.SequenceMatcher(None, a, b).get_opcodes()


def _histodiff_opcodes(algorithm: str) -> ToolFunc:
    def run(a: Lines, b: Lines) -> Opcodes:
        return [op.as_opcode() for op in histodiff.diff(a, b, algorithm)]

    return run


def _patiencediff_opcodes(a: Lines, b: Lines) -> Opcodes:
    return patiencediff.PatienceSequenceMatcher(None, a, b).get_opcodes()


TOOLS: list[tuple[str, ToolFunc]] = [
    ("difflib", _difflib_opcodes),
    ("histodiff-histogram", _histodiff_opcodes("histogram")),
    ("histodiff-patience", _histodiff_opcodes("patience")),
    ("histodiff-myers", _histodiff_opcodes("myers")),
]
if HAVE_PATIENCEDIFF:
    TOOLS.append(("patiencediff", _patiencediff_opcodes))


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@dataclass
class Scenario:
    number: int
    title: str
    note: str
    old: Lines
    new: Lines
    large: bool = False  # measure peak memory too
    extra: dict[str, ToolFunc] = field(default_factory=dict)
    epilogue: Callable[[], None] | None = None


def _lines(text: str) -> Lines:
    return text.splitlines(keepends=True)


# Twenty small, similarly-shaped validators - realistic for a generated or
# hand-written form-validation module, and large and repetitive enough
# (220 lines) to cross difflib's 200-line autojunk threshold, the same
# threshold the README's "Why" section describes.
_VALIDATED_FIELDS = [
    "email",
    "phone",
    "zip_code",
    "username",
    "password",
    "url",
    "ipv4_address",
    "hex_color",
    "credit_card",
    "ssn",
    "iban",
    "mac_address",
    "uuid",
    "isbn",
    "vin",
    "license_plate",
    "coordinates",
    "hostname",
    "port_number",
    "currency_code",
    "postal_code",
    "tax_id",
]


def _validator(name: str, max_len: int, guard: bool = False) -> str:
    out = [
        f"def validate_{name}(value):",
        '    """Validate a single form field before it is saved."""',
        "    errors = []",
    ]
    if guard:
        out += ["    if value is None:", "        return errors"]
    out += [
        "    if not value:",
        f'        errors.append("{name} is required")',
        f"    if len(str(value)) > {max_len}:",
        f'        errors.append("{name} is too long")',
        "    return errors",
        "",
        "",
    ]
    return "\n".join(out) + "\n"


def _validators_module() -> list[str]:
    return [_validator(name, 12 + i) for i, name in enumerate(_VALIDATED_FIELDS)]


def scenario_1() -> Scenario:
    funcs = _validators_module()
    old = "".join(funcs)
    # validate_username (index 3) moves to the end, unchanged.
    new = "".join(funcs[:3] + funcs[4:] + [funcs[3]])
    return Scenario(
        1,
        "A function moved to another location, unchanged",
        "The move is unambiguous, so histogram, patience and myers all agree "
        "exactly on the minimal 20-line diff, and even the external "
        "patiencediff package finds it too. difflib does not: at 220 lines, "
        "its autojunk heuristic stops anchoring on the docstring and blank "
        "lines every function shares, and its greedy longest-match search "
        "goes on to report 18x as many changed lines for the same edit.",
        _lines(old),
        _lines(new),
    )


def scenario_2() -> Scenario:
    funcs = _validators_module()
    old = "".join(funcs)
    # validate_password (index 4) moves to the end *and* gains a guard clause.
    edited = _validator("password", 12 + 4, guard=True)
    new = "".join(funcs[:4] + funcs[5:] + [edited])
    return Scenario(
        2,
        "A function moved to another location and lightly edited",
        "Same file, but the moved function also gains a guard clause. The "
        "move is still unambiguous enough that histogram, patience and myers "
        "keep agreeing (22 changed lines: the 20-line move plus the 2-line "
        "guard) - editing a block on its way past doesn't reintroduce the "
        "ambiguity that confuses difflib.",
        _lines(old),
        _lines(new),
    )


def scenario_3() -> Scenario:
    old = """\
import sys
import json
from collections import defaultdict
import os
from typing import Any, Optional
import re
from myapp.models import User, Order
import logging
from myapp.utils import slugify
import datetime
from django.db import models
from django.conf import settings
import itertools
from myapp.serializers import OrderSerializer
"""
    new = """\
import datetime
import functools
import itertools
import json
import logging
import os
import re
import sys
from collections import defaultdict
from typing import Any, Optional

from django.conf import settings
from django.db import models

from myapp.models import Order, User
from myapp.serializers import OrderSerializer
from myapp.utils import slugify
"""
    return Scenario(
        3,
        "An ad hoc import block reformatted into isort-style groups",
        "Regrouping *and* alphabetizing every line leaves almost no line in "
        "its old position, so this is a genuinely hard case for line-based "
        "diffing, not just for one algorithm: patience and myers agree "
        "exactly (21 changed lines) and difflib is close behind (23). "
        "histogram does slightly *worse* here (25) - its rarest-line-first "
        "rule happens to anchor on `import itertools`, which turns out to be "
        "a poor anchor since the block around it still needs a full rewrite "
        "either way. None of the five reads as a small, clean change; a full "
        "reshuffle like an isort pass is a real weak spot for this kind of "
        "diffing in general.",
        _lines(old),
        _lines(new),
    )


def scenario_4() -> Scenario:
    old = """\
# Widget Toolkit

A small toolkit for building and rendering UI widgets.

## Installation

Run `pip install widget-toolkit` to install the package from PyPI.

## Usage

```python
from widgets import Widget

Widget(label="Save").render()
```

## Configuration

Set the `WIDGET_THEME` environment variable to switch between the light and
dark themes. The default is `light`.

## FAQ

**Does it work offline?**
Yes, no network access is required at runtime.

**Is it thread-safe?**
Yes, as of version 2.0.

## License

Released under the MIT license.
"""
    new = """\
# Widget Toolkit

A small toolkit for building and rendering UI widgets.

## Installation

Run `pip install widget-toolkit` to install the package from PyPI.

## FAQ

**Does it work offline?**
Yes, no network access is required at runtime.

**Is it thread-safe?**
Yes, as of version 2.0.

## Usage

```python
from widgets import Widget

Widget(label="Save").render()
```

## Configuration

Set the `WIDGET_THEME` environment variable to switch between the light and
dark themes. The default is `light`.

## License

Released under the MIT license.
"""
    return Scenario(
        4,
        "A Markdown section moved earlier in the document",
        "All five tools tie here too (16 changed lines: the FAQ section "
        "deleted from one spot and inserted, unchanged, in another). At only "
        "32 lines there's nothing repeated nearby to confuse difflib's "
        "matching - a reminder that the difference this corpus keeps coming "
        "back to (scenarios 1, 2 and 6) is specifically about scale and "
        "repetition, not about moves in general.",
        _lines(old),
        _lines(new),
    )


def _yaml_services(count: int, changed_index: int, changed_replicas: int) -> str:
    out = ["services:"]
    for i in range(count):
        replicas = changed_replicas if i == changed_index else 2
        out += [
            f"  - name: svc-{i:04d}",
            f"    image: registry.example.com/svc-{i:04d}:1.4.2",
            f"    replicas: {replicas}",
            f"    port: {8000 + i}",
            "    healthcheck: /healthz",
            "",
        ]
    return "\n".join(out) + "\n"


def scenario_5(quick: bool) -> Scenario:
    count = 40 if quick else 300
    changed = count // 2
    old = _yaml_services(count, changed_index=-1, changed_replicas=2)
    new = _yaml_services(count, changed_index=changed, changed_replicas=6)
    return Scenario(
        5,
        "One field changed deep inside a large, repetitive YAML file",
        "All five tools tie here (2 changed lines: the old and new "
        "`replicas:` value), including difflib. Every service block repeats "
        "`replicas:`, `healthcheck:` and a blank line, but each block also "
        "keeps a genuinely unique `name:`/`image:`/`port:` right next to "
        "them - and that's enough for even difflib's heuristic to align "
        "correctly despite autojunk. Contrast with the next scenario, where "
        "the repeated rows have no unique content at all left for anything "
        "to anchor on.",
        _lines(old),
        _lines(new),
        large=True,
    )


def scenario_6(quick: bool) -> Scenario:
    count = 200 if quick else 4000
    anomaly_at = count // 2
    header = "timestamp,sensor_id,temperature_c,status\n"
    normal = "2024-01-01T00:00:00Z,TEMP-07,21.4,OK\n"
    anomaly = "2024-01-01T00:00:00Z,TEMP-07,86.2,ALERT\n"
    old = [header] + [normal] * count
    new = [header] + [normal] * anomaly_at + [anomaly] + [normal] * (count - anomaly_at)
    return Scenario(
        6,
        "One anomalous row inserted among thousands of identical CSV rows",
        "Every data row is byte-for-byte identical, which is exactly the "
        "case difflib's autojunk heuristic is built to give up on in files "
        "this size - it can end up treating the second half of the file as "
        "entirely replaced. Every histodiff algorithm reports the true, "
        "one-line insertion.",
        old,
        new,
        large=True,
    )


def scenario_7() -> Scenario:
    old = """\
def checkout(cart, user):
    total = cart.total()
    charge = payments.charge(user, total)
    order = Order.objects.create(user=user, total=total, charge_id=charge.id)
    send_receipt(user, order)
    return order
"""
    new = """\
def checkout(cart, user):
    total = cart.total()
    if feature_enabled("new_checkout_flow"):
        charge = payments.charge(user, total)
        order = Order.objects.create(user=user, total=total, charge_id=charge.id)
        send_receipt(user, order)
        return order
    return legacy_checkout(cart, user)
"""

    def show_whitespace_key() -> None:
        print()
        print(
            "Bonus row above: adding key=ignore_space_change (the -b flag) "
            "on top of histogram collapses the diff further, since it stops "
            "counting the re-indentation itself as a change - see 'Ignoring "
            "whitespace' in the README."
        )

    return Scenario(
        7,
        "An existing code block wrapped in a new conditional",
        "Every line in the wrapped block is now indented one level deeper, "
        "which is literally different text, so all five tools (correctly) "
        "mark all four lines as changed - alignment doesn't help when the "
        "*content* really did change on every line. What does help is "
        "comparing lines a different way: the bonus row below reruns "
        "histogram with a whitespace-insensitive key (`-b`) and narrows the "
        "diff to just the genuinely new `if`/`return` lines.",
        _lines(old),
        _lines(new),
        extra={
            "histogram + ignore_space_change (-b)": lambda a, b: [
                op.as_opcode()
                for op in histodiff.diff(
                    a, b, "histogram", key=histodiff.ignore_space_change
                )
            ],
        },
        epilogue=show_whitespace_key,
    )


def scenario_8() -> Scenario:
    count = 25
    anomaly_at = count // 2

    def record(i: int, level: str = "INFO", msg: str = "heartbeat") -> str:
        return (
            f'{{"ts": "2024-01-01T00:{i // 60 % 60:02d}:{i % 60:02d}Z", '
            f'"level": "{level}", "service": "billing", "msg": "{msg}", '
            f'"id": {i}}}\n'
        )

    old = [record(i) for i in range(count)]
    new = list(old)
    new[anomaly_at] = record(anomaly_at, "ERROR", "payment gateway timeout")

    def show_highlight() -> None:
        old_line = old[anomaly_at].rstrip("\n")
        new_line = new[anomaly_at].rstrip("\n")
        highlighted = histodiff.highlight_words([old_line], [new_line])
        print()
        print(
            "Every record carries its own timestamp and id, so all five "
            "tools already agree on which single line changed - there is no "
            "alignment problem to solve here. What histodiff adds on top is "
            "word-level highlighting *inside* that line (its --color/--html "
            "output; shown here as [brackets] instead of color):"
        )
        if highlighted is None:
            print("  (lines too different to highlight)")
            return
        old_segments, new_segments = highlighted

        def render(segments: list[tuple[str, bool]]) -> str:
            return "".join(
                f"[{text}]" if changed else text for text, changed in segments
            )

        print("  - " + render(old_segments[0]))
        print("  + " + render(new_segments[0]))

    return Scenario(
        8,
        "Generated-looking records with one meaningful change",
        "Every line is already unique (its own timestamp/id), so this is a "
        "control case: expect every tool to report the same one-line "
        "change. The follow-up below shows where the real value is instead - "
        "word-level highlighting inside that line.",
        old,
        new,
        epilogue=show_highlight,
    )


def _inventory_module(n: int) -> Lines:
    out = ['"""Inventory management helpers."""', "", "import datetime", ""]
    for i in range(n):
        out += [
            f"def restock_item_{i}(sku, quantity):",
            f'    """Restock SKU {i:05d} by `quantity` units."""',
            "    record = InventoryRecord(sku=sku, quantity=quantity, "
            "at=datetime.datetime.utcnow())",
            "    ledger.append(record)",
            "    return record",
            "",
        ]
    return [line + "\n" for line in out]


def _forecast_module(n: int) -> Lines:
    out = ['"""Weather forecasting helpers."""', "", "import datetime", ""]
    for i in range(n):
        out += [
            f"def forecast_region_{i}(latitude, longitude):",
            f'    """Forecast conditions for region {i:05d}."""',
            "    sample = WeatherModel.sample(latitude, longitude, "
            "at=datetime.datetime.utcnow())",
            "    cache.store(sample)",
            "    return sample",
            "",
        ]
    return [line + "\n" for line in out]


def scenario_9(quick: bool) -> Scenario:
    n = 20 if quick else 400
    return Scenario(
        9,
        "Two files with almost nothing in common",
        "Sharing only a docstring shape, `import datetime` and blank lines, "
        "this is the pathological case for any alignment algorithm - see "
        "'Unrelated files' in the README's Performance section for how it "
        "scales. No algorithm can find structure that isn't there, but they "
        "don't all fail identically: difflib and patiencediff report almost "
        "the entire file changed (~4,800 lines) in well under a "
        "millisecond, while histodiff's three algorithms take noticeably "
        "longer (still well under a second at this size) to find a little "
        "genuine overlap - a handful of shared blank lines and the "
        "`import datetime` line - and report about 16% fewer changed lines "
        "for it. For a file this unrelated, that speed difference is the "
        "more important number; see 'Unrelated files' in the Performance "
        "section for how it scales and how `minimal=True` trades more of it "
        "for a slightly smaller diff.",
        _inventory_module(n),
        _forecast_module(n),
        large=True,
    )


def scenario_10() -> Scenario:
    old = """\
# settings.py
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
SECRET_KEY = "dev-secret-key"
DATABASE_URL = "sqlite:///db.sqlite3"
CACHE_BACKEND = "locmem"
LOG_LEVEL = "DEBUG"
"""
    new = """\
# settings.py
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
SECRET_KEY = "dev-secret-key"
DATABASE_URL = "sqlite:///db.sqlite3"
CACHE_BACKEND = "locmem"
LOG_LEVEL = "DEBUG"
"""
    return Scenario(
        10,
        "A single, unambiguous one-line change (difflib is already fine)",
        "Nothing moved and nothing repeats: there is exactly one place the "
        "two files can be aligned. Expect every tool, including plain "
        "difflib, to report the identical, minimal diff - there's nothing "
        "for a smarter alignment to improve on, so the stdlib tool you "
        "already have is the pragmatic choice for changes shaped like this "
        "one.",
        _lines(old),
        _lines(new),
    )


# --------------------------------------------------------------------------
# Running and reporting
# --------------------------------------------------------------------------


def run_tool(
    name: str, fn: ToolFunc, old: Lines, new: Lines, repeat: int, memory: bool
) -> dict[str, object]:
    try:
        codes = fn(old, new)
    except Exception as exc:  # noqa: BLE001 - an external tool guard, not our code
        return {"name": name, "error": f"{type(exc).__name__}: {exc}"}
    result: dict[str, object] = {
        "name": name,
        "changed": changed_lines(codes),
        "hunks": hunk_count(codes),
        "time": best_time(lambda: fn(old, new), repeat),
    }
    if memory:
        result["memory"] = peak_memory(lambda: fn(old, new))
    return result


def print_scenario(scenario: Scenario, repeat: int) -> list[dict[str, object]]:
    print(f"\n{RULE}")
    print(f"{scenario.number}. {scenario.title}")
    print(f"   ({len(scenario.old):,} -> {len(scenario.new):,} lines)")
    print(RULE)
    print(scenario.note)
    print()

    rows = [
        run_tool(name, fn, scenario.old, scenario.new, repeat, scenario.large)
        for name, fn in TOOLS
    ]
    rows += [
        run_tool(name, fn, scenario.old, scenario.new, repeat, False)
        for name, fn in scenario.extra.items()
    ]

    name_width = max(len(str(r["name"])) for r in rows)
    time_header = f"time (best of {repeat})"
    header = f"{'tool':<{name_width}}  {'changed':>7}  {'hunks':>5}  {time_header:>18}"
    if scenario.large:
        header += f"  {'peak memory':>12}"
    print(header)
    print("-" * len(header))
    for r in rows:
        if "error" in r:
            print(
                f"{r['name']:<{name_width}}  {'n/a':>7}  {'':>5}  "
                f"{str(r['error'])[:18]:>18}"
            )
            continue
        line = (
            f"{r['name']:<{name_width}}  {r['changed']:>7}  {r['hunks']:>5}  "
            f"{format_time(r['time']):>18}"
        )  # type: ignore[arg-type]
        if scenario.large:
            line += f"  {format_bytes(r['memory']):>12}"  # type: ignore[arg-type]
        print(line)

    if scenario.epilogue is not None:
        scenario.epilogue()
    return rows


def print_summary(
    scenarios: list[Scenario], all_rows: list[list[dict[str, object]]]
) -> None:
    print(f"\n{RULE}")
    print("Summary: which tool(s) reported the fewest changed lines per scenario")
    print("(not an overall ranking - see each scenario's note for why)")
    print(RULE)
    for scenario, rows in zip(scenarios, all_rows):
        ok = [r for r in rows if "error" not in r]
        if not ok:
            continue
        best = min(r["changed"] for r in ok)  # type: ignore[type-var]
        winners = ", ".join(str(r["name"]) for r in ok if r["changed"] == best)
        title = (
            scenario.title if len(scenario.title) <= 52 else scenario.title[:51] + "…"
        )
        print(f"{scenario.number:>2}. {title:<53} {winners}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repeat",
        type=int,
        default=5,
        help="timing samples per tool, best kept (default: 5)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="shrink the large scenarios, for a fast smoke test",
    )
    args = parser.parse_args()

    if not HAVE_PATIENCEDIFF:
        print(
            "(patiencediff is not installed, so that column is left out. "
            "`pip install patiencediff` to add it - it's optional, not a "
            "histodiff dependency.)\n"
        )

    scenarios = [
        scenario_1(),
        scenario_2(),
        scenario_3(),
        scenario_4(),
        scenario_5(args.quick),
        scenario_6(args.quick),
        scenario_7(),
        scenario_8(),
        scenario_9(args.quick),
        scenario_10(),
    ]
    all_rows = [print_scenario(s, args.repeat) for s in scenarios]
    print_summary(scenarios, all_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
