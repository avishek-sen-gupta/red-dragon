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
from interpreter.frontends.rust.node_types import RustNodeType


class RustFrontend(BaseFrontend):
    """Lowers a Rust tree-sitter AST into flattened TAC IR."""

    BLOCK_SCOPED = True

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="value",
            attr_attribute_field="field",
            attribute_node_type=RustNodeType.FIELD_EXPRESSION,
            comment_types=frozenset(
                {
                    RustNodeType.COMMENT,
                    RustNodeType.LINE_COMMENT,
                    RustNodeType.BLOCK_COMMENT,
                }
            ),
            noise_types=frozenset({RustNodeType.NEWLINE}),
            block_node_types=frozenset({RustNodeType.BLOCK, RustNodeType.SOURCE_FILE}),
            none_literal="None",
            true_literal="True",
            false_literal="False",
            default_return_value="()",
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "i8": "Int",
            "i16": "Int",
            "i32": "Int",
            "i64": "Int",
            "i128": "Int",
            "isize": "Int",
            "u8": "Int",
            "u16": "Int",
            "u32": "Int",
            "u64": "Int",
            "u128": "Int",
            "usize": "Int",
            "f32": "Float",
            "f64": "Float",
            "bool": "Bool",
            "String": "String",
            "str": "String",
            "&str": "String",
        }

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            RustNodeType.IDENTIFIER: common_expr.lower_identifier,
            RustNodeType.INTEGER_LITERAL: common_expr.lower_const_literal,
            RustNodeType.FLOAT_LITERAL: common_expr.lower_const_literal,
            RustNodeType.STRING_LITERAL: common_expr.lower_const_literal,
            RustNodeType.CHAR_LITERAL: common_expr.lower_const_literal,
            RustNodeType.RAW_STRING_LITERAL: common_expr.lower_const_literal,
            RustNodeType.NEGATIVE_LITERAL: common_expr.lower_const_literal,
            RustNodeType.BOOLEAN_LITERAL: common_expr.lower_canonical_bool,
            RustNodeType.UNIT_EXPRESSION: common_expr.lower_const_literal,
            RustNodeType.TRUE: common_expr.lower_canonical_true,
            RustNodeType.FALSE: common_expr.lower_canonical_false,
            RustNodeType.BINARY_EXPRESSION: common_expr.lower_binop,
            RustNodeType.UNARY_EXPRESSION: rust_expr.lower_unary_or_deref,
            RustNodeType.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            RustNodeType.CALL_EXPRESSION: rust_expr.lower_call_with_box_option,
            RustNodeType.FIELD_EXPRESSION: rust_expr.lower_field_expr,
            RustNodeType.REFERENCE_EXPRESSION: rust_expr.lower_reference_expr,
            RustNodeType.DEREFERENCE_EXPRESSION: rust_expr.lower_deref_expr,
            RustNodeType.ASSIGNMENT_EXPRESSION: rust_expr.lower_assignment_expr,
            RustNodeType.COMPOUND_ASSIGNMENT_EXPR: rust_expr.lower_compound_assignment_expr,
            RustNodeType.IF_EXPRESSION: rust_expr.lower_if_expr,
            RustNodeType.MATCH_EXPRESSION: rust_expr.lower_match_expr,
            RustNodeType.CLOSURE_EXPRESSION: rust_expr.lower_closure_expr,
            RustNodeType.STRUCT_EXPRESSION: rust_expr.lower_struct_instantiation,
            RustNodeType.BLOCK: rust_expr.lower_block_expr,
            RustNodeType.RETURN_EXPRESSION: rust_expr.lower_return_expr,
            RustNodeType.MACRO_INVOCATION: rust_expr.lower_macro_invocation,
            RustNodeType.TYPE_IDENTIFIER: common_expr.lower_identifier,
            RustNodeType.SELF: common_expr.lower_identifier,
            RustNodeType.ARRAY_EXPRESSION: common_expr.lower_list_literal,
            RustNodeType.INDEX_EXPRESSION: rust_expr.lower_index_expr,
            RustNodeType.TUPLE_EXPRESSION: rust_expr.lower_tuple_expr,
            RustNodeType.ELSE_CLAUSE: rust_expr.lower_else_clause,
            RustNodeType.EXPRESSION_STATEMENT: rust_expr.lower_expr_stmt_as_expr,
            RustNodeType.RANGE_EXPRESSION: rust_expr.lower_range_expr,
            RustNodeType.TRY_EXPRESSION: rust_expr.lower_try_expr,
            RustNodeType.AWAIT_EXPRESSION: rust_expr.lower_await_expr,
            RustNodeType.ASYNC_BLOCK: rust_expr.lower_block_expr,
            RustNodeType.UNSAFE_BLOCK: rust_expr.lower_block_expr,
            RustNodeType.TYPE_CAST_EXPRESSION: rust_expr.lower_type_cast_expr,
            RustNodeType.SCOPED_IDENTIFIER: rust_expr.lower_scoped_identifier,
            RustNodeType.WHILE_EXPRESSION: rust_expr.lower_loop_as_expr,
            RustNodeType.LOOP_EXPRESSION: rust_expr.lower_loop_as_expr,
            RustNodeType.FOR_EXPRESSION: rust_expr.lower_loop_as_expr,
            RustNodeType.CONTINUE_EXPRESSION: rust_expr.lower_continue_as_expr,
            RustNodeType.BREAK_EXPRESSION: rust_expr.lower_break_as_expr,
            RustNodeType.MATCH_PATTERN: common_expr.lower_paren,
            RustNodeType.TUPLE_STRUCT_PATTERN: rust_expr.lower_tuple_struct_pattern,
            RustNodeType.GENERIC_FUNCTION: rust_expr.lower_generic_function,
            RustNodeType.LET_CONDITION: rust_expr.lower_let_condition,
            RustNodeType.STRUCT_PATTERN: rust_expr.lower_struct_pattern_expr,
            RustNodeType.MUT_PATTERN: common_expr.lower_paren,
        }

    def _emit_prelude(self, ctx) -> None:
        from interpreter.frontends.rust.declarations import emit_prelude

        emit_prelude(ctx)

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            RustNodeType.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            RustNodeType.LET_DECLARATION: rust_decl.lower_let_decl,
            RustNodeType.FUNCTION_ITEM: rust_decl.lower_function_def,
            RustNodeType.STRUCT_ITEM: rust_decl.lower_struct_def,
            RustNodeType.IMPL_ITEM: rust_decl.lower_impl_item,
            RustNodeType.IF_EXPRESSION: rust_cf.lower_if_stmt,
            RustNodeType.WHILE_EXPRESSION: rust_cf.lower_while_stmt,
            RustNodeType.LOOP_EXPRESSION: rust_cf.lower_loop,
            RustNodeType.FOR_EXPRESSION: rust_cf.lower_for,
            RustNodeType.RETURN_EXPRESSION: rust_cf.lower_return_stmt,
            RustNodeType.BLOCK: lambda ctx, node: ctx.lower_block(node),
            RustNodeType.SOURCE_FILE: lambda ctx, node: ctx.lower_block(node),
            RustNodeType.USE_DECLARATION: lambda ctx, node: None,
            RustNodeType.ATTRIBUTE_ITEM: lambda ctx, node: None,
            RustNodeType.MACRO_INVOCATION: rust_cf.lower_macro_stmt,
            RustNodeType.BREAK_EXPRESSION: common_cf.lower_break,
            RustNodeType.CONTINUE_EXPRESSION: common_cf.lower_continue,
            RustNodeType.TRAIT_ITEM: rust_decl.lower_trait_item,
            RustNodeType.ENUM_ITEM: rust_decl.lower_enum_item,
            RustNodeType.CONST_ITEM: rust_decl.lower_const_item,
            RustNodeType.STATIC_ITEM: rust_decl.lower_static_item,
            RustNodeType.TYPE_ITEM: rust_decl.lower_type_item,
            RustNodeType.MOD_ITEM: rust_decl.lower_mod_item,
            RustNodeType.EXTERN_CRATE_DECLARATION: lambda ctx, node: None,
            RustNodeType.FUNCTION_SIGNATURE_ITEM: rust_decl.lower_function_signature,
            RustNodeType.FOREIGN_MOD_ITEM: rust_decl.lower_foreign_mod_item,
            RustNodeType.UNION_ITEM: rust_decl.lower_struct_def,
            RustNodeType.MACRO_DEFINITION: lambda ctx, node: None,
        }

    def _extract_symbols(self, root) -> "SymbolTable":
        from interpreter.frontends.rust.declarations import extract_rust_symbols
        from interpreter.frontends.symbol_table import SymbolTable

        return extract_rust_symbols(root)
