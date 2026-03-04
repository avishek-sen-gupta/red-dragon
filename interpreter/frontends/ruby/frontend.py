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


class RubyFrontend(BaseFrontend):
    """Lowers a Ruby tree-sitter AST into flattened TAC IR."""

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="receiver",
            attr_attribute_field="method",
            attribute_node_type="call",
            comment_types=frozenset({"comment"}),
            noise_types=frozenset({"then", "do", "end", "\n"}),
            block_node_types=frozenset({"program", "body_statement"}),
        )

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            "identifier": common_expr.lower_identifier,
            "instance_variable": ruby_expr.lower_instance_variable,
            "constant": common_expr.lower_identifier,
            "integer": common_expr.lower_const_literal,
            "float": common_expr.lower_const_literal,
            "string": ruby_expr.lower_ruby_string,
            "true": common_expr.lower_canonical_true,
            "false": common_expr.lower_canonical_false,
            "nil": common_expr.lower_canonical_none,
            "binary": common_expr.lower_binop,
            "call": ruby_expr.lower_ruby_call,
            "parenthesized_expression": common_expr.lower_paren,
            "parenthesized_statements": common_expr.lower_paren,
            "array": common_expr.lower_list_literal,
            "hash": ruby_expr.lower_ruby_hash,
            "argument_list": ruby_expr.lower_ruby_argument_list,
            "simple_symbol": common_expr.lower_const_literal,
            "hash_key_symbol": common_expr.lower_const_literal,
            "range": ruby_expr.lower_ruby_range,
            "regex": common_expr.lower_const_literal,
            "lambda": ruby_expr.lower_ruby_lambda,
            "string_array": ruby_expr.lower_ruby_word_array,
            "symbol_array": ruby_expr.lower_ruby_word_array,
            "global_variable": common_expr.lower_identifier,
            "class_variable": common_expr.lower_identifier,
            "heredoc_body": ruby_expr.lower_ruby_heredoc_body,
            "element_reference": ruby_expr.lower_element_reference,
            "heredoc_beginning": common_expr.lower_const_literal,
            "right_assignment_list": common_expr.lower_list_literal,
            "pattern": ruby_expr.lower_ruby_pattern,
            "delimited_symbol": common_expr.lower_const_literal,
            "in": common_expr.lower_const_literal,
            "conditional": ruby_expr.lower_ruby_conditional,
            "unary": common_expr.lower_unop,
            "self": ruby_expr.lower_ruby_self,
            "super": ruby_expr.lower_ruby_super,
            "yield": ruby_expr.lower_ruby_yield,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            "expression_statement": common_assign.lower_expression_statement,
            "assignment": ruby_assign.lower_ruby_assignment,
            "operator_assignment": ruby_assign.lower_ruby_augmented_assignment,
            "return": ruby_assign.lower_ruby_return,
            "return_statement": ruby_assign.lower_ruby_return,
            "if": ruby_cf.lower_ruby_if,
            "if_modifier": ruby_cf.lower_ruby_if_modifier,
            "unless": ruby_cf.lower_unless,
            "unless_modifier": ruby_cf.lower_ruby_unless_modifier,
            "elsif": ruby_cf.lower_ruby_elsif_stmt,
            "while": common_cf.lower_while,
            "while_modifier": ruby_cf.lower_ruby_while_modifier,
            "until": ruby_cf.lower_until,
            "until_modifier": ruby_cf.lower_ruby_until_modifier,
            "for": ruby_cf.lower_ruby_for,
            "method": ruby_decl.lower_ruby_method_stmt,
            "singleton_method": ruby_decl.lower_ruby_singleton_method,
            "class": ruby_decl.lower_ruby_class,
            "singleton_class": ruby_decl.lower_ruby_singleton_class,
            "program": lambda ctx, node: ctx.lower_block(node),
            "body_statement": lambda ctx, node: ctx.lower_block(node),
            "do_block": lambda ctx, node: ruby_expr.lower_ruby_block(ctx, node),
            "block": lambda ctx, node: ruby_expr.lower_ruby_block(ctx, node),
            "break": common_cf.lower_break,
            "next": common_cf.lower_continue,
            "begin": ruby_cf.lower_begin,
            "case": ruby_cf.lower_case,
            "module": ruby_decl.lower_ruby_module,
            "super": lambda ctx, node: ruby_expr.lower_ruby_super(ctx, node),
            "yield": lambda ctx, node: ruby_expr.lower_ruby_yield(ctx, node),
            "in": ruby_cf.lower_ruby_in_clause,
            "retry": ruby_cf.lower_ruby_retry,
        }
