"""Single-source version derivation.

``pyproject.toml``'s ``[project] version`` is the one definition of this
package's version. Any second copy of that string — a ``__version__``
literal, a README line, a ``--version`` banner — is correct on the day it is
typed and wrong from the next release onward, so it is derived here instead
of restated.

``tests/test_docs_consistency.py`` asserts that every route to the version
agrees, and rejects any re-introduced ``__version__ = "..."`` literal.
"""

from __future__ import annotations

import pathlib
import re
from importlib.metadata import PackageNotFoundError, version

_UNKNOWN = "0+unknown"


def read_version() -> str:
    """Return the distribution version, preferring installed metadata."""
    try:
        return version("provably")
    except PackageNotFoundError:
        pass

    # Source checkout that was never installed: read the manifest directly.
    manifest = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return _UNKNOWN
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else _UNKNOWN
