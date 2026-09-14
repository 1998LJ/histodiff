#!/usr/bin/env python3
"""Verify the artifacts in dist/ before they're installed or published.

Checks, in order:

* Exactly one wheel and one sdist are present.
* Their version numbers agree with each other and with
  ``src/histodiff/__init__.py``'s ``__version__`` - derived from the actual
  filenames and source, never a hard-coded version number, so this keeps
  working release after release without being edited.
* The wheel contains ``histodiff/py.typed`` and a ``LICENSE`` file.
* ``python -m twine check --strict`` passes for both artifacts.

Used by CI and the release workflows (see .github/workflows/); run it
yourself after ``python -m build``::

    python scripts/verify_dist.py
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    dist = ROOT / "dist"
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1:
        fail(f"expected exactly one wheel in dist/, found {[w.name for w in wheels]}")
    if len(sdists) != 1:
        fail(f"expected exactly one sdist in dist/, found {[s.name for s in sdists]}")
    wheel, sdist = wheels[0], sdists[0]
    print(f"wheel: {wheel.name}")
    print(f"sdist: {sdist.name}")

    init_py = (ROOT / "src" / "histodiff" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init_py)
    if not match:
        fail("couldn't find __version__ in src/histodiff/__init__.py")
    src_version = match.group(1)  # type: ignore[union-attr]

    # Wheel filenames are "{name}-{version}-{python tag}-{abi tag}-{platform
    # tag}.whl" (PEP 427); the project name has no hyphens, so the version is
    # always the second field.
    wheel_version = wheel.name.split("-")[1]
    # Sdist filenames are "{name}-{version}.tar.gz" (PEP 625).
    sdist_version = sdist.name.removesuffix(".tar.gz").rsplit("-", 1)[1]

    versions = {
        "src/histodiff/__init__.py": src_version,
        "wheel filename": wheel_version,
        "sdist filename": sdist_version,
    }
    if len(set(versions.values())) != 1:
        fail(f"version mismatch across build outputs: {versions}")
    print(f"version {src_version!r} consistent across: {', '.join(versions)}")

    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    if "histodiff/py.typed" not in names:
        fail(f"histodiff/py.typed missing from the wheel; wheel contains: {names}")
    if not any(name.endswith(("licenses/LICENSE", "/LICENSE")) for name in names):
        fail(f"LICENSE missing from the wheel's dist-info; wheel contains: {names}")
    print("py.typed and a LICENSE file are both present in the wheel")

    result = subprocess.run(
        [sys.executable, "-m", "twine", "check", "--strict", str(wheel), str(sdist)],
        check=False,
    )
    if result.returncode != 0:
        fail("twine check failed (see output above)")
    print("twine check passed for both artifacts")

    print("\nAll distribution checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
