"""Device connection details, taken from the environment and nowhere else.

No defaults: a credential with a default is a credential in the repository, and
this repository is the input to the packaging pipeline. Export them before
running any script in this directory:

    PRINT_HOST=10.0.0.10 PRINT_PORT=22 PRINT_USER=admin PRINT_PASS=... \
        python _ops/_deploy.py
"""

import os


def setting(name):
    """Return an environment variable, or stop with an explanation."""
    value = os.environ.get(name)
    if value:
        return value
    raise SystemExit(
        "%s is not set. Export PRINT_HOST / PRINT_PORT / PRINT_USER / PRINT_PASS "
        "before running this script." % name
    )
