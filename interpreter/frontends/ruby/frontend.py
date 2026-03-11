"""RubyFrontend — thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.ruby import expressions as ruby_expr
from interpreter.frontends.ruby import control_flow as ruby_cf
from interpreter.frontends.ruby import declarations as ruby_decl
from interpreter.frontends.ruby import assignments as ruby_assign
from interpreter.frontends.ruby.node_types import RubyNodeType


class RubyFrontend(BaseFrontend):
    """Lowers a Ruby tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="receiver",
            attr_attribute_field="method",
            attribute_node_type=RubyNodeType.CALL,
            comment_types=frozenset({RubyNodeType.COMMENT}),
            noise_types=frozenset(
                {
                    RubyNodeType.THEN,
                    RubyNodeType.DO,
                    RubyNodeType.END,
                    RubyNodeType.NEWLINE_CHAR,
                }
            ),
            block_node_types=frozenset(
                {RubyNodeType.PROGRAM, RubyNodeType.BODY_STATEMENT}
            ),
        )

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            RubyNodeType.SCOPE_RESOLUTION: ruby_expr.lower_scope_resolution,
            RubyNodeType.IDENTIFIER: common_expr.lower_identifier,
            RubyNodeType.INSTANCE_VARIABLE: ruby_expr.lower_instance_variable,
            RubyNodeType.CONSTANT: common_expr.lower_identifier,
            RubyNodeType.INTEGER: common_expr.lower_const_literal,
            RubyNodeType.FLOAT: common_expr.lower_const_literal,
            RubyNodeType.STRING: ruby_expr.lower_ruby_string,
            RubyNodeType.TRUE: common_expr.lower_canonical_true,
            RubyNodeType.FALSE: common_expr.lower_canonical_false,
            RubyNodeType.NIL: common_expr.lower_canonical_none,
            RubyNodeType.BINARY: common_expr.lower_binop,
            RubyNodeType.CALL: ruby_expr.lower_ruby_call,
            RubyNodeType.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            RubyNodeType.PARENTHESIZED_STATEMENTS: common_expr.lower_paren,
            RubyNodeType.ARRAY: common_expr.lower_list_literal,
            RubyNodeType.HASH: ruby_expr.lower_ruby_hash,
            RubyNodeType.ARGUMENT_LIST: ruby_expr.lower_ruby_argument_list,
            RubyNodeType.SIMPLE_SYMBOL: common_expr.lower_const_literal,
            RubyNodeType.HASH_KEY_SYMBOL: common_expr.lower_const_literal,
            RubyNodeType.RANGE: ruby_expr.lower_ruby_range,
            RubyNodeType.REGEX: common_expr.lower_const_literal,
            RubyNodeType.LAMBDA: ruby_expr.lower_ruby_lambda,
            RubyNodeType.STRING_ARRAY: ruby_expr.lower_ruby_word_array,
            RubyNodeType.SYMBOL_ARRAY: ruby_expr.lower_ruby_word_array,
            RubyNodeType.GLOBAL_VARIABLE: common_expr.lower_identifier,
            RubyNodeType.CLASS_VARIABLE: common_expr.lower_identifier,
            RubyNodeType.HEREDOC_BODY: ruby_expr.lower_ruby_heredoc_body,
            RubyNodeType.ELEMENT_REFERENCE: ruby_expr.lower_element_reference,
            RubyNodeType.HEREDOC_BEGINNING: common_expr.lower_const_literal,
            RubyNodeType.RIGHT_ASSIGNMENT_LIST: common_expr.lower_list_literal,
            RubyNodeType.PATTERN: ruby_expr.lower_ruby_pattern,
            RubyNodeType.DELIMITED_SYMBOL: common_expr.lower_const_literal,
            RubyNodeType.IN: common_expr.lower_const_literal,
            RubyNodeType.CONDITIONAL: ruby_expr.lower_ruby_conditional,
            RubyNodeType.UNARY: common_expr.lower_unop,
            RubyNodeType.SELF: ruby_expr.lower_ruby_self,
            RubyNodeType.SUPER: ruby_expr.lower_ruby_super,
            RubyNodeType.YIELD: ruby_expr.lower_ruby_yield,
            RubyNodeType.RESCUE_MODIFIER: ruby_cf.lower_ruby_rescue_modifier_expr,
            RubyNodeType.SPLAT_ARGUMENT: common_expr.lower_paren,
            RubyNodeType.HASH_SPLAT_ARGUMENT: common_expr.lower_paren,
            RubyNodeType.BLOCK_ARGUMENT: common_expr.lower_paren,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            RubyNodeType.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            RubyNodeType.ASSIGNMENT: ruby_assign.lower_ruby_assignment,
            RubyNodeType.OPERATOR_ASSIGNMENT: ruby_assign.lower_ruby_augmented_assignment,
            RubyNodeType.RETURN: ruby_assign.lower_ruby_return,
            RubyNodeType.RETURN_STATEMENT: ruby_assign.lower_ruby_return,
            RubyNodeType.IF: ruby_cf.lower_ruby_if,
            RubyNodeType.IF_MODIFIER: ruby_cf.lower_ruby_if_modifier,
            RubyNodeType.UNLESS: ruby_cf.lower_unless,
            RubyNodeType.UNLESS_MODIFIER: ruby_cf.lower_ruby_unless_modifier,
            RubyNodeType.ELSIF: ruby_cf.lower_ruby_elsif_stmt,
            RubyNodeType.WHILE: common_cf.lower_while,
            RubyNodeType.WHILE_MODIFIER: ruby_cf.lower_ruby_while_modifier,
            RubyNodeType.UNTIL: ruby_cf.lower_until,
            RubyNodeType.UNTIL_MODIFIER: ruby_cf.lower_ruby_until_modifier,
            RubyNodeType.FOR: ruby_cf.lower_ruby_for,
            RubyNodeType.METHOD: ruby_decl.lower_ruby_method_stmt,
            RubyNodeType.SINGLETON_METHOD: ruby_decl.lower_ruby_singleton_method,
            RubyNodeType.CLASS: ruby_decl.lower_ruby_class,
            RubyNodeType.SINGLETON_CLASS: ruby_decl.lower_ruby_singleton_class,
            RubyNodeType.PROGRAM: lambda ctx, node: ctx.lower_block(node),
            RubyNodeType.BODY_STATEMENT: lambda ctx, node: ctx.lower_block(node),
            RubyNodeType.DO_BLOCK: lambda ctx, node: ruby_expr.lower_ruby_block(
                ctx, node
            ),
            RubyNodeType.BLOCK: lambda ctx, node: ruby_expr.lower_ruby_block(ctx, node),
            RubyNodeType.BREAK: common_cf.lower_break,
            RubyNodeType.NEXT: common_cf.lower_continue,
            RubyNodeType.BEGIN: ruby_cf.lower_begin,
            RubyNodeType.CASE: ruby_cf.lower_case,
            RubyNodeType.MODULE: ruby_decl.lower_ruby_module,
            RubyNodeType.SUPER: lambda ctx, node: ruby_expr.lower_ruby_super(ctx, node),
            RubyNodeType.YIELD: lambda ctx, node: ruby_expr.lower_ruby_yield(ctx, node),
            RubyNodeType.IN: ruby_cf.lower_ruby_in_clause,
            RubyNodeType.RETRY: ruby_cf.lower_ruby_retry,
            RubyNodeType.RESCUE_MODIFIER: ruby_cf.lower_ruby_rescue_modifier,
            RubyNodeType.BEGIN_BLOCK: lambda ctx, node: None,
            RubyNodeType.END_BLOCK: lambda ctx, node: None,
        }
