"""RubyFrontend — tree-sitter Ruby AST -> IR lowering."""

from __future__ import annotations

import logging
from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)


class RubyFrontend(BaseFrontend):
    """Lowers a Ruby tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "nil"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    DEFAULT_RETURN_VALUE = "nil"

    ATTRIBUTE_NODE_TYPE = "call"
    ATTR_OBJECT_FIELD = "receiver"
    ATTR_ATTRIBUTE_FIELD = "method"

    COMMENT_TYPES = frozenset({"comment"})
    NOISE_TYPES = frozenset({"then", "do", "end", "\n"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "instance_variable": self._lower_identifier,
            "constant": self._lower_identifier,
            "integer": self._lower_const_literal,
            "float": self._lower_const_literal,
            "string": self._lower_const_literal,
            "true": self._lower_const_literal,
            "false": self._lower_const_literal,
            "nil": self._lower_const_literal,
            "binary": self._lower_binop,
            "call": self._lower_ruby_call,
            "parenthesized_expression": self._lower_paren,
            "array": self._lower_list_literal,
            "hash": self._lower_ruby_hash,
            "argument_list": self._lower_ruby_argument_list,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "expression_statement": self._lower_expression_statement,
            "assignment": self._lower_assignment,
            "operator_assignment": self._lower_augmented_assignment,
            "return": self._lower_ruby_return,
            "return_statement": self._lower_ruby_return,
            "if": self._lower_if,
            "unless": self._lower_unless,
            "elsif": self._lower_ruby_elsif_stmt,
            "while": self._lower_while,
            "until": self._lower_until,
            "for": self._lower_ruby_for,
            "method": self._lower_ruby_method,
            "class": self._lower_ruby_class,
            "program": self._lower_block,
            "body_statement": self._lower_block,
            "do_block": self._lower_symbolic_block,
            "block": self._lower_symbolic_block,
        }

    # -- Ruby: argument_list unwrap -------------------------------------------

    def _lower_ruby_argument_list(self, node) -> str:
        """Unwrap argument_list to its first named child (e.g. return value)."""
        named = [c for c in node.children if c.is_named]
        if named:
            return self._lower_expr(named[0])
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[self.DEFAULT_RETURN_VALUE])
        return reg

    # -- Ruby: call lowering ---------------------------------------------------

    def _lower_ruby_call(self, node) -> str:
        receiver_node = node.child_by_field_name("receiver")
        method_node = node.child_by_field_name("method")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args(args_node) if args_node else []

        # Method call on receiver: obj.method(...)
        if receiver_node and method_node:
            obj_reg = self._lower_expr(receiver_node)
            method_name = self._node_text(method_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_METHOD,
                result_reg=reg,
                operands=[obj_reg, method_name] + arg_regs,
                source_location=self._source_loc(node),
            )
            return reg

        # Standalone function call: method(args)
        if method_node:
            func_name = self._node_text(method_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=reg,
                operands=[func_name] + arg_regs,
                source_location=self._source_loc(node),
            )
            return reg

        # Fallback: unknown call
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

    # -- Ruby: return ----------------------------------------------------------

    def _lower_ruby_return(self, node):
        children = [
            c for c in node.children if c.type not in ("return", "return_statement")
        ]
        if children:
            val_reg = self._lower_expr(children[0])
        else:
            val_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[self.DEFAULT_RETURN_VALUE],
            )
        self._emit(
            Opcode.RETURN,
            operands=[val_reg],
            source_location=self._source_loc(node),
        )

    # -- Ruby: unless (inverted if) --------------------------------------------

    def _lower_unless(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        cond_reg = self._lower_expr(cond_node)
        negated_reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=negated_reg,
            operands=["!", cond_reg],
            source_location=self._source_loc(node),
        )

        true_label = self._fresh_label("unless_true")
        false_label = self._fresh_label("unless_false")
        end_label = self._fresh_label("unless_end")

        if alt_node:
            self._emit(
                Opcode.BRANCH_IF,
                operands=[negated_reg],
                label=f"{true_label},{false_label}",
                source_location=self._source_loc(node),
            )
        else:
            self._emit(
                Opcode.BRANCH_IF,
                operands=[negated_reg],
                label=f"{true_label},{end_label}",
                source_location=self._source_loc(node),
            )

        self._emit(Opcode.LABEL, label=true_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            self._lower_ruby_alternative(alt_node, end_label)
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Ruby: until (inverted while) ------------------------------------------

    def _lower_until(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

        loop_label = self._fresh_label("until_cond")
        body_label = self._fresh_label("until_body")
        end_label = self._fresh_label("until_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._lower_expr(cond_node)
        negated_reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=negated_reg,
            operands=["!", cond_reg],
            source_location=self._source_loc(node),
        )
        self._emit(
            Opcode.BRANCH_IF,
            operands=[negated_reg],
            label=f"{body_label},{end_label}",
            source_location=self._source_loc(node),
        )

        self._emit(Opcode.LABEL, label=body_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Ruby: for loop --------------------------------------------------------

    def _lower_ruby_for(self, node):
        pattern_node = node.child_by_field_name("pattern")
        value_node = node.child_by_field_name("value")
        body_node = node.child_by_field_name("body")

        iter_reg = self._lower_expr(value_node) if value_node else self._fresh_reg()
        var_name = self._node_text(pattern_node) if pattern_node else "__for_var"

        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

        loop_label = self._fresh_label("for_cond")
        body_label = self._fresh_label("for_body")
        end_label = self._fresh_label("for_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
        )

        self._emit(Opcode.LABEL, label=body_label)
        elem_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[iter_reg, idx_reg])
        self._emit(Opcode.STORE_VAR, operands=[var_name, elem_reg])

        if body_node:
            self._lower_block(body_node)

        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
        self._emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Ruby: method definition -----------------------------------------------

    def _lower_ruby_method(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = self._node_text(name_node) if name_node else "__anon"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_ruby_params(params_node)

        if body_node:
            self._lower_block(body_node)

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

    def _lower_ruby_params(self, params_node):
        for child in params_node.children:
            if child.type in ("(", ")", ",", "|"):
                continue
            pname = self._node_text(child) if child.type == "identifier" else None
            if pname is None:
                pname = self._extract_param_name(child)
            if pname is None:
                continue
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

    # -- Ruby: class definition ------------------------------------------------

    def _lower_ruby_class(self, node):
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        class_name = self._node_text(name_node) if name_node else "__anon_class"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=class_label)
        if body_node:
            self._lower_block(body_node)
        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=cls_reg,
            operands=[
                constants.CLASS_REF_TEMPLATE.format(name=class_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])

    # -- Ruby: if with elsif handling ------------------------------------------

    def _lower_alternative(self, alt_node, end_label: str):
        alt_type = alt_node.type
        if alt_type == "elsif":
            self._lower_ruby_elsif(alt_node, end_label)
        elif alt_type in ("else", "else_clause"):
            for child in alt_node.children:
                if child.type not in ("else", ":") and child.is_named:
                    self._lower_stmt(child)
        else:
            self._lower_block(alt_node)

    def _lower_ruby_elsif(self, node, end_label: str):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("elsif_true")
        false_label = self._fresh_label("elsif_false") if alt_node else end_label

        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
            source_location=self._source_loc(node),
        )

        self._emit(Opcode.LABEL, label=true_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            self._lower_alternative(alt_node, end_label)
            self._emit(Opcode.BRANCH, label=end_label)

    def _lower_ruby_elsif_stmt(self, node):
        """Handle elsif appearing as a top-level statement (fallback)."""
        end_label = self._fresh_label("elsif_end")
        self._lower_ruby_elsif(node, end_label)
        self._emit(Opcode.LABEL, label=end_label)

    def _lower_ruby_alternative(self, alt_node, end_label: str):
        self._lower_alternative(alt_node, end_label)

    # -- Ruby: store target with instance variables ----------------------------

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type in ("identifier", "instance_variable", "constant"):
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
        else:
            super()._lower_store_target(target, val_reg, parent_node)

    # -- Ruby: hash literal ----------------------------------------------------

    def _lower_ruby_hash(self, node) -> str:
        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=["hash"],
            source_location=self._source_loc(node),
        )
        for child in node.children:
            if child.type == "pair":
                key_node = child.child_by_field_name("key")
                val_node = child.child_by_field_name("value")
                if key_node and val_node:
                    key_reg = self._lower_expr(key_node)
                    val_reg = self._lower_expr(val_node)
                    self._emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
        return obj_reg

    # -- Ruby: symbolic block (do_block, block) --------------------------------

    def _lower_symbolic_block(self, node):
        reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"block:{node.type}"],
            source_location=self._source_loc(node),
        )
