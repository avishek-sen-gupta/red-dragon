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
                "new_expression": cpp_expr.lower_new_expr,
                "delete_expression": cpp_expr.lower_delete_expr,
                "lambda_expression": cpp_expr.lower_lambda,
                "template_function": common_expr.lower_identifier,
                "qualified_identifier": cpp_expr.lower_qualified_id,
                "scoped_identifier": cpp_expr.lower_qualified_id,
                "scope_resolution": cpp_expr.lower_qualified_id,
                "this": common_expr.lower_identifier,
                "condition_clause": cpp_expr.lower_condition_clause,
                "nullptr": common_expr.lower_canonical_none,
                "user_defined_literal": common_expr.lower_const_literal,
                "raw_string_literal": common_expr.lower_const_literal,
                "throw_expression": cpp_expr.lower_throw_expr,
                "static_cast_expression": cpp_expr.lower_cpp_cast,
                "dynamic_cast_expression": cpp_expr.lower_cpp_cast,
                "reinterpret_cast_expression": cpp_expr.lower_cpp_cast,
                "const_cast_expression": cpp_expr.lower_cpp_cast,
                # Override C subscript with C++ version
                "subscript_expression": cpp_expr.lower_cpp_subscript_expr,
                # Override C assignment with C++ version
                "assignment_expression": cpp_expr.lower_cpp_assignment_expr,
            }
        )
        return dispatch

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        dispatch = super()._build_stmt_dispatch()
        dispatch.update(
            {
                "class_specifier": cpp_decl.lower_class_specifier,
                "namespace_definition": cpp_cf.lower_namespace_def,
                "template_declaration": cpp_cf.lower_template_decl,
                "using_declaration": lambda ctx, _: None,
                "access_specifier": lambda ctx, _: None,
                "alias_declaration": lambda ctx, _: None,
                "static_assert_declaration": lambda ctx, _: None,
                "friend_declaration": lambda ctx, _: None,
                "try_statement": cpp_cf.lower_try,
                "throw_statement": cpp_cf.lower_throw,
                "for_range_loop": cpp_cf.lower_range_for,
                "concept_definition": lambda ctx, _: None,
                # Override C handlers with C++ versions
                "if_statement": cpp_cf.lower_cpp_if,
                "while_statement": cpp_cf.lower_cpp_while,
                "function_definition": cpp_decl.lower_cpp_function_def,
                "struct_specifier": cpp_decl.lower_cpp_struct_def,
                # Override C++ declaration handler for struct types
                "declaration": cpp_decl.lower_cpp_declaration,
            }
        )
        return dispatch
