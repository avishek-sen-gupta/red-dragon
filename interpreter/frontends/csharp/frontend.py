"""CSharpFrontend -- thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.csharp import expressions as csharp_expr
from interpreter.frontends.csharp import control_flow as csharp_cf
from interpreter.frontends.csharp import declarations as csharp_decl


class CSharpFrontend(BaseFrontend):
    """Lowers a C# tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="expression",
            attr_attribute_field="name",
            attribute_node_type="member_access_expression",
            comment_types=frozenset({"comment"}),
            noise_types=frozenset({"\n", "using_directive"}),
            block_node_types=frozenset(
                {"block", "compilation_unit", "declaration_list"}
            ),
        )

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "identifier": common_expr.lower_identifier,
            "integer_literal": common_expr.lower_const_literal,
            "real_literal": common_expr.lower_const_literal,
            "string_literal": common_expr.lower_const_literal,
            "character_literal": common_expr.lower_const_literal,
            "verbatim_string_literal": common_expr.lower_const_literal,
            "constant_pattern": common_expr.lower_const_literal,
            "declaration_pattern": csharp_expr.lower_declaration_pattern,
            "boolean_literal": common_expr.lower_canonical_bool,
            "null_literal": common_expr.lower_canonical_none,
            "this_expression": common_expr.lower_identifier,
            "this": common_expr.lower_identifier,
            "binary_expression": common_expr.lower_binop,
            "prefix_unary_expression": common_expr.lower_unop,
            "postfix_unary_expression": common_expr.lower_update_expr,
            "parenthesized_expression": common_expr.lower_paren,
            "invocation_expression": csharp_expr.lower_invocation,
            "object_creation_expression": csharp_expr.lower_object_creation,
            "member_access_expression": csharp_expr.lower_member_access,
            "element_access_expression": csharp_expr.lower_element_access,
            "initializer_expression": csharp_expr.lower_initializer_expr,
            "assignment_expression": csharp_expr.lower_assignment_expr,
            "cast_expression": csharp_expr.lower_cast_expr,
            "conditional_expression": csharp_expr.lower_ternary,
            "interpolated_string_expression": csharp_expr.lower_csharp_interpolated_string,
            "type_identifier": common_expr.lower_identifier,
            "predefined_type": common_expr.lower_identifier,
            "typeof_expression": csharp_expr.lower_typeof,
            "is_expression": csharp_expr.lower_is_expr,
            "as_expression": csharp_expr.lower_as_expr,
            "lambda_expression": csharp_expr.lower_lambda,
            "array_creation_expression": csharp_expr.lower_array_creation,
            "implicit_array_creation_expression": csharp_expr.lower_array_creation,
            "implicit_object_creation_expression": csharp_expr.lower_implicit_object_creation,
            "query_expression": csharp_expr.lower_query_expression,
            "from_clause": csharp_expr.lower_linq_clause,
            "select_clause": csharp_expr.lower_linq_clause,
            "where_clause": csharp_expr.lower_linq_clause,
            "await_expression": csharp_expr.lower_await_expr,
            "switch_expression": csharp_cf.lower_switch_expr,
            "conditional_access_expression": csharp_expr.lower_conditional_access,
            "member_binding_expression": csharp_expr.lower_member_binding,
            "tuple_expression": csharp_expr.lower_tuple_expr,
            "is_pattern_expression": csharp_expr.lower_is_pattern_expr,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "expression_statement": common_assign.lower_expression_statement,
            "local_declaration_statement": csharp_decl.lower_local_decl_stmt,
            "return_statement": common_assign.lower_return,
            "if_statement": csharp_cf.lower_if,
            "while_statement": common_cf.lower_while,
            "for_statement": common_cf.lower_c_style_for,
            "foreach_statement": csharp_cf.lower_foreach,
            "method_declaration": csharp_decl.lower_method_decl,
            "class_declaration": csharp_decl.lower_class_def,
            "struct_declaration": csharp_decl.lower_class_def,
            "interface_declaration": csharp_decl.lower_interface_decl,
            "enum_declaration": csharp_decl.lower_enum_decl,
            "namespace_declaration": csharp_decl.lower_namespace,
            "throw_statement": csharp_cf.lower_throw,
            "block": lambda ctx, node: ctx.lower_block(node),
            "global_statement": csharp_cf.lower_global_statement,
            "using_directive": lambda ctx, node: None,
            "do_statement": csharp_cf.lower_do_while,
            "switch_statement": csharp_cf.lower_switch,
            "try_statement": csharp_cf.lower_try,
            "constructor_declaration": csharp_decl.lower_constructor_decl,
            "field_declaration": csharp_decl.lower_field_decl,
            "property_declaration": csharp_decl.lower_property_decl,
            "break_statement": common_cf.lower_break,
            "continue_statement": common_cf.lower_continue,
            "lock_statement": csharp_cf.lower_lock_stmt,
            "using_statement": csharp_cf.lower_using_stmt,
            "checked_statement": csharp_cf.lower_checked_stmt,
            "fixed_statement": csharp_cf.lower_fixed_stmt,
            "event_field_declaration": csharp_decl.lower_event_field_decl,
            "event_declaration": csharp_decl.lower_event_decl,
            "record_declaration": csharp_decl.lower_class_def,
            "record_struct_declaration": csharp_decl.lower_class_def,
            "variable_declaration": csharp_decl.lower_variable_declaration,
            "delegate_declaration": csharp_decl.lower_delegate_declaration,
            "local_function_statement": csharp_decl.lower_local_function_stmt,
            "yield_statement": csharp_cf.lower_yield_stmt,
        }
