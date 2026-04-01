# pyright: standard
"""PhpFrontend -- thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Any, Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.register import Register
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.php import expressions as php_expr
from interpreter.frontends.php import control_flow as php_cf
from interpreter.frontends.php import declarations as php_decl
from interpreter.frontends.php.node_types import PHPNodeType


class PhpFrontend(BaseFrontend):
    """Lowers a PHP tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="object",
            attr_attribute_field="name",
            attribute_node_type=PHPNodeType.MEMBER_ACCESS_EXPRESSION,
            comment_types=frozenset({PHPNodeType.COMMENT}),
            noise_types=frozenset(
                {
                    PHPNodeType.PHP_TAG,
                    PHPNodeType.TEXT_INTERPOLATION,
                    PHPNodeType.PHP_END_TAG,
                    PHPNodeType.NEWLINE,
                }
            ),
            block_node_types=frozenset(
                {PHPNodeType.COMPOUND_STATEMENT, PHPNodeType.PROGRAM}
            ),
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

    def _build_expr_dispatch(
        self,
    ) -> dict[str, Callable[[TreeSitterEmitContext, Any], Register]]:
        return {  # type: ignore[return-value]  # see red-dragon-rke4
            PHPNodeType.VARIABLE_NAME: php_expr.lower_php_variable,
            PHPNodeType.NAME: common_expr.lower_identifier,
            PHPNodeType.INTEGER: common_expr.lower_const_literal,
            PHPNodeType.FLOAT: common_expr.lower_const_literal,
            PHPNodeType.STRING: common_expr.lower_const_literal,
            PHPNodeType.ENCAPSED_STRING: php_expr.lower_php_encapsed_string,
            PHPNodeType.BOOLEAN: common_expr.lower_canonical_bool,
            PHPNodeType.NULL: common_expr.lower_canonical_none,
            PHPNodeType.BINARY_EXPRESSION: common_expr.lower_binop,
            PHPNodeType.UNARY_OP_EXPRESSION: common_expr.lower_unop,
            PHPNodeType.UPDATE_EXPRESSION: common_expr.lower_update_expr,
            PHPNodeType.FUNCTION_CALL_EXPRESSION: php_expr.lower_php_func_call,
            PHPNodeType.MEMBER_CALL_EXPRESSION: php_expr.lower_php_method_call,
            PHPNodeType.MEMBER_ACCESS_EXPRESSION: php_expr.lower_php_member_access,
            PHPNodeType.SUBSCRIPT_EXPRESSION: php_expr.lower_php_subscript,
            PHPNodeType.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            PHPNodeType.ARRAY_CREATION_EXPRESSION: php_expr.lower_php_array,
            PHPNodeType.ASSIGNMENT_EXPRESSION: php_expr.lower_php_assignment_expr,
            PHPNodeType.AUGMENTED_ASSIGNMENT_EXPRESSION: php_expr.lower_php_augmented_assignment_expr,
            PHPNodeType.CAST_EXPRESSION: php_expr.lower_php_cast,
            PHPNodeType.CONDITIONAL_EXPRESSION: php_expr.lower_php_ternary,
            PHPNodeType.THROW_EXPRESSION: php_expr.lower_php_throw_expr,
            PHPNodeType.OBJECT_CREATION_EXPRESSION: php_expr.lower_php_object_creation,
            PHPNodeType.MATCH_EXPRESSION: php_expr.lower_php_match_expression,
            PHPNodeType.ARROW_FUNCTION: php_expr.lower_php_arrow_function,
            PHPNodeType.SCOPED_CALL_EXPRESSION: php_expr.lower_php_scoped_call,
            PHPNodeType.ANONYMOUS_FUNCTION: php_expr.lower_php_anonymous_function,
            PHPNodeType.NULLSAFE_MEMBER_ACCESS_EXPRESSION: php_expr.lower_php_nullsafe_member_access,
            PHPNodeType.CLASS_CONSTANT_ACCESS_EXPRESSION: php_expr.lower_php_class_constant_access,
            PHPNodeType.SCOPED_PROPERTY_ACCESS_EXPRESSION: php_expr.lower_php_scoped_property_access,
            PHPNodeType.YIELD_EXPRESSION: php_expr.lower_php_yield,
            PHPNodeType.REFERENCE_ASSIGNMENT_EXPRESSION: php_expr.lower_php_reference_assignment,
            PHPNodeType.HEREDOC: php_expr.lower_php_heredoc,
            PHPNodeType.NOWDOC: common_expr.lower_const_literal,
            PHPNodeType.RELATIVE_SCOPE: common_expr.lower_identifier,
            PHPNodeType.DYNAMIC_VARIABLE_NAME: php_expr.lower_php_dynamic_variable,
            PHPNodeType.INCLUDE_EXPRESSION: php_expr.lower_php_include,
            PHPNodeType.NULLSAFE_MEMBER_CALL_EXPRESSION: php_expr.lower_php_nullsafe_method_call,
            PHPNodeType.REQUIRE_ONCE_EXPRESSION: php_expr.lower_php_include,
            PHPNodeType.VARIADIC_UNPACKING: php_expr.lower_php_variadic_unpacking,  # type: ignore[dict-item]  # see red-dragon-rke4
            PHPNodeType.PRINT_INTRINSIC: php_expr.lower_php_print_intrinsic,
            PHPNodeType.CLONE_EXPRESSION: php_expr.lower_php_clone_expression,
            PHPNodeType.ERROR_SUPPRESSION_EXPRESSION: php_expr.lower_php_error_suppression,
            PHPNodeType.SEQUENCE_EXPRESSION: php_expr.lower_php_sequence_expression,
            PHPNodeType.INCLUDE_ONCE_EXPRESSION: php_expr.lower_php_include,
            PHPNodeType.REQUIRE_EXPRESSION: php_expr.lower_php_include,
        }

    def _build_stmt_dispatch(
        self,
    ) -> dict[str, Callable[[TreeSitterEmitContext, Any], None]]:
        return {
            PHPNodeType.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            PHPNodeType.RETURN_STATEMENT: php_cf.lower_php_return,
            PHPNodeType.ECHO_STATEMENT: php_cf.lower_php_echo,
            PHPNodeType.IF_STATEMENT: php_cf.lower_php_if,
            PHPNodeType.WHILE_STATEMENT: common_cf.lower_while,
            PHPNodeType.FOR_STATEMENT: common_cf.lower_c_style_for,
            PHPNodeType.FOREACH_STATEMENT: php_cf.lower_php_foreach,
            PHPNodeType.FUNCTION_DEFINITION: php_decl.lower_php_func_def,
            PHPNodeType.METHOD_DECLARATION: php_decl.lower_php_method_decl,
            PHPNodeType.CLASS_DECLARATION: php_decl.lower_php_class,
            PHPNodeType.THROW_EXPRESSION: php_cf.lower_php_throw,
            PHPNodeType.COMPOUND_STATEMENT: php_cf.lower_php_compound,
            PHPNodeType.PROGRAM: lambda ctx, node: ctx.lower_block(node),
            PHPNodeType.BREAK_STATEMENT: common_cf.lower_break,
            PHPNodeType.CONTINUE_STATEMENT: common_cf.lower_continue,
            PHPNodeType.TRY_STATEMENT: php_cf.lower_php_try,
            PHPNodeType.SWITCH_STATEMENT: php_cf.lower_php_switch,
            PHPNodeType.DO_STATEMENT: php_cf.lower_php_do,
            PHPNodeType.NAMESPACE_DEFINITION: php_cf.lower_php_namespace,
            PHPNodeType.INTERFACE_DECLARATION: php_decl.lower_php_interface,
            PHPNodeType.TRAIT_DECLARATION: php_decl.lower_php_trait,
            PHPNodeType.FUNCTION_STATIC_DECLARATION: php_decl.lower_php_function_static,
            PHPNodeType.ENUM_DECLARATION: php_decl.lower_php_enum,
            PHPNodeType.NAMED_LABEL_STATEMENT: php_cf.lower_php_named_label,
            PHPNodeType.GOTO_STATEMENT: php_cf.lower_php_goto,
            PHPNodeType.PROPERTY_DECLARATION: php_decl.lower_php_property_declaration,
            PHPNodeType.USE_DECLARATION: php_decl.lower_php_use_declaration,
            PHPNodeType.NAMESPACE_USE_DECLARATION: php_decl.lower_php_namespace_use_declaration,
            PHPNodeType.ENUM_CASE: php_decl.lower_php_enum_case,
            PHPNodeType.GLOBAL_DECLARATION: php_decl.lower_php_global_declaration,
            PHPNodeType.CONST_DECLARATION: php_decl.lower_php_const_declaration,
            PHPNodeType.EXIT_STATEMENT: lambda ctx, node: None,
            PHPNodeType.DECLARE_STATEMENT: lambda ctx, node: None,
            PHPNodeType.UNSET_STATEMENT: lambda ctx, node: None,
        }

    def _extract_symbols(self, root) -> SymbolTable:
        from interpreter.frontends.php.declarations import extract_php_symbols

        return extract_php_symbols(root)
