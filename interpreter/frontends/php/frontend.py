"""PhpFrontend -- thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.php import expressions as php_expr
from interpreter.frontends.php import control_flow as php_cf
from interpreter.frontends.php import declarations as php_decl


class PhpFrontend(BaseFrontend):
    """Lowers a PHP tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="object",
            attr_attribute_field="name",
            attribute_node_type="member_access_expression",
            comment_types=frozenset({"comment"}),
            noise_types=frozenset(
                {"php_tag", "text_interpolation", "php_end_tag", "\n"}
            ),
            block_node_types=frozenset({"compound_statement", "program"}),
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "int": "Int",
            "integer": "Int",
            "float": "Float",
            "double": "Float",
            "bool": "Bool",
            "boolean": "Bool",
            "string": "String",
            "array": "Array",
            "object": "Object",
            "void": "Any",
            "mixed": "Any",
            "null": "Any",
        }

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "variable_name": php_expr.lower_php_variable,
            "name": common_expr.lower_identifier,
            "integer": common_expr.lower_const_literal,
            "float": common_expr.lower_const_literal,
            "string": common_expr.lower_const_literal,
            "encapsed_string": php_expr.lower_php_encapsed_string,
            "boolean": common_expr.lower_canonical_bool,
            "null": common_expr.lower_canonical_none,
            "binary_expression": common_expr.lower_binop,
            "unary_op_expression": common_expr.lower_unop,
            "update_expression": common_expr.lower_update_expr,
            "function_call_expression": php_expr.lower_php_func_call,
            "member_call_expression": php_expr.lower_php_method_call,
            "member_access_expression": php_expr.lower_php_member_access,
            "subscript_expression": php_expr.lower_php_subscript,
            "parenthesized_expression": common_expr.lower_paren,
            "array_creation_expression": php_expr.lower_php_array,
            "assignment_expression": php_expr.lower_php_assignment_expr,
            "augmented_assignment_expression": php_expr.lower_php_augmented_assignment_expr,
            "cast_expression": php_expr.lower_php_cast,
            "conditional_expression": php_expr.lower_php_ternary,
            "throw_expression": php_expr.lower_php_throw_expr,
            "object_creation_expression": php_expr.lower_php_object_creation,
            "match_expression": php_expr.lower_php_match_expression,
            "arrow_function": php_expr.lower_php_arrow_function,
            "scoped_call_expression": php_expr.lower_php_scoped_call,
            "anonymous_function": php_expr.lower_php_anonymous_function,
            "nullsafe_member_access_expression": php_expr.lower_php_nullsafe_member_access,
            "class_constant_access_expression": php_expr.lower_php_class_constant_access,
            "scoped_property_access_expression": php_expr.lower_php_scoped_property_access,
            "yield_expression": php_expr.lower_php_yield,
            "reference_assignment_expression": php_expr.lower_php_reference_assignment,
            "heredoc": php_expr.lower_php_heredoc,
            "nowdoc": common_expr.lower_const_literal,
            "relative_scope": common_expr.lower_identifier,
            "dynamic_variable_name": php_expr.lower_php_dynamic_variable,
            "include_expression": php_expr.lower_php_include,
            "nullsafe_member_call_expression": php_expr.lower_php_nullsafe_method_call,
            "require_once_expression": php_expr.lower_php_include,
            "variadic_unpacking": php_expr.lower_php_variadic_unpacking,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "expression_statement": common_assign.lower_expression_statement,
            "return_statement": php_cf.lower_php_return,
            "echo_statement": php_cf.lower_php_echo,
            "if_statement": php_cf.lower_php_if,
            "while_statement": common_cf.lower_while,
            "for_statement": common_cf.lower_c_style_for,
            "foreach_statement": php_cf.lower_php_foreach,
            "function_definition": php_decl.lower_php_func_def,
            "method_declaration": php_decl.lower_php_method_decl,
            "class_declaration": php_decl.lower_php_class,
            "throw_expression": php_cf.lower_php_throw,
            "compound_statement": php_cf.lower_php_compound,
            "program": lambda ctx, node: ctx.lower_block(node),
            "break_statement": common_cf.lower_break,
            "continue_statement": common_cf.lower_continue,
            "try_statement": php_cf.lower_php_try,
            "switch_statement": php_cf.lower_php_switch,
            "do_statement": php_cf.lower_php_do,
            "namespace_definition": php_cf.lower_php_namespace,
            "interface_declaration": php_decl.lower_php_interface,
            "trait_declaration": php_decl.lower_php_trait,
            "function_static_declaration": php_decl.lower_php_function_static,
            "enum_declaration": php_decl.lower_php_enum,
            "named_label_statement": php_cf.lower_php_named_label,
            "goto_statement": php_cf.lower_php_goto,
            "property_declaration": php_decl.lower_php_property_declaration,
            "use_declaration": php_decl.lower_php_use_declaration,
            "namespace_use_declaration": php_decl.lower_php_namespace_use_declaration,
            "enum_case": php_decl.lower_php_enum_case,
            "global_declaration": php_decl.lower_php_global_declaration,
        }
