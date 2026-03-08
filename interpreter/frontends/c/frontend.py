"""CFrontend — thin orchestrator that builds dispatch tables from pure functions."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.frontends.context import GrammarConstants
from interpreter.frontends.common import expressions as common_expr
from interpreter.frontends.common import control_flow as common_cf
from interpreter.frontends.common import assignments as common_assign
from interpreter.frontends.c import expressions as c_expr
from interpreter.frontends.c import control_flow as c_cf
from interpreter.frontends.c import declarations as c_decl
from interpreter.frontends.c.node_types import CNodeType

PREPROC_NOISE_TYPES = frozenset(
    {
        CNodeType.PREPROC_INCLUDE,
        CNodeType.PREPROC_DEFINE,
        CNodeType.PREPROC_IFDEF,
        CNodeType.PREPROC_IFNDEF,
        CNodeType.PREPROC_IF,
        CNodeType.PREPROC_ELSE,
        CNodeType.PREPROC_ELIF,
        CNodeType.PREPROC_ENDIF,
        CNodeType.PREPROC_CALL,
        CNodeType.PREPROC_DEF,
    }
)


class CFrontend(BaseFrontend):
    """Lowers a C tree-sitter AST into flattened TAC IR."""

    BLOCK_SCOPED = True

    def _build_constants(self) -> GrammarConstants:
        return GrammarConstants(
            attr_object_field="argument",
            attr_attribute_field="field",
            attribute_node_type=CNodeType.FIELD_EXPRESSION,
            subscript_value_field="argument",
            subscript_index_field="index",
            comment_types=frozenset({CNodeType.COMMENT}),
            noise_types=frozenset({"\n"}) | PREPROC_NOISE_TYPES,
            block_node_types=frozenset(
                {CNodeType.COMPOUND_STATEMENT, CNodeType.TRANSLATION_UNIT}
            ),
            none_literal="None",
            true_literal="True",
            false_literal="False",
            default_return_value="0",
        )

    def _build_type_map(self) -> dict[str, str]:
        return {
            "int": "Int",
            "long": "Int",
            "short": "Int",
            "char": "Int",
            "unsigned": "Int",
            "signed": "Int",
            "size_t": "Int",
            "float": "Float",
            "double": "Float",
            "bool": "Bool",
            "_Bool": "Bool",
            "void": "Any",
        }

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        return {
            CNodeType.IDENTIFIER: common_expr.lower_identifier,
            CNodeType.NUMBER_LITERAL: common_expr.lower_const_literal,
            CNodeType.STRING_LITERAL: common_expr.lower_const_literal,
            CNodeType.CHAR_LITERAL: common_expr.lower_const_literal,
            CNodeType.TRUE: common_expr.lower_canonical_true,
            CNodeType.FALSE: common_expr.lower_canonical_false,
            CNodeType.NULL: common_expr.lower_canonical_none,
            CNodeType.BINARY_EXPRESSION: common_expr.lower_binop,
            CNodeType.UNARY_EXPRESSION: common_expr.lower_unop,
            CNodeType.UPDATE_EXPRESSION: common_expr.lower_update_expr,
            CNodeType.PARENTHESIZED_EXPRESSION: common_expr.lower_paren,
            CNodeType.CALL_EXPRESSION: common_expr.lower_call,
            CNodeType.FIELD_EXPRESSION: c_expr.lower_field_expr,
            CNodeType.SUBSCRIPT_EXPRESSION: c_expr.lower_subscript_expr,
            CNodeType.ASSIGNMENT_EXPRESSION: c_expr.lower_assignment_expr,
            CNodeType.CAST_EXPRESSION: c_expr.lower_cast_expr,
            CNodeType.POINTER_EXPRESSION: c_expr.lower_pointer_expr,
            CNodeType.SIZEOF_EXPRESSION: c_expr.lower_sizeof,
            CNodeType.CONDITIONAL_EXPRESSION: c_expr.lower_ternary,
            CNodeType.COMMA_EXPRESSION: c_expr.lower_comma_expr,
            CNodeType.CONCATENATED_STRING: common_expr.lower_const_literal,
            CNodeType.TYPE_IDENTIFIER: common_expr.lower_identifier,
            CNodeType.COMPOUND_LITERAL_EXPRESSION: c_expr.lower_compound_literal,
            CNodeType.PREPROC_ARG: common_expr.lower_const_literal,
            CNodeType.INITIALIZER_LIST: c_expr.lower_initializer_list,
            CNodeType.INITIALIZER_PAIR: c_expr.lower_initializer_pair,
        }

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        return {
            CNodeType.EXPRESSION_STATEMENT: common_assign.lower_expression_statement,
            CNodeType.DECLARATION: c_decl.lower_declaration,
            CNodeType.RETURN_STATEMENT: common_assign.lower_return,
            CNodeType.IF_STATEMENT: common_cf.lower_if,
            CNodeType.WHILE_STATEMENT: common_cf.lower_while,
            CNodeType.FOR_STATEMENT: common_cf.lower_c_style_for,
            CNodeType.DO_STATEMENT: c_cf.lower_do_while,
            CNodeType.FUNCTION_DEFINITION: c_decl.lower_function_def_c,
            CNodeType.STRUCT_SPECIFIER: c_decl.lower_struct_def,
            CNodeType.COMPOUND_STATEMENT: lambda ctx, node: ctx.lower_block(node),
            CNodeType.SWITCH_STATEMENT: c_cf.lower_switch,
            CNodeType.CASE_STATEMENT: c_cf.lower_case_as_block,
            CNodeType.GOTO_STATEMENT: c_cf.lower_goto,
            CNodeType.LABELED_STATEMENT: c_cf.lower_labeled_stmt,
            CNodeType.BREAK_STATEMENT: common_cf.lower_break,
            CNodeType.CONTINUE_STATEMENT: common_cf.lower_continue,
            CNodeType.TRANSLATION_UNIT: lambda ctx, node: ctx.lower_block(node),
            CNodeType.TYPE_DEFINITION: c_decl.lower_typedef,
            CNodeType.ENUM_SPECIFIER: c_decl.lower_enum_def,
            CNodeType.UNION_SPECIFIER: c_decl.lower_union_def,
            CNodeType.PREPROC_FUNCTION_DEF: c_decl.lower_preproc_function_def,
        }
