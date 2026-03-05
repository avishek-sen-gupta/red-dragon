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


class PascalFrontend(BaseFrontend):
    """Lowers a Pascal tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            comment_types=frozenset({"comment"}),
            noise_types=KEYWORD_NOISE,
            block_node_types=frozenset(
                {
                    "block",
                    "root",
                    "program",
                    "statements",
                    "statement",
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
            "identifier": common_expr.lower_identifier,
            "literalNumber": common_expr.lower_const_literal,
            "literalString": common_expr.lower_const_literal,
            "exprBinary": pascal_expr.lower_pascal_binop,
            "exprCall": pascal_expr.lower_pascal_call,
            "exprParens": pascal_expr.lower_pascal_paren,
            "exprDot": pascal_expr.lower_pascal_dot,
            "exprSubscript": pascal_expr.lower_pascal_subscript,
            "exprUnary": pascal_expr.lower_pascal_unary,
            "exprBrackets": pascal_expr.lower_pascal_brackets,
            "kTrue": common_expr.lower_canonical_true,
            "kFalse": common_expr.lower_canonical_false,
            "kNil": common_expr.lower_canonical_none,
            "range": pascal_expr.lower_pascal_range,
            "inherited": pascal_expr.lower_pascal_inherited_expr,
            "typeref": common_expr.lower_const_literal,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "root": pascal_cf.lower_pascal_root,
            "program": pascal_cf.lower_pascal_program,
            "block": pascal_cf.lower_pascal_block,
            "statement": pascal_cf.lower_pascal_statement,
            "assignment": pascal_decl.lower_pascal_assignment,
            "declVars": pascal_decl.lower_pascal_decl_vars,
            "declVar": pascal_decl.lower_pascal_decl_var,
            "ifElse": pascal_cf.lower_pascal_if,
            "if": pascal_cf.lower_pascal_if,
            "while": pascal_cf.lower_pascal_while,
            "for": pascal_cf.lower_pascal_for,
            "defProc": pascal_decl.lower_pascal_proc,
            "declProc": pascal_decl.lower_pascal_proc,
            "statements": pascal_cf.lower_pascal_block,
            "case": pascal_cf.lower_pascal_case,
            "repeat": pascal_cf.lower_pascal_repeat,
            "declConsts": pascal_decl.lower_pascal_decl_consts,
            "declConst": pascal_decl.lower_pascal_decl_const,
            "declType": pascal_decl.lower_pascal_decl_type,
            "declTypes": pascal_decl.lower_pascal_decl_types,
            "declUses": pascal_cf.lower_pascal_noop,
            "try": pascal_cf.lower_pascal_try,
            "exceptionHandler": pascal_cf.lower_pascal_exception_handler,
            "raise": pascal_cf.lower_pascal_raise,
            "with": pascal_cf.lower_pascal_with,
            "inherited": pascal_cf.lower_pascal_inherited_stmt,
        }
