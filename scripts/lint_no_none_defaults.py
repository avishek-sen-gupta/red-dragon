#!/usr/bin/env python3
"""Flag `= None` parameter defaults, per .claude/conditional/design-principles.md:

    No `None` as a default parameter. Use empty structures (`{}`, `[]`, `()`).
    No `None` returns from non-None return types. Use null object pattern.

A parameter default of literal `None` is flagged regardless of its type
annotation. This is a mechanical check, not a style opinion: the project has
already decided the convention, this just catches drift from it.

Usage: poetry run python scripts/lint_no_none_defaults.py <path> [<path> ...]
Exit code 1 if any violation is found (0 otherwise), for CI/pre-commit use.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _is_none_constant(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _find_violations(tree: ast.Module, filename: str) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args

        positional = args.posonlyargs + args.args
        defaults = args.defaults
        # `defaults` aligns to the tail of `positional`.
        offset = len(positional) - len(defaults)
        for param, default in zip(positional[offset:], defaults):
            if _is_none_constant(default):
                violations.append(
                    f"{filename}:{node.lineno}: {node.name}({param.arg}=None)"
                )

        for param, default in zip(args.kwonlyargs, args.kw_defaults):
            # kw_defaults entries are the literal Python None (no default at
            # all) when the kwonly arg is required — distinct from an
            # ast.Constant(value=None) default, which is what we're after.
            if default is not None and _is_none_constant(default):
                violations.append(
                    f"{filename}:{node.lineno}: {node.name}({param.arg}=None)"
                )

    return violations


def main(paths: list[str]) -> int:
    all_violations: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        tree = ast.parse(path.read_text(), filename=str(path))
        all_violations.extend(_find_violations(tree, str(path)))

    for v in all_violations:
        print(v)

    if all_violations:
        print(f"\n{len(all_violations)} violation(s) found.")
        return 1
    print("No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
