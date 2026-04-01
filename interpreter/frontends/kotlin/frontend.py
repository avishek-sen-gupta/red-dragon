# pyright: standard
"""KotlinFrontend -- thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Any, Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.register import Register
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.kotlin import expressions as kotlin_expr
from interpreter.frontends.kotlin import control_flow as kotlin_cf
from interpreter.frontends.kotlin import declarations as kotlin_decl
from interpreter.frontends.kotlin.node_types import KotlinNodeType as KNT


class KotlinFrontend(BaseFrontend):
    """Lowers a Kotlin tree-sitter AST into flattened TAC IR."""

    BLOCK_SCOPED = True

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            comment_types=frozenset(
                {KNT.COMMENT, KNT.MULTILINE_COMMENT, KNT.LINE_COMMENT}
            ),
            noise_types=frozenset({"\n"}),
            block_node_types=frozenset({KNT.SOURCE_FILE, KNT.STATEMENTS}),
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

    def _build_expr_dispatch(
        self,
    ) -> dict[str, Callable[[TreeSitterEmitContext, Any], Register]]:
        return {  # type: ignore[return-value]  # see red-dragon-rke4
            KNT.SIMPLE_IDENTIFIER: kotlin_expr.lower_kotlin_identifier,
            KNT.INTEGER_LITERAL: common_expr.lower_const_literal,
            KNT.LONG_LITERAL: common_expr.lower_const_literal,
            KNT.REAL_LITERAL: common_expr.lower_const_literal,
            KNT.CHARACTER_LITERAL: common_expr.lower_const_literal,
            KNT.STRING_LITERAL: kotlin_expr.lower_kotlin_string_literal,
            KNT.BOOLEAN_LITERAL: common_expr.lower_canonical_bool,
            KNT.NULL_LITERAL: common_expr.lower_canonical_none,
            KNT.ADDITIVE_EXPRESSION: common_expr.lower_binop,
            KNT.MULTIPLICATIVE_EXPRESSION: common_expr.lower_binop,
            KNT.COMPARISON_EXPRESSION: common_expr.lower_binop,
            KNT.EQUALITY_EXPRESSION: common_expr.lower_binop,
            KNT.CONJUNCTION_EXPRESSION: common_expr.lower_binop,
            KNT.DISJUNCTION_EXPRESSION: common_expr.lower_binop,
            KNT.PREFIX_EXPRESSION: common_expr.lower_unop,
            KNT.POSTFIX_EXPRESSION: kotlin_expr.lower_postfix_expr,
            KNT.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            KNT.CALL_EXPRESSION: kotlin_expr.lower_kotlin_call,
            KNT.NAVIGATION_EXPRESSION: kotlin_expr.lower_navigation_expr,
            KNT.IF_EXPRESSION: kotlin_expr.lower_if_expr,
            KNT.WHEN_EXPRESSION: kotlin_expr.lower_when_expr,
            KNT.COLLECTION_LITERAL: common_expr.lower_list_literal,
            KNT.THIS_EXPRESSION: common_expr.lower_identifier,
            KNT.SUPER_EXPRESSION: common_expr.lower_identifier,
            KNT.LAMBDA_LITERAL: kotlin_expr.lower_lambda_literal,
            KNT.OBJECT_LITERAL: kotlin_expr.lower_object_literal,
            KNT.RANGE_EXPRESSION: kotlin_expr.lower_range_expr,
            KNT.STATEMENTS: kotlin_expr.lower_statements_expr,
            KNT.JUMP_EXPRESSION: kotlin_expr.lower_jump_as_expr,
            KNT.ASSIGNMENT: kotlin_expr.lower_kotlin_assignment_expr,
            KNT.CHECK_EXPRESSION: kotlin_expr.lower_check_expr,
            KNT.TRY_EXPRESSION: kotlin_expr.lower_try_expr,
            KNT.HEX_LITERAL: common_expr.lower_const_literal,
            KNT.ELVIS_EXPRESSION: kotlin_expr.lower_elvis_expr,
            KNT.INFIX_EXPRESSION: kotlin_expr.lower_infix_expr,
            KNT.INDEXING_EXPRESSION: kotlin_expr.lower_indexing_expr,
            KNT.AS_EXPRESSION: kotlin_expr.lower_as_expr,
            KNT.WHILE_STATEMENT: kotlin_expr.lower_loop_as_expr,
            KNT.FOR_STATEMENT: kotlin_expr.lower_loop_as_expr,
            KNT.DO_WHILE_STATEMENT: kotlin_expr.lower_loop_as_expr,
            KNT.TYPE_TEST: kotlin_expr.lower_type_test,
            KNT.LABEL: common_expr.lower_const_literal,
            KNT.ANONYMOUS_FUNCTION: kotlin_expr.lower_anonymous_function,
            KNT.UNSIGNED_LITERAL: kotlin_expr.lower_unsigned_literal,
            KNT.CALLABLE_REFERENCE: kotlin_expr.lower_callable_reference,
            KNT.SPREAD_EXPRESSION: kotlin_expr.lower_spread_expression,  # type: ignore[dict-item]  # see red-dragon-rke4
        }

    def _build_stmt_dispatch(
        self,
    ) -> dict[str, Callable[[TreeSitterEmitContext, Any], None]]:
        return {
            KNT.PROPERTY_DECLARATION: kotlin_decl.lower_property_decl,
            KNT.ASSIGNMENT: kotlin_cf.lower_kotlin_assignment,
            KNT.FUNCTION_DECLARATION: kotlin_decl.lower_function_decl,
            KNT.CLASS_DECLARATION: kotlin_decl.lower_class_decl,
            KNT.IF_EXPRESSION: kotlin_cf.lower_if_stmt,
            KNT.WHEN_EXPRESSION: kotlin_cf.lower_when_stmt,
            KNT.WHILE_STATEMENT: kotlin_cf.lower_while_stmt,
            KNT.FOR_STATEMENT: kotlin_cf.lower_for_stmt,
            KNT.JUMP_EXPRESSION: kotlin_cf.lower_jump_expr,
            KNT.SOURCE_FILE: lambda ctx, node: ctx.lower_block(node),
            KNT.STATEMENTS: lambda ctx, node: ctx.lower_block(node),
            KNT.IMPORT_LIST: lambda ctx, node: None,
            KNT.IMPORT_HEADER: lambda ctx, node: None,
            KNT.WILDCARD_IMPORT: lambda ctx, node: None,
            KNT.PACKAGE_HEADER: lambda ctx, node: None,
            KNT.DO_WHILE_STATEMENT: kotlin_cf.lower_do_while_stmt,
            KNT.OBJECT_DECLARATION: kotlin_decl.lower_object_decl,
            KNT.TRY_EXPRESSION: kotlin_cf.lower_try_stmt,
            KNT.TYPE_ALIAS: lambda ctx, node: None,
            KNT.SETTER: lambda ctx, node: None,
            KNT.GETTER: lambda ctx, node: None,
        }

    def _extract_symbols(self, root) -> SymbolTable:
        from interpreter.frontends.kotlin.declarations import extract_kotlin_symbols

        return extract_kotlin_symbols(root)
