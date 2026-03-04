"""JavaScriptFrontend — thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.common import declarations as common_decl
from interpreter.frontends.javascript import expressions as js_expr
from interpreter.frontends.javascript import control_flow as js_cf
from interpreter.frontends.javascript import declarations as js_decl


class JavaScriptFrontend(BaseFrontend):
    """Lowers a JavaScript tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="object",
            attr_attribute_field="property",
            attribute_node_type="member_expression",
            subscript_value_field="object",
            subscript_index_field="index",
            comment_types=frozenset({"comment"}),
            noise_types=frozenset({"\n"}),
            block_node_types=frozenset({"statement_block", "program", "module"}),
        )

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "identifier": common_expr.lower_identifier,
            "number": common_expr.lower_const_literal,
            "string": common_expr.lower_const_literal,
            "template_string": js_expr.lower_template_string,
            "template_substitution": js_expr.lower_template_substitution,
            "true": common_expr.lower_canonical_true,
            "false": common_expr.lower_canonical_false,
            "null": common_expr.lower_canonical_none,
            "undefined": common_expr.lower_canonical_none,
            "binary_expression": common_expr.lower_binop,
            "augmented_assignment_expression": common_expr.lower_binop,
            "unary_expression": common_expr.lower_unop,
            "update_expression": common_expr.lower_update_expr,
            "call_expression": js_expr.lower_js_call,
            "new_expression": js_expr.lower_new_expression,
            "member_expression": js_expr.lower_js_attribute,
            "subscript_expression": js_expr.lower_js_subscript,
            "parenthesized_expression": common_expr.lower_paren,
            "array": common_expr.lower_list_literal,
            "object": js_expr.lower_js_object_literal,
            "assignment_expression": js_expr.lower_assignment_expr,
            "arrow_function": js_expr.lower_arrow_function,
            "ternary_expression": js_expr.lower_ternary,
            "this": common_expr.lower_identifier,
            "super": common_expr.lower_identifier,
            "property_identifier": common_expr.lower_identifier,
            "shorthand_property_identifier": common_expr.lower_identifier,
            "await_expression": js_expr.lower_await_expression,
            "yield_expression": js_expr.lower_yield_expression,
            "regex": common_expr.lower_const_literal,
            "sequence_expression": js_expr.lower_sequence_expression,
            "spread_element": js_expr.lower_spread_element,
            "function": js_expr.lower_function_expression,
            "function_expression": js_expr.lower_function_expression,
            "generator_function": js_expr.lower_function_expression,
            "generator_function_declaration": js_decl.lower_js_function_def,
            "string_fragment": common_expr.lower_const_literal,
            "field_definition": js_expr.lower_js_field_definition,
            "export_clause": js_expr.lower_export_clause,
            "export_specifier": common_expr.lower_paren,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "expression_statement": common_assign.lower_expression_statement,
            "lexical_declaration": js_decl.lower_js_var_declaration,
            "variable_declaration": js_decl.lower_js_var_declaration,
            "return_statement": common_assign.lower_return,
            "if_statement": js_cf.lower_js_if,
            "while_statement": common_cf.lower_while,
            "for_statement": common_cf.lower_c_style_for,
            "for_in_statement": js_cf.lower_for_in,
            "function_declaration": js_decl.lower_js_function_def,
            "class_declaration": js_decl.lower_js_class_def,
            "throw_statement": js_cf.lower_js_throw,
            "statement_block": lambda ctx, node: ctx.lower_block(node),
            "empty_statement": lambda ctx, node: None,
            "break_statement": common_cf.lower_break,
            "continue_statement": common_cf.lower_continue,
            "try_statement": js_cf.lower_js_try,
            "switch_statement": js_cf.lower_switch_statement,
            "do_statement": js_cf.lower_do_statement,
            "labeled_statement": js_cf.lower_labeled_statement,
            "import_statement": lambda ctx, node: None,
            "export_statement": js_decl.lower_export_statement,
            "with_statement": js_cf.lower_with_statement,
        }
