"""LuaFrontend -- thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.lua import expressions as lua_expr
from interpreter.frontends.lua import control_flow as lua_cf
from interpreter.frontends.lua import declarations as lua_decl


class LuaFrontend(BaseFrontend):
    """Lowers a Lua tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="table",
            attr_attribute_field="field",
            comment_types=frozenset({"comment"}),
            noise_types=frozenset({"hash_bang_line", "\n"}),
            block_node_types=frozenset({"block", "chunk"}),
            paren_expr_type="parenthesized_expression",
        )

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "identifier": common_expr.lower_identifier,
            "number": common_expr.lower_const_literal,
            "string": common_expr.lower_const_literal,
            "true": common_expr.lower_canonical_true,
            "false": common_expr.lower_canonical_false,
            "nil": common_expr.lower_canonical_none,
            "binary_expression": common_expr.lower_binop,
            "unary_expression": common_expr.lower_unop,
            "parenthesized_expression": common_expr.lower_paren,
            "function_call": lua_expr.lower_lua_call,
            "dot_index_expression": lua_expr.lower_dot_index,
            "bracket_index_expression": lua_expr.lower_bracket_index,
            "table_constructor": lua_expr.lower_table_constructor,
            "expression_list": lua_expr.lower_expression_list,
            "function_definition": lua_expr.lower_lua_function_definition,
            "vararg_expression": lua_expr.lower_lua_vararg,
            "string_content": common_expr.lower_const_literal,
            "escape_sequence": common_expr.lower_const_literal,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "variable_declaration": lua_decl.lower_lua_variable_declaration,
            "assignment_statement": lua_decl.lower_lua_assignment,
            "function_declaration": lua_decl.lower_lua_function_declaration,
            "if_statement": lua_cf.lower_lua_if,
            "while_statement": lua_cf.lower_lua_while,
            "for_statement": lua_cf.lower_lua_for,
            "repeat_statement": lua_cf.lower_lua_repeat,
            "return_statement": lua_decl.lower_lua_return,
            "do_statement": lua_cf.lower_lua_do,
            "expression_statement": common_assign.lower_expression_statement,
            "break_statement": common_cf.lower_break,
            "goto_statement": lua_cf.lower_lua_goto,
            "label_statement": lua_cf.lower_lua_label,
        }
