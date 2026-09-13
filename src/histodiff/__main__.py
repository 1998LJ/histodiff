"""Allow ``python -m histodiff``."""

import sys

from .cli import main

sys.exit(main())
