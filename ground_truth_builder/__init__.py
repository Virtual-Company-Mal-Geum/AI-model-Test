"""Build conservative, auditable HTML text for GEO-model training."""

import sys


if sys.version_info < (3, 10):
    raise RuntimeError(
        "GEO-project requires Python 3.10 or newer. "
        "Create a new virtual environment with Python 3.11, then reinstall requirements."
    )
