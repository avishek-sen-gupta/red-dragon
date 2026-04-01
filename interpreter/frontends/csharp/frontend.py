# pyright: standard
"""CSharpFrontend -- thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Any, Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.register import Register
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.csharp import expressions as csharp_expr
from interpreter.frontends.csharp import control_flow as csharp_cf
from interpreter.frontends.csharp import declarations as csharp_decl
from interpreter.frontends.csharp.node_types import CSharpNodeType as NT


class CSharpFrontend(BaseFrontend):
    """Lowers a C# tree-sitter AST into flattened TAC IR."""

    BLOCK_SCOPED = True

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="expression",
            attr_attribute_field="name",
            attribute_node_type=NT.MEMBER_ACCESS_EXPRESSION,
            comment_types=frozenset({NT.COMMENT}),
            noise_types=frozenset({NT.NEWLINE, NT.USING_DIRECTIVE}),
            block_node_types=frozenset(
                {NT.BLOCK, NT.COMPILATION_UNIT, NT.DECLARATION_LIST}
            ),
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "int": "Int",
            "long": "Int",
            "short": "Int",
            "byte": "Int",
            "sbyte": "Int",
            "uint": "Int",
            "ulong": "Int",
            "ushort": "Int",
            "char": "Int",
            "Int32": "Int",
            "Int64": "Int",
            "float": "Float",
            "double": "Float",
            "decimal": "Float",
            "Single": "Float",
            "Double": "Float",
            "Decimal": "Float",
            "bool": "Bool",
            "Boolean": "Bool",
            "string": "String",
            "String": "String",
            "void": "Any",
            "object": "Object",
            "Object": "Object",
        }

    def _build_expr_dispatch(
        self,
    ) -> dict[str, Callable[[TreeSitterEmitContext, Any], Register]]:
        return {
            NT.IDENTIFIER: csharp_expr.lower_csharp_identifier,
            NT.INTEGER_LITERAL: common_expr.lower_const_literal,
            NT.REAL_LITERAL: common_expr.lower_const_literal,
            NT.STRING_LITERAL: common_expr.lower_const_literal,
            NT.CHARACTER_LITERAL: common_expr.lower_const_literal,
            NT.VERBATIM_STRING_LITERAL: common_expr.lower_const_literal,
            NT.CONSTANT_PATTERN: common_expr.lower_const_literal,
            NT.DECLARATION_PATTERN: csharp_expr.lower_declaration_pattern,
            NT.DECLARATION_EXPRESSION: csharp_expr.lower_declaration_expression,
            NT.REF_EXPRESSION: csharp_expr.lower_ref_expression,
            NT.BOOLEAN_LITERAL: common_expr.lower_canonical_bool,
            NT.NULL_LITERAL: common_expr.lower_canonical_none,
            NT.THIS_EXPRESSION: common_expr.lower_identifier,
            NT.THIS: common_expr.lower_identifier,
            NT.BINARY_EXPRESSION: common_expr.lower_binop,
            NT.PREFIX_UNARY_EXPRESSION: common_expr.lower_unop,
            NT.POSTFIX_UNARY_EXPRESSION: common_expr.lower_update_expr,
            NT.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            NT.INVOCATION_EXPRESSION: csharp_expr.lower_invocation,
            NT.OBJECT_CREATION_EXPRESSION: csharp_expr.lower_object_creation,
            NT.MEMBER_ACCESS_EXPRESSION: csharp_expr.lower_member_access,
            NT.ELEMENT_ACCESS_EXPRESSION: csharp_expr.lower_element_access,
            NT.INITIALIZER_EXPRESSION: csharp_expr.lower_initializer_expr,
            NT.ASSIGNMENT_EXPRESSION: csharp_expr.lower_assignment_expr,
            NT.CAST_EXPRESSION: csharp_expr.lower_cast_expr,
            NT.CONDITIONAL_EXPRESSION: csharp_expr.lower_ternary,
            NT.INTERPOLATED_STRING_EXPRESSION: csharp_expr.lower_csharp_interpolated_string,
            NT.TYPE_IDENTIFIER: common_expr.lower_identifier,
            NT.PREDEFINED_TYPE: common_expr.lower_identifier,
            NT.TYPEOF_EXPRESSION: csharp_expr.lower_typeof,
            NT.IS_EXPRESSION: csharp_expr.lower_is_expr,
            NT.AS_EXPRESSION: csharp_expr.lower_as_expr,
            NT.LAMBDA_EXPRESSION: csharp_expr.lower_lambda,
            NT.ARRAY_CREATION_EXPRESSION: csharp_expr.lower_array_creation,
            NT.IMPLICIT_ARRAY_CREATION_EXPRESSION: csharp_expr.lower_array_creation,
            NT.IMPLICIT_OBJECT_CREATION_EXPRESSION: csharp_expr.lower_implicit_object_creation,
            NT.ANONYMOUS_OBJECT_CREATION_EXPRESSION: csharp_expr.lower_anonymous_object_creation,
            NT.WITH_EXPRESSION: csharp_expr.lower_with_expression,
            NT.QUERY_EXPRESSION: csharp_expr.lower_query_expression,
            NT.FROM_CLAUSE: csharp_expr.lower_linq_clause,
            NT.SELECT_CLAUSE: csharp_expr.lower_linq_clause,
            NT.WHERE_CLAUSE: csharp_expr.lower_linq_clause,
            NT.AWAIT_EXPRESSION: csharp_expr.lower_await_expr,
            NT.SWITCH_EXPRESSION: csharp_cf.lower_switch_expr,
            NT.CONDITIONAL_ACCESS_EXPRESSION: csharp_expr.lower_conditional_access,
            NT.MEMBER_BINDING_EXPRESSION: csharp_expr.lower_member_binding,
            NT.TUPLE_EXPRESSION: csharp_expr.lower_tuple_expr,
            NT.IS_PATTERN_EXPRESSION: csharp_expr.lower_is_pattern_expr,
            NT.THROW_EXPRESSION: csharp_cf.lower_throw_expr,
            NT.DEFAULT_EXPRESSION: common_expr.lower_const_literal,
            NT.SIZEOF_EXPRESSION: common_expr.lower_const_literal,
            NT.CHECKED_EXPRESSION: csharp_expr.lower_checked_expr,
            NT.RANGE_EXPRESSION: csharp_expr.lower_range_expr,
        }

    def _build_stmt_dispatch(
        self,
    ) -> dict[str, Callable[[TreeSitterEmitContext, Any], None]]:
        return {
            NT.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            NT.LOCAL_DECLARATION_STATEMENT: csharp_decl.lower_local_decl_stmt,
            NT.RETURN_STATEMENT: common_assign.lower_return,
            NT.IF_STATEMENT: csharp_cf.lower_if,
            NT.WHILE_STATEMENT: common_cf.lower_while,
            NT.FOR_STATEMENT: common_cf.lower_c_style_for,
            NT.FOREACH_STATEMENT: csharp_cf.lower_foreach,
            NT.METHOD_DECLARATION: csharp_decl.lower_method_decl,
            NT.CLASS_DECLARATION: csharp_decl.lower_class_def,
            NT.STRUCT_DECLARATION: csharp_decl.lower_class_def,
            NT.INTERFACE_DECLARATION: csharp_decl.lower_interface_decl,
            NT.ENUM_DECLARATION: csharp_decl.lower_enum_decl,
            NT.NAMESPACE_DECLARATION: csharp_decl.lower_namespace,
            NT.FILE_SCOPED_NAMESPACE_DECLARATION: csharp_decl.lower_file_scoped_namespace,
            NT.THROW_STATEMENT: csharp_cf.lower_throw,
            NT.BLOCK: lambda ctx, node: ctx.lower_block(node),
            NT.GLOBAL_STATEMENT: csharp_cf.lower_global_statement,
            NT.USING_DIRECTIVE: lambda ctx, node: None,
            NT.DO_STATEMENT: csharp_cf.lower_do_while,
            NT.SWITCH_STATEMENT: csharp_cf.lower_switch,
            NT.TRY_STATEMENT: csharp_cf.lower_try,
            NT.CONSTRUCTOR_DECLARATION: csharp_decl.lower_constructor_decl,
            NT.FIELD_DECLARATION: csharp_decl.lower_field_decl,
            NT.PROPERTY_DECLARATION: csharp_decl.lower_property_decl,
            NT.BREAK_STATEMENT: common_cf.lower_break,
            NT.CONTINUE_STATEMENT: common_cf.lower_continue,
            NT.LOCK_STATEMENT: csharp_cf.lower_lock_stmt,
            NT.USING_STATEMENT: csharp_cf.lower_using_stmt,
            NT.CHECKED_STATEMENT: csharp_cf.lower_checked_stmt,
            NT.FIXED_STATEMENT: csharp_cf.lower_fixed_stmt,
            NT.EVENT_FIELD_DECLARATION: csharp_decl.lower_event_field_decl,
            NT.EVENT_DECLARATION: csharp_decl.lower_event_decl,
            NT.RECORD_DECLARATION: csharp_decl.lower_class_def,
            NT.RECORD_STRUCT_DECLARATION: csharp_decl.lower_class_def,
            NT.VARIABLE_DECLARATION: csharp_decl.lower_variable_declaration,
            NT.DELEGATE_DECLARATION: csharp_decl.lower_delegate_declaration,
            NT.LOCAL_FUNCTION_STATEMENT: csharp_decl.lower_local_function_stmt,
            NT.YIELD_STATEMENT: csharp_cf.lower_yield_stmt,
            NT.EMPTY_STATEMENT: lambda ctx, node: None,
            NT.GOTO_STATEMENT: csharp_cf.lower_goto,
            NT.LABELED_STATEMENT: csharp_cf.lower_labeled_stmt,
        }

    def _extract_symbols(self, root) -> SymbolTable:
        from interpreter.frontends.csharp.declarations import extract_csharp_symbols

        return extract_csharp_symbols(root)
