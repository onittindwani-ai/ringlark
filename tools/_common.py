"""Shared bits for the tools: put the API source and the shared core package on the path, so `python3 tools/hash_password.py` works on a fresh clone
before `make install` has put the packages in a virtual environment. The libraries they need (argon2, pydantic, sqlalchemy) still have to be installed:
the tools say so in one line, with the command that uses the project's own environment, instead of a traceback."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "core-py" / "src"))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
sys.path.insert(0, str(ROOT))


def need_libraries(exc: ImportError) -> SystemExit:
    """What to tell someone whose plain python lacks the libraries: use the virtual environment that `make install` made (or install, then try again)."""
    return SystemExit(f"A library is missing ({exc.name}). Use the project's own Python: .venv/bin/python {Path(sys.argv[0]).as_posix()}  (run `make install` first if there is no .venv folder).")
