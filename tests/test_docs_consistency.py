"""Documentation-vs-code consistency gate.

Every value in this repository's prose that must track a fact about the code is
asserted here against its single definition. A hand-typed value duplicating a
system fact is correct the day it is written and wrong forever after; these
tests turn that silent drift into a failing test.

Covered:
  * package version — ``pyproject.toml`` is the single definition, and
    ``provably.__version__`` / installed distribution metadata must agree;
  * the bounded-loop unroll limit ``provably.translator._MAX_UNROLL`` vs every
    place the README and docs state the number;
  * the SOTA bench sidecar path (``scripts/sota_bench.py::SIDECAR_PATH``) vs
    the README;
  * ``requires-python`` vs the Python versions the README and docs claim;
  * that every relative Markdown link in the README and docs resolves;
  * that ``mkdocs.yml``'s nav points at files that exist.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
README = REPO_ROOT / "README.md"
DOCS_DIR = REPO_ROOT / "docs"
SOTA_BENCH = REPO_ROOT / "scripts" / "sota_bench.py"


def _manifest() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _markdown_docs() -> list[Path]:
    docs = [README]
    if DOCS_DIR.is_dir():
        docs.extend(sorted(DOCS_DIR.rglob("*.md")))
    return [d for d in docs if d.is_file()]


def _relative_links(text: str) -> list[str]:
    """Relative link targets from Markdown ``[text](target)`` pairs."""
    out = []
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if target.startswith(("http://", "https://", "mailto:", "#", "<")):
            continue
        out.append(target.split("#", 1)[0])
    return [t for t in out if t]


# ---------------------------------------------------------------------------
# Version — pyproject.toml is the single definition
# ---------------------------------------------------------------------------


def test_dunder_version_is_derived_not_transcribed() -> None:
    """``provably.__version__`` must equal the manifest, however it is obtained.

    The constant used to be a literal ``__version__ = "0.4.0"`` beside a
    ``version = "0.4.0"`` in pyproject.toml — two copies of one fact.
    """
    import provably

    assert provably.__version__ == _manifest()["project"]["version"], (
        "provably.__version__ disagrees with pyproject.toml [project] version. "
        "pyproject.toml is the single definition; __version__ derives from it "
        "via importlib.metadata."
    )


def test_installed_distribution_metadata_matches_manifest() -> None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        installed = version("provably")
    except PackageNotFoundError:
        pytest.skip("provably is not installed in this environment")
    assert installed == _manifest()["project"]["version"], (
        "installed distribution metadata is stale relative to pyproject.toml; "
        "reinstall the package (`uv sync`) so the derived __version__ is right"
    )


def test_source_carries_no_second_version_literal() -> None:
    """No module may hardcode the release version string again.

    Checked over the parsed AST, not the raw text, so prose about the rule
    (docstrings, comments) is not mistaken for a violation of it.
    """
    declared = _manifest()["project"]["version"]
    offenders = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            if "__version__" not in names:
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                    f"__version__ = {node.value.value!r}"
                )
    assert not offenders, (
        "a literal __version__ assignment reappeared; the version "
        f"({declared}) must be derived from distribution metadata, not typed:\n"
        + "\n".join(offenders)
    )


def test_changelog_documents_the_current_version() -> None:
    declared = _manifest()["project"]["version"]
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"(?m)^##\s+\[?([0-9][^\s\]]*)", changelog)
    assert declared in headings, (
        f"CHANGELOG.md has no section for the current version {declared}; "
        f"found sections: {headings[:5]}"
    )


# ---------------------------------------------------------------------------
# Unroll limit — provably.translator._MAX_UNROLL is the single definition
# ---------------------------------------------------------------------------


def _documented_unroll_numbers(text: str) -> list[int]:
    """Numbers the prose attaches to the unroll bound."""
    patterns = [
        r"unrolled \(up to (\d+) iterations\)",
        r"unrolled up to (\d+) iterations",
        r"max (\d+) iterations",
        r"max is (\d+)",
        r"literal N, max (\d+)",
    ]
    found: list[int] = []
    for pattern in patterns:
        found.extend(int(m) for m in re.findall(pattern, text))
    return found


def test_documented_unroll_limit_matches_translator_constant() -> None:
    from provably.translator import _MAX_UNROLL

    checked = 0
    for doc in _markdown_docs():
        for value in _documented_unroll_numbers(doc.read_text(encoding="utf-8")):
            checked += 1
            assert value == _MAX_UNROLL, (
                f"{doc.relative_to(REPO_ROOT)} states an unroll bound of {value}, "
                f"but provably.translator._MAX_UNROLL is {_MAX_UNROLL}. "
                "The constant is the single definition."
            )
    assert checked >= 3, (
        "expected the unroll bound to be documented in several places; only "
        f"{checked} mentions matched the known phrasings — this test has "
        "probably stopped seeing the docs it is supposed to guard"
    )


# ---------------------------------------------------------------------------
# Bench sidecar path — scripts/sota_bench.py is the single definition
# ---------------------------------------------------------------------------


def _sidecar_path_from_script() -> str:
    match = re.search(
        r'(?m)^SIDECAR_PATH\s*=\s*Path\("([^"]+)"\)', SOTA_BENCH.read_text(encoding="utf-8")
    )
    assert match is not None, (
        "scripts/sota_bench.py must define SIDECAR_PATH as the single "
        "definition of the benchmark sidecar path"
    )
    return match.group(1)


def test_readme_bench_path_matches_the_script() -> None:
    canonical = _sidecar_path_from_script()
    mentioned = re.findall(r"/tmp/[\w.-]+\.json", README.read_text(encoding="utf-8"))
    assert mentioned, "README documents `make bench`; it should name the sidecar it writes"
    for path in mentioned:
        assert path == canonical, (
            f"README names bench artifact {path}, but scripts/sota_bench.py "
            f"writes {canonical}."
        )


def test_script_has_exactly_one_sidecar_path_literal() -> None:
    source = SOTA_BENCH.read_text(encoding="utf-8")
    literals = re.findall(r'"(/tmp/kagami-provably[\w.-]*\.json)"', source)
    assert len(literals) == 1, (
        "scripts/sota_bench.py should spell the sidecar path exactly once "
        f"(in SIDECAR_PATH); found {len(literals)}: {literals}"
    )


# ---------------------------------------------------------------------------
# Python version support — pyproject.toml is the single definition
# ---------------------------------------------------------------------------


def test_documented_python_floor_matches_requires_python() -> None:
    project = _manifest()["project"]
    floor = re.search(r"(\d+\.\d+)", project["requires-python"])
    assert floor is not None
    minimum = floor.group(1)

    for doc in _markdown_docs():
        text = doc.read_text(encoding="utf-8")
        for claimed in re.findall(r"Python (\d+\.\d+)\+", text):
            assert claimed == minimum, (
                f"{doc.relative_to(REPO_ROOT)} claims Python {claimed}+, but "
                f"pyproject.toml requires-python is {project['requires-python']}"
            )


def test_classifiers_cover_every_supported_python() -> None:
    """Trove classifiers are a hand-maintained list; check them against the floor."""
    project = _manifest()["project"]
    classified = sorted(
        c.rsplit(" :: ", 1)[1]
        for c in project["classifiers"]
        if c.startswith("Programming Language :: Python :: ") and "." in c
    )
    minimum = re.search(r"(\d+)\.(\d+)", project["requires-python"])
    assert minimum is not None
    lowest = f"{minimum.group(1)}.{minimum.group(2)}"
    assert classified, "expected per-minor Python classifiers"
    assert classified[0] == lowest, (
        f"lowest Python classifier is {classified[0]} but requires-python floor "
        f"is {lowest}; the two lists disagree"
    )
    # The classifier list must be contiguous — a gap means a hand edit went wrong.
    minors = [int(v.split(".")[1]) for v in classified]
    assert minors == list(range(minors[0], minors[0] + len(minors))), (
        f"Python classifiers are not contiguous: {classified}"
    )


# ---------------------------------------------------------------------------
# Link and nav integrity
# ---------------------------------------------------------------------------


def test_relative_markdown_links_resolve() -> None:
    broken = []
    for doc in _markdown_docs():
        for target in _relative_links(doc.read_text(encoding="utf-8")):
            if (doc.parent / target).exists():
                continue
            # mkdocs docs link between pages by URL path, not file path.
            if DOCS_DIR in doc.parents and (DOCS_DIR / target.lstrip("/")).exists():
                continue
            broken.append(f"{doc.relative_to(REPO_ROOT)} -> {target}")
    assert not broken, "relative links that do not resolve:\n" + "\n".join(broken)


# ---------------------------------------------------------------------------
# Capability table — the README's claims are executed, not trusted
# ---------------------------------------------------------------------------


def test_readme_capability_table_rows_are_executable_claims() -> None:
    """Each 'Yes' row below is proved by actually running the construct.

    The README table previously listed `list` as unsupported and omitted
    membership tests and comprehensions entirely, while both verified
    end-to-end. A capability table nobody executes is a claim nobody checks.
    """
    from provably import verified

    @verified(
        pre=lambda x: (x >= 0) & (x <= 3),
        post=lambda x, result: (result >= 0) & (result <= 1),
    )
    def membership(x: int) -> int:
        return 1 if x in [0, 1, 2, 3] else 0

    @verified(post=lambda result: result == 0)
    def comprehension() -> int:
        return sum([i * 0 for i in range(3)])

    @verified(post=lambda x, result: result >= 0)
    def ternary(x: int) -> int:
        return x if x >= 0 else -x

    claims = {
        "`x in [...]` / `x not in [...]` over a list literal": membership,
        "List comprehensions over `range(N)` inside `sum`/`any`/`all`": comprehension,
        "`if`/`elif`/`else`/ternary": ternary,
    }
    readme = README.read_text(encoding="utf-8")
    for row, fn in claims.items():
        assert row in readme, (
            f"README capability table lost the row {row!r}, but the construct "
            "still verifies — the table understates the library."
        )
        assert fn.__proof__.verified, (
            f"README claims {row!r} is supported, but the construct did not "
            f"verify (status={fn.__proof__.status})."
        )


def test_mkdocs_nav_targets_exist() -> None:
    mkdocs = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    nav = mkdocs.split("\nnav:", 1)
    assert len(nav) == 2, "mkdocs.yml should declare a nav section"
    missing = [
        target
        for target in re.findall(r":\s+([\w./-]+\.md)\s*$", nav[1], flags=re.MULTILINE)
        if not (DOCS_DIR / target).exists()
    ]
    assert not missing, f"mkdocs.yml nav points at missing files: {missing}"
