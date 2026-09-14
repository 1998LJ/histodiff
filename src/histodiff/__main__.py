"""Allow ``python -m histodiff``.

Exercised by tests/test_cli.py::test_python_dash_m via a real subprocess
(``python -m histodiff ...``). coverage.py only instruments the process
running pytest, so it can't see that subprocess's execution of this module;
it's omitted from coverage reporting entirely (see pyproject.toml) rather
than left showing as permanently, misleadingly untested.
"""

import sys

from .cli import main

sys.exit(main())
