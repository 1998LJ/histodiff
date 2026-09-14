#!/usr/bin/env bash
# Install a single built artifact (a wheel or an sdist) into a brand-new
# virtualenv and smoke-test it, running entirely outside the source tree so
# nothing can accidentally succeed by importing the checkout instead of the
# installed package.
#
# Usage: scripts/smoke_test_install.sh dist/histodiff-*.whl
#        scripts/smoke_test_install.sh dist/histodiff-*.tar.gz
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: $0 <path to a wheel or sdist>" >&2
    exit 2
fi

# Resolve to an absolute path before any `cd`.
artifact_dir="$(cd "$(dirname "$1")" && pwd)"
artifact="$artifact_dir/$(basename "$1")"
if [ ! -f "$artifact" ]; then
    echo "no such file: $artifact" >&2
    exit 2
fi

venv="$(mktemp -d)/venv"
workdir="$(mktemp -d)"

python3 -m venv "$venv"
if [ -x "$venv/bin/python" ]; then
    bin="$venv/bin"
else
    bin="$venv/Scripts" # Windows venvs use Scripts/, not bin/
fi

"$bin/python" -m pip install --quiet --upgrade pip
"$bin/python" -m pip install --quiet "$artifact"

cd "$workdir"
printf 'line one\nline two\nline three\n' >old.txt
printf 'line one\nline TWO\nline three\nline four\n' >new.txt

echo "== import + __version__ matches installed metadata =="
"$bin/python" -c "
import importlib.metadata as m
import histodiff
installed = m.version('histodiff')
assert histodiff.__version__ == installed, (histodiff.__version__, installed)
print(histodiff.__version__)
"

echo "== histodiff --version =="
"$bin/histodiff" --version

echo "== git-histodiff --version =="
"$bin/git-histodiff" --version

echo "== histodiff old.txt new.txt (expects a real diff: exit 1) =="
set +e
"$bin/histodiff" old.txt new.txt
status=$?
set -e
if [ "$status" -ne 1 ]; then
    echo "expected exit status 1, got $status" >&2
    exit 1
fi

echo
echo "OK: $artifact installs and runs correctly from $workdir"
