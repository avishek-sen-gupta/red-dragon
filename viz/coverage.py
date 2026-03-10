"""Frontend coverage matrix — introspects dispatch tables across all frontends."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from interpreter.constants import Language
from interpreter.frontend import get_frontend

logger = logging.getLogger(__name__)

# Semantic categories for grouping node types in the matrix
FEATURE_CATEGORIES: dict[str, list[str]] = {
    "Literals": [
        "integer",
        "float",
        "string",
        "boolean",
        "none",
        "null",
        "number_literal",
        "integer_literal",
        "float_literal",
        "string_literal",
        "char_literal",
        "boolean_literal",
        "true",
        "false",
        "nil",
        "undefined",
    ],
    "Expressions": [
        "identifier",
        "binary_expression",
        "unary_expression",
        "parenthesized_expression",
        "call_expression",
        "member_expression",
        "subscript_expression",
        "assignment_expression",
        "conditional_expression",
        "ternary_expression",
        "lambda",
        "lambda_expression",
        "arrow_function",
        "closure_expression",
        "list_comprehension",
        "dictionary_comprehension",
        "set_comprehension",
        "generator_expression",
    ],
    "Pointer/Reference": [
        "pointer_expression",
        "pointer_declarator",
        "reference_expression",
        "dereference_expression",
        "address_of_expression",
    ],
    "Control Flow": [
        "if_statement",
        "if_expression",
        "else_clause",
        "while_statement",
        "for_statement",
        "for_in_statement",
        "do_statement",
        "switch_statement",
        "match_expression",
        "break_statement",
        "continue_statement",
        "return_statement",
        "return_expression",
    ],
    "Declarations": [
        "function_definition",
        "function_declaration",
        "function_item",
        "method_declaration",
        "class_definition",
        "class_declaration",
        "variable_declaration",
        "let_declaration",
        "struct_item",
        "enum_definition",
        "interface_declaration",
        "trait_item",
        "impl_item",
    ],
    "Error Handling": [
        "try_statement",
        "catch_clause",
        "finally_clause",
        "throw_statement",
        "raise_statement",
    ],
    "Pattern Matching": [
        "match_expression",
        "match_arm",
        "match_pattern",
        "switch_expression",
        "case_clause",
        "if_let_expression",
        "while_let_expression",
    ],
    "OOP": [
        "class_definition",
        "class_declaration",
        "field_expression",
        "field_declaration",
        "method_declaration",
        "constructor_declaration",
        "this",
        "self",
    ],
}


@dataclass(frozen=True)
class HandlerInfo:
    """Info about a single dispatch table entry."""

    node_type: str
    handler_name: str
    module_path: str
    is_shared: bool  # True if from common/, False if language-specific


@dataclass(frozen=True)
class FrontendCoverage:
    """Coverage data for a single frontend."""

    language: str
    stmt_handlers: dict[str, HandlerInfo] = field(default_factory=dict)
    expr_handlers: dict[str, HandlerInfo] = field(default_factory=dict)


def _extract_handler_info(node_type: str, handler) -> HandlerInfo:
    """Extract handler metadata from a callable."""
    module = getattr(handler, "__module__", "")
    name = getattr(handler, "__name__", str(handler))
    is_shared = ".common." in module or ".common/" in module
    return HandlerInfo(
        node_type=node_type,
        handler_name=name,
        module_path=module,
        is_shared=is_shared,
    )


def build_coverage(
    languages: list[str] | None = None,
) -> list[FrontendCoverage]:
    """Build coverage data for all (or specified) frontends."""
    if languages is None:
        languages = [lang.value for lang in Language if lang != Language.COBOL]

    coverages = []
    for lang in languages:
        try:
            frontend = get_frontend(lang, frontend_type="deterministic")
            # Check if frontend uses context mode (has dispatch builders)
            if not hasattr(frontend, "_build_stmt_dispatch"):
                logger.info("Skipping %s: no dispatch builders", lang)
                continue

            stmt_dispatch = frontend._build_stmt_dispatch()
            expr_dispatch = frontend._build_expr_dispatch()

            stmt_handlers = {
                ntype: _extract_handler_info(ntype, handler)
                for ntype, handler in stmt_dispatch.items()
            }
            expr_handlers = {
                ntype: _extract_handler_info(ntype, handler)
                for ntype, handler in expr_dispatch.items()
            }

            coverages.append(
                FrontendCoverage(
                    language=lang,
                    stmt_handlers=stmt_handlers,
                    expr_handlers=expr_handlers,
                )
            )
        except Exception as e:
            logger.warning("Failed to build coverage for %s: %s", lang, e)

    return coverages


def all_node_types(coverages: list[FrontendCoverage]) -> list[str]:
    """Collect all unique node types across all frontends, sorted."""
    types: set[str] = set()
    for cov in coverages:
        types.update(cov.stmt_handlers.keys())
        types.update(cov.expr_handlers.keys())
    return sorted(types)
