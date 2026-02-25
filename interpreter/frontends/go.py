"""GoFrontend — tree-sitter Go AST -> IR lowering."""

from __future__ import annotations

import logging
from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)


class GoFrontend(BaseFrontend):
    """Lowers a Go tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "nil"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    DEFAULT_RETURN_VALUE = "nil"

    ATTRIBUTE_NODE_TYPE = "selector_expression"
    ATTR_OBJECT_FIELD = "operand"
    ATTR_ATTRIBUTE_FIELD = "field"

    COMMENT_TYPES = frozenset({"comment"})
    NOISE_TYPES = frozenset({"package_clause", "import_declaration", "\n"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "int_literal": self._lower_const_literal,
            "float_literal": self._lower_const_literal,
            "interpreted_string_literal": self._lower_const_literal,
            "raw_string_literal": self._lower_const_literal,
            "true": self._lower_const_literal,
            "false": self._lower_const_literal,
            "nil": self._lower_const_literal,
            "binary_expression": self._lower_binop,
            "unary_expression": self._lower_unop,
            "call_expression": self._lower_go_call,
            "selector_expression": self._lower_selector,
            "index_expression": self._lower_go_index,
            "parenthesized_expression": self._lower_paren,
            "composite_literal": self._lower_composite_literal,
            "type_identifier": self._lower_identifier,
            "field_identifier": self._lower_identifier,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "expression_statement": self._lower_expression_statement,
            "short_var_declaration": self._lower_short_var_decl,
            "assignment_statement": self._lower_go_assignment,
            "return_statement": self._lower_go_return,
            "if_statement": self._lower_go_if,
            "for_statement": self._lower_go_for,
            "function_declaration": self._lower_go_func_decl,
            "method_declaration": self._lower_go_method_decl,
            "type_declaration": self._lower_go_type_decl,
            "inc_statement": self._lower_go_inc,
            "dec_statement": self._lower_go_dec,
            "block": self._lower_go_block,
            "statement_list": self._lower_block,
            "source_file": self._lower_block,
            "var_declaration": self._lower_go_var_decl,
        }

    # -- Go: block (iterate named children, skip braces) -----------------------

    def _lower_go_block(self, node):
        for child in node.children:
            if child.is_named:
                self._lower_stmt(child)

    # -- Go: short variable declaration (:=) -----------------------------------

    def _lower_short_var_decl(self, node):
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        left_names = self._extract_expression_list(left)
        right_regs = self._lower_expression_list(right)

        for name, val_reg in zip(left_names, right_regs):
            self._emit(
                Opcode.STORE_VAR,
                operands=[name, val_reg],
                source_location=self._source_loc(node),
            )

    # -- Go: assignment statement (=) ------------------------------------------

    def _lower_go_assignment(self, node):
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        left_nodes = self._get_expression_list_children(left)
        right_regs = self._lower_expression_list(right)

        for target, val_reg in zip(left_nodes, right_regs):
            self._lower_store_target(target, val_reg, node)

    # -- Go: expression list helpers -------------------------------------------

    def _extract_expression_list(self, node) -> list[str]:
        """Extract identifiers from an expression_list node."""
        if node is None:
            return []
        if node.type == "expression_list":
            return [
                self._node_text(c)
                for c in node.children
                if c.type not in (",",) and c.is_named
            ]
        return [self._node_text(node)]

    def _get_expression_list_children(self, node) -> list:
        """Get child nodes from an expression_list."""
        if node is None:
            return []
        if node.type == "expression_list":
            return [c for c in node.children if c.type not in (",",) and c.is_named]
        return [node]

    def _lower_expression_list(self, node) -> list[str]:
        """Lower each expression in an expression_list, return registers."""
        if node is None:
            return []
        if node.type == "expression_list":
            return [
                self._lower_expr(c)
                for c in node.children
                if c.type not in (",",) and c.is_named
            ]
        return [self._lower_expr(node)]

    # -- Go: return statement --------------------------------------------------

    def _lower_go_return(self, node):
        children = [c for c in node.children if c.type != "return" and c.is_named]
        if not children:
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
            return
        # If expression_list, lower each value
        if len(children) == 1 and children[0].type == "expression_list":
            regs = self._lower_expression_list(children[0])
        else:
            regs = [self._lower_expr(c) for c in children]
        for reg in regs:
            self._emit(
                Opcode.RETURN,
                operands=[reg],
                source_location=self._source_loc(node),
            )

    # -- Go: call expression ---------------------------------------------------

    def _lower_go_call(self, node) -> str:
        func_node = node.child_by_field_name("function")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args(args_node) if args_node else []

        # Method call via selector: obj.Method(...)
        if func_node and func_node.type == "selector_expression":
            operand_node = func_node.child_by_field_name("operand")
            field_node = func_node.child_by_field_name("field")
            if operand_node and field_node:
                obj_reg = self._lower_expr(operand_node)
                method_name = self._node_text(field_node)
                reg = self._fresh_reg()
                self._emit(
                    Opcode.CALL_METHOD,
                    result_reg=reg,
                    operands=[obj_reg, method_name] + arg_regs,
                    source_location=self._source_loc(node),
                )
                return reg

        # Plain function call
        if func_node and func_node.type == "identifier":
            func_name = self._node_text(func_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=reg,
                operands=[func_name] + arg_regs,
                source_location=self._source_loc(node),
            )
            return reg

        # Dynamic / unknown call
        target_reg = self._lower_expr(func_node) if func_node else self._fresh_reg()
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    # -- Go: selector expression (obj.field) -----------------------------------

    def _lower_selector(self, node) -> str:
        operand_node = node.child_by_field_name("operand")
        field_node = node.child_by_field_name("field")
        if operand_node is None or field_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(operand_node)
        field_name = self._node_text(field_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, field_name],
            source_location=self._source_loc(node),
        )
        return reg

    # -- Go: index expression (arr[i]) -----------------------------------------

    def _lower_go_index(self, node) -> str:
        operand_node = node.child_by_field_name("operand")
        index_node = node.child_by_field_name("index")
        if operand_node is None or index_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(operand_node)
        idx_reg = self._lower_expr(index_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_INDEX,
            result_reg=reg,
            operands=[obj_reg, idx_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # -- Go: if statement ------------------------------------------------------

    def _lower_go_if(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

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
        if body_node:
            self._lower_go_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            # alt_node may be a block (else) or an if_statement (else if)
            if alt_node.type == "if_statement":
                self._lower_go_if(alt_node)
            else:
                self._lower_go_block(alt_node)
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Go: for statement -----------------------------------------------------

    def _lower_go_for(self, node):
        body_node = node.child_by_field_name("body")

        # Look for for_clause (C-style) or range_clause
        for_clause = next((c for c in node.children if c.type == "for_clause"), None)
        range_clause = next(
            (c for c in node.children if c.type == "range_clause"), None
        )

        if for_clause:
            self._lower_go_for_clause(for_clause, body_node, node)
        elif range_clause:
            self._lower_go_range(range_clause, body_node, node)
        else:
            # Bare for (condition-only or infinite loop)
            self._lower_go_bare_for(node, body_node)

    def _lower_go_for_clause(self, clause, body_node, parent):
        init_node = clause.child_by_field_name("initializer")
        cond_node = clause.child_by_field_name("condition")
        update_node = clause.child_by_field_name("update")

        if init_node:
            self._lower_stmt(init_node)

        loop_label = self._fresh_label("for_cond")
        body_label = self._fresh_label("for_body")
        end_label = self._fresh_label("for_end")

        self._emit(Opcode.LABEL, label=loop_label)
        if cond_node:
            cond_reg = self._lower_expr(cond_node)
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{body_label},{end_label}",
            )
        else:
            self._emit(Opcode.BRANCH, label=body_label)

        self._emit(Opcode.LABEL, label=body_label)
        if body_node:
            self._lower_go_block(body_node)
        if update_node:
            self._lower_stmt(update_node)
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_go_range(self, clause, body_node, parent):
        # for k, v := range expr { body }
        left = clause.child_by_field_name("left")
        right = clause.child_by_field_name("right")

        iter_reg = self._lower_expr(right) if right else self._fresh_reg()
        var_names = self._extract_expression_list(left) if left else ["__range_var"]

        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

        loop_label = self._fresh_label("range_cond")
        body_label = self._fresh_label("range_body")
        end_label = self._fresh_label("range_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
        )

        self._emit(Opcode.LABEL, label=body_label)
        # Store index variable
        if len(var_names) >= 1:
            self._emit(Opcode.STORE_VAR, operands=[var_names[0], idx_reg])
        # Store value variable
        if len(var_names) >= 2:
            elem_reg = self._fresh_reg()
            self._emit(
                Opcode.LOAD_INDEX,
                result_reg=elem_reg,
                operands=[iter_reg, idx_reg],
            )
            self._emit(Opcode.STORE_VAR, operands=[var_names[1], elem_reg])

        if body_node:
            self._lower_go_block(body_node)

        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
        self._emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_go_bare_for(self, node, body_node):
        """Bare for loop: `for { ... }` or `for cond { ... }`."""
        # Check if there is a condition child (not for_clause/range_clause/block)
        cond_node = next(
            (
                c
                for c in node.children
                if c.is_named
                and c.type not in ("for_clause", "range_clause", "block", "for")
            ),
            None,
        )

        loop_label = self._fresh_label("for_cond")
        body_label = self._fresh_label("for_body")
        end_label = self._fresh_label("for_end")

        self._emit(Opcode.LABEL, label=loop_label)
        if cond_node:
            cond_reg = self._lower_expr(cond_node)
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{body_label},{end_label}",
            )
        else:
            self._emit(Opcode.BRANCH, label=body_label)

        self._emit(Opcode.LABEL, label=body_label)
        if body_node:
            self._lower_go_block(body_node)
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Go: function declaration ----------------------------------------------

    def _lower_go_func_decl(self, node):
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
            self._lower_go_params(params_node)

        if body_node:
            self._lower_go_block(body_node)

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

    # -- Go: method declaration ------------------------------------------------

    def _lower_go_method_decl(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")
        receiver_node = node.child_by_field_name("receiver")

        func_name = self._node_text(name_node) if name_node else "__anon"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=func_label)

        # Lower receiver as parameter
        if receiver_node:
            self._lower_go_params(receiver_node)

        if params_node:
            self._lower_go_params(params_node)

        if body_node:
            self._lower_go_block(body_node)

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

    def _lower_go_params(self, params_node):
        for child in params_node.children:
            if child.type == "parameter_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    pname = self._node_text(name_node)
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

    # -- Go: inc/dec statements ------------------------------------------------

    def _lower_go_inc(self, node):
        children = [c for c in node.children if c.is_named]
        if not children:
            return
        operand = children[0]
        operand_reg = self._lower_expr(operand)
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        result_reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=result_reg,
            operands=["+", operand_reg, one_reg],
            source_location=self._source_loc(node),
        )
        self._lower_store_target(operand, result_reg, node)

    def _lower_go_dec(self, node):
        children = [c for c in node.children if c.is_named]
        if not children:
            return
        operand = children[0]
        operand_reg = self._lower_expr(operand)
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        result_reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=result_reg,
            operands=["-", operand_reg, one_reg],
            source_location=self._source_loc(node),
        )
        self._lower_store_target(operand, result_reg, node)

    # -- Go: store target with selector_expression -----------------------------

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
        elif target.type == "selector_expression":
            operand_node = target.child_by_field_name("operand")
            field_node = target.child_by_field_name("field")
            if operand_node and field_node:
                obj_reg = self._lower_expr(operand_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(field_node), val_reg],
                    source_location=self._source_loc(parent_node),
                )
        elif target.type == "index_expression":
            operand_node = target.child_by_field_name("operand")
            index_node = target.child_by_field_name("index")
            if operand_node and index_node:
                obj_reg = self._lower_expr(operand_node)
                idx_reg = self._lower_expr(index_node)
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                    source_location=self._source_loc(parent_node),
                )
        else:
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )

    # -- Go: type declaration (struct) -----------------------------------------

    def _lower_go_type_decl(self, node):
        for child in node.children:
            if child.type == "type_spec":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                if name_node:
                    type_name = self._node_text(name_node)
                    reg = self._fresh_reg()
                    hint = (
                        f"struct:{type_name}"
                        if type_node and type_node.type == "struct_type"
                        else f"type:{type_name}"
                    )
                    self._emit(
                        Opcode.SYMBOLIC,
                        result_reg=reg,
                        operands=[hint],
                        source_location=self._source_loc(node),
                    )
                    self._emit(Opcode.STORE_VAR, operands=[type_name, reg])

    # -- Go: var declaration ---------------------------------------------------

    def _lower_go_var_decl(self, node):
        for child in node.children:
            if child.type == "var_spec":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node and value_node:
                    val_reg = self._lower_expr(value_node)
                    self._emit(
                        Opcode.STORE_VAR,
                        operands=[self._node_text(name_node), val_reg],
                        source_location=self._source_loc(node),
                    )
                elif name_node:
                    val_reg = self._fresh_reg()
                    self._emit(
                        Opcode.CONST,
                        result_reg=val_reg,
                        operands=[self.NONE_LITERAL],
                    )
                    self._emit(
                        Opcode.STORE_VAR,
                        operands=[self._node_text(name_node), val_reg],
                        source_location=self._source_loc(node),
                    )

    # -- Go: composite literal -------------------------------------------------

    def _lower_composite_literal(self, node) -> str:
        reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"composite_literal:{self._node_text(node)[:60]}"],
            source_location=self._source_loc(node),
        )
        return reg
