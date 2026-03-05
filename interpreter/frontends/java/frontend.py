"""JavaFrontend — thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.java import expressions as java_expr
from interpreter.frontends.java import control_flow as java_cf
from interpreter.frontends.java import declarations as java_decl


class JavaFrontend(BaseFrontend):
    """Lowers a Java tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="object",
            attr_attribute_field="field",
            attribute_node_type="field_access",
            comment_types=frozenset({"comment", "line_comment", "block_comment"}),
            noise_types=frozenset({"\n"}),
            block_node_types=frozenset({"block", "program"}),
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "int": "Int",
            "long": "Int",
            "short": "Int",
            "byte": "Int",
            "char": "Int",
            "Integer": "Int",
            "Long": "Int",
            "Short": "Int",
            "Byte": "Int",
            "Character": "Int",
            "double": "Float",
            "float": "Float",
            "Double": "Float",
            "Float": "Float",
            "boolean": "Bool",
            "Boolean": "Bool",
            "String": "String",
            "void": "Any",
        }

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "identifier": common_expr.lower_identifier,
            "decimal_integer_literal": common_expr.lower_const_literal,
            "hex_integer_literal": common_expr.lower_const_literal,
            "octal_integer_literal": common_expr.lower_const_literal,
            "binary_integer_literal": common_expr.lower_const_literal,
            "decimal_floating_point_literal": common_expr.lower_const_literal,
            "string_literal": common_expr.lower_const_literal,
            "character_literal": common_expr.lower_const_literal,
            "true": common_expr.lower_canonical_true,
            "false": common_expr.lower_canonical_false,
            "null_literal": common_expr.lower_canonical_none,
            "this": common_expr.lower_identifier,
            "binary_expression": common_expr.lower_binop,
            "unary_expression": common_expr.lower_unop,
            "update_expression": common_expr.lower_update_expr,
            "parenthesized_expression": common_expr.lower_paren,
            "method_invocation": java_expr.lower_method_invocation,
            "object_creation_expression": java_expr.lower_object_creation,
            "field_access": java_expr.lower_field_access,
            "array_access": java_expr.lower_array_access,
            "array_creation_expression": java_expr.lower_array_creation,
            "array_initializer": java_expr.lower_array_creation,
            "assignment_expression": java_expr.lower_assignment_expr,
            "cast_expression": java_expr.lower_cast_expr,
            "instanceof_expression": java_expr.lower_instanceof,
            "ternary_expression": java_expr.lower_ternary,
            "type_identifier": common_expr.lower_identifier,
            "method_reference": java_expr.lower_method_reference,
            "lambda_expression": java_expr.lower_lambda,
            "class_literal": java_expr.lower_class_literal,
            "super": common_expr.lower_identifier,
            "scoped_identifier": java_expr.lower_scoped_identifier,
            "switch_expression": java_cf.lower_java_switch_expr,
            "expression_statement": java_expr.lower_expr_stmt_as_expr,
            "throw_statement": java_expr.lower_throw_as_expr,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "expression_statement": common_assign.lower_expression_statement,
            "local_variable_declaration": java_decl.lower_local_var_decl,
            "return_statement": common_assign.lower_return,
            "if_statement": java_cf.lower_if,
            "while_statement": common_cf.lower_while,
            "for_statement": common_cf.lower_c_style_for,
            "enhanced_for_statement": java_cf.lower_enhanced_for,
            "method_declaration": java_decl.lower_method_decl_stmt,
            "class_declaration": java_decl.lower_class_def,
            "interface_declaration": java_decl.lower_interface_decl,
            "enum_declaration": java_decl.lower_enum_decl,
            "throw_statement": java_cf.lower_throw,
            "import_declaration": lambda ctx, node: None,
            "package_declaration": lambda ctx, node: None,
            "break_statement": common_cf.lower_break,
            "continue_statement": common_cf.lower_continue,
            "switch_expression": java_cf.lower_java_switch,
            "try_statement": java_cf.lower_try,
            "try_with_resources_statement": java_cf.lower_try,
            "do_statement": java_cf.lower_do_statement,
            "assert_statement": java_cf.lower_assert_statement,
            "labeled_statement": java_cf.lower_labeled_statement,
            "synchronized_statement": java_cf.lower_synchronized_statement,
            "explicit_constructor_invocation": java_cf.lower_explicit_constructor_invocation,
            "annotation_type_declaration": java_decl.lower_annotation_type_decl,
            "record_declaration": java_decl.lower_record_decl,
        }
