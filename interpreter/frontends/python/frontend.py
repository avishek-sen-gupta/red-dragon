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
from interpreter.frontends.python import declarations as py_decl
from interpreter.frontends.python.node_types import PythonNodeType


class PythonFrontend(BaseFrontend):
    """Lowers a Python tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="object",
            attr_attribute_field="attribute",
            attribute_node_type="attribute",
            subscript_value_field="value",
            subscript_index_field="subscript",
            comment_types=frozenset({PythonNodeType.COMMENT}),
            noise_types=frozenset(
                {PythonNodeType.NEWLINE, PythonNodeType.NEWLINE_CHAR}
            ),
            block_node_types=frozenset({PythonNodeType.BLOCK, PythonNodeType.MODULE}),
            paren_expr_type=PythonNodeType.PARENTHESIZED_EXPRESSION,
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "int": "Int",
            "float": "Float",
            "bool": "Bool",
            "str": "String",
            "bytes": "String",
            "list": "Array",
            "dict": "Object",
            "object": "Object",
            "None": "Any",
        }

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            PythonNodeType.IDENTIFIER: common_expr.lower_identifier,
            PythonNodeType.INTEGER: common_expr.lower_const_literal,
            PythonNodeType.FLOAT: common_expr.lower_const_literal,
            PythonNodeType.STRING: py_expr.lower_python_string,
            PythonNodeType.CONCATENATED_STRING: common_expr.lower_const_literal,
            PythonNodeType.TRUE: common_expr.lower_canonical_true,
            PythonNodeType.FALSE: common_expr.lower_canonical_false,
            PythonNodeType.NONE: common_expr.lower_canonical_none,
            PythonNodeType.BINARY_OPERATOR: common_expr.lower_binop,
            PythonNodeType.BOOLEAN_OPERATOR: common_expr.lower_binop,
            PythonNodeType.COMPARISON_OPERATOR: common_expr.lower_comparison,
            PythonNodeType.UNARY_OPERATOR: common_expr.lower_unop,
            PythonNodeType.NOT_OPERATOR: common_expr.lower_unop,
            PythonNodeType.CALL: py_expr.lower_call,
            PythonNodeType.ATTRIBUTE: common_expr.lower_attribute,
            PythonNodeType.SUBSCRIPT: common_expr.lower_subscript,
            PythonNodeType.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            PythonNodeType.LIST: common_expr.lower_list_literal,
            PythonNodeType.DICTIONARY: common_expr.lower_dict_literal,
            PythonNodeType.TUPLE: py_expr.lower_tuple_literal,
            PythonNodeType.CONDITIONAL_EXPRESSION: py_expr.lower_conditional_expr,
            PythonNodeType.LIST_COMPREHENSION: py_expr.lower_list_comprehension,
            PythonNodeType.DICTIONARY_COMPREHENSION: py_expr.lower_dict_comprehension,
            PythonNodeType.LAMBDA: py_expr.lower_lambda,
            PythonNodeType.GENERATOR_EXPRESSION: py_expr.lower_generator_expression,
            PythonNodeType.SET_COMPREHENSION: py_expr.lower_set_comprehension,
            PythonNodeType.SET: py_expr.lower_set_literal,
            PythonNodeType.YIELD: py_expr.lower_yield,
            PythonNodeType.AWAIT: py_expr.lower_await,
            PythonNodeType.NAMED_EXPRESSION: py_expr.lower_named_expression,
            PythonNodeType.SLICE: py_expr.lower_slice,
            PythonNodeType.KEYWORD_SEPARATOR: py_expr.lower_noop_expr,
            PythonNodeType.POSITIONAL_SEPARATOR: py_expr.lower_noop_expr,
            PythonNodeType.LIST_PATTERN: py_expr.lower_list_pattern,
            PythonNodeType.CASE_PATTERN: py_expr.lower_case_pattern,
            PythonNodeType.INTERPOLATION: py_expr.lower_interpolation,
            PythonNodeType.FORMAT_SPECIFIER: common_expr.lower_const_literal,
            PythonNodeType.STRING_CONTENT: common_expr.lower_const_literal,
            PythonNodeType.STRING_START: common_expr.lower_const_literal,
            PythonNodeType.STRING_END: common_expr.lower_const_literal,
            PythonNodeType.TYPE_CONVERSION: common_expr.lower_const_literal,
            PythonNodeType.ELLIPSIS: common_expr.lower_const_literal,
            PythonNodeType.LIST_SPLAT: py_expr.lower_splat_expr,
            PythonNodeType.DICTIONARY_SPLAT: py_expr.lower_splat_expr,
            PythonNodeType.EXPRESSION_LIST: py_expr.lower_tuple_literal,
            PythonNodeType.DOTTED_NAME: common_expr.lower_identifier,
            PythonNodeType.DICT_PATTERN: py_expr.lower_dict_pattern,
            PythonNodeType.SPLAT_PATTERN: py_expr.lower_splat_expr,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            PythonNodeType.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            PythonNodeType.ASSIGNMENT: py_assign.lower_assignment,
            PythonNodeType.AUGMENTED_ASSIGNMENT: py_assign.lower_augmented_assignment,
            PythonNodeType.RETURN_STATEMENT: common_assign.lower_return,
            PythonNodeType.IF_STATEMENT: py_cf.lower_python_if,
            PythonNodeType.WHILE_STATEMENT: common_cf.lower_while,
            PythonNodeType.FOR_STATEMENT: py_cf.lower_for,
            PythonNodeType.FUNCTION_DEFINITION: common_decl.lower_function_def,
            PythonNodeType.CLASS_DEFINITION: py_decl.lower_python_class_def,
            PythonNodeType.RAISE_STATEMENT: py_cf.lower_raise,
            PythonNodeType.TRY_STATEMENT: py_cf.lower_try,
            PythonNodeType.PASS_STATEMENT: lambda ctx, node: None,
            PythonNodeType.BREAK_STATEMENT: common_cf.lower_break,
            PythonNodeType.CONTINUE_STATEMENT: common_cf.lower_continue,
            PythonNodeType.WITH_STATEMENT: py_cf.lower_with,
            PythonNodeType.DECORATED_DEFINITION: py_cf.lower_decorated_def,
            PythonNodeType.ASSERT_STATEMENT: py_cf.lower_assert,
            PythonNodeType.GLOBAL_STATEMENT: lambda ctx, node: None,
            PythonNodeType.NONLOCAL_STATEMENT: lambda ctx, node: None,
            PythonNodeType.DELETE_STATEMENT: py_cf.lower_delete,
            PythonNodeType.IMPORT_STATEMENT: py_cf.lower_import,
            PythonNodeType.IMPORT_FROM_STATEMENT: py_cf.lower_import_from,
            PythonNodeType.FUTURE_IMPORT_STATEMENT: lambda ctx, node: None,
            PythonNodeType.MATCH_STATEMENT: py_cf.lower_match,
            PythonNodeType.TYPE_ALIAS_STATEMENT: lambda ctx, node: None,
        }
