#!/usr/bin/env python3
# pyright: standard
"""covers-guard — PreToolUse hook that rejects test writes missing @covers decorators.

Reads Claude tool input JSON from stdin.
For test files (test_*.py under tests/), parses the content with ast and checks
that every def test_* function has at least one @covers(...) decorator.
Exits non-zero to block the tool call if violations are found.
"""

import ast
import json
import os
import sys

_VALID_DECORATOR_NAMES = frozenset({"covers"})


def has_valid_decorator(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in func.decorator_list:
        if isinstance(decorator, ast.Call):
            func_node = decorator.func
            if (
                isinstance(func_node, ast.Name)
                and func_node.id in _VALID_DECORATOR_NAMES
            ):
                return True
    return False


def main() -> None:
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})

    file_path: str = tool_input.get("file_path", "")
    basename = os.path.basename(file_path)

    if not basename.startswith("test_") or not basename.endswith(".py"):
        sys.exit(0)

    content: str = tool_input.get("content") or tool_input.get("new_string") or ""
    if not content:
        sys.exit(0)

    try:
        tree = ast.parse(content)
    except SyntaxError:
        sys.exit(0)

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        if not has_valid_decorator(node):
            violations.append(f"  Line {node.lineno}: {node.name}")

    if violations:
        print(
            f"covers-guard: BLOCKED — missing @covers decorator in {basename}:",
            file=sys.stderr,
        )
        for v in violations:
            print(v, file=sys.stderr)
        print(file=sys.stderr)
        print(
            "Every test_* method needs @covers(LangFeature.MEMBER) — where LangFeature is the language-specific feature enum",
            file=sys.stderr,
        )
        print(
            "(e.g. GoFeature.TYPE_ALIAS, RustFeature.TYPE_ITEM) — or @covers(NotLanguageFeature.INFRASTRUCTURE) for non-language-feature tests.",
            file=sys.stderr,
        )
        print(
            "See tests/covers.py and interpreter/frontends/<lang>/features.py.",
            file=sys.stderr,
        )
        sys.exit(2)


main()
