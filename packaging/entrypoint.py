"""PyInstaller entry script.

A frozen entry script runs as ``__main__`` with no package context, so a module
full of relative imports cannot be the entry point directly — ``from .packaging
import ...`` raises "attempted relative import with no known parent package"
before anything else happens. This file exists only to import the real module
by its absolute name, which restores the package context.

Keep it dependency-free and keep the logic in ``dynamic_pricing.runner``, which
is importable and testable from a checkout.
"""

import multiprocessing
import sys

if __name__ == "__main__":
    # PyInstaller re-executes the binary to create a child process; without
    # this a --onefile build can spawn copies of itself instead.
    multiprocessing.freeze_support()

    from dynamic_pricing.runner import main

    sys.exit(main())
