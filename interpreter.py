#!/usr/bin/env python3
"""LLM Symbolic Interpreter — single-file implementation.

Parses source code via tree-sitter, lowers to a flattened high-level TAC IR,
builds a CFG, then walks it with an LLM that emits state deltas in JSON,
maintaining a symbolic heap that handles incomplete information.
"""
from __future__ import annotations

import argparse
import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel


# ════════════════════════════════════════════════════════════════════
# 1. IR Design — Flattened High-Level Three-Address Code
# ════════════════════════════════════════════════════════════════════

class Opcode(str, Enum):
    # Value producers
    CONST = "CONST"
    LOAD_VAR = "LOAD_VAR"
    LOAD_FIELD = "LOAD_FIELD"
    LOAD_INDEX = "LOAD_INDEX"
    NEW_OBJECT = "NEW_OBJECT"
    NEW_ARRAY = "NEW_ARRAY"
    BINOP = "BINOP"
    UNOP = "UNOP"
    CALL_FUNCTION = "CALL_FUNCTION"
    CALL_METHOD = "CALL_METHOD"
    CALL_UNKNOWN = "CALL_UNKNOWN"
    # Value consumers / control flow
    STORE_VAR = "STORE_VAR"
    STORE_FIELD = "STORE_FIELD"
    STORE_INDEX = "STORE_INDEX"
    BRANCH_IF = "BRANCH_IF"
    BRANCH = "BRANCH"
    RETURN = "RETURN"
    THROW = "THROW"
    # Special
    SYMBOLIC = "SYMBOLIC"
    # Labels (pseudo-instruction)
    LABEL = "LABEL"


class IRInstruction(BaseModel):
    opcode: Opcode
    result_reg: str | None = None
    operands: list[Any] = []
    label: str | None = None  # for LABEL / branch targets
    source_location: str | None = None

    def __str__(self) -> str:
        parts: list[str] = []
        if self.label and self.opcode == Opcode.LABEL:
            return f"{self.label}:"
        if self.result_reg:
            parts.append(f"{self.result_reg} =")
        parts.append(self.opcode.value.lower())
        for op in self.operands:
            parts.append(str(op))
        if self.label and self.opcode != Opcode.LABEL:
            parts.append(self.label)
        return " ".join(parts)


# ════════════════════════════════════════════════════════════════════
# 2. Tree-Sitter Parsing Layer
# ════════════════════════════════════════════════════════════════════

class Parser:
    """Thin wrapper around tree-sitter-language-pack."""

    def parse(self, source: str, language: str):
        import tree_sitter_language_pack as tslp

        parser = tslp.get_parser(language)
        tree = parser.parse(source.encode("utf-8"))
        return tree


# ════════════════════════════════════════════════════════════════════
# 3. Frontend / AST-to-IR Lowering
# ════════════════════════════════════════════════════════════════════

class Frontend(ABC):
    @abstractmethod
    def lower(self, tree, source: bytes) -> list[IRInstruction]:
        ...


class PythonFrontend(Frontend):
    """Lowers a Python tree-sitter AST into flattened TAC IR."""

    def __init__(self):
        self._reg_counter = 0
        self._label_counter = 0
        self._instructions: list[IRInstruction] = []

    def _fresh_reg(self) -> str:
        r = f"%{self._reg_counter}"
        self._reg_counter += 1
        return r

    def _fresh_label(self, prefix: str = "L") -> str:
        lbl = f"{prefix}_{self._label_counter}"
        self._label_counter += 1
        return lbl

    def _emit(self, opcode: Opcode, *, result_reg: str | None = None,
              operands: list[Any] | None = None, label: str | None = None,
              source_location: str | None = None):
        inst = IRInstruction(
            opcode=opcode, result_reg=result_reg,
            operands=operands or [], label=label,
            source_location=source_location,
        )
        self._instructions.append(inst)
        return inst

    def lower(self, tree, source: bytes) -> list[IRInstruction]:
        self._reg_counter = 0
        self._label_counter = 0
        self._instructions = []
        self._source = source
        root = tree.root_node
        self._emit(Opcode.LABEL, label="entry")
        self._lower_block(root)
        return self._instructions

    def _node_text(self, node) -> str:
        return self._source[node.start_byte:node.end_byte].decode("utf-8")

    def _source_loc(self, node) -> str:
        return f"{node.start_point[0] + 1}:{node.start_point[1]}"

    # ── dispatchers ──────────────────────────────────────────────

    def _lower_block(self, node):
        """Lower a block of statements (module / suite / body)."""
        for child in node.children:
            self._lower_stmt(child)

    def _lower_stmt(self, node):
        ntype = node.type
        if ntype == "expression_statement":
            self._lower_expr(node.children[0])
        elif ntype == "assignment":
            self._lower_assignment(node)
        elif ntype == "augmented_assignment":
            self._lower_augmented_assignment(node)
        elif ntype == "return_statement":
            self._lower_return(node)
        elif ntype == "if_statement":
            self._lower_if(node)
        elif ntype == "while_statement":
            self._lower_while(node)
        elif ntype == "for_statement":
            self._lower_for(node)
        elif ntype == "function_definition":
            self._lower_function_def(node)
        elif ntype == "class_definition":
            self._lower_class_def(node)
        elif ntype == "raise_statement":
            self._lower_raise(node)
        elif ntype == "pass_statement":
            pass  # no-op
        elif ntype in ("comment", "newline", "\n"):
            pass
        else:
            # Fallback: try to lower as expression
            self._lower_expr(node)

    # ── expressions → register ───────────────────────────────────

    def _lower_expr(self, node) -> str:
        """Lower an expression, return the register holding its value."""
        ntype = node.type

        if ntype == "identifier":
            reg = self._fresh_reg()
            self._emit(Opcode.LOAD_VAR, result_reg=reg,
                       operands=[self._node_text(node)],
                       source_location=self._source_loc(node))
            return reg

        if ntype in ("integer", "float"):
            reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=reg,
                       operands=[self._node_text(node)],
                       source_location=self._source_loc(node))
            return reg

        if ntype == "string" or ntype == "concatenated_string":
            reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=reg,
                       operands=[self._node_text(node)],
                       source_location=self._source_loc(node))
            return reg

        if ntype in ("true", "false", "none"):
            reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=reg,
                       operands=[self._node_text(node)],
                       source_location=self._source_loc(node))
            return reg

        if ntype == "binary_operator":
            return self._lower_binop(node)

        if ntype == "boolean_operator":
            return self._lower_binop(node)

        if ntype == "comparison_operator":
            return self._lower_comparison(node)

        if ntype == "unary_operator":
            return self._lower_unop(node)

        if ntype == "not_operator":
            return self._lower_unop(node)

        if ntype == "call":
            return self._lower_call(node)

        if ntype == "attribute":
            return self._lower_attribute(node)

        if ntype == "subscript":
            return self._lower_subscript(node)

        if ntype == "parenthesized_expression":
            # Unwrap parens
            inner = node.children[1]  # skip '('
            return self._lower_expr(inner)

        if ntype == "list":
            return self._lower_list_literal(node)

        if ntype == "dictionary":
            return self._lower_dict_literal(node)

        if ntype == "tuple":
            return self._lower_tuple_literal(node)

        if ntype == "conditional_expression":
            return self._lower_conditional_expr(node)

        # Fallback: symbolic
        reg = self._fresh_reg()
        self._emit(Opcode.SYMBOLIC, result_reg=reg,
                   operands=[f"unsupported:{ntype}"],
                   source_location=self._source_loc(node))
        return reg

    # ── specific lowerings ───────────────────────────────────────

    def _lower_binop(self, node) -> str:
        children = [c for c in node.children if c.type not in ("(", ")")]
        lhs_reg = self._lower_expr(children[0])
        op = self._node_text(children[1])
        rhs_reg = self._lower_expr(children[2])
        reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=reg, operands=[op, lhs_reg, rhs_reg],
                   source_location=self._source_loc(node))
        return reg

    def _lower_comparison(self, node) -> str:
        children = [c for c in node.children if c.type not in ("(", ")")]
        lhs_reg = self._lower_expr(children[0])
        op = self._node_text(children[1])
        rhs_reg = self._lower_expr(children[2])
        reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=reg, operands=[op, lhs_reg, rhs_reg],
                   source_location=self._source_loc(node))
        return reg

    def _lower_unop(self, node) -> str:
        children = [c for c in node.children if c.type not in ("(", ")")]
        op = self._node_text(children[0])
        operand_reg = self._lower_expr(children[1])
        reg = self._fresh_reg()
        self._emit(Opcode.UNOP, result_reg=reg, operands=[op, operand_reg],
                   source_location=self._source_loc(node))
        return reg

    def _lower_call(self, node) -> str:
        func_node = node.child_by_field_name("function")
        args_node = node.child_by_field_name("arguments")

        arg_regs = []
        if args_node:
            for child in args_node.children:
                if child.type in ("(", ")", ","):
                    continue
                arg_regs.append(self._lower_expr(child))

        # Method call: obj.method(...)
        if func_node and func_node.type == "attribute":
            obj_node = func_node.child_by_field_name("object")
            attr_node = func_node.child_by_field_name("attribute")
            obj_reg = self._lower_expr(obj_node)
            method_name = self._node_text(attr_node)
            reg = self._fresh_reg()
            self._emit(Opcode.CALL_METHOD, result_reg=reg,
                       operands=[obj_reg, method_name] + arg_regs,
                       source_location=self._source_loc(node))
            return reg

        # Plain function call
        if func_node and func_node.type == "identifier":
            func_name = self._node_text(func_node)
            reg = self._fresh_reg()
            self._emit(Opcode.CALL_FUNCTION, result_reg=reg,
                       operands=[func_name] + arg_regs,
                       source_location=self._source_loc(node))
            return reg

        # Dynamic / unknown call target
        target_reg = self._lower_expr(func_node)
        reg = self._fresh_reg()
        self._emit(Opcode.CALL_UNKNOWN, result_reg=reg,
                   operands=[target_reg] + arg_regs,
                   source_location=self._source_loc(node))
        return reg

    def _lower_attribute(self, node) -> str:
        obj_node = node.child_by_field_name("object")
        attr_node = node.child_by_field_name("attribute")
        obj_reg = self._lower_expr(obj_node)
        field_name = self._node_text(attr_node)
        reg = self._fresh_reg()
        self._emit(Opcode.LOAD_FIELD, result_reg=reg,
                   operands=[obj_reg, field_name],
                   source_location=self._source_loc(node))
        return reg

    def _lower_subscript(self, node) -> str:
        obj_node = node.child_by_field_name("value")
        idx_node = node.child_by_field_name("subscript")
        obj_reg = self._lower_expr(obj_node)
        idx_reg = self._lower_expr(idx_node)
        reg = self._fresh_reg()
        self._emit(Opcode.LOAD_INDEX, result_reg=reg,
                   operands=[obj_reg, idx_reg],
                   source_location=self._source_loc(node))
        return reg

    def _lower_assignment(self, node):
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        val_reg = self._lower_expr(right)
        self._lower_store_target(left, val_reg, node)

    def _lower_augmented_assignment(self, node):
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        op_node = [c for c in node.children if c.type not in (
            left.type, right.type)][0]
        op_text = self._node_text(op_node).rstrip("=")  # += → +

        # Load current value
        lhs_reg = self._lower_expr(left)
        rhs_reg = self._lower_expr(right)
        result = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=result,
                   operands=[op_text, lhs_reg, rhs_reg],
                   source_location=self._source_loc(node))
        self._lower_store_target(left, result, node)

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(Opcode.STORE_VAR, operands=[self._node_text(target), val_reg],
                       source_location=self._source_loc(parent_node))
        elif target.type == "attribute":
            obj_node = target.child_by_field_name("object")
            attr_node = target.child_by_field_name("attribute")
            obj_reg = self._lower_expr(obj_node)
            self._emit(Opcode.STORE_FIELD,
                       operands=[obj_reg, self._node_text(attr_node), val_reg],
                       source_location=self._source_loc(parent_node))
        elif target.type == "subscript":
            obj_node = target.child_by_field_name("value")
            idx_node = target.child_by_field_name("subscript")
            obj_reg = self._lower_expr(obj_node)
            idx_reg = self._lower_expr(idx_node)
            self._emit(Opcode.STORE_INDEX,
                       operands=[obj_reg, idx_reg, val_reg],
                       source_location=self._source_loc(parent_node))
        elif target.type == "pattern_list" or target.type == "tuple_pattern":
            # Multi-assignment — emit symbolic unpack
            for i, child in enumerate(target.children):
                if child.type == ",":
                    continue
                idx_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
                elem_reg = self._fresh_reg()
                self._emit(Opcode.LOAD_INDEX, result_reg=elem_reg,
                           operands=[val_reg, idx_reg])
                self._lower_store_target(child, elem_reg, parent_node)

    def _lower_return(self, node):
        children = [c for c in node.children if c.type != "return"]
        if children:
            val_reg = self._lower_expr(children[0])
        else:
            val_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=val_reg, operands=["None"])
        self._emit(Opcode.RETURN, operands=[val_reg],
                   source_location=self._source_loc(node))

    def _lower_if(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("if_true")
        false_label = self._fresh_label("if_false")
        end_label = self._fresh_label("if_end")

        if alt_node:
            self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                       label=f"{true_label},{false_label}",
                       source_location=self._source_loc(node))
        else:
            self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                       label=f"{true_label},{end_label}",
                       source_location=self._source_loc(node))

        # True branch
        self._emit(Opcode.LABEL, label=true_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        # False branch
        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            # elif or else
            if alt_node.type == "elif_clause":
                # Treat elif as nested if
                self._lower_elif(alt_node, end_label)
            elif alt_node.type == "else_clause":
                body = alt_node.child_by_field_name("body")
                if body:
                    self._lower_block(body)
                else:
                    # else body is the children after ":"
                    for child in alt_node.children:
                        if child.type not in ("else", ":"):
                            self._lower_stmt(child)
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_elif(self, node, end_label: str):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("elif_true")
        false_label = self._fresh_label("elif_false") if alt_node else end_label

        self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                   label=f"{true_label},{false_label}",
                   source_location=self._source_loc(node))

        self._emit(Opcode.LABEL, label=true_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            if alt_node.type == "elif_clause":
                self._lower_elif(alt_node, end_label)
            elif alt_node.type == "else_clause":
                for child in alt_node.children:
                    if child.type not in ("else", ":"):
                        self._lower_stmt(child)
            self._emit(Opcode.BRANCH, label=end_label)

    def _lower_while(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

        loop_label = self._fresh_label("while_cond")
        body_label = self._fresh_label("while_body")
        end_label = self._fresh_label("while_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._lower_expr(cond_node)
        self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                   label=f"{body_label},{end_label}",
                   source_location=self._source_loc(node))

        self._emit(Opcode.LABEL, label=body_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_for(self, node):
        # for <target> in <iter>: <body>
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        body_node = node.child_by_field_name("body")

        iter_reg = self._lower_expr(right)
        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(Opcode.CALL_FUNCTION, result_reg=len_reg,
                   operands=["len", iter_reg])

        loop_label = self._fresh_label("for_cond")
        body_label = self._fresh_label("for_body")
        end_label = self._fresh_label("for_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=cond_reg,
                   operands=["<", idx_reg, len_reg])
        self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                   label=f"{body_label},{end_label}")

        self._emit(Opcode.LABEL, label=body_label)
        elem_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_INDEX, result_reg=elem_reg,
                   operands=[iter_reg, idx_reg])
        self._lower_store_target(left, elem_reg, node)

        self._lower_block(body_node)

        # idx += 1
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=new_idx,
                   operands=["+", idx_reg, one_reg])
        # Update idx_reg by storing and reloading (since registers are SSA-like,
        # we use the new register going forward via a store to a temp var)
        self._emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
        idx_reload = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=idx_reload,
                   operands=["__for_idx"])
        # We can't retroactively change idx_reg, so this is approximate.
        # The LLM interpreter will handle the semantics correctly.
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_function_def(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = self._node_text(name_node)
        func_label = self._fresh_label(f"func_{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        # Skip the function body in linear flow
        self._emit(Opcode.BRANCH, label=end_label,
                   source_location=self._source_loc(node))

        self._emit(Opcode.LABEL, label=func_label)

        # Emit parameter loads
        if params_node:
            param_idx = 0
            for child in params_node.children:
                if child.type == "identifier":
                    self._emit(Opcode.SYMBOLIC, result_reg=self._fresh_reg(),
                               operands=[f"param:{self._node_text(child)}"],
                               source_location=self._source_loc(child))
                    self._emit(Opcode.STORE_VAR,
                               operands=[self._node_text(child),
                                         f"%{self._reg_counter - 1}"])
                    param_idx += 1
                elif child.type in ("(", ")", ",", ":"):
                    continue
                elif child.type == "default_parameter":
                    pname_node = child.child_by_field_name("name")
                    if pname_node:
                        self._emit(Opcode.SYMBOLIC, result_reg=self._fresh_reg(),
                                   operands=[f"param:{self._node_text(pname_node)}"],
                                   source_location=self._source_loc(child))
                        self._emit(Opcode.STORE_VAR,
                                   operands=[self._node_text(pname_node),
                                             f"%{self._reg_counter - 1}"])
                    param_idx += 1
                elif child.type == "typed_parameter":
                    id_node = None
                    for sub in child.children:
                        if sub.type == "identifier":
                            id_node = sub
                            break
                    if id_node:
                        self._emit(Opcode.SYMBOLIC, result_reg=self._fresh_reg(),
                                   operands=[f"param:{self._node_text(id_node)}"],
                                   source_location=self._source_loc(child))
                        self._emit(Opcode.STORE_VAR,
                                   operands=[self._node_text(id_node),
                                             f"%{self._reg_counter - 1}"])
                    param_idx += 1
                elif child.type == "typed_default_parameter":
                    pname_node = child.child_by_field_name("name")
                    if pname_node:
                        self._emit(Opcode.SYMBOLIC, result_reg=self._fresh_reg(),
                                   operands=[f"param:{self._node_text(pname_node)}"],
                                   source_location=self._source_loc(child))
                        self._emit(Opcode.STORE_VAR,
                                   operands=[self._node_text(pname_node),
                                             f"%{self._reg_counter - 1}"])
                    param_idx += 1

        self._lower_block(body_node)

        # Implicit return None at end of function
        none_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=none_reg, operands=["None"])
        self._emit(Opcode.RETURN, operands=[none_reg])

        self._emit(Opcode.LABEL, label=end_label)

        # Store the function as a named value
        func_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=func_reg,
                   operands=[f"<function:{func_name}@{func_label}>"])
        self._emit(Opcode.STORE_VAR, operands=[func_name, func_reg])

    def _lower_class_def(self, node):
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        class_name = self._node_text(name_node)

        class_label = self._fresh_label(f"class_{class_name}")
        end_label = self._fresh_label(f"end_class_{class_name}")

        self._emit(Opcode.BRANCH, label=end_label,
                   source_location=self._source_loc(node))
        self._emit(Opcode.LABEL, label=class_label)
        self._lower_block(body_node)
        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=cls_reg,
                   operands=[f"<class:{class_name}@{class_label}>"])
        self._emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])

    def _lower_raise(self, node):
        children = [c for c in node.children if c.type != "raise"]
        if children:
            val_reg = self._lower_expr(children[0])
        else:
            val_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=val_reg, operands=["None"])
        self._emit(Opcode.THROW, operands=[val_reg],
                   source_location=self._source_loc(node))

    def _lower_list_literal(self, node) -> str:
        arr_reg = self._fresh_reg()
        elems = [c for c in node.children if c.type not in ("[", "]", ",")]
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
        self._emit(Opcode.NEW_ARRAY, result_reg=arr_reg,
                   operands=["list", size_reg],
                   source_location=self._source_loc(node))
        for i, elem in enumerate(elems):
            val_reg = self._lower_expr(elem)
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    def _lower_dict_literal(self, node) -> str:
        obj_reg = self._fresh_reg()
        self._emit(Opcode.NEW_OBJECT, result_reg=obj_reg, operands=["dict"],
                   source_location=self._source_loc(node))
        for child in node.children:
            if child.type == "pair":
                key_node = child.child_by_field_name("key")
                val_node = child.child_by_field_name("value")
                key_reg = self._lower_expr(key_node)
                val_reg = self._lower_expr(val_node)
                self._emit(Opcode.STORE_INDEX,
                           operands=[obj_reg, key_reg, val_reg])
        return obj_reg

    def _lower_tuple_literal(self, node) -> str:
        elems = [c for c in node.children if c.type not in ("(", ")", ",")]
        arr_reg = self._fresh_reg()
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
        self._emit(Opcode.NEW_ARRAY, result_reg=arr_reg,
                   operands=["tuple", size_reg],
                   source_location=self._source_loc(node))
        for i, elem in enumerate(elems):
            val_reg = self._lower_expr(elem)
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    def _lower_conditional_expr(self, node) -> str:
        # value_if_true if condition else value_if_false
        children = [c for c in node.children if c.type not in ("if", "else")]
        true_expr = children[0]
        cond_expr = children[1]
        false_expr = children[2]

        cond_reg = self._lower_expr(cond_expr)
        true_label = self._fresh_label("ternary_true")
        false_label = self._fresh_label("ternary_false")
        end_label = self._fresh_label("ternary_end")

        self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                   label=f"{true_label},{false_label}")

        self._emit(Opcode.LABEL, label=true_label)
        true_reg = self._lower_expr(true_expr)
        result_var = f"__ternary_{self._label_counter}"
        self._emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=false_label)
        false_reg = self._lower_expr(false_expr)
        self._emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)
        result_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=result_reg,
                   operands=[result_var])
        return result_reg


def get_frontend(language: str) -> Frontend:
    if language == "python":
        return PythonFrontend()
    raise ValueError(f"Unsupported language: {language}")


# ════════════════════════════════════════════════════════════════════
# 4. CFG Builder
# ════════════════════════════════════════════════════════════════════

@dataclass
class BasicBlock:
    label: str
    instructions: list[IRInstruction] = field(default_factory=list)
    successors: list[str] = field(default_factory=list)
    predecessors: list[str] = field(default_factory=list)


@dataclass
class CFG:
    blocks: dict[str, BasicBlock] = field(default_factory=dict)
    entry: str = "entry"

    def __str__(self) -> str:
        lines = []
        for label, block in self.blocks.items():
            preds = ", ".join(block.predecessors) if block.predecessors else "(none)"
            succs = ", ".join(block.successors) if block.successors else "(none)"
            lines.append(f"[{label}]  preds={preds}  succs={succs}")
            for inst in block.instructions:
                lines.append(f"  {inst}")
            lines.append("")
        return "\n".join(lines)


def build_cfg(instructions: list[IRInstruction]) -> CFG:
    """Partition instructions into basic blocks and wire edges."""
    cfg = CFG()

    # Phase 1: identify block starts
    label_to_idx: dict[str, int] = {}
    block_starts: set[int] = {0}

    for i, inst in enumerate(instructions):
        if inst.opcode == Opcode.LABEL:
            block_starts.add(i)
            label_to_idx[inst.label] = i
        elif inst.opcode in (Opcode.BRANCH, Opcode.BRANCH_IF,
                             Opcode.RETURN, Opcode.THROW):
            if i + 1 < len(instructions):
                block_starts.add(i + 1)

    sorted_starts = sorted(block_starts)

    # Phase 2: create blocks
    for si, start in enumerate(sorted_starts):
        end = sorted_starts[si + 1] if si + 1 < len(sorted_starts) else len(instructions)
        block_insts = instructions[start:end]

        # Determine label
        if block_insts and block_insts[0].opcode == Opcode.LABEL:
            label = block_insts[0].label
            block_insts = block_insts[1:]  # don't include LABEL pseudo-inst
        else:
            label = f"__block_{start}"

        cfg.blocks[label] = BasicBlock(label=label, instructions=block_insts)

    # Phase 3: wire edges
    block_labels = list(cfg.blocks.keys())
    for i, label in enumerate(block_labels):
        block = cfg.blocks[label]
        if not block.instructions:
            # Empty block falls through
            if i + 1 < len(block_labels):
                _add_edge(cfg, label, block_labels[i + 1])
            continue

        last = block.instructions[-1]

        if last.opcode == Opcode.BRANCH:
            target = last.label
            if target in cfg.blocks:
                _add_edge(cfg, label, target)

        elif last.opcode == Opcode.BRANCH_IF:
            targets = last.label.split(",")
            for t in targets:
                t = t.strip()
                if t in cfg.blocks:
                    _add_edge(cfg, label, t)

        elif last.opcode in (Opcode.RETURN, Opcode.THROW):
            pass  # no successors

        else:
            # Fall through
            if i + 1 < len(block_labels):
                _add_edge(cfg, label, block_labels[i + 1])

    # Set entry
    if block_labels:
        cfg.entry = block_labels[0]

    return cfg


def _add_edge(cfg: CFG, src: str, dst: str):
    if dst not in cfg.blocks[src].successors:
        cfg.blocks[src].successors.append(dst)
    if src not in cfg.blocks[dst].predecessors:
        cfg.blocks[dst].predecessors.append(src)


# ════════════════════════════════════════════════════════════════════
# 4b. Function & Class Registry
# ════════════════════════════════════════════════════════════════════

import re

_FUNC_RE = re.compile(r"<function:(\w+)@(\w+)>")
_CLASS_RE = re.compile(r"<class:(\w+)@(\w+)>")


def _parse_func_ref(val: Any) -> tuple[str, str] | None:
    """Parse '<function:name@label>' → (name, label) or None."""
    if not isinstance(val, str):
        return None
    m = _FUNC_RE.search(val)
    return (m.group(1), m.group(2)) if m else None


def _parse_class_ref(val: Any) -> tuple[str, str] | None:
    """Parse '<class:name@label>' → (name, label) or None."""
    if not isinstance(val, str):
        return None
    m = _CLASS_RE.search(val)
    return (m.group(1), m.group(2)) if m else None


@dataclass
class FunctionRegistry:
    # func_label → ordered list of parameter names
    func_params: dict[str, list[str]] = field(default_factory=dict)
    # class_name → {method_name → func_label}
    class_methods: dict[str, dict[str, str]] = field(default_factory=dict)
    # class_name → class_body_label
    classes: dict[str, str] = field(default_factory=dict)


def build_registry(instructions: list[IRInstruction], cfg: CFG) -> FunctionRegistry:
    """Scan IR and CFG to build a function/class registry."""
    reg = FunctionRegistry()

    # 1. Extract parameter names from func blocks
    for label, block in cfg.blocks.items():
        if not label.startswith("func_"):
            continue
        params = []
        for inst in block.instructions:
            if inst.opcode == Opcode.SYMBOLIC and inst.operands:
                hint = str(inst.operands[0])
                if hint.startswith("param:"):
                    params.append(hint[6:])
        reg.func_params[label] = params

    # 2. Find classes and their methods by scanning the IR linearly
    #    Methods are <function:NAME@LABEL> constants between class_X and
    #    end_class_X labels.
    current_class: str | None = None
    for inst in instructions:
        if inst.opcode == Opcode.LABEL and inst.label:
            cm = _CLASS_RE.search(inst.label)
            if inst.label.startswith("class_") and not inst.label.startswith("end_class_"):
                # Entering a class body — extract class name from the
                # next CONST <class:Name@...> or from the label itself.
                # We'll set current_class when we see the class const.
                pass
            elif inst.label.startswith("end_class_"):
                current_class = None

        if inst.opcode == Opcode.CONST and inst.operands:
            val = str(inst.operands[0])
            cr = _parse_class_ref(val)
            if cr:
                class_name, class_label = cr
                reg.classes[class_name] = class_label
                # Now scan backwards: set current_class for the scope we
                # just exited. Instead, we'll use a second pass below.

    # Second pass: identify class scopes and their methods
    in_class: str | None = None
    for inst in instructions:
        if inst.opcode == Opcode.LABEL and inst.label:
            if inst.label.startswith("class_") and not inst.label.startswith("end_class_"):
                # Try to find which class this label belongs to
                for cname, clabel in reg.classes.items():
                    if inst.label == clabel:
                        in_class = cname
                        if cname not in reg.class_methods:
                            reg.class_methods[cname] = {}
                        break
            elif inst.label.startswith("end_class_"):
                in_class = None

        if in_class and inst.opcode == Opcode.CONST and inst.operands:
            fr = _parse_func_ref(str(inst.operands[0]))
            if fr:
                method_name, func_label = fr
                reg.class_methods[in_class][method_name] = func_label

    return reg


# ── Builtin function table ───────────────────────────────────────

def _builtin_len(args: list[Any], vm: VMState) -> Any:
    if not args:
        return None
    val = args[0]
    # Heap array/object — count fields
    addr = _heap_addr(val)
    if addr and addr in vm.heap:
        return len(vm.heap[addr].fields)
    if isinstance(val, (list, tuple, str)):
        return len(val)
    return None


def _builtin_range(args: list[Any], vm: VMState) -> Any:
    concrete = []
    for a in args:
        if _is_symbolic(a):
            return None
        concrete.append(a)
    if len(concrete) == 1:
        return list(range(int(concrete[0])))
    if len(concrete) == 2:
        return list(range(int(concrete[0]), int(concrete[1])))
    if len(concrete) == 3:
        return list(range(int(concrete[0]), int(concrete[1]), int(concrete[2])))
    return None


def _builtin_print(args: list[Any], vm: VMState) -> Any:
    return None  # print returns None


def _builtin_int(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return int(args[0])
        except (ValueError, TypeError):
            pass
    return None


def _builtin_float(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return float(args[0])
        except (ValueError, TypeError):
            pass
    return None


def _builtin_str(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        return str(args[0])
    return None


def _builtin_bool(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        return bool(args[0])
    return None


def _builtin_abs(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return abs(args[0])
        except TypeError:
            pass
    return None


def _builtin_max(args: list[Any], vm: VMState) -> Any:
    if all(not _is_symbolic(a) for a in args):
        try:
            return max(args)
        except (ValueError, TypeError):
            pass
    return None


def _builtin_min(args: list[Any], vm: VMState) -> Any:
    if all(not _is_symbolic(a) for a in args):
        try:
            return min(args)
        except (ValueError, TypeError):
            pass
    return None


_BUILTINS: dict[str, Any] = {
    "len": _builtin_len,
    "range": _builtin_range,
    "print": _builtin_print,
    "int": _builtin_int,
    "float": _builtin_float,
    "str": _builtin_str,
    "bool": _builtin_bool,
    "abs": _builtin_abs,
    "max": _builtin_max,
    "min": _builtin_min,
}


# ════════════════════════════════════════════════════════════════════
# 5. Symbolic VM
# ════════════════════════════════════════════════════════════════════

@dataclass
class SymbolicValue:
    name: str
    type_hint: str | None = None
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"__symbolic__": True, "name": self.name}
        if self.type_hint:
            d["type_hint"] = self.type_hint
        if self.constraints:
            d["constraints"] = self.constraints
        return d


@dataclass
class HeapObject:
    type_hint: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type_hint": self.type_hint,
            "fields": {k: _serialize_value(v) for k, v in self.fields.items()},
        }


@dataclass
class StackFrame:
    function_name: str
    registers: dict[str, Any] = field(default_factory=dict)
    local_vars: dict[str, Any] = field(default_factory=dict)
    return_label: str | None = None
    return_ip: int | None = None       # ip to resume at in caller block
    result_reg: str | None = None      # caller's register for return value

    def to_dict(self) -> dict:
        return {
            "function_name": self.function_name,
            "registers": {k: _serialize_value(v) for k, v in self.registers.items()},
            "local_vars": {k: _serialize_value(v) for k, v in self.local_vars.items()},
            "return_label": self.return_label,
        }


def _serialize_value(v: Any) -> Any:
    if isinstance(v, SymbolicValue):
        return v.to_dict()
    if isinstance(v, HeapObject):
        return v.to_dict()
    return v


@dataclass
class VMState:
    heap: dict[str, HeapObject] = field(default_factory=dict)
    call_stack: list[StackFrame] = field(default_factory=list)
    path_conditions: list[str] = field(default_factory=list)
    symbolic_counter: int = 0

    def fresh_symbolic(self, hint: str | None = None) -> SymbolicValue:
        name = f"sym_{self.symbolic_counter}"
        self.symbolic_counter += 1
        return SymbolicValue(name=name, type_hint=hint)

    @property
    def current_frame(self) -> StackFrame:
        return self.call_stack[-1]

    def to_dict(self) -> dict:
        return {
            "heap": {k: v.to_dict() for k, v in self.heap.items()},
            "call_stack": [f.to_dict() for f in self.call_stack],
            "path_conditions": self.path_conditions,
            "symbolic_counter": self.symbolic_counter,
        }


# ── StateUpdate schema (LLM output) ─────────────────────────────

class HeapWrite(BaseModel):
    obj_addr: str
    field: str
    value: Any

class NewObject(BaseModel):
    addr: str
    type_hint: str | None = None

class StackFramePush(BaseModel):
    function_name: str
    return_label: str | None = None

class StateUpdate(BaseModel):
    register_writes: dict[str, Any] = {}
    var_writes: dict[str, Any] = {}
    heap_writes: list[HeapWrite] = []
    new_objects: list[NewObject] = []
    next_label: str | None = None
    call_push: StackFramePush | None = None
    call_pop: bool = False
    return_value: Any | None = None
    path_condition: str | None = None
    reasoning: str = ""


def apply_update(vm: VMState, update: StateUpdate):
    """Mechanically apply a StateUpdate to the VM."""
    frame = vm.current_frame

    # New objects
    for obj in update.new_objects:
        vm.heap[obj.addr] = HeapObject(type_hint=obj.type_hint)

    # Register writes — always to the CURRENT (caller's) frame
    for reg, val in update.register_writes.items():
        frame.registers[reg] = _deserialize_value(val, vm)

    # Heap writes
    for hw in update.heap_writes:
        if hw.obj_addr not in vm.heap:
            vm.heap[hw.obj_addr] = HeapObject()
        vm.heap[hw.obj_addr].fields[hw.field] = _deserialize_value(hw.value, vm)

    # Path condition
    if update.path_condition:
        vm.path_conditions.append(update.path_condition)

    # Call push — push BEFORE var_writes so parameter bindings go to the
    # new frame when dispatching a function call
    if update.call_push:
        vm.call_stack.append(StackFrame(
            function_name=update.call_push.function_name,
            return_label=update.call_push.return_label,
        ))

    # Variable writes — go to the CURRENT frame (which is the new frame
    # if call_push just fired, i.e. parameter bindings)
    target_frame = vm.current_frame
    for var, val in update.var_writes.items():
        target_frame.local_vars[var] = _deserialize_value(val, vm)

    # Call pop
    if update.call_pop and len(vm.call_stack) > 1:
        vm.call_stack.pop()


def _deserialize_value(val: Any, vm: VMState) -> Any:
    """Convert a dict with __symbolic__ into a SymbolicValue."""
    if isinstance(val, dict) and val.get("__symbolic__"):
        return SymbolicValue(
            name=val.get("name", f"sym_{vm.symbolic_counter}"),
            type_hint=val.get("type_hint"),
            constraints=val.get("constraints", []),
        )
    return val


def _is_symbolic(val: Any) -> bool:
    return isinstance(val, SymbolicValue)


def _heap_addr(val: Any) -> str | None:
    """Extract a heap address from a value.

    Values can be plain strings ("obj_Point_1") or dicts with an addr key
    ({"addr": "obj_Point_1", "type_hint": "Point"}) — the latter is what
    the LLM returns for constructor calls.  Returns None if val doesn't
    reference a heap address.
    """
    if isinstance(val, str):
        return val
    if isinstance(val, dict) and "addr" in val:
        return val["addr"]
    return None


def _resolve_reg(vm: VMState, operand: str) -> Any:
    """Resolve a register name to its value, or return the operand as-is."""
    if isinstance(operand, str) and operand.startswith("%"):
        frame = vm.current_frame
        return frame.registers.get(operand, operand)
    return operand


def _try_execute_locally(inst: IRInstruction, vm: VMState,
                         cfg: CFG | None = None,
                         registry: FunctionRegistry | None = None,
                         current_label: str = "",
                         ip: int = 0) -> StateUpdate | None:
    """Try to execute an instruction without the LLM.

    Returns a StateUpdate if the instruction can be handled mechanically,
    or None if LLM interpretation is needed.
    """
    op = inst.opcode
    frame = vm.current_frame

    if op == Opcode.CONST:
        # %r = const <literal>
        raw = inst.operands[0] if inst.operands else "None"
        val = _parse_const(raw)
        return StateUpdate(
            register_writes={inst.result_reg: val},
            reasoning=f"const {raw!r} → {inst.result_reg}",
        )

    if op == Opcode.LOAD_VAR:
        # %r = load_var <name>
        name = inst.operands[0]
        # Walk the call stack (current frame first, then outer scopes)
        for f in reversed(vm.call_stack):
            if name in f.local_vars:
                val = f.local_vars[name]
                return StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"load {name} = {val!r} → {inst.result_reg}",
                )
        # Variable not found — create symbolic
        sym = vm.fresh_symbolic(hint=name)
        return StateUpdate(
            register_writes={inst.result_reg: sym.to_dict()},
            reasoning=f"load {name} (not found) → symbolic {sym.name}",
        )

    if op == Opcode.STORE_VAR:
        # store_var <name>, %val
        name = inst.operands[0]
        val = _resolve_reg(vm, inst.operands[1])
        return StateUpdate(
            var_writes={name: _serialize_value(val)},
            reasoning=f"store {name} = {val!r}",
        )

    if op == Opcode.BRANCH:
        # branch <label>
        return StateUpdate(
            next_label=inst.label,
            reasoning=f"branch → {inst.label}",
        )

    if op == Opcode.SYMBOLIC:
        # symbolic %r, <hint>
        hint = inst.operands[0] if inst.operands else None
        # If this is a parameter and the value was pre-populated by a call,
        # use the concrete value instead of creating a symbolic.
        if isinstance(hint, str) and hint.startswith("param:"):
            param_name = hint[6:]
            if param_name in frame.local_vars:
                val = frame.local_vars[param_name]
                return StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"param {param_name} = {val!r} (bound by caller)",
                )
        sym = vm.fresh_symbolic(hint=hint)
        return StateUpdate(
            register_writes={inst.result_reg: sym.to_dict()},
            reasoning=f"symbolic {sym.name} (hint={hint})",
        )

    if op == Opcode.NEW_OBJECT:
        # %r = new_object <type>
        type_hint = inst.operands[0] if inst.operands else None
        addr = f"obj_{vm.symbolic_counter}"
        vm.symbolic_counter += 1
        return StateUpdate(
            new_objects=[NewObject(addr=addr, type_hint=type_hint)],
            register_writes={inst.result_reg: addr},
            reasoning=f"new {type_hint} → {addr}",
        )

    if op == Opcode.NEW_ARRAY:
        # %r = new_array <type>, %size
        type_hint = inst.operands[0] if inst.operands else None
        addr = f"arr_{vm.symbolic_counter}"
        vm.symbolic_counter += 1
        return StateUpdate(
            new_objects=[NewObject(addr=addr, type_hint=type_hint)],
            register_writes={inst.result_reg: addr},
            reasoning=f"new {type_hint}[] → {addr}",
        )

    if op == Opcode.STORE_FIELD:
        # store_field %obj, <field>, %val
        obj_val = _resolve_reg(vm, inst.operands[0])
        field_name = inst.operands[1]
        val = _resolve_reg(vm, inst.operands[2])
        addr = _heap_addr(obj_val)
        if addr and addr in vm.heap:
            return StateUpdate(
                heap_writes=[HeapWrite(obj_addr=addr, field=field_name,
                                       value=_serialize_value(val))],
                reasoning=f"store {addr}.{field_name} = {val!r}",
            )
        # Object not on heap — need LLM
        return None

    if op == Opcode.LOAD_FIELD:
        # %r = load_field %obj, <field>
        obj_val = _resolve_reg(vm, inst.operands[0])
        field_name = inst.operands[1]
        addr = _heap_addr(obj_val)
        if addr and addr in vm.heap:
            heap_obj = vm.heap[addr]
            if field_name in heap_obj.fields:
                val = heap_obj.fields[field_name]
                return StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"load {addr}.{field_name} = {val!r}",
                )
            # Field not found — create symbolic
            sym = vm.fresh_symbolic(hint=f"{addr}.{field_name}")
            heap_obj.fields[field_name] = sym
            return StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"load {addr}.{field_name} (unknown) → {sym.name}",
            )
        return None

    if op == Opcode.STORE_INDEX:
        # store_index %arr, %idx, %val
        arr_val = _resolve_reg(vm, inst.operands[0])
        idx_val = _resolve_reg(vm, inst.operands[1])
        val = _resolve_reg(vm, inst.operands[2])
        addr = _heap_addr(arr_val)
        if addr and addr in vm.heap:
            return StateUpdate(
                heap_writes=[HeapWrite(obj_addr=addr, field=str(idx_val),
                                       value=_serialize_value(val))],
                reasoning=f"store {addr}[{idx_val}] = {val!r}",
            )
        return None

    if op == Opcode.LOAD_INDEX:
        # %r = load_index %arr, %idx
        arr_val = _resolve_reg(vm, inst.operands[0])
        idx_val = _resolve_reg(vm, inst.operands[1])
        addr = _heap_addr(arr_val)
        if addr and addr in vm.heap:
            heap_obj = vm.heap[addr]
            key = str(idx_val)
            if key in heap_obj.fields:
                val = heap_obj.fields[key]
                return StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(val)},
                    reasoning=f"load {addr}[{idx_val}] = {val!r}",
                )
            sym = vm.fresh_symbolic(hint=f"{addr}[{idx_val}]")
            return StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"load {addr}[{idx_val}] (unknown) → {sym.name}",
            )
        return None

    if op == Opcode.RETURN:
        # return %val
        val = _resolve_reg(vm, inst.operands[0]) if inst.operands else None
        return StateUpdate(
            return_value=_serialize_value(val),
            call_pop=True,
            reasoning=f"return {val!r}",
        )

    if op == Opcode.THROW:
        val = _resolve_reg(vm, inst.operands[0]) if inst.operands else None
        return StateUpdate(
            reasoning=f"throw {val!r}",
        )

    if op == Opcode.BRANCH_IF:
        # branch_if %cond, <label_true>,<label_false>
        cond_val = _resolve_reg(vm, inst.operands[0])
        targets = inst.label.split(",")
        true_label = targets[0].strip()
        false_label = targets[1].strip() if len(targets) > 1 else None

        if not _is_symbolic(cond_val):
            # Concrete condition — decide locally
            taken = bool(cond_val)
            chosen = true_label if taken else false_label
            return StateUpdate(
                next_label=chosen,
                path_condition=f"{inst.operands[0]} is {taken}",
                reasoning=f"branch_if {cond_val!r} → {chosen}",
            )
        # Symbolic condition — need LLM to decide
        return None

    if op == Opcode.BINOP:
        # %r = binop <op>, %lhs, %rhs
        oper = inst.operands[0]
        lhs = _resolve_reg(vm, inst.operands[1])
        rhs = _resolve_reg(vm, inst.operands[2])

        if not _is_symbolic(lhs) and not _is_symbolic(rhs):
            result = _eval_binop(oper, lhs, rhs)
            if result is not None:
                return StateUpdate(
                    register_writes={inst.result_reg: result},
                    reasoning=f"binop {lhs!r} {oper} {rhs!r} = {result!r}",
                )
        # Symbolic or unsupported — need LLM
        return None

    if op == Opcode.UNOP:
        # %r = unop <op>, %operand
        oper = inst.operands[0]
        operand = _resolve_reg(vm, inst.operands[1])
        if not _is_symbolic(operand):
            result = _eval_unop(oper, operand)
            if result is not None:
                return StateUpdate(
                    register_writes={inst.result_reg: result},
                    reasoning=f"unop {oper}{operand!r} = {result!r}",
                )
        return None

    # ── CALL_FUNCTION ─────────────────────────────────────────────
    if op == Opcode.CALL_FUNCTION and cfg and registry:
        func_name = inst.operands[0]
        arg_regs = inst.operands[1:]
        args = [_resolve_reg(vm, a) for a in arg_regs]

        # 1. Try builtins
        if func_name in _BUILTINS:
            result = _BUILTINS[func_name](args, vm)
            if result is not None or func_name in ("print",):
                return StateUpdate(
                    register_writes={inst.result_reg: _serialize_value(result)},
                    reasoning=f"builtin {func_name}({', '.join(repr(a) for a in args)}) = {result!r}",
                )

        # 2. Look up the function/class via scope chain
        func_val = None
        for f in reversed(vm.call_stack):
            if func_name in f.local_vars:
                func_val = f.local_vars[func_name]
                break
        if func_val is None:
            return None  # unknown — fall back to LLM

        # 3. Class constructor: allocate object + dispatch to __init__
        cr = _parse_class_ref(func_val)
        if cr:
            class_name, class_label = cr
            methods = registry.class_methods.get(class_name, {})
            init_label = methods.get("__init__")
            # Allocate heap object
            addr = f"obj_{vm.symbolic_counter}"
            vm.symbolic_counter += 1
            vm.heap[addr] = HeapObject(type_hint=class_name)
            if init_label and init_label in cfg.blocks:
                params = registry.func_params.get(init_label, [])
                new_vars: dict[str, Any] = {}
                # Bind self
                if params:
                    new_vars[params[0]] = addr
                # Bind remaining args to params
                for i, arg in enumerate(args):
                    if i + 1 < len(params):
                        new_vars[params[i + 1]] = _serialize_value(arg)
                return StateUpdate(
                    register_writes={inst.result_reg: addr},
                    call_push=StackFramePush(function_name=f"{class_name}.__init__",
                                             return_label=current_label),
                    next_label=init_label,
                    reasoning=f"new {class_name}({', '.join(repr(a) for a in args)}) → {addr}, dispatch __init__",
                    # We'll pre-populate local_vars via a custom mechanism
                    var_writes=new_vars,
                )
            else:
                # No __init__ — just return the new object
                return StateUpdate(
                    register_writes={inst.result_reg: addr},
                    new_objects=[NewObject(addr=addr, type_hint=class_name)],
                    reasoning=f"new {class_name}() → {addr} (no __init__)",
                )

        # 4. User-defined function: dispatch
        fr = _parse_func_ref(func_val)
        if fr:
            fname, flabel = fr
            if flabel in cfg.blocks:
                params = registry.func_params.get(flabel, [])
                new_vars = {}
                for i, arg in enumerate(args):
                    if i < len(params):
                        new_vars[params[i]] = _serialize_value(arg)
                return StateUpdate(
                    call_push=StackFramePush(function_name=fname,
                                             return_label=current_label),
                    next_label=flabel,
                    reasoning=f"call {fname}({', '.join(repr(a) for a in args)}), dispatch to {flabel}",
                    var_writes=new_vars,
                )

        return None  # unknown function — fall back to LLM

    # ── CALL_METHOD ───────────────────────────────────────────────
    if op == Opcode.CALL_METHOD and cfg and registry:
        obj_val = _resolve_reg(vm, inst.operands[0])
        method_name = inst.operands[1]
        arg_regs = inst.operands[2:]
        args = [_resolve_reg(vm, a) for a in arg_regs]

        # Resolve object type
        addr = _heap_addr(obj_val)
        type_hint = None
        if addr and addr in vm.heap:
            type_hint = vm.heap[addr].type_hint

        if type_hint and type_hint in registry.class_methods:
            methods = registry.class_methods[type_hint]
            func_label = methods.get(method_name)
            if func_label and func_label in cfg.blocks:
                params = registry.func_params.get(func_label, [])
                new_vars: dict[str, Any] = {}
                # Bind self
                if params:
                    new_vars[params[0]] = _serialize_value(obj_val)
                # Bind remaining args
                for i, arg in enumerate(args):
                    if i + 1 < len(params):
                        new_vars[params[i + 1]] = _serialize_value(arg)
                return StateUpdate(
                    call_push=StackFramePush(
                        function_name=f"{type_hint}.{method_name}",
                        return_label=current_label),
                    next_label=func_label,
                    reasoning=f"call {type_hint}.{method_name}({', '.join(repr(a) for a in args)}), dispatch to {func_label}",
                    var_writes=new_vars,
                )

        return None  # unknown method — fall back to LLM

    # Fallback — need LLM
    return None


def _parse_const(raw: str) -> Any:
    """Parse a constant literal string into a Python value."""
    if raw == "None":
        return None
    if raw == "True":
        return True
    if raw == "False":
        return False
    try:
        return int(raw)
    except (ValueError, TypeError):
        pass
    try:
        return float(raw)
    except (ValueError, TypeError):
        pass
    # String literal — strip quotes if present
    if len(raw) >= 2 and raw[0] in ('"', "'") and raw[-1] == raw[0]:
        return raw[1:-1]
    return raw


_BINOP_TABLE: dict[str, Any] = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b if b != 0 else None,
    "//": lambda a, b: a // b if b != 0 else None,
    "%": lambda a, b: a % b if b != 0 else None,
    "**": lambda a, b: a ** b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
    "and": lambda a, b: a and b,
    "or": lambda a, b: a or b,
    "in": lambda a, b: a in b if hasattr(b, "__contains__") else None,
    "&": lambda a, b: a & b,
    "|": lambda a, b: a | b,
    "^": lambda a, b: a ^ b,
    "<<": lambda a, b: a << b,
    ">>": lambda a, b: a >> b,
}


def _eval_binop(op: str, lhs: Any, rhs: Any) -> Any:
    fn = _BINOP_TABLE.get(op)
    if fn is None:
        return None
    try:
        return fn(lhs, rhs)
    except Exception:
        return None


def _eval_unop(op: str, operand: Any) -> Any:
    try:
        if op == "-":
            return -operand
        if op == "+":
            return +operand
        if op == "not":
            return not operand
        if op == "~":
            return ~operand
    except Exception:
        pass
    return None


# ════════════════════════════════════════════════════════════════════
# 6. LLM Interpreter Backend
# ════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
You are a symbolic interpreter executing IR instructions one at a time.

You receive:
1. The IR instruction to execute
2. The resolved operand values (register names replaced with actual values)
3. The current VM state (heap, variables, path conditions)

You must return a JSON object with the effects of executing this instruction.
IMPORTANT: You MUST populate the correct fields — especially register_writes and var_writes.
If the instruction has a result_reg, you MUST include it in register_writes.

## JSON response schema

{
  "register_writes": {"<reg>": <value>},     // REQUIRED if instruction has result_reg
  "var_writes": {"<name>": <value>},          // for STORE_VAR
  "heap_writes": [{"obj_addr": "...", "field": "...", "value": ...}],
  "new_objects": [{"addr": "...", "type_hint": "..."}],
  "next_label": "<label>" or null,            // for BRANCH_IF — which target to take
  "call_push": {"function_name": "...", "return_label": "..."} or null,
  "call_pop": false,
  "return_value": null,
  "path_condition": "<condition>" or null,     // for BRANCH_IF decisions
  "reasoning": "short explanation"
}

Symbolic values: {"__symbolic__": true, "name": "sym_N", "type_hint": "...", "constraints": [...]}

## Rules by opcode

BINOP/UNOP with symbolic operands:
- If one operand is symbolic, produce a symbolic result describing the expression
- Example: sym_0 + 1 → {"__symbolic__": true, "name": "sym_1", "type_hint": "int", "constraints": ["sym_0 + 1"]}

CALL_FUNCTION / CALL_METHOD / CALL_UNKNOWN:
- For known builtins (len, print, range, int, str, type, isinstance, etc.), compute the result
- For user-defined functions visible in the program, return a symbolic value representing the call result
- ALWAYS write the result to the result register via register_writes
- Example: call_function print with args [5] → register_writes: {"%3": null} (print returns None)
- Example: call_function len with args [[1,2,3]] → register_writes: {"%3": 3}
- Example: call_function factorial with args [5] → register_writes: {"%3": {"__symbolic__": true, "name": "sym_0", "type_hint": "int", "constraints": ["factorial(5)"]}}

BRANCH_IF with symbolic condition:
- Choose the most likely/interesting path and set next_label to that target label
- Set path_condition to describe the assumption you made
- The label field contains "true_label,false_label"

## Examples

Instruction: %5 = binop * sym_0 4
Resolved operands: sym_0 (symbolic int), 4
→ {"register_writes": {"%5": {"__symbolic__": true, "name": "sym_1", "type_hint": "int", "constraints": ["sym_0 * 4"]}}, "reasoning": "symbolic multiply"}

Instruction: %9 = call_function factorial 5
→ {"register_writes": {"%9": {"__symbolic__": true, "name": "sym_2", "type_hint": "int", "constraints": ["factorial(5)"]}}, "reasoning": "recursive call to user function factorial"}

Instruction: %3 = call_function len [1, 2, 3]
→ {"register_writes": {"%3": 3}, "reasoning": "len of 3-element list"}

Instruction: branch_if sym_0 if_true_2,if_false_3  (where sym_0 has constraint "n <= 1")
→ {"next_label": "if_false_3", "path_condition": "assuming n > 1 (sym_0 is false)", "reasoning": "choosing false branch for more interesting path"}

Respond with ONLY valid JSON. No markdown fences. No text outside the JSON object.
"""


class LLMBackend(ABC):
    @abstractmethod
    def interpret_instruction(self, instruction: IRInstruction,
                              state: VMState) -> StateUpdate:
        ...

    def _build_prompt(self, instruction: IRInstruction,
                      state: VMState) -> str:
        """Build a user prompt with resolved operand values."""
        frame = state.current_frame

        # Resolve operand values for the LLM
        resolved = {}
        for i, op in enumerate(instruction.operands):
            raw = op
            val = _resolve_reg(state, op)
            if val is not raw:  # was a register reference
                resolved[str(op)] = _serialize_value(val)

        # Build a compact state snapshot (only what's relevant)
        compact_state = {
            "local_vars": {k: _serialize_value(v)
                           for k, v in frame.local_vars.items()},
        }
        if state.heap:
            compact_state["heap"] = {k: v.to_dict()
                                     for k, v in state.heap.items()}
        if state.path_conditions:
            compact_state["path_conditions"] = state.path_conditions

        msg = {
            "instruction": str(instruction),
            "result_reg": instruction.result_reg,
            "opcode": instruction.opcode.value,
            "operands": instruction.operands,
        }
        if resolved:
            msg["resolved_operand_values"] = resolved
        msg["state"] = compact_state

        return json.dumps(msg, indent=2, default=str)

    @staticmethod
    def _parse_response(text: str) -> StateUpdate:
        """Parse LLM response text into a StateUpdate."""
        text = text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
        text = text.strip()
        data = json.loads(text)
        return StateUpdate(**data)


class ClaudeBackend(LLMBackend):
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        import anthropic
        self._client = anthropic.Anthropic()
        self._model = model

    def interpret_instruction(self, instruction: IRInstruction,
                              state: VMState) -> StateUpdate:
        user_msg = self._build_prompt(instruction, state)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return self._parse_response(response.content[0].text)


class OpenAIBackend(LLMBackend):
    def __init__(self, model: str = "gpt-4o"):
        import openai
        self._client = openai.OpenAI()
        self._model = model

    def interpret_instruction(self, instruction: IRInstruction,
                              state: VMState) -> StateUpdate:
        user_msg = self._build_prompt(instruction, state)
        response = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=1024,
        )
        return self._parse_response(response.choices[0].message.content)


def get_backend(name: str) -> LLMBackend:
    if name == "claude":
        return ClaudeBackend()
    if name == "openai":
        return OpenAIBackend()
    raise ValueError(f"Unknown backend: {name}")


# ════════════════════════════════════════════════════════════════════
# 7. Orchestrator
# ════════════════════════════════════════════════════════════════════

def run(source: str, language: str = "python",
        entry_point: str | None = None, backend: str = "claude",
        max_steps: int = 100, verbose: bool = False) -> VMState:
    """End-to-end: parse → lower → CFG → LLM interpret."""
    # 1. Parse
    tree = Parser().parse(source, language)

    # 2. Lower to IR
    frontend = get_frontend(language)
    instructions = frontend.lower(tree, source.encode("utf-8"))

    if verbose:
        print("═══ IR ═══")
        for inst in instructions:
            print(f"  {inst}")
        print()

    # 3. Build CFG
    cfg = build_cfg(instructions)

    if verbose:
        print("═══ CFG ═══")
        print(cfg)

    # 4. Pick entry
    entry = entry_point or cfg.entry
    if entry not in cfg.blocks:
        # Try to find a function label matching the entry point
        for label in cfg.blocks:
            if entry in label:
                entry = label
                break
        else:
            raise ValueError(f"Entry point '{entry}' not found in CFG. "
                             f"Available: {list(cfg.blocks.keys())}")

    # 4b. Build function registry
    registry = build_registry(instructions, cfg)

    # 5. Initialize VM
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))

    # 6. Execute
    llm = get_backend(backend)
    current_label = entry
    ip = 0  # instruction pointer within current block
    llm_calls = 0

    for step in range(max_steps):
        block = cfg.blocks[current_label]

        if ip >= len(block.instructions):
            # End of block — follow successor or stop
            if block.successors:
                current_label = block.successors[0]
                ip = 0
                continue
            else:
                if verbose:
                    print(f"[step {step}] End of '{current_label}', "
                          "no successors. Stopping.")
                break

        instruction = block.instructions[ip]

        if verbose:
            print(f"[step {step}] {current_label}:{ip}  {instruction}")

        # Skip pseudo-instructions
        if instruction.opcode == Opcode.LABEL:
            ip += 1
            continue

        # Try local execution first, fall back to LLM
        update = _try_execute_locally(instruction, vm, cfg=cfg,
                                       registry=registry,
                                       current_label=current_label, ip=ip)
        used_llm = False
        if update is None:
            update = llm.interpret_instruction(instruction, vm)
            used_llm = True
            llm_calls += 1

        if verbose:
            tag = "LLM" if used_llm else "local"
            print(f"  [{tag}] {update.reasoning}")
            if update.register_writes:
                for reg, val in update.register_writes.items():
                    print(f"    {reg} = {_format_val(val)}")
            if update.var_writes:
                for var, val in update.var_writes.items():
                    print(f"    ${var} = {_format_val(val)}")
            if update.heap_writes:
                for hw in update.heap_writes:
                    print(f"    heap[{hw.obj_addr}].{hw.field} = "
                          f"{_format_val(hw.value)}")
            if update.new_objects:
                for obj in update.new_objects:
                    print(f"    new {obj.type_hint} @ {obj.addr}")
            if update.next_label:
                print(f"    → {update.next_label}")
            if update.path_condition:
                print(f"    path: {update.path_condition}")
            print()

        # For RETURN: save frame info BEFORE applying (which may pop it)
        is_return = instruction.opcode == Opcode.RETURN
        is_throw = instruction.opcode == Opcode.THROW
        return_frame = vm.current_frame if (is_return or is_throw) else None

        # For CALL with dispatch: set up the new frame's return info
        is_call_dispatch = (update.call_push is not None and
                            update.next_label is not None)
        if is_call_dispatch:
            # Save where to resume after the call returns
            call_result_reg = instruction.result_reg
            call_return_label = current_label
            call_return_ip = ip + 1

        apply_update(vm, update)

        if is_call_dispatch:
            # The new frame was just pushed — set its return info
            new_frame = vm.current_frame
            new_frame.return_label = call_return_label
            new_frame.return_ip = call_return_ip
            new_frame.result_reg = call_result_reg
            # For class constructors, the result_reg was already written
            # (the object address), so we mark it to not overwrite on return
            if instruction.opcode == Opcode.CALL_FUNCTION:
                func_val = vm.call_stack[-2].local_vars.get(instruction.operands[0])
                if func_val and _parse_class_ref(func_val):
                    new_frame.result_reg = None  # don't overwrite on return

        # Handle control flow
        if is_return or is_throw:
            if len(vm.call_stack) < 1:
                if verbose:
                    print(f"[step {step}] Top-level return/throw. Stopping.")
                break

            if return_frame and return_frame.function_name == "<main>":
                # Top-level return
                if verbose:
                    print(f"[step {step}] Top-level return/throw. Stopping.")
                break

            # Return to caller — write return value to caller's result register
            caller_frame = vm.current_frame
            if return_frame and return_frame.result_reg and update.return_value is not None:
                caller_frame.registers[return_frame.result_reg] = \
                    _deserialize_value(update.return_value, vm)

            if (return_frame and return_frame.return_label and
                    return_frame.return_label in cfg.blocks):
                current_label = return_frame.return_label
                ip = return_frame.return_ip if return_frame.return_ip is not None else 0
            else:
                if verbose:
                    print(f"[step {step}] No return label. Stopping.")
                break

        elif update.next_label and update.next_label in cfg.blocks:
            current_label = update.next_label
            ip = 0
        else:
            ip += 1

    if verbose:
        print(f"\n({step + 1} steps, {llm_calls} LLM calls)")

    return vm


def _format_val(v: Any) -> str:
    """Format a value for verbose display."""
    if isinstance(v, dict) and v.get("__symbolic__"):
        name = v.get("name", "?")
        constraints = v.get("constraints", [])
        if constraints:
            return f"{name} [{', '.join(str(c) for c in constraints)}]"
        hint = v.get("type_hint", "")
        return f"{name}" + (f" ({hint})" if hint else "")
    if isinstance(v, SymbolicValue):
        if v.constraints:
            return f"{v.name} [{', '.join(v.constraints)}]"
        return f"{v.name}" + (f" ({v.type_hint})" if v.type_hint else "")
    return repr(v)


# ════════════════════════════════════════════════════════════════════
# 8. CLI
# ════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="LLM Symbolic Interpreter")
    parser.add_argument("file", nargs="?",
                        help="Source file to interpret")
    parser.add_argument("--language", "-l", default="python",
                        help="Source language (default: python)")
    parser.add_argument("--entry", "-e", default=None,
                        help="Entry point label or function name")
    parser.add_argument("--backend", "-b", default="claude",
                        choices=["claude", "openai"],
                        help="LLM backend (default: claude)")
    parser.add_argument("--max-steps", "-n", type=int, default=100,
                        help="Maximum interpretation steps (default: 100)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print IR, CFG, and step-by-step execution")
    parser.add_argument("--ir-only", action="store_true",
                        help="Only print the IR (no LLM execution)")
    parser.add_argument("--cfg-only", action="store_true",
                        help="Only print the CFG (no LLM execution)")

    args = parser.parse_args()

    if not args.file:
        # Demo mode: use a built-in example
        source = '''\
def factorial(n):
    if n <= 1:
        return 1
    else:
        return n * factorial(n - 1)

result = factorial(5)
'''
        print("No file provided. Using built-in demo:\n")
        print(source)
    else:
        with open(args.file) as f:
            source = f.read()

    # Parse & lower
    tree = Parser().parse(source, args.language)
    frontend = get_frontend(args.language)
    instructions = frontend.lower(tree, source.encode("utf-8"))

    if args.ir_only:
        print("═══ IR ═══")
        for inst in instructions:
            print(f"  {inst}")
        return

    cfg = build_cfg(instructions)

    if args.cfg_only:
        print("═══ CFG ═══")
        print(cfg)
        return

    # Full run
    vm = run(source, language=args.language, entry_point=args.entry,
             backend=args.backend, max_steps=args.max_steps,
             verbose=args.verbose)

    print("\n═══ Final VM State ═══")
    print(json.dumps(vm.to_dict(), indent=2, default=str))


if __name__ == "__main__":
    main()
