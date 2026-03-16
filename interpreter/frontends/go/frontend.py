"""GoFrontend — thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.go import expressions as go_expr
from interpreter.frontends.go import control_flow as go_cf
from interpreter.frontends.go import declarations as go_decl
from interpreter.frontends.go.node_types import GoNodeType


class GoFrontend(BaseFrontend):
    """Lowers a Go tree-sitter AST into flattened TAC IR."""

    BLOCK_SCOPED = True

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="operand",
            attr_attribute_field="field",
            attribute_node_type="selector_expression",
            comment_types=frozenset({GoNodeType.COMMENT}),
            noise_types=frozenset(
                {
                    GoNodeType.PACKAGE_CLAUSE,
                    GoNodeType.IMPORT_DECLARATION,
                    GoNodeType.NEWLINE,
                }
            ),
            block_node_types=frozenset(
                {GoNodeType.BLOCK, GoNodeType.STATEMENT_LIST, GoNodeType.SOURCE_FILE}
            ),
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "int": "Int",
            "int8": "Int",
            "int16": "Int",
            "int32": "Int",
            "int64": "Int",
            "uint": "Int",
            "uint8": "Int",
            "uint16": "Int",
            "uint32": "Int",
            "uint64": "Int",
            "uintptr": "Int",
            "rune": "Int",
            "byte": "Int",
            "float32": "Float",
            "float64": "Float",
            "bool": "Bool",
            "string": "String",
        }

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            GoNodeType.IDENTIFIER: common_expr.lower_identifier,
            GoNodeType.INT_LITERAL: common_expr.lower_const_literal,
            GoNodeType.FLOAT_LITERAL: common_expr.lower_const_literal,
            GoNodeType.INTERPRETED_STRING_LITERAL: common_expr.lower_const_literal,
            GoNodeType.RAW_STRING_LITERAL: common_expr.lower_const_literal,
            GoNodeType.RUNE_LITERAL: common_expr.lower_const_literal,
            GoNodeType.BLANK_IDENTIFIER: common_expr.lower_const_literal,
            GoNodeType.TRUE: common_expr.lower_canonical_true,
            GoNodeType.FALSE: common_expr.lower_canonical_false,
            GoNodeType.NIL: common_expr.lower_canonical_none,
            GoNodeType.BINARY_EXPRESSION: common_expr.lower_binop,
            GoNodeType.UNARY_EXPRESSION: common_expr.lower_unop,
            GoNodeType.CALL_EXPRESSION: go_expr.lower_go_call,
            GoNodeType.SELECTOR_EXPRESSION: go_expr.lower_selector,
            GoNodeType.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            GoNodeType.INDEX_EXPRESSION: go_expr.lower_go_index,
            GoNodeType.COMPOSITE_LITERAL: go_expr.lower_composite_literal,
            GoNodeType.TYPE_IDENTIFIER: common_expr.lower_identifier,
            GoNodeType.FIELD_IDENTIFIER: common_expr.lower_identifier,
            GoNodeType.TYPE_ASSERTION_EXPRESSION: go_expr.lower_type_assertion,
            GoNodeType.SLICE_EXPRESSION: go_expr.lower_slice_expr,
            GoNodeType.FUNC_LITERAL: go_expr.lower_func_literal,
            GoNodeType.TYPE_CONVERSION_EXPRESSION: go_expr.lower_type_conversion,
            GoNodeType.GENERIC_TYPE: go_expr.lower_generic_type,
            GoNodeType.CHANNEL_TYPE: common_expr.lower_const_literal,
            GoNodeType.SLICE_TYPE: common_expr.lower_const_literal,
            GoNodeType.EXPRESSION_LIST: common_expr.lower_const_literal,
            GoNodeType.VARIADIC_ARGUMENT: common_expr.lower_paren,
            GoNodeType.IOTA: go_expr.lower_go_iota,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            GoNodeType.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            GoNodeType.SHORT_VAR_DECLARATION: go_decl.lower_short_var_decl,
            GoNodeType.ASSIGNMENT_STATEMENT: go_decl.lower_go_assignment,
            GoNodeType.RETURN_STATEMENT: go_cf.lower_go_return,
            GoNodeType.IF_STATEMENT: go_cf.lower_go_if,
            GoNodeType.FOR_STATEMENT: go_cf.lower_go_for,
            GoNodeType.FUNCTION_DECLARATION: go_decl.lower_go_func_decl,
            GoNodeType.METHOD_DECLARATION: go_decl.lower_go_method_decl,
            GoNodeType.TYPE_DECLARATION: go_decl.lower_go_type_decl,
            GoNodeType.INC_STATEMENT: go_cf.lower_go_inc,
            GoNodeType.DEC_STATEMENT: go_cf.lower_go_dec,
            GoNodeType.BLOCK: lambda ctx, node: ctx.lower_block(node),
            GoNodeType.STATEMENT_LIST: lambda ctx, node: ctx.lower_block(node),
            GoNodeType.SOURCE_FILE: lambda ctx, node: ctx.lower_block(node),
            GoNodeType.VAR_DECLARATION: go_decl.lower_go_var_decl,
            GoNodeType.BREAK_STATEMENT: common_cf.lower_break,
            GoNodeType.CONTINUE_STATEMENT: common_cf.lower_continue,
            GoNodeType.DEFER_STATEMENT: go_cf.lower_defer_stmt,
            GoNodeType.GO_STATEMENT: go_cf.lower_go_stmt,
            GoNodeType.EXPRESSION_SWITCH_STATEMENT: go_cf.lower_expression_switch,
            GoNodeType.TYPE_SWITCH_STATEMENT: go_cf.lower_type_switch,
            GoNodeType.SELECT_STATEMENT: go_cf.lower_select_stmt,
            GoNodeType.SEND_STATEMENT: go_cf.lower_send_stmt,
            GoNodeType.LABELED_STATEMENT: go_cf.lower_labeled_stmt,
            GoNodeType.CONST_DECLARATION: go_decl.lower_go_const_decl,
            GoNodeType.GOTO_STATEMENT: go_cf.lower_goto_stmt,
            GoNodeType.FALLTHROUGH_STATEMENT: lambda ctx, node: None,
            GoNodeType.RECEIVE_STATEMENT: go_cf.lower_receive_stmt,
        }
