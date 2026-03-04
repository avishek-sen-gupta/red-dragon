"""PythonFrontend -- thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.common import declarations as common_decl
from interpreter.frontends.python import expressions as py_expr
from interpreter.frontends.python import control_flow as py_cf
from interpreter.frontends.python import assignments as py_assign


class PythonFrontend(BaseFrontend):
    """Lowers a Python tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="object",
            attr_attribute_field="attribute",
            attribute_node_type="attribute",
            subscript_value_field="value",
            subscript_index_field="subscript",
            comment_types=frozenset({"comment"}),
            noise_types=frozenset({"newline", "\n"}),
            block_node_types=frozenset({"block", "module"}),
            paren_expr_type="parenthesized_expression",
        )

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "identifier": common_expr.lower_identifier,
            "integer": common_expr.lower_const_literal,
            "float": common_expr.lower_const_literal,
            "string": py_expr.lower_python_string,
            "concatenated_string": common_expr.lower_const_literal,
            "true": common_expr.lower_canonical_true,
            "false": common_expr.lower_canonical_false,
            "none": common_expr.lower_canonical_none,
            "binary_operator": common_expr.lower_binop,
            "boolean_operator": common_expr.lower_binop,
            "comparison_operator": common_expr.lower_comparison,
            "unary_operator": common_expr.lower_unop,
            "not_operator": common_expr.lower_unop,
            "call": py_expr.lower_call,
            "attribute": common_expr.lower_attribute,
            "subscript": common_expr.lower_subscript,
            "parenthesized_expression": common_expr.lower_paren,
            "list": common_expr.lower_list_literal,
            "dictionary": common_expr.lower_dict_literal,
            "tuple": py_expr.lower_tuple_literal,
            "conditional_expression": py_expr.lower_conditional_expr,
            "list_comprehension": py_expr.lower_list_comprehension,
            "dictionary_comprehension": py_expr.lower_dict_comprehension,
            "lambda": py_expr.lower_lambda,
            "generator_expression": py_expr.lower_generator_expression,
            "set_comprehension": py_expr.lower_set_comprehension,
            "set": py_expr.lower_set_literal,
            "yield": py_expr.lower_yield,
            "await": py_expr.lower_await,
            "named_expression": py_expr.lower_named_expression,
            "slice": py_expr.lower_slice,
            "keyword_separator": py_expr.lower_noop_expr,
            "positional_separator": py_expr.lower_noop_expr,
            "list_pattern": py_expr.lower_list_pattern,
            "case_pattern": py_expr.lower_case_pattern,
            "interpolation": py_expr.lower_interpolation,
            "format_specifier": common_expr.lower_const_literal,
            "string_content": common_expr.lower_const_literal,
            "string_start": common_expr.lower_const_literal,
            "string_end": common_expr.lower_const_literal,
            "type_conversion": common_expr.lower_const_literal,
            "ellipsis": common_expr.lower_const_literal,
            "list_splat": py_expr.lower_splat_expr,
            "dictionary_splat": py_expr.lower_splat_expr,
            "expression_list": py_expr.lower_tuple_literal,
            "dotted_name": common_expr.lower_identifier,
            "dict_pattern": py_expr.lower_dict_pattern,
            "splat_pattern": py_expr.lower_splat_expr,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "expression_statement": common_assign.lower_expression_statement,
            "assignment": py_assign.lower_assignment,
            "augmented_assignment": py_assign.lower_augmented_assignment,
            "return_statement": common_assign.lower_return,
            "if_statement": py_cf.lower_python_if,
            "while_statement": common_cf.lower_while,
            "for_statement": py_cf.lower_for,
            "function_definition": common_decl.lower_function_def,
            "class_definition": common_decl.lower_class_def,
            "raise_statement": py_cf.lower_raise,
            "try_statement": py_cf.lower_try,
            "pass_statement": lambda ctx, node: None,
            "break_statement": common_cf.lower_break,
            "continue_statement": common_cf.lower_continue,
            "with_statement": py_cf.lower_with,
            "decorated_definition": py_cf.lower_decorated_def,
            "assert_statement": py_cf.lower_assert,
            "global_statement": lambda ctx, node: None,
            "nonlocal_statement": lambda ctx, node: None,
            "delete_statement": py_cf.lower_delete,
            "import_statement": py_cf.lower_import,
            "import_from_statement": py_cf.lower_import_from,
            "match_statement": py_cf.lower_match,
            "type_alias_statement": lambda ctx, node: None,
        }
