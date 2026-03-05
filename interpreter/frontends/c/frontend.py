"""CFrontend — thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.c import expressions as c_expr
from interpreter.frontends.c import control_flow as c_cf
from interpreter.frontends.c import declarations as c_decl

PREPROC_NOISE_TYPES = frozenset(
    {
        "preproc_include",
        "preproc_define",
        "preproc_ifdef",
        "preproc_ifndef",
        "preproc_if",
        "preproc_else",
        "preproc_elif",
        "preproc_endif",
        "preproc_call",
        "preproc_def",
    }
)


class CFrontend(BaseFrontend):
    """Lowers a C tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="argument",
            attr_attribute_field="field",
            attribute_node_type="field_expression",
            subscript_value_field="argument",
            subscript_index_field="index",
            comment_types=frozenset({"comment"}),
            noise_types=frozenset({"\n"}) | PREPROC_NOISE_TYPES,
            block_node_types=frozenset({"compound_statement", "translation_unit"}),
            none_literal="None",
            true_literal="True",
            false_literal="False",
            default_return_value="0",
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "int": "Int",
            "long": "Int",
            "short": "Int",
            "char": "Int",
            "unsigned": "Int",
            "signed": "Int",
            "size_t": "Int",
            "float": "Float",
            "double": "Float",
            "bool": "Bool",
            "_Bool": "Bool",
            "void": "Any",
        }

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "identifier": common_expr.lower_identifier,
            "number_literal": common_expr.lower_const_literal,
            "string_literal": common_expr.lower_const_literal,
            "char_literal": common_expr.lower_const_literal,
            "true": common_expr.lower_canonical_true,
            "false": common_expr.lower_canonical_false,
            "null": common_expr.lower_canonical_none,
            "binary_expression": common_expr.lower_binop,
            "unary_expression": common_expr.lower_unop,
            "update_expression": common_expr.lower_update_expr,
            "parenthesized_expression": common_expr.lower_paren,
            "call_expression": common_expr.lower_call,
            "field_expression": c_expr.lower_field_expr,
            "subscript_expression": c_expr.lower_subscript_expr,
            "assignment_expression": c_expr.lower_assignment_expr,
            "cast_expression": c_expr.lower_cast_expr,
            "pointer_expression": c_expr.lower_pointer_expr,
            "sizeof_expression": c_expr.lower_sizeof,
            "conditional_expression": c_expr.lower_ternary,
            "comma_expression": c_expr.lower_comma_expr,
            "concatenated_string": common_expr.lower_const_literal,
            "type_identifier": common_expr.lower_identifier,
            "compound_literal_expression": c_expr.lower_compound_literal,
            "preproc_arg": common_expr.lower_const_literal,
            "initializer_list": c_expr.lower_initializer_list,
            "initializer_pair": c_expr.lower_initializer_pair,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "expression_statement": common_assign.lower_expression_statement,
            "declaration": c_decl.lower_declaration,
            "return_statement": common_assign.lower_return,
            "if_statement": common_cf.lower_if,
            "while_statement": common_cf.lower_while,
            "for_statement": common_cf.lower_c_style_for,
            "do_statement": c_cf.lower_do_while,
            "function_definition": c_decl.lower_function_def_c,
            "struct_specifier": c_decl.lower_struct_def,
            "compound_statement": lambda ctx, node: ctx.lower_block(node),
            "switch_statement": c_cf.lower_switch,
            "case_statement": c_cf.lower_case_as_block,
            "goto_statement": c_cf.lower_goto,
            "labeled_statement": c_cf.lower_labeled_stmt,
            "break_statement": common_cf.lower_break,
            "continue_statement": common_cf.lower_continue,
            "translation_unit": lambda ctx, node: ctx.lower_block(node),
            "type_definition": c_decl.lower_typedef,
            "enum_specifier": c_decl.lower_enum_def,
            "union_specifier": c_decl.lower_union_def,
            "preproc_function_def": c_decl.lower_preproc_function_def,
        }
