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
from interpreter.frontends.lua.node_types import LuaNodeType


class LuaFrontend(BaseFrontend):
    """Lowers a Lua tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="table",
            attr_attribute_field="field",
            comment_types=frozenset({LuaNodeType.COMMENT}),
            noise_types=frozenset({LuaNodeType.HASH_BANG_LINE, LuaNodeType.NEWLINE}),
            block_node_types=frozenset({LuaNodeType.BLOCK, LuaNodeType.CHUNK}),
            paren_expr_type=LuaNodeType.PARENTHESIZED_EXPRESSION,
        )

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            LuaNodeType.IDENTIFIER: common_expr.lower_identifier,
            LuaNodeType.NUMBER: common_expr.lower_const_literal,
            LuaNodeType.STRING: common_expr.lower_const_literal,
            LuaNodeType.TRUE: common_expr.lower_canonical_true,
            LuaNodeType.FALSE: common_expr.lower_canonical_false,
            LuaNodeType.NIL: common_expr.lower_canonical_none,
            LuaNodeType.BINARY_EXPRESSION: common_expr.lower_binop,
            LuaNodeType.UNARY_EXPRESSION: common_expr.lower_unop,
            LuaNodeType.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            LuaNodeType.FUNCTION_CALL: lua_expr.lower_lua_call,
            LuaNodeType.DOT_INDEX_EXPRESSION: lua_expr.lower_dot_index,
            LuaNodeType.METHOD_INDEX_EXPRESSION: lua_expr.lower_method_index,
            LuaNodeType.BRACKET_INDEX_EXPRESSION: lua_expr.lower_bracket_index,
            LuaNodeType.TABLE_CONSTRUCTOR: lua_expr.lower_table_constructor,
            LuaNodeType.EXPRESSION_LIST: lua_expr.lower_expression_list,
            LuaNodeType.FUNCTION_DEFINITION: lua_expr.lower_lua_function_definition,
            LuaNodeType.VARARG_EXPRESSION: lua_expr.lower_lua_vararg,
            LuaNodeType.STRING_CONTENT: common_expr.lower_const_literal,
            LuaNodeType.ESCAPE_SEQUENCE: common_expr.lower_const_literal,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            LuaNodeType.VARIABLE_DECLARATION: lua_decl.lower_lua_variable_declaration,
            LuaNodeType.ASSIGNMENT_STATEMENT: lua_decl.lower_lua_assignment,
            LuaNodeType.FUNCTION_DECLARATION: lua_decl.lower_lua_function_declaration,
            LuaNodeType.IF_STATEMENT: lua_cf.lower_lua_if,
            LuaNodeType.WHILE_STATEMENT: lua_cf.lower_lua_while,
            LuaNodeType.FOR_STATEMENT: lua_cf.lower_lua_for,
            LuaNodeType.REPEAT_STATEMENT: lua_cf.lower_lua_repeat,
            LuaNodeType.RETURN_STATEMENT: lua_decl.lower_lua_return,
            LuaNodeType.DO_STATEMENT: lua_cf.lower_lua_do,
            LuaNodeType.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            LuaNodeType.BREAK_STATEMENT: common_cf.lower_break,
            LuaNodeType.GOTO_STATEMENT: lua_cf.lower_lua_goto,
            LuaNodeType.LABEL_STATEMENT: lua_cf.lower_lua_label,
        }
