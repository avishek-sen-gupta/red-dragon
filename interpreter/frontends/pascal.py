"""PascalFrontend — tree-sitter Pascal AST -> IR lowering."""

from __future__ import annotations

import logging
from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)

_K_OPERATOR_MAP: dict[str, str] = {
    "kAdd": "+",
    "kSub": "-",
    "kMul": "*",
    "kDiv": "/",
    "kGt": ">",
    "kLt": "<",
    "kEq": "==",
    "kNeq": "!=",
    "kGte": ">=",
    "kLte": "<=",
    "kAnd": "and",
    "kOr": "or",
    "kMod": "mod",
}

_KEYWORD_NOISE: frozenset[str] = frozenset(
    {
        "kProgram",
        "kBegin",
        "kEnd",
        "kEndDot",
        "kVar",
        "kDo",
        "kThen",
        "kElse",
        "kOf",
        "kTo",
        "kDownto",
        "kAssign",
        "kSemicolon",
        "kColon",
        "kComma",
        "kDot",
        "kLParen",
        "kRParen",
        "kIf",
        "kWhile",
        "kFor",
        "kRepeat",
        "kUntil",
        "kFunction",
        "kProcedure",
        ";",
        ":",
        ",",
        ".",
        "(",
        ")",
        "\n",
    }
)


class PascalFrontend(BaseFrontend):
    """Lowers a Pascal tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "nil"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    DEFAULT_RETURN_VALUE = "nil"

    COMMENT_TYPES = frozenset({"comment"})
    NOISE_TYPES = _KEYWORD_NOISE

    BLOCK_NODE_TYPES = frozenset({"block"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "literalNumber": self._lower_const_literal,
            "literalString": self._lower_const_literal,
            "exprBinary": self._lower_pascal_binop,
            "exprCall": self._lower_pascal_call,
            "parenthesized_expression": self._lower_paren,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "root": self._lower_pascal_root,
            "program": self._lower_pascal_program,
            "block": self._lower_pascal_block,
            "statement": self._lower_pascal_statement,
            "assignment": self._lower_pascal_assignment,
            "declVars": self._lower_pascal_decl_vars,
            "declVar": self._lower_pascal_decl_var,
            "ifElse": self._lower_pascal_if,
            "if": self._lower_pascal_if,
            "while": self._lower_pascal_while,
            "for": self._lower_pascal_for,
            "defProc": self._lower_pascal_proc,
            "declProc": self._lower_pascal_proc,
        }

    # -- Pascal: root / program structure ------------------------------------------

    def _lower_pascal_root(self, node):
        """Lower the root node — contains a program node."""
        for child in node.children:
            if child.is_named:
                self._lower_stmt(child)

    def _lower_pascal_program(self, node):
        """Lower the program node — contains moduleName, declVars, block, etc."""
        for child in node.children:
            if child.type in _KEYWORD_NOISE:
                continue
            if child.type == "moduleName":
                continue
            if child.is_named:
                self._lower_stmt(child)

    def _lower_pascal_block(self, node):
        """Lower a block — children between kBegin and kEnd."""
        for child in node.children:
            if child.type in _KEYWORD_NOISE:
                continue
            if child.is_named:
                self._lower_stmt(child)

    def _lower_pascal_statement(self, node):
        """Unwrap a statement node and lower its inner content."""
        for child in node.children:
            if child.type in _KEYWORD_NOISE:
                continue
            if child.is_named:
                self._lower_stmt(child)
                return
        # Fallback: try each named child as expression
        for child in node.children:
            if child.is_named:
                self._lower_expr(child)

    # -- Pascal: variable declarations ---------------------------------------------

    def _lower_pascal_decl_vars(self, node):
        """Lower declVars — contains multiple declVar children."""
        for child in node.children:
            if child.type == "declVar":
                self._lower_pascal_decl_var(child)

    def _lower_pascal_decl_var(self, node):
        """Lower declVar — identifier : typeref — declare with nil default."""
        id_node = next((c for c in node.children if c.type == "identifier"), None)
        if id_node is None:
            return
        var_name = self._node_text(id_node)
        val_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[self.NONE_LITERAL],
        )
        self._emit(
            Opcode.STORE_VAR,
            operands=[var_name, val_reg],
            source_location=self._source_loc(node),
        )

    # -- Pascal: assignment (identifier := expression) -----------------------------

    def _lower_pascal_assignment(self, node):
        """Lower assignment — children: identifier, kAssign, expression."""
        named_children = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]
        if len(named_children) < 2:
            logger.warning(
                "Pascal assignment with fewer than 2 named children at %s",
                self._source_loc(node),
            )
            return
        target = named_children[0]
        value = named_children[-1]
        val_reg = self._lower_expr(value)
        self._emit(
            Opcode.STORE_VAR,
            operands=[self._node_text(target), val_reg],
            source_location=self._source_loc(node),
        )

    # -- Pascal: binary expression -------------------------------------------------

    def _lower_pascal_binop(self, node) -> str:
        """Lower exprBinary — children: lhs, operator_keyword, rhs."""
        named_children = [c for c in node.children if c.is_named]
        if len(named_children) < 2:
            return self._lower_const_literal(node)

        # Find the operator keyword between operands
        op_symbol = "?"
        lhs_node = named_children[0]
        rhs_node = named_children[-1]

        for child in node.children:
            mapped = _K_OPERATOR_MAP.get(child.type)
            if mapped:
                op_symbol = mapped
                break

        # Fallback: if no k-prefixed operator found, use text of middle child
        if op_symbol == "?" and len(named_children) >= 3:
            op_symbol = self._node_text(named_children[1])

        lhs_reg = self._lower_expr(lhs_node)
        rhs_reg = self._lower_expr(rhs_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=reg,
            operands=[op_symbol, lhs_reg, rhs_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # -- Pascal: function/procedure call -------------------------------------------

    def _lower_pascal_call(self, node) -> str:
        """Lower exprCall — children: identifier, (, exprArgs, )."""
        id_node = next((c for c in node.children if c.type == "identifier"), None)
        args_node = next((c for c in node.children if c.type == "exprArgs"), None)
        arg_regs = self._extract_pascal_args(args_node)

        if id_node:
            func_name = self._node_text(id_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=reg,
                operands=[func_name] + arg_regs,
                source_location=self._source_loc(node),
            )
            return reg

        target_reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=target_reg,
            operands=["unknown_call_target"],
        )
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    def _extract_pascal_args(self, args_node) -> list[str]:
        """Extract argument registers from exprArgs node."""
        if args_node is None:
            return []
        return [
            self._lower_expr(c)
            for c in args_node.children
            if c.is_named and c.type not in _KEYWORD_NOISE
        ]

    # -- Pascal: if/ifElse ---------------------------------------------------------

    def _lower_pascal_if(self, node):
        """Lower if/ifElse — contains kIf, condition, kThen, consequence, optional kElse, alternative."""
        named_children = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]
        if len(named_children) < 2:
            logger.warning(
                "Pascal if with fewer than 2 named children at %s",
                self._source_loc(node),
            )
            return

        cond_node = named_children[0]
        body_node = named_children[1]
        alt_node = named_children[2] if len(named_children) > 2 else None

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("if_true")
        false_label = self._fresh_label("if_false")
        end_label = self._fresh_label("if_end")

        if alt_node:
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{true_label},{false_label}",
                source_location=self._source_loc(node),
            )
        else:
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{true_label},{end_label}",
                source_location=self._source_loc(node),
            )

        self._emit(Opcode.LABEL, label=true_label)
        self._lower_stmt(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            self._lower_stmt(alt_node)
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Pascal: while loop --------------------------------------------------------

    def _lower_pascal_while(self, node):
        """Lower while — contains kWhile, condition, kDo, body."""
        named_children = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]
        if len(named_children) < 2:
            logger.warning(
                "Pascal while with fewer than 2 named children at %s",
                self._source_loc(node),
            )
            return

        cond_node = named_children[0]
        body_node = named_children[1]

        loop_label = self._fresh_label("while_cond")
        body_label = self._fresh_label("while_body")
        end_label = self._fresh_label("while_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._lower_expr(cond_node)
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
            source_location=self._source_loc(node),
        )

        self._emit(Opcode.LABEL, label=body_label)
        self._lower_stmt(body_node)
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Pascal: for loop ----------------------------------------------------------

    def _lower_pascal_for(self, node):
        """Lower for — contains kFor, identifier, kAssign, start, kTo/kDownto, end, kDo, body."""
        named_children = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]
        if len(named_children) < 4:
            reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=reg,
                operands=["unsupported:for_incomplete"],
                source_location=self._source_loc(node),
            )
            return

        var_node = named_children[0]
        start_node = named_children[1]
        end_node = named_children[2]
        body_node = named_children[3]

        # Determine direction: kTo or kDownto
        is_downto = any(c.type == "kDownto" for c in node.children)

        var_name = self._node_text(var_node)
        start_reg = self._lower_expr(start_node)
        end_reg = self._lower_expr(end_node)

        self._emit(Opcode.STORE_VAR, operands=[var_name, start_reg])

        loop_label = self._fresh_label("for_cond")
        body_label = self._fresh_label("for_body")
        end_label = self._fresh_label("for_end")

        cmp_op = ">=" if is_downto else "<="

        self._emit(Opcode.LABEL, label=loop_label)
        current_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=current_reg, operands=[var_name])
        cond_reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=cond_reg,
            operands=[cmp_op, current_reg, end_reg],
        )
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
            source_location=self._source_loc(node),
        )

        self._emit(Opcode.LABEL, label=body_label)
        self._lower_stmt(body_node)

        step_op = "-" if is_downto else "+"
        cur_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=cur_reg, operands=[var_name])
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        next_reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=next_reg,
            operands=[step_op, cur_reg, one_reg],
        )
        self._emit(Opcode.STORE_VAR, operands=[var_name, next_reg])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Pascal: procedure/function definition -------------------------------------

    def _lower_pascal_proc(self, node):
        """Lower defProc/declProc — contains kFunction/kProcedure, identifier, declArgs, type, block."""
        id_node = next((c for c in node.children if c.type == "identifier"), None)
        args_node = next((c for c in node.children if c.type == "declArgs"), None)
        body_node = next((c for c in node.children if c.type == "block"), None)

        func_name = self._node_text(id_node) if id_node else "__anon"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=func_label)

        if args_node:
            self._lower_pascal_params(args_node)

        if body_node:
            self._lower_pascal_block(body_node)

        none_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST, result_reg=none_reg, operands=[self.DEFAULT_RETURN_VALUE]
        )
        self._emit(Opcode.RETURN, operands=[none_reg])
        self._emit(Opcode.LABEL, label=end_label)

        func_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=func_reg,
            operands=[
                constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[func_name, func_reg])

    def _lower_pascal_params(self, args_node):
        """Lower declArgs — contains declArg children with identifier and typeref."""
        for child in args_node.children:
            if child.type in _KEYWORD_NOISE:
                continue
            if child.type == "declArg":
                self._lower_pascal_single_param(child)
            elif child.type == "identifier":
                pname = self._node_text(child)
                self._emit(
                    Opcode.SYMBOLIC,
                    result_reg=self._fresh_reg(),
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    source_location=self._source_loc(child),
                )
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[pname, f"%{self._reg_counter - 1}"],
                )

    def _lower_pascal_single_param(self, child):
        """Lower a single declArg — extract identifier name."""
        id_node = next((c for c in child.children if c.type == "identifier"), None)
        if id_node is None:
            return
        pname = self._node_text(id_node)
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=self._fresh_reg(),
            operands=[f"{constants.PARAM_PREFIX}{pname}"],
            source_location=self._source_loc(child),
        )
        self._emit(
            Opcode.STORE_VAR,
            operands=[pname, f"%{self._reg_counter - 1}"],
        )
