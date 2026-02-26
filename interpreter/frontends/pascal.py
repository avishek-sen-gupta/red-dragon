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
        "kCase",
        "kNot",
        "kSub",
        "kAdd",
        "kEq",
        "kConst",
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
            "exprParens": self._lower_paren,
            "exprDot": self._lower_pascal_dot,
            "exprSubscript": self._lower_pascal_subscript,
            "exprUnary": self._lower_pascal_unary,
            "exprBrackets": self._lower_pascal_brackets,
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
            "statements": self._lower_pascal_block,
            "case": self._lower_pascal_case,
            "repeat": self._lower_pascal_repeat,
            "declConsts": self._lower_pascal_decl_consts,
            "declConst": self._lower_pascal_decl_const,
            "declType": self._lower_pascal_noop,
            "declTypes": self._lower_pascal_noop,
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
        """Lower for — contains kFor, assignment(var := start), kTo/kDownto, end, kDo, body.

        The tree-sitter AST packs the loop variable and start value into an
        ``assignment`` node, so named non-noise children are typically 3:
        [assignment, end_value, body].  We detect this case and extract
        var_node / start_node from the assignment.
        """
        named_children = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]

        if len(named_children) >= 3 and named_children[0].type == "assignment":
            assignment_node = named_children[0]
            assign_children = [
                c
                for c in assignment_node.children
                if c.is_named and c.type not in _KEYWORD_NOISE
            ]
            var_node = assign_children[0] if assign_children else None
            start_node = assign_children[1] if len(assign_children) > 1 else None
            end_node = named_children[1]
            body_node = named_children[2]
        elif len(named_children) >= 4:
            var_node = named_children[0]
            start_node = named_children[1]
            end_node = named_children[2]
            body_node = named_children[3]
        else:
            logger.warning(
                "Pascal for-loop: insufficient children (%d), skipping",
                len(named_children),
            )
            return

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

    # -- Pascal: dot access (obj.field) --------------------------------------------

    def _lower_pascal_dot(self, node) -> str:
        """Lower exprDot — first child = object, last child = field name."""
        named_children = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]
        if len(named_children) < 2:
            return self._lower_const_literal(node)
        obj_node = named_children[0]
        field_node = named_children[-1]
        obj_reg = self._lower_expr(obj_node)
        field_name = self._node_text(field_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, field_name],
            source_location=self._source_loc(node),
        )
        return reg

    # -- Pascal: subscript access (arr[idx]) ---------------------------------------

    def _lower_pascal_subscript(self, node) -> str:
        """Lower exprSubscript — object followed by exprArgs containing index."""
        named_children = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]
        if not named_children:
            return self._lower_const_literal(node)
        obj_node = named_children[0]
        args_node = next((c for c in node.children if c.type == "exprArgs"), None)
        obj_reg = self._lower_expr(obj_node)
        if args_node:
            idx_children = [
                c
                for c in args_node.children
                if c.is_named and c.type not in _KEYWORD_NOISE
            ]
            if idx_children:
                idx_reg = self._lower_expr(idx_children[0])
                reg = self._fresh_reg()
                self._emit(
                    Opcode.LOAD_INDEX,
                    result_reg=reg,
                    operands=[obj_reg, idx_reg],
                    source_location=self._source_loc(node),
                )
                return reg
        return obj_reg

    # -- Pascal: unary expression --------------------------------------------------

    _K_UNARY_MAP: dict[str, str] = {
        "kNot": "not",
        "kSub": "-",
        "kAdd": "+",
    }

    def _lower_pascal_unary(self, node) -> str:
        """Lower exprUnary — operator keyword + operand."""
        op_symbol = "?"
        for child in node.children:
            mapped = self._K_UNARY_MAP.get(child.type)
            if mapped:
                op_symbol = mapped
                break
        named_children = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]
        if not named_children:
            return self._lower_const_literal(node)
        operand_reg = self._lower_expr(named_children[0])
        reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=reg,
            operands=[op_symbol, operand_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # -- Pascal: case statement ----------------------------------------------------

    def _lower_pascal_case(self, node):
        """Lower case statement as if/else chain on caseCase children."""
        named_children = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]
        if not named_children:
            return

        # First named child is the selector expression
        selector_node = named_children[0]
        selector_reg = self._lower_expr(selector_node)

        case_cases = [c for c in node.children if c.type == "caseCase"]
        else_case = next((c for c in node.children if c.type == "kElse"), None)

        end_label = self._fresh_label("case_end")

        for case_node in case_cases:
            self._lower_pascal_case_branch(case_node, selector_reg, end_label)

        # Handle else branch: lower remaining statements after kElse
        if else_case:
            logger.debug("Lowering case else branch at %s", self._source_loc(node))
            # Children after kElse are the else-body statements
            found_else = False
            for child in node.children:
                if child.type == "kElse":
                    found_else = True
                    continue
                if found_else and child.is_named and child.type not in _KEYWORD_NOISE:
                    self._lower_stmt(child)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_pascal_case_branch(self, case_node, selector_reg: str, end_label: str):
        """Lower a single caseCase — extract caseLabel values, BINOP == + BRANCH_IF."""
        labels = [c for c in case_node.children if c.type == "caseLabel"]
        body_children = [
            c
            for c in case_node.children
            if c.is_named and c.type not in _KEYWORD_NOISE and c.type != "caseLabel"
        ]

        true_label = self._fresh_label("case_match")
        next_label = self._fresh_label("case_next")

        # Build OR of all label comparisons
        if labels:
            label_values = [
                c
                for lbl in labels
                for c in lbl.children
                if c.is_named and c.type not in _KEYWORD_NOISE
            ]
            if label_values:
                cmp_reg = self._fresh_reg()
                first_val_reg = self._lower_expr(label_values[0])
                self._emit(
                    Opcode.BINOP,
                    result_reg=cmp_reg,
                    operands=["==", selector_reg, first_val_reg],
                    source_location=self._source_loc(case_node),
                )
                for extra_val in label_values[1:]:
                    extra_reg = self._lower_expr(extra_val)
                    extra_cmp = self._fresh_reg()
                    self._emit(
                        Opcode.BINOP,
                        result_reg=extra_cmp,
                        operands=["==", selector_reg, extra_reg],
                    )
                    or_reg = self._fresh_reg()
                    self._emit(
                        Opcode.BINOP,
                        result_reg=or_reg,
                        operands=["or", cmp_reg, extra_cmp],
                    )
                    cmp_reg = or_reg

                self._emit(
                    Opcode.BRANCH_IF,
                    operands=[cmp_reg],
                    label=f"{true_label},{next_label}",
                    source_location=self._source_loc(case_node),
                )

        self._emit(Opcode.LABEL, label=true_label)
        for child in body_children:
            self._lower_stmt(child)
        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=next_label)

    # -- Pascal: repeat-until loop -------------------------------------------------

    def _lower_pascal_repeat(self, node):
        """Lower repeat ... until condition (execute body first, then check)."""
        named_children = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]
        if len(named_children) < 2:
            logger.warning(
                "Pascal repeat with fewer than 2 named children at %s",
                self._source_loc(node),
            )
            return

        # Last named child is the condition, everything before is body
        cond_node = named_children[-1]
        body_nodes = named_children[:-1]

        body_label = self._fresh_label("repeat_body")
        end_label = self._fresh_label("repeat_end")

        self._emit(Opcode.LABEL, label=body_label)
        for child in body_nodes:
            self._lower_stmt(child)

        cond_reg = self._lower_expr(cond_node)
        # repeat-until: loop continues while condition is FALSE
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{end_label},{body_label}",
            source_location=self._source_loc(node),
        )
        self._emit(Opcode.LABEL, label=end_label)

    # -- Pascal: set literal ([1, 2, 3]) -------------------------------------------

    def _lower_pascal_brackets(self, node) -> str:
        """Lower exprBrackets (set literal) as NEW_ARRAY + STORE_INDEX per element."""
        elems = [
            c for c in node.children if c.is_named and c.type not in _KEYWORD_NOISE
        ]
        arr_reg = self._fresh_reg()
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
        self._emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["set", size_reg],
            source_location=self._source_loc(node),
        )
        for i, elem in enumerate(elems):
            val_reg = self._lower_expr(elem)
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    # -- Pascal: const declarations ------------------------------------------------

    def _lower_pascal_decl_consts(self, node):
        """Lower declConsts — iterate declConst children."""
        for child in node.children:
            if child.type == "declConst":
                self._lower_pascal_decl_const(child)

    def _lower_pascal_decl_const(self, node):
        """Lower declConst — extract name + defaultValue child, lower value, STORE_VAR."""
        id_node = next((c for c in node.children if c.type == "identifier"), None)
        if id_node is None:
            return
        var_name = self._node_text(id_node)
        value_node = next((c for c in node.children if c.type == "defaultValue"), None)
        if value_node:
            # defaultValue wraps the actual expression
            inner = next(
                (
                    c
                    for c in value_node.children
                    if c.is_named and c.type not in _KEYWORD_NOISE
                ),
                None,
            )
            val_reg = self._lower_expr(inner) if inner else self._fresh_reg()
            if inner is None:
                self._emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[self.NONE_LITERAL],
                )
        else:
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

    # -- Pascal: type declarations (no-op) -----------------------------------------

    def _lower_pascal_noop(self, node):
        """No-op handler for declType/declTypes — type declarations produce no IR."""
        logger.debug("Skipping %s at %s (no-op)", node.type, self._source_loc(node))
