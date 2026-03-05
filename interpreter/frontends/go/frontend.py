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


class GoFrontend(BaseFrontend):
    """Lowers a Go tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="operand",
            attr_attribute_field="field",
            attribute_node_type="selector_expression",
            comment_types=frozenset({"comment"}),
            noise_types=frozenset({"package_clause", "import_declaration", "\n"}),
            block_node_types=frozenset({"block", "statement_list", "source_file"}),
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
            "identifier": common_expr.lower_identifier,
            "int_literal": common_expr.lower_const_literal,
            "float_literal": common_expr.lower_const_literal,
            "interpreted_string_literal": common_expr.lower_const_literal,
            "raw_string_literal": common_expr.lower_const_literal,
            "true": common_expr.lower_canonical_true,
            "false": common_expr.lower_canonical_false,
            "nil": common_expr.lower_canonical_none,
            "binary_expression": common_expr.lower_binop,
            "unary_expression": common_expr.lower_unop,
            "call_expression": go_expr.lower_go_call,
            "selector_expression": go_expr.lower_selector,
            "parenthesized_expression": common_expr.lower_paren,
            "index_expression": go_expr.lower_go_index,
            "composite_literal": go_expr.lower_composite_literal,
            "type_identifier": common_expr.lower_identifier,
            "field_identifier": common_expr.lower_identifier,
            "type_assertion_expression": go_expr.lower_type_assertion,
            "slice_expression": go_expr.lower_slice_expr,
            "func_literal": go_expr.lower_func_literal,
            "channel_type": common_expr.lower_const_literal,
            "slice_type": common_expr.lower_const_literal,
            "expression_list": common_expr.lower_const_literal,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "expression_statement": common_assign.lower_expression_statement,
            "short_var_declaration": go_decl.lower_short_var_decl,
            "assignment_statement": go_decl.lower_go_assignment,
            "return_statement": go_cf.lower_go_return,
            "if_statement": go_cf.lower_go_if,
            "for_statement": go_cf.lower_go_for,
            "function_declaration": go_decl.lower_go_func_decl,
            "method_declaration": go_decl.lower_go_method_decl,
            "type_declaration": go_decl.lower_go_type_decl,
            "inc_statement": go_cf.lower_go_inc,
            "dec_statement": go_cf.lower_go_dec,
            "block": lambda ctx, node: ctx.lower_block(node),
            "statement_list": lambda ctx, node: ctx.lower_block(node),
            "source_file": lambda ctx, node: ctx.lower_block(node),
            "var_declaration": go_decl.lower_go_var_decl,
            "break_statement": common_cf.lower_break,
            "continue_statement": common_cf.lower_continue,
            "defer_statement": go_cf.lower_defer_stmt,
            "go_statement": go_cf.lower_go_stmt,
            "expression_switch_statement": go_cf.lower_expression_switch,
            "type_switch_statement": go_cf.lower_type_switch,
            "select_statement": go_cf.lower_select_stmt,
            "send_statement": go_cf.lower_send_stmt,
            "labeled_statement": go_cf.lower_labeled_stmt,
            "const_declaration": go_decl.lower_go_const_decl,
            "goto_statement": go_cf.lower_goto_stmt,
            "receive_statement": go_cf.lower_receive_stmt,
        }
