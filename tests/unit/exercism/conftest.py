"""Shared helpers for the Exercism cross-language test suite.

Extends the Rosetta infrastructure with file-based solution loading,
canonical test case parsing, and argument substitution for parametrized
multi-case execution.
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

EXERCISES_DIR = Path(__file__).parent / "exercises"

LANGUAGE_EXTENSIONS: dict[str, str] = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "java": ".java",
    "ruby": ".rb",
    "go": ".go",
    "php": ".php",
    "csharp": ".cs",
    "c": ".c",
    "cpp": ".cpp",
    "rust": ".rs",
    "kotlin": ".kt",
    "scala": ".scala",
    "lua": ".lua",
    "pascal": ".pas",
}


def load_solution(exercise: str, language: str) -> str:
    """Read a solution source file for *exercise* in *language*."""
    ext = LANGUAGE_EXTENSIONS[language]
    path = EXERCISES_DIR / exercise / "solutions" / f"{language}{ext}"
    logger.info("Loading solution: %s", path)
    return path.read_text(encoding="utf-8")


def load_canonical_cases(exercise: str, property_filter: str = "") -> list[dict]:
    """Load and filter canonical test cases from JSON.

    Returns only cases that have an ``expected`` field that is not an
    error object (dict with ``error`` key).  When *property_filter* is
    non-empty, only cases whose ``property`` matches are returned.
    """
    path = EXERCISES_DIR / exercise / "canonical_data.json"
    logger.info("Loading canonical data: %s", path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    cases = _flatten_cases(raw.get("cases", []))

    result = [
        case
        for case in cases
        if not _is_error_case(case)
        and (not property_filter or case.get("property") == property_filter)
    ]
    logger.info(
        "Loaded %d canonical cases for %s (filter=%r)",
        len(result),
        exercise,
        property_filter,
    )
    return result


def _flatten_cases(cases: list[dict]) -> list[dict]:
    """Recursively flatten nested case groups into a flat list."""
    result = []
    for case in cases:
        if "cases" in case:
            result.extend(_flatten_cases(case["cases"]))
        else:
            result.append(case)
    return result


def _is_error_case(case: dict) -> bool:
    """Return True if the case expects an error result."""
    expected = case.get("expected")
    return isinstance(expected, dict) and "error" in expected


def format_arg(value: object, language: str) -> str:
    """Format a Python value as a source-code literal for *language*.

    Handles int, bool, float, and str.  Booleans are mapped to the
    language-appropriate literal form.
    """
    if isinstance(value, bool):
        return _format_bool(value, language)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return _format_string(value, language)
    return str(value)


_TRUE_LITERALS: dict[str, str] = {
    "python": "True",
    "ruby": "true",
    "lua": "true",
    "pascal": "True",
    "rust": "true",
    "kotlin": "true",
    "scala": "true",
    "java": "true",
    "csharp": "true",
    "c": "1",
    "cpp": "1",
    "go": "true",
    "javascript": "true",
    "typescript": "true",
    "php": "true",
}

_FALSE_LITERALS: dict[str, str] = {
    "python": "False",
    "ruby": "false",
    "lua": "false",
    "pascal": "False",
    "rust": "false",
    "kotlin": "false",
    "scala": "false",
    "java": "false",
    "csharp": "false",
    "c": "0",
    "cpp": "0",
    "go": "false",
    "javascript": "false",
    "typescript": "false",
    "php": "false",
}


def _format_bool(value: bool, language: str) -> str:
    table = _TRUE_LITERALS if value else _FALSE_LITERALS
    return table[language]


def _format_string(value: str, language: str) -> str:
    if language == "pascal":
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_program(
    solution_source: str,
    function_name: str,
    args: list[object],
    language: str,
    default_function_name: str = "",
) -> str:
    """Substitute function call in the invocation line of a solution.

    Finds the line that assigns ``answer = default_function_name(...)``
    (or its language-specific equivalent) and replaces both the function
    name and arguments.  When *default_function_name* is empty it
    defaults to *function_name* (i.e. only the arguments change).
    """
    source_fn = default_function_name if default_function_name else function_name
    formatted_args = ", ".join(format_arg(a, language) for a in args)
    var_prefix = "$" if language == "php" else ""
    source_fn_pattern = re.escape(source_fn)
    answer_var = f"{var_prefix}answer"

    lines = solution_source.split("\n")
    replaced = [
        _replace_invocation(
            line, answer_var, source_fn_pattern, function_name, formatted_args
        )
        for line in lines
    ]
    return "\n".join(replaced)


def _replace_invocation(
    line: str,
    answer_var: str,
    source_fn_pattern: str,
    target_fn_name: str,
    new_args: str,
) -> str:
    """Replace function name and arguments in an answer-assignment line."""
    # Match varied assignment forms: =, :=, : type =, etc.
    pattern = re.escape(answer_var) + r"[^=]*=\s*" + source_fn_pattern + r"\s*\([^)]*\)"
    match = re.search(pattern, line)
    if not match:
        return line
    call_pattern = source_fn_pattern + r"\s*\([^)]*\)"
    return re.sub(call_pattern, f"{target_fn_name}({new_args})", line)
