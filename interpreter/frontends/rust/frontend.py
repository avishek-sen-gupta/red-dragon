"""RustFrontend -- thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.rust import expressions as rust_expr
from interpreter.frontends.rust import control_flow as rust_cf
from interpreter.frontends.rust import declarations as rust_decl


class RustFrontend(BaseFrontend):
    """Lowers a Rust tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="value",
            attr_attribute_field="field",
            attribute_node_type="field_expression",
            comment_types=frozenset({"comment", "line_comment", "block_comment"}),
            noise_types=frozenset({"\n"}),
            block_node_types=frozenset({"block", "source_file"}),
            none_literal="None",
            true_literal="True",
            false_literal="False",
            default_return_value="()",
        )

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "identifier": common_expr.lower_identifier,
            "integer_literal": common_expr.lower_const_literal,
            "float_literal": common_expr.lower_const_literal,
            "string_literal": common_expr.lower_const_literal,
            "char_literal": common_expr.lower_const_literal,
            "boolean_literal": common_expr.lower_canonical_bool,
            "true": common_expr.lower_canonical_true,
            "false": common_expr.lower_canonical_false,
            "binary_expression": common_expr.lower_binop,
            "unary_expression": common_expr.lower_unop,
            "parenthesized_expression": common_expr.lower_paren,
            "call_expression": common_expr.lower_call,
            "field_expression": rust_expr.lower_field_expr,
            "reference_expression": rust_expr.lower_reference_expr,
            "dereference_expression": rust_expr.lower_deref_expr,
            "assignment_expression": rust_expr.lower_assignment_expr,
            "compound_assignment_expr": rust_expr.lower_compound_assignment_expr,
            "if_expression": rust_expr.lower_if_expr,
            "match_expression": rust_expr.lower_match_expr,
            "closure_expression": rust_expr.lower_closure_expr,
            "struct_expression": rust_expr.lower_struct_instantiation,
            "block": rust_expr.lower_block_expr,
            "return_expression": rust_expr.lower_return_expr,
            "macro_invocation": rust_expr.lower_macro_invocation,
            "type_identifier": common_expr.lower_identifier,
            "self": common_expr.lower_identifier,
            "array_expression": common_expr.lower_list_literal,
            "index_expression": rust_expr.lower_index_expr,
            "tuple_expression": rust_expr.lower_tuple_expr,
            "else_clause": rust_expr.lower_else_clause,
            "expression_statement": rust_expr.lower_expr_stmt_as_expr,
            "range_expression": rust_expr.lower_range_expr,
            "try_expression": rust_expr.lower_try_expr,
            "await_expression": rust_expr.lower_await_expr,
            "async_block": rust_expr.lower_block_expr,
            "unsafe_block": rust_expr.lower_block_expr,
            "type_cast_expression": rust_expr.lower_type_cast_expr,
            "scoped_identifier": rust_expr.lower_scoped_identifier,
            "while_expression": rust_expr.lower_loop_as_expr,
            "loop_expression": rust_expr.lower_loop_as_expr,
            "for_expression": rust_expr.lower_loop_as_expr,
            "continue_expression": rust_expr.lower_continue_as_expr,
            "break_expression": rust_expr.lower_break_as_expr,
            "match_pattern": common_expr.lower_paren,
            "tuple_struct_pattern": rust_expr.lower_tuple_struct_pattern,
            "generic_function": rust_expr.lower_generic_function,
            "let_condition": rust_expr.lower_let_condition,
            "struct_pattern": rust_expr.lower_struct_pattern_expr,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "expression_statement": common_assign.lower_expression_statement,
            "let_declaration": rust_decl.lower_let_decl,
            "function_item": rust_decl.lower_function_def,
            "struct_item": rust_decl.lower_struct_def,
            "impl_item": rust_decl.lower_impl_item,
            "if_expression": rust_cf.lower_if_stmt,
            "while_expression": common_cf.lower_while,
            "loop_expression": rust_cf.lower_loop,
            "for_expression": rust_cf.lower_for,
            "return_expression": rust_cf.lower_return_stmt,
            "block": lambda ctx, node: ctx.lower_block(node),
            "source_file": lambda ctx, node: ctx.lower_block(node),
            "use_declaration": lambda ctx, node: None,
            "attribute_item": lambda ctx, node: None,
            "macro_invocation": rust_cf.lower_macro_stmt,
            "break_expression": common_cf.lower_break,
            "continue_expression": common_cf.lower_continue,
            "trait_item": rust_decl.lower_trait_item,
            "enum_item": rust_decl.lower_enum_item,
            "const_item": rust_decl.lower_const_item,
            "static_item": rust_decl.lower_static_item,
            "type_item": rust_decl.lower_type_item,
            "mod_item": rust_decl.lower_mod_item,
            "extern_crate_declaration": lambda ctx, node: None,
            "function_signature_item": rust_decl.lower_function_signature,
        }
