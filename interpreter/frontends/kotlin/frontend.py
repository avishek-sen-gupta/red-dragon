"""KotlinFrontend -- thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.kotlin import expressions as kotlin_expr
from interpreter.frontends.kotlin import control_flow as kotlin_cf
from interpreter.frontends.kotlin import declarations as kotlin_decl


class KotlinFrontend(BaseFrontend):
    """Lowers a Kotlin tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            comment_types=frozenset({"comment", "multiline_comment", "line_comment"}),
            noise_types=frozenset({"\n"}),
            block_node_types=frozenset({"source_file", "statements"}),
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "Int": "Int",
            "Long": "Int",
            "Short": "Int",
            "Byte": "Int",
            "Char": "Int",
            "Float": "Float",
            "Double": "Float",
            "Boolean": "Bool",
            "String": "String",
            "Unit": "Any",
            "Any": "Any",
        }

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "simple_identifier": common_expr.lower_identifier,
            "integer_literal": common_expr.lower_const_literal,
            "long_literal": common_expr.lower_const_literal,
            "real_literal": common_expr.lower_const_literal,
            "character_literal": common_expr.lower_const_literal,
            "string_literal": kotlin_expr.lower_kotlin_string_literal,
            "boolean_literal": common_expr.lower_canonical_bool,
            "null_literal": common_expr.lower_canonical_none,
            "additive_expression": common_expr.lower_binop,
            "multiplicative_expression": common_expr.lower_binop,
            "comparison_expression": common_expr.lower_binop,
            "equality_expression": common_expr.lower_binop,
            "conjunction_expression": common_expr.lower_binop,
            "disjunction_expression": common_expr.lower_binop,
            "prefix_expression": common_expr.lower_unop,
            "postfix_expression": kotlin_expr.lower_postfix_expr,
            "parenthesized_expression": common_expr.lower_paren,
            "call_expression": kotlin_expr.lower_kotlin_call,
            "navigation_expression": kotlin_expr.lower_navigation_expr,
            "if_expression": kotlin_expr.lower_if_expr,
            "when_expression": kotlin_expr.lower_when_expr,
            "collection_literal": common_expr.lower_list_literal,
            "this_expression": common_expr.lower_identifier,
            "super_expression": common_expr.lower_identifier,
            "lambda_literal": kotlin_expr.lower_lambda_literal,
            "object_literal": kotlin_expr.lower_object_literal,
            "range_expression": kotlin_expr.lower_range_expr,
            "statements": kotlin_expr.lower_statements_expr,
            "jump_expression": kotlin_expr.lower_jump_as_expr,
            "assignment": kotlin_expr.lower_kotlin_assignment_expr,
            "check_expression": kotlin_expr.lower_check_expr,
            "try_expression": kotlin_expr.lower_try_expr,
            "hex_literal": common_expr.lower_const_literal,
            "elvis_expression": kotlin_expr.lower_elvis_expr,
            "infix_expression": kotlin_expr.lower_infix_expr,
            "indexing_expression": kotlin_expr.lower_indexing_expr,
            "as_expression": kotlin_expr.lower_as_expr,
            "while_statement": kotlin_expr.lower_loop_as_expr,
            "for_statement": kotlin_expr.lower_loop_as_expr,
            "do_while_statement": kotlin_expr.lower_loop_as_expr,
            "type_test": kotlin_expr.lower_type_test,
            "label": common_expr.lower_const_literal,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "property_declaration": kotlin_decl.lower_property_decl,
            "assignment": kotlin_cf.lower_kotlin_assignment,
            "function_declaration": kotlin_decl.lower_function_decl,
            "class_declaration": kotlin_decl.lower_class_decl,
            "if_expression": kotlin_cf.lower_if_stmt,
            "while_statement": kotlin_cf.lower_while_stmt,
            "for_statement": kotlin_cf.lower_for_stmt,
            "jump_expression": kotlin_cf.lower_jump_expr,
            "source_file": lambda ctx, node: ctx.lower_block(node),
            "statements": lambda ctx, node: ctx.lower_block(node),
            "import_list": lambda ctx, node: None,
            "import_header": lambda ctx, node: None,
            "package_header": lambda ctx, node: None,
            "do_while_statement": kotlin_cf.lower_do_while_stmt,
            "object_declaration": kotlin_decl.lower_object_decl,
            "try_expression": kotlin_cf.lower_try_stmt,
            "type_alias": lambda ctx, node: None,
        }
