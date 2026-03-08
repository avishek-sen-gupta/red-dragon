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
from interpreter.frontends.java.node_types import JavaNodeType


class JavaFrontend(BaseFrontend):
    """Lowers a Java tree-sitter AST into flattened TAC IR."""

    BLOCK_SCOPED = True

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            for_initializer_field="init",
            attr_object_field="object",
            attr_attribute_field="field",
            attribute_node_type=JavaNodeType.FIELD_ACCESS,
            comment_types=frozenset(
                {
                    JavaNodeType.COMMENT,
                    JavaNodeType.LINE_COMMENT,
                    JavaNodeType.BLOCK_COMMENT,
                }
            ),
            noise_types=frozenset({JavaNodeType.NEWLINE}),
            block_node_types=frozenset({JavaNodeType.BLOCK, JavaNodeType.PROGRAM}),
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
            JavaNodeType.IDENTIFIER: common_expr.lower_identifier,
            JavaNodeType.DECIMAL_INTEGER_LITERAL: common_expr.lower_const_literal,
            JavaNodeType.HEX_INTEGER_LITERAL: common_expr.lower_const_literal,
            JavaNodeType.OCTAL_INTEGER_LITERAL: common_expr.lower_const_literal,
            JavaNodeType.BINARY_INTEGER_LITERAL: common_expr.lower_const_literal,
            JavaNodeType.DECIMAL_FLOATING_POINT_LITERAL: common_expr.lower_const_literal,
            JavaNodeType.STRING_LITERAL: common_expr.lower_const_literal,
            JavaNodeType.CHARACTER_LITERAL: common_expr.lower_const_literal,
            JavaNodeType.TRUE: common_expr.lower_canonical_true,
            JavaNodeType.FALSE: common_expr.lower_canonical_false,
            JavaNodeType.NULL_LITERAL: common_expr.lower_canonical_none,
            JavaNodeType.THIS: common_expr.lower_identifier,
            JavaNodeType.BINARY_EXPRESSION: common_expr.lower_binop,
            JavaNodeType.UNARY_EXPRESSION: common_expr.lower_unop,
            JavaNodeType.UPDATE_EXPRESSION: common_expr.lower_update_expr,
            JavaNodeType.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            JavaNodeType.METHOD_INVOCATION: java_expr.lower_method_invocation,
            JavaNodeType.OBJECT_CREATION_EXPRESSION: java_expr.lower_object_creation,
            JavaNodeType.FIELD_ACCESS: java_expr.lower_field_access,
            JavaNodeType.ARRAY_ACCESS: java_expr.lower_array_access,
            JavaNodeType.ARRAY_CREATION_EXPRESSION: java_expr.lower_array_creation,
            JavaNodeType.ARRAY_INITIALIZER: java_expr.lower_array_creation,
            JavaNodeType.ASSIGNMENT_EXPRESSION: java_expr.lower_assignment_expr,
            JavaNodeType.CAST_EXPRESSION: java_expr.lower_cast_expr,
            JavaNodeType.INSTANCEOF_EXPRESSION: java_expr.lower_instanceof,
            JavaNodeType.TERNARY_EXPRESSION: java_expr.lower_ternary,
            JavaNodeType.TYPE_IDENTIFIER: common_expr.lower_identifier,
            JavaNodeType.METHOD_REFERENCE: java_expr.lower_method_reference,
            JavaNodeType.LAMBDA_EXPRESSION: java_expr.lower_lambda,
            JavaNodeType.CLASS_LITERAL: java_expr.lower_class_literal,
            JavaNodeType.SUPER: common_expr.lower_identifier,
            JavaNodeType.SCOPED_IDENTIFIER: java_expr.lower_scoped_identifier,
            JavaNodeType.SWITCH_EXPRESSION: java_cf.lower_java_switch_expr,
            JavaNodeType.EXPRESSION_STATEMENT: java_expr.lower_expr_stmt_as_expr,
            JavaNodeType.THROW_STATEMENT: java_expr.lower_throw_as_expr,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            JavaNodeType.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            JavaNodeType.LOCAL_VARIABLE_DECLARATION: java_decl.lower_local_var_decl,
            JavaNodeType.RETURN_STATEMENT: common_assign.lower_return,
            JavaNodeType.IF_STATEMENT: java_cf.lower_if,
            JavaNodeType.WHILE_STATEMENT: common_cf.lower_while,
            JavaNodeType.FOR_STATEMENT: common_cf.lower_c_style_for,
            JavaNodeType.ENHANCED_FOR_STATEMENT: java_cf.lower_enhanced_for,
            JavaNodeType.METHOD_DECLARATION: java_decl.lower_method_decl_stmt,
            JavaNodeType.CLASS_DECLARATION: java_decl.lower_class_def,
            JavaNodeType.INTERFACE_DECLARATION: java_decl.lower_interface_decl,
            JavaNodeType.ENUM_DECLARATION: java_decl.lower_enum_decl,
            JavaNodeType.THROW_STATEMENT: java_cf.lower_throw,
            JavaNodeType.IMPORT_DECLARATION: lambda ctx, node: None,
            JavaNodeType.PACKAGE_DECLARATION: lambda ctx, node: None,
            JavaNodeType.BREAK_STATEMENT: common_cf.lower_break,
            JavaNodeType.CONTINUE_STATEMENT: common_cf.lower_continue,
            JavaNodeType.SWITCH_EXPRESSION: java_cf.lower_java_switch,
            JavaNodeType.TRY_STATEMENT: java_cf.lower_try,
            JavaNodeType.TRY_WITH_RESOURCES_STATEMENT: java_cf.lower_try,
            JavaNodeType.DO_STATEMENT: java_cf.lower_do_statement,
            JavaNodeType.ASSERT_STATEMENT: java_cf.lower_assert_statement,
            JavaNodeType.LABELED_STATEMENT: java_cf.lower_labeled_statement,
            JavaNodeType.SYNCHRONIZED_STATEMENT: java_cf.lower_synchronized_statement,
            JavaNodeType.EXPLICIT_CONSTRUCTOR_INVOCATION: java_cf.lower_explicit_constructor_invocation,
            JavaNodeType.ANNOTATION_TYPE_DECLARATION: java_decl.lower_annotation_type_decl,
            JavaNodeType.RECORD_DECLARATION: java_decl.lower_record_decl,
        }
