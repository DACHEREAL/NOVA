#!/usr/bin/env python3
"""Convenience top-level launcher for N.O.V.A.

Usage:
    python3 run.py status
    python3 run.py inspect
    python3 run.py run "arrange windows side by side"
    python3 run.py test
"""

import os
import sys

# Ensure current directory is at the front of sys.path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if len(sys.argv) > 1 and sys.argv[1] == "test":
    import importlib.util
    import unittest

    test_file_path = os.path.join(BASE_DIR, "tests", "run_tests.py")
    spec = importlib.util.spec_from_file_location("nova_test_module", test_file_path)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        suite = unittest.TestLoader().loadTestsFromTestCase(mod.TestNovaCore)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)

from nova.cli import main

if __name__ == "__main__":
    main()
