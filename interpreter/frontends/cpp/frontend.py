"""CppFrontend — thin orchestrator that extends CFrontend with C++-specific handlers."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends.c.frontend import CFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.cpp import expressions as cpp_expr
from interpreter.frontends.cpp import control_flow as cpp_cf
from interpreter.frontends.cpp import declarations as cpp_decl
from interpreter.frontends.cpp.node_types import CppNodeType


class CppFrontend(CFrontend):
    """Lowers a C++ tree-sitter AST into flattened TAC IR.

    Extends CFrontend with C++-specific constructs: classes, namespaces,
    templates, new/delete, lambdas, and reference types.
    """

    def _build_constants(self) -> GrammarConstants:
        base = super()._build_constants()
        # C++ struct bodies are handled via cpp_class_body, so add
        # field_declaration_list to block types if needed
        return GrammarConstants(
            attr_object_field=base.attr_object_field,
            attr_attribute_field=base.attr_attribute_field,
            attribute_node_type=base.attribute_node_type,
            subscript_value_field=base.subscript_value_field,
            subscript_index_field=base.subscript_index_field,
            comment_types=base.comment_types,
            noise_types=base.noise_types,
            block_node_types=base.block_node_types,
            none_literal=base.none_literal,
            true_literal=base.true_literal,
            false_literal=base.false_literal,
            default_return_value=base.default_return_value,
        )

    def _build_type_map(self) -> dict[str, str]:
        base = super()._build_type_map()
        base.update(
            {
                "bool": "Bool",
                "void": "Any",
                "string": "String",
                "std::string": "String",
            }
        )
        return base

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        dispatch = super()._build_expr_dispatch()
        dispatch.update(
            {
                CppNodeType.NEW_EXPRESSION: cpp_expr.lower_new_expr,
                CppNodeType.DELETE_EXPRESSION: cpp_expr.lower_delete_expr,
                CppNodeType.LAMBDA_EXPRESSION: cpp_expr.lower_lambda,
                CppNodeType.TEMPLATE_FUNCTION: common_expr.lower_identifier,
                CppNodeType.QUALIFIED_IDENTIFIER: cpp_expr.lower_qualified_id,
                CppNodeType.SCOPED_IDENTIFIER: cpp_expr.lower_qualified_id,
                CppNodeType.SCOPE_RESOLUTION: cpp_expr.lower_qualified_id,
                CppNodeType.CALL_EXPRESSION: cpp_expr.lower_cpp_call,
                CppNodeType.THIS: common_expr.lower_identifier,
                CppNodeType.CONDITION_CLAUSE: cpp_expr.lower_condition_clause,
                CppNodeType.NULLPTR: common_expr.lower_canonical_none,
                CppNodeType.USER_DEFINED_LITERAL: common_expr.lower_const_literal,
                CppNodeType.RAW_STRING_LITERAL: common_expr.lower_const_literal,
                CppNodeType.THROW_EXPRESSION: cpp_expr.lower_throw_expr,
                CppNodeType.STATIC_CAST_EXPRESSION: cpp_expr.lower_cpp_cast,
                CppNodeType.DYNAMIC_CAST_EXPRESSION: cpp_expr.lower_cpp_cast,
                CppNodeType.REINTERPRET_CAST_EXPRESSION: cpp_expr.lower_cpp_cast,
                CppNodeType.CONST_CAST_EXPRESSION: cpp_expr.lower_cpp_cast,
                # Override C subscript with C++ version
                CppNodeType.SUBSCRIPT_EXPRESSION: cpp_expr.lower_cpp_subscript_expr,
                # Override C assignment with C++ version
                CppNodeType.ASSIGNMENT_EXPRESSION: cpp_expr.lower_cpp_assignment_expr,
            }
        )
        return dispatch

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        dispatch = super()._build_stmt_dispatch()
        dispatch.update(
            {
                CppNodeType.CLASS_SPECIFIER: cpp_decl.lower_class_specifier,
                CppNodeType.NAMESPACE_DEFINITION: cpp_cf.lower_namespace_def,
                CppNodeType.TEMPLATE_DECLARATION: cpp_cf.lower_template_decl,
                CppNodeType.USING_DECLARATION: lambda ctx, _: None,
                CppNodeType.ACCESS_SPECIFIER: lambda ctx, _: None,
                CppNodeType.ALIAS_DECLARATION: lambda ctx, _: None,
                CppNodeType.STATIC_ASSERT_DECLARATION: lambda ctx, _: None,
                CppNodeType.FRIEND_DECLARATION: lambda ctx, _: None,
                CppNodeType.TRY_STATEMENT: cpp_cf.lower_try,
                CppNodeType.THROW_STATEMENT: cpp_cf.lower_throw,
                CppNodeType.FOR_RANGE_LOOP: cpp_cf.lower_range_for,
                CppNodeType.CONCEPT_DEFINITION: lambda ctx, _: None,
                # Override C handlers with C++ versions
                CppNodeType.IF_STATEMENT: cpp_cf.lower_cpp_if,
                CppNodeType.WHILE_STATEMENT: cpp_cf.lower_cpp_while,
                CppNodeType.FUNCTION_DEFINITION: cpp_decl.lower_cpp_function_def,
                CppNodeType.STRUCT_SPECIFIER: cpp_decl.lower_cpp_struct_def,
                # Override C++ declaration handler for struct types
                CppNodeType.DECLARATION: cpp_decl.lower_cpp_declaration,
            }
        )
        return dispatch

    def _extract_symbols(self, root) -> "SymbolTable":
        from interpreter.frontends.cpp.declarations import extract_cpp_symbols
        from interpreter.frontends.symbol_table import SymbolTable

        return extract_cpp_symbols(root)
