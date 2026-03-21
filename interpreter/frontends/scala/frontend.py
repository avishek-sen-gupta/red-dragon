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
from interpreter.frontends.scala.node_types import ScalaNodeType as NT


class ScalaFrontend(BaseFrontend):
    """Lowers a Scala tree-sitter AST into flattened TAC IR."""

    BLOCK_SCOPED = True

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            call_function_field="function",
            call_arguments_field="arguments",
            attr_object_field="value",
            attr_attribute_field="field",
            attribute_node_type=NT.FIELD_EXPRESSION,
            assign_left_field="left",
            assign_right_field="right",
            comment_types=frozenset({NT.COMMENT, NT.BLOCK_COMMENT}),
            noise_types=frozenset({"\n"}),
            block_node_types=frozenset(
                {NT.BLOCK, NT.TEMPLATE_BODY, NT.COMPILATION_UNIT}
            ),
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
            NT.IDENTIFIER: common_expr.lower_identifier,
            NT.INTEGER_LITERAL: common_expr.lower_const_literal,
            NT.FLOATING_POINT_LITERAL: common_expr.lower_const_literal,
            NT.STRING: common_expr.lower_const_literal,
            NT.BOOLEAN_LITERAL: common_expr.lower_canonical_bool,
            NT.NULL_LITERAL: common_expr.lower_canonical_none,
            NT.UNIT: common_expr.lower_const_literal,
            NT.INFIX_EXPRESSION: common_expr.lower_binop,
            NT.PREFIX_EXPRESSION: common_expr.lower_unop,
            NT.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            NT.CALL_EXPRESSION: scala_expr.lower_scala_call,
            NT.FIELD_EXPRESSION: scala_expr.lower_field_expr,
            NT.IF_EXPRESSION: scala_expr.lower_if_expr,
            NT.MATCH_EXPRESSION: scala_expr.lower_match_expr,
            NT.BLOCK: scala_expr.lower_block_expr,
            NT.ASSIGNMENT_EXPRESSION: scala_expr.lower_assignment_expr,
            NT.RETURN_EXPRESSION: scala_expr.lower_return_expr,
            NT.THIS: common_expr.lower_identifier,
            NT.SUPER: common_expr.lower_identifier,
            NT.WILDCARD: scala_expr.lower_wildcard,
            NT.TUPLE_EXPRESSION: scala_expr.lower_tuple_expr,
            NT.STRING_LITERAL: common_expr.lower_const_literal,
            NT.INTERPOLATED_STRING_EXPRESSION: scala_expr.lower_scala_interpolated_string,
            NT.INTERPOLATED_STRING: scala_expr.lower_scala_interpolated_string_body,
            NT.LAMBDA_EXPRESSION: scala_expr.lower_lambda_expr,
            NT.INSTANCE_EXPRESSION: scala_expr.lower_new_expr,
            NT.GENERIC_TYPE: scala_expr.lower_symbolic_node,
            NT.TYPE_IDENTIFIER: common_expr.lower_identifier,
            NT.TRY_EXPRESSION: scala_expr.lower_try_expr,
            NT.THROW_EXPRESSION: scala_expr.lower_throw_expr,
            NT.WHILE_EXPRESSION: scala_expr.lower_loop_as_expr,
            NT.FOR_EXPRESSION: scala_expr.lower_loop_as_expr,
            NT.DO_WHILE_EXPRESSION: scala_expr.lower_loop_as_expr,
            NT.BREAK_EXPRESSION: scala_expr.lower_break_as_expr,
            NT.CONTINUE_EXPRESSION: scala_expr.lower_continue_as_expr,
            NT.OPERATOR_IDENTIFIER: common_expr.lower_const_literal,
            NT.ARGUMENTS: common_expr.lower_paren,
            NT.CASE_CLASS_PATTERN: scala_expr.lower_case_class_pattern,
            NT.TYPED_PATTERN: scala_expr.lower_typed_pattern,
            NT.GUARD: scala_expr.lower_guard,
            NT.TUPLE_PATTERN: scala_expr.lower_tuple_pattern_expr,
            NT.CASE_BLOCK: scala_expr.lower_block_expr,
            NT.INFIX_PATTERN: scala_expr.lower_infix_pattern,
            NT.CASE_CLAUSE: scala_expr.lower_case_clause_expr,
            NT.GENERIC_FUNCTION: scala_expr.lower_generic_function,
            NT.POSTFIX_EXPRESSION: scala_expr.lower_postfix_expression,
            NT.STABLE_TYPE_IDENTIFIER: scala_expr.lower_stable_type_identifier,
            NT.ALTERNATIVE_PATTERN: scala_expr.lower_alternative_pattern,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            NT.VAL_DEFINITION: scala_decl.lower_val_def,
            NT.VAR_DEFINITION: scala_decl.lower_var_def,
            NT.FUNCTION_DEFINITION: scala_decl.lower_function_def_stmt,
            NT.CLASS_DEFINITION: scala_decl.lower_class_def,
            NT.OBJECT_DEFINITION: scala_decl.lower_object_def,
            NT.IF_EXPRESSION: scala_cf.lower_if_stmt,
            NT.WHILE_EXPRESSION: scala_cf.lower_while,
            NT.MATCH_EXPRESSION: scala_cf.lower_match_stmt,
            NT.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            NT.BLOCK: lambda ctx, node: ctx.lower_block(node),
            NT.TEMPLATE_BODY: lambda ctx, node: ctx.lower_block(node),
            NT.COMPILATION_UNIT: lambda ctx, node: ctx.lower_block(node),
            NT.IMPORT_DECLARATION: lambda ctx, node: None,
            NT.EXPORT_DECLARATION: lambda ctx, node: None,
            NT.PACKAGE_CLAUSE: lambda ctx, node: None,
            NT.BREAK_EXPRESSION: common_cf.lower_break,
            NT.CONTINUE_EXPRESSION: common_cf.lower_continue,
            NT.TRY_EXPRESSION: scala_cf.lower_try_stmt,
            NT.FOR_EXPRESSION: scala_cf.lower_for_expr,
            NT.TRAIT_DEFINITION: scala_decl.lower_trait_def,
            NT.CASE_CLASS_DEFINITION: scala_decl.lower_class_def,
            NT.LAZY_VAL_DEFINITION: scala_decl.lower_val_def,
            NT.DO_WHILE_EXPRESSION: scala_cf.lower_do_while,
            NT.TYPE_DEFINITION: lambda ctx, node: None,
            NT.FUNCTION_DECLARATION: scala_decl.lower_function_declaration,
            NT.VAL_DECLARATION: lambda ctx, node: None,
        }

    def _extract_symbols(self, root) -> "SymbolTable":
        from interpreter.frontends.scala.declarations import extract_scala_symbols
        from interpreter.frontends.symbol_table import SymbolTable

        return extract_scala_symbols(root)
