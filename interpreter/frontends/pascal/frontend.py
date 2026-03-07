"""PascalFrontend -- thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.pascal import expressions as pascal_expr
from interpreter.frontends.pascal import control_flow as pascal_cf
from interpreter.frontends.pascal import declarations as pascal_decl
from interpreter.frontends.pascal.pascal_constants import KEYWORD_NOISE
from interpreter.frontends.pascal.node_types import PascalNodeType


class PascalFrontend(BaseFrontend):
    """Lowers a Pascal tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            comment_types=frozenset({PascalNodeType.COMMENT}),
            noise_types=KEYWORD_NOISE,
            block_node_types=frozenset(
                {
                    PascalNodeType.BLOCK,
                    PascalNodeType.ROOT,
                    PascalNodeType.PROGRAM,
                    PascalNodeType.STATEMENTS,
                    PascalNodeType.STATEMENT,
                }
            ),
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "integer": "Int",
            "longint": "Int",
            "shortint": "Int",
            "byte": "Int",
            "word": "Int",
            "cardinal": "Int",
            "real": "Float",
            "single": "Float",
            "double": "Float",
            "extended": "Float",
            "boolean": "Bool",
            "char": "String",
            "string": "String",
        }

    def _build_context(self, source: bytes) -> TreeSitterEmitContext:
        ctx = super()._build_context(source)
        # Pascal-specific mutable state stored on the context
        ctx._pascal_current_function_name = ""
        ctx._pascal_record_types = set()
        return ctx

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            PascalNodeType.IDENTIFIER: common_expr.lower_identifier,
            PascalNodeType.LITERAL_NUMBER: common_expr.lower_const_literal,
            PascalNodeType.LITERAL_STRING: common_expr.lower_const_literal,
            PascalNodeType.EXPR_BINARY: pascal_expr.lower_pascal_binop,
            PascalNodeType.EXPR_CALL: pascal_expr.lower_pascal_call,
            PascalNodeType.EXPR_PARENS: pascal_expr.lower_pascal_paren,
            PascalNodeType.EXPR_DOT: pascal_expr.lower_pascal_dot,
            PascalNodeType.EXPR_SUBSCRIPT: pascal_expr.lower_pascal_subscript,
            PascalNodeType.EXPR_UNARY: pascal_expr.lower_pascal_unary,
            PascalNodeType.EXPR_BRACKETS: pascal_expr.lower_pascal_brackets,
            PascalNodeType.K_TRUE: common_expr.lower_canonical_true,
            PascalNodeType.K_FALSE: common_expr.lower_canonical_false,
            PascalNodeType.K_NIL: common_expr.lower_canonical_none,
            PascalNodeType.RANGE: pascal_expr.lower_pascal_range,
            PascalNodeType.INHERITED: pascal_expr.lower_pascal_inherited_expr,
            PascalNodeType.TYPEREF: common_expr.lower_const_literal,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            PascalNodeType.ROOT: pascal_cf.lower_pascal_root,
            PascalNodeType.PROGRAM: pascal_cf.lower_pascal_program,
            PascalNodeType.BLOCK: pascal_cf.lower_pascal_block,
            PascalNodeType.STATEMENT: pascal_cf.lower_pascal_statement,
            PascalNodeType.ASSIGNMENT: pascal_decl.lower_pascal_assignment,
            PascalNodeType.DECL_VARS: pascal_decl.lower_pascal_decl_vars,
            PascalNodeType.DECL_VAR: pascal_decl.lower_pascal_decl_var,
            PascalNodeType.IF_ELSE: pascal_cf.lower_pascal_if,
            PascalNodeType.IF: pascal_cf.lower_pascal_if,
            PascalNodeType.WHILE: pascal_cf.lower_pascal_while,
            PascalNodeType.FOR: pascal_cf.lower_pascal_for,
            PascalNodeType.DEF_PROC: pascal_decl.lower_pascal_proc,
            PascalNodeType.DECL_PROC: pascal_decl.lower_pascal_proc,
            PascalNodeType.STATEMENTS: pascal_cf.lower_pascal_block,
            PascalNodeType.CASE: pascal_cf.lower_pascal_case,
            PascalNodeType.REPEAT: pascal_cf.lower_pascal_repeat,
            PascalNodeType.DECL_CONSTS: pascal_decl.lower_pascal_decl_consts,
            PascalNodeType.DECL_CONST: pascal_decl.lower_pascal_decl_const,
            PascalNodeType.DECL_TYPE: pascal_decl.lower_pascal_decl_type,
            PascalNodeType.DECL_TYPES: pascal_decl.lower_pascal_decl_types,
            PascalNodeType.DECL_USES: pascal_cf.lower_pascal_noop,
            PascalNodeType.TRY: pascal_cf.lower_pascal_try,
            PascalNodeType.EXCEPTION_HANDLER: pascal_cf.lower_pascal_exception_handler,
            PascalNodeType.RAISE: pascal_cf.lower_pascal_raise,
            PascalNodeType.WITH: pascal_cf.lower_pascal_with,
            PascalNodeType.INHERITED: pascal_cf.lower_pascal_inherited_stmt,
        }
