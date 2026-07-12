"""JavaScriptFrontend — thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
from interpreter.frontends.javascript import control_flow as js_cf
from interpreter.frontends.javascript import declarations as js_decl
from interpreter.frontends.javascript import expressions as js_expr
from interpreter.frontends.javascript.expressions import (
    lower_js_meta_property,
    lower_js_number,
    lower_js_regex,
    lower_js_string,
    lower_js_string_fragment,
)
from interpreter.frontends.javascript.node_types import JavaScriptNodeType as JSN
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.register import Register


class JavaScriptFrontend(BaseFrontend):
    """Lowers a JavaScript tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="object",
            attr_attribute_field="property",
            attribute_node_type=JSN.MEMBER_EXPRESSION,
            subscript_value_field="object",
            subscript_index_field="index",
            comment_types=frozenset({JSN.COMMENT}),
            noise_types=frozenset({JSN.NEWLINE}),
            block_node_types=frozenset({JSN.STATEMENT_BLOCK, JSN.PROGRAM, JSN.MODULE}),
            for_update_field="increment",
        )

    def _build_expr_dispatch(
        self,
    ) -> dict[str, Callable[[TreeSitterEmitContext, Any], Register]]:
        return {
            JSN.IDENTIFIER: common_expr.lower_identifier,
            JSN.NUMBER: lower_js_number,
            JSN.STRING: lower_js_string,
            JSN.TEMPLATE_STRING: js_expr.lower_template_string,
            JSN.TEMPLATE_SUBSTITUTION: js_expr.lower_template_substitution,
            JSN.TRUE: common_expr.lower_canonical_true,
            JSN.FALSE: common_expr.lower_canonical_false,
            JSN.NULL: common_expr.lower_canonical_none,
            JSN.UNDEFINED: common_expr.lower_canonical_none,
            JSN.BINARY_EXPRESSION: common_expr.lower_binop,
            JSN.AUGMENTED_ASSIGNMENT_EXPRESSION: common_expr.lower_binop,
            JSN.UNARY_EXPRESSION: common_expr.lower_unop,
            JSN.UPDATE_EXPRESSION: common_expr.lower_update_expr,
            JSN.CALL_EXPRESSION: js_expr.lower_js_call,
            JSN.NEW_EXPRESSION: js_expr.lower_new_expression,
            JSN.MEMBER_EXPRESSION: js_expr.lower_js_attribute,
            JSN.SUBSCRIPT_EXPRESSION: js_expr.lower_js_subscript,
            JSN.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            JSN.ARRAY: common_expr.lower_list_literal,
            JSN.OBJECT: js_expr.lower_js_object_literal,
            JSN.ASSIGNMENT_EXPRESSION: js_expr.lower_assignment_expr,
            JSN.ARROW_FUNCTION: js_expr.lower_arrow_function,
            JSN.TERNARY_EXPRESSION: js_expr.lower_ternary,
            JSN.THIS: common_expr.lower_identifier,
            JSN.SUPER: common_expr.lower_identifier,
            JSN.PROPERTY_IDENTIFIER: common_expr.lower_identifier,
            JSN.SHORTHAND_PROPERTY_IDENTIFIER: common_expr.lower_identifier,
            JSN.AWAIT_EXPRESSION: js_expr.lower_await_expression,
            JSN.YIELD_EXPRESSION: js_expr.lower_yield_expression,
            JSN.REGEX: lower_js_regex,
            JSN.SEQUENCE_EXPRESSION: js_expr.lower_sequence_expression,
            JSN.SPREAD_ELEMENT: js_expr.lower_spread_element,
            JSN.FUNCTION: js_expr.lower_function_expression,
            JSN.FUNCTION_EXPRESSION: js_expr.lower_function_expression,
            JSN.GENERATOR_FUNCTION: js_expr.lower_function_expression,
            JSN.GENERATOR_FUNCTION_DECLARATION: js_decl.lower_js_function_def,
            JSN.STRING_FRAGMENT: lower_js_string_fragment,
            JSN.FIELD_DEFINITION: js_expr.lower_js_field_definition,
            JSN.EXPORT_CLAUSE: js_expr.lower_export_clause,
            JSN.EXPORT_SPECIFIER: common_expr.lower_paren,
            JSN.META_PROPERTY: lower_js_meta_property,
            JSN.CLASS: js_decl.lower_js_class_expression,
        }

    def _build_stmt_dispatch(
        self,
    ) -> dict[str, Callable[[TreeSitterEmitContext, Any], None]]:
        return {
            JSN.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            JSN.LEXICAL_DECLARATION: js_decl.lower_js_var_declaration,
            JSN.VARIABLE_DECLARATION: js_decl.lower_js_var_declaration,
            JSN.USING_DECLARATION: js_decl.lower_js_var_declaration,
            JSN.RETURN_STATEMENT: common_assign.lower_return,
            JSN.IF_STATEMENT: js_cf.lower_js_if,
            JSN.WHILE_STATEMENT: common_cf.lower_while,
            JSN.FOR_STATEMENT: common_cf.lower_c_style_for,
            JSN.FOR_IN_STATEMENT: js_cf.lower_for_in,
            JSN.FUNCTION_DECLARATION: js_decl.lower_js_function_def,
            JSN.CLASS_DECLARATION: js_decl.lower_js_class_def,
            JSN.THROW_STATEMENT: js_cf.lower_js_throw,
            JSN.STATEMENT_BLOCK: lambda ctx, node: ctx.lower_block(node),
            JSN.EMPTY_STATEMENT: lambda ctx, node: None,
            JSN.BREAK_STATEMENT: common_cf.lower_break,
            JSN.CONTINUE_STATEMENT: common_cf.lower_continue,
            JSN.TRY_STATEMENT: js_cf.lower_js_try,
            JSN.SWITCH_STATEMENT: js_cf.lower_switch_statement,
            JSN.DO_STATEMENT: js_cf.lower_do_statement,
            JSN.LABELED_STATEMENT: js_cf.lower_labeled_statement,
            JSN.IMPORT_STATEMENT: js_cf.lower_import_statement,
            JSN.EXPORT_STATEMENT: js_decl.lower_export_statement,
            JSN.WITH_STATEMENT: js_cf.lower_with_statement,
        }

    def _extract_symbols(self, root) -> SymbolTable:
        from interpreter.frontends.javascript.declarations import (
            extract_javascript_symbols,
        )

        return extract_javascript_symbols(root)
