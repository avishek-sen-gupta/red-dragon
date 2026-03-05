"""ScalaFrontend — thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.scala import expressions as scala_expr
from interpreter.frontends.scala import control_flow as scala_cf
from interpreter.frontends.scala import declarations as scala_decl


class ScalaFrontend(BaseFrontend):
    """Lowers a Scala tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            call_function_field="function",
            call_arguments_field="arguments",
            attr_object_field="value",
            attr_attribute_field="field",
            attribute_node_type="field_expression",
            assign_left_field="left",
            assign_right_field="right",
            comment_types=frozenset({"comment", "block_comment"}),
            noise_types=frozenset({"\n"}),
            block_node_types=frozenset({"block", "template_body", "compilation_unit"}),
            default_return_value="()",
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "Int": "Int",
            "Long": "Int",
            "Short": "Int",
            "Byte": "Int",
            "Char": "Int",
            "Float": "Float",
            "Double": "Float",
            "Boolean": "Bool",
            "String": "String",
            "Unit": "Any",
            "Any": "Any",
        }

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "identifier": common_expr.lower_identifier,
            "integer_literal": common_expr.lower_const_literal,
            "floating_point_literal": common_expr.lower_const_literal,
            "string": common_expr.lower_const_literal,
            "boolean_literal": common_expr.lower_canonical_bool,
            "null_literal": common_expr.lower_canonical_none,
            "unit": common_expr.lower_const_literal,
            "infix_expression": common_expr.lower_binop,
            "prefix_expression": common_expr.lower_unop,
            "parenthesized_expression": common_expr.lower_paren,
            "call_expression": common_expr.lower_call,
            "field_expression": scala_expr.lower_field_expr,
            "if_expression": scala_expr.lower_if_expr,
            "match_expression": scala_expr.lower_match_expr,
            "block": scala_expr.lower_block_expr,
            "assignment_expression": scala_expr.lower_assignment_expr,
            "return_expression": scala_expr.lower_return_expr,
            "this": common_expr.lower_identifier,
            "super": common_expr.lower_identifier,
            "wildcard": scala_expr.lower_wildcard,
            "tuple_expression": scala_expr.lower_tuple_expr,
            "string_literal": common_expr.lower_const_literal,
            "interpolated_string_expression": scala_expr.lower_scala_interpolated_string,
            "interpolated_string": scala_expr.lower_scala_interpolated_string_body,
            "lambda_expression": scala_expr.lower_lambda_expr,
            "instance_expression": scala_expr.lower_new_expr,
            "generic_type": scala_expr.lower_symbolic_node,
            "type_identifier": common_expr.lower_identifier,
            "try_expression": scala_expr.lower_try_expr,
            "throw_expression": scala_expr.lower_throw_expr,
            "while_expression": scala_expr.lower_loop_as_expr,
            "for_expression": scala_expr.lower_loop_as_expr,
            "do_while_expression": scala_expr.lower_loop_as_expr,
            "break_expression": scala_expr.lower_break_as_expr,
            "continue_expression": scala_expr.lower_continue_as_expr,
            "operator_identifier": common_expr.lower_const_literal,
            "arguments": common_expr.lower_paren,
            "case_class_pattern": scala_expr.lower_case_class_pattern,
            "typed_pattern": scala_expr.lower_typed_pattern,
            "guard": scala_expr.lower_guard,
            "tuple_pattern": scala_expr.lower_tuple_pattern_expr,
            "case_block": scala_expr.lower_block_expr,
            "infix_pattern": scala_expr.lower_infix_pattern,
            "case_clause": scala_expr.lower_case_clause_expr,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "val_definition": scala_decl.lower_val_def,
            "var_definition": scala_decl.lower_var_def,
            "function_definition": scala_decl.lower_function_def_stmt,
            "class_definition": scala_decl.lower_class_def,
            "object_definition": scala_decl.lower_object_def,
            "if_expression": scala_cf.lower_if_stmt,
            "while_expression": scala_cf.lower_while,
            "match_expression": scala_cf.lower_match_stmt,
            "expression_statement": common_assign.lower_expression_statement,
            "block": lambda ctx, node: ctx.lower_block(node),
            "template_body": lambda ctx, node: ctx.lower_block(node),
            "compilation_unit": lambda ctx, node: ctx.lower_block(node),
            "import_declaration": lambda ctx, node: None,
            "package_clause": lambda ctx, node: None,
            "break_expression": common_cf.lower_break,
            "continue_expression": common_cf.lower_continue,
            "try_expression": scala_cf.lower_try_stmt,
            "for_expression": scala_cf.lower_for_expr,
            "trait_definition": scala_decl.lower_trait_def,
            "case_class_definition": scala_decl.lower_class_def,
            "lazy_val_definition": scala_decl.lower_val_def,
            "do_while_expression": scala_cf.lower_do_while,
            "type_definition": lambda ctx, node: None,
            "function_declaration": scala_decl.lower_function_declaration,
        }
