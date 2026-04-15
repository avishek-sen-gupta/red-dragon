# pyright: standard
"""Feature coverage audit — reports which language features lack test coverage.

Discovers per-language feature enums from interpreter/frontends/*/features.py,
scans all test files for @covers(...) annotations, and reports which enum
members have no associated test.

Usage:
    poetry run python scripts/feature_coverage_audit.py
    poetry run python scripts/feature_coverage_audit.py --output results.json
    poetry run python scripts/feature_coverage_audit.py --language java

With no --output flag: JSON to stdout, summary to stderr.
With --output FILE: JSON to file, summary to stdout.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureRef:
    """A (EnumClassName, MEMBER_NAME) pair extracted from a @covers decorator."""

    enum_class_name: str
    member_name: str


@dataclass(frozen=True)
class FeatureModule:
    """A discovered per-language feature enum loaded from features.py."""

    language: str
    enum_class_name: str
    all_members: frozenset[str]


@dataclass(frozen=True)
class LanguageCoverageResult:
    language: str
    total_features: int
    covered_count: int
    uncovered_count: int
    covered: list[str]
    uncovered: list[str]


# ---------------------------------------------------------------------------
# Feature module discovery
# ---------------------------------------------------------------------------


def _enum_classes_in_module(module: object, module_path: str) -> list[type[Enum]]:
    """Return Enum subclasses defined directly in this module (not imported ones)."""
    return [
        obj
        for obj in vars(module).values()  # type: ignore[arg-type]
        if isinstance(obj, type)
        and issubclass(obj, Enum)
        and obj.__module__ == module_path
    ]


def _load_feature_module(path: Path) -> FeatureModule:
    """Load a FeatureModule from an interpreter/frontends/<lang>/features.py file."""
    language = path.parent.name
    module_path = f"interpreter.frontends.{language}.features"
    module = importlib.import_module(module_path)
    enum_classes = _enum_classes_in_module(module, module_path)
    if not enum_classes:
        raise ValueError(f"No Enum subclass found in {module_path}")
    enum_class = enum_classes[0]
    return FeatureModule(
        language=language,
        enum_class_name=enum_class.__name__,
        all_members=frozenset(m.name for m in enum_class),
    )


def discover_feature_modules(project_root: Path) -> tuple[FeatureModule, ...]:
    """Return all FeatureModules found under interpreter/frontends/*/features.py."""
    feature_paths = sorted(project_root.glob("interpreter/frontends/*/features.py"))
    return tuple(_load_feature_module(path) for path in feature_paths)


# ---------------------------------------------------------------------------
# Test file scanning
# ---------------------------------------------------------------------------


def _covers_refs_in_file(path: Path) -> frozenset[FeatureRef]:
    """Return all FeatureRefs found in @covers(...) decorators in a test file."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return frozenset(
        FeatureRef(enum_class_name=arg.value.id, member_name=arg.attr)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for dec in node.decorator_list
        if isinstance(dec, ast.Call)
        and isinstance(dec.func, ast.Name)
        and dec.func.id == "covers"
        for arg in dec.args
        if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name)
    )


def scan_test_dirs(test_dirs: Sequence[Path]) -> frozenset[FeatureRef]:
    """Scan all test_*.py files in the given directories and return all FeatureRefs."""
    return frozenset(
        ref
        for test_dir in test_dirs
        for path in sorted(test_dir.rglob("test_*.py"))
        for ref in _covers_refs_in_file(path)
    )


# ---------------------------------------------------------------------------
# Coverage computation
# ---------------------------------------------------------------------------


def audit_language(
    module: FeatureModule, all_refs: frozenset[FeatureRef]
) -> LanguageCoverageResult:
    """Compute coverage for one language against the collected FeatureRefs."""
    covered_members = frozenset(
        ref.member_name
        for ref in all_refs
        if ref.enum_class_name == module.enum_class_name
    )
    covered = sorted(module.all_members & covered_members)
    uncovered = sorted(module.all_members - covered_members)
    return LanguageCoverageResult(
        language=module.language,
        total_features=len(module.all_members),
        covered_count=len(covered),
        uncovered_count=len(uncovered),
        covered=covered,
        uncovered=uncovered,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def build_json(results: Sequence[LanguageCoverageResult]) -> dict[str, object]:
    """Build the full JSON output structure."""
    languages_json = {
        r.language: {
            "total_features": r.total_features,
            "covered_count": r.covered_count,
            "uncovered_count": r.uncovered_count,
            "covered": r.covered,
            "uncovered": r.uncovered,
        }
        for r in results
    }
    total_uncovered = sum(r.uncovered_count for r in results)
    languages_with_gaps = [r.language for r in results if r.uncovered_count > 0]
    return {
        "generated": str(date.today()),
        "languages": languages_json,
        "summary": {
            "total_uncovered": total_uncovered,
            "languages_with_gaps": languages_with_gaps,
        },
    }


def _print_language_row(
    result: LanguageCoverageResult, col_width: int, output_stream: object
) -> None:
    label = f"{result.language:<{col_width}}"
    print(
        f"  {label}: {result.covered_count:3d} / {result.total_features:3d} covered"
        f"  ({result.uncovered_count} uncovered)",
        file=output_stream,
    )
    for feature in result.uncovered:
        print(f"    - {feature}", file=output_stream)


def print_summary(
    results: Sequence[LanguageCoverageResult], output_stream: object
) -> None:
    """Print a human-readable coverage summary table."""
    if not results:
        print("  No feature modules found.", file=output_stream)
        return
    col_width = max(len(r.language) for r in results) + 2
    for r in results:
        _print_language_row(r, col_width, output_stream)

    total_uncovered = sum(r.uncovered_count for r in results)
    print("  " + "─" * 50, file=output_stream)
    n = len(results)
    print(
        f"  TOTAL: {total_uncovered} uncovered features across {n} languages",
        file=output_stream,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Feature coverage audit for RedDragon language frontends."
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write JSON to FILE instead of stdout (summary then goes to stdout).",
    )
    parser.add_argument(
        "--language",
        metavar="LANG",
        help="Audit only this language (e.g. java, go).",
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    test_dirs = (
        project_root / "tests" / "unit",
        project_root / "tests" / "integration",
    )

    sys.stderr.write("Scanning test files for @covers annotations...\n")
    all_refs = scan_test_dirs(test_dirs)

    sys.stderr.write("Discovering feature modules...\n")
    modules = discover_feature_modules(project_root)

    filtered = (
        tuple(m for m in modules if m.language == args.language)
        if args.language
        else modules
    )

    results = [audit_language(m, all_refs) for m in filtered]

    payload = build_json(results)
    json_text = json.dumps(payload, indent=2)

    summary_stream = sys.stdout if args.output else sys.stderr
    if args.output:
        with open(args.output, "w") as f:
            f.write(json_text + "\n")
    else:
        sys.stdout.write(json_text + "\n")

    print_summary(results, summary_stream)


if __name__ == "__main__":
    main()
