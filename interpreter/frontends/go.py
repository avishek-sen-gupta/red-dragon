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
            "true": self._lower_canonical_true,
            "false": self._lower_canonical_false,
            "nil": self._lower_canonical_none,
            "binary_expression": self._lower_binop,
            "unary_expression": self._lower_unop,
            "call_expression": self._lower_go_call,
            "selector_expression": self._lower_selector,
            "index_expression": self._lower_go_index,
            "parenthesized_expression": self._lower_paren,
            "composite_literal": self._lower_composite_literal,
            "type_identifier": self._lower_identifier,
            "field_identifier": self._lower_identifier,
            "type_assertion_expression": self._lower_type_assertion,
            "slice_expression": self._lower_slice_expr,
            "func_literal": self._lower_func_literal,
            "channel_type": self._lower_const_literal,
            "slice_type": self._lower_const_literal,
            "expression_list": self._lower_const_literal,
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
            "break_statement": self._lower_break,
            "continue_statement": self._lower_continue,
            "defer_statement": self._lower_defer_stmt,
            "go_statement": self._lower_go_stmt,
            "expression_switch_statement": self._lower_expression_switch,
            "type_switch_statement": self._lower_type_switch,
            "select_statement": self._lower_select_stmt,
            "send_statement": self._lower_send_stmt,
            "labeled_statement": self._lower_labeled_stmt,
            "const_declaration": self._lower_go_const_decl,
            "goto_statement": self._lower_goto_stmt,
            "receive_statement": self._lower_receive_stmt,
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
                node=node,
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
                node=node,
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
                node=node,
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
                    node=node,
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
                node=node,
            )
            return reg

        # Dynamic / unknown call
        target_reg = self._lower_expr(func_node) if func_node else self._fresh_reg()
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            node=node,
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
            node=node,
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
            node=node,
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
                node=node,
            )
        else:
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{true_label},{end_label}",
                node=node,
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
        update_label = self._fresh_label("for_update") if update_node else loop_label
        self._push_loop(update_label, end_label)
        if body_node:
            self._lower_go_block(body_node)
        self._pop_loop()
        if update_node:
            self._emit(Opcode.LABEL, label=update_label)
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

        update_label = self._fresh_label("range_update")
        self._push_loop(update_label, end_label)
        if body_node:
            self._lower_go_block(body_node)
        self._pop_loop()

        self._emit(Opcode.LABEL, label=update_label)
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
        self._push_loop(loop_label, end_label)
        if body_node:
            self._lower_go_block(body_node)
        self._pop_loop()
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Go: function declaration ----------------------------------------------

    _GO_MAIN_FUNC_NAME = "main"

    def _lower_go_func_decl(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = self._node_text(name_node) if name_node else "__anon"

        if func_name == self._GO_MAIN_FUNC_NAME:
            self._lower_go_main_hoisted(body_node)
            return

        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
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

    def _lower_go_main_hoisted(self, body_node):
        """Hoist func main() body to top level so its locals land in frame 0.

        Go's ``func main()`` is the program entry point.  Rather than
        wrapping it in a function definition (which the VM would skip),
        we emit its statements directly on the top-level path.
        """
        if body_node:
            self._lower_go_block(body_node)

    # -- Go: method declaration ------------------------------------------------

    def _lower_go_method_decl(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")
        receiver_node = node.child_by_field_name("receiver")

        func_name = self._node_text(name_node) if name_node else "__anon"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
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
                        node=child,
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
                    node=child,
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
            node=node,
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
            node=node,
        )
        self._lower_store_target(operand, result_reg, node)

    # -- Go: store target with selector_expression -----------------------------

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                node=parent_node,
            )
        elif target.type == "selector_expression":
            operand_node = target.child_by_field_name("operand")
            field_node = target.child_by_field_name("field")
            if operand_node and field_node:
                obj_reg = self._lower_expr(operand_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(field_node), val_reg],
                    node=parent_node,
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
                    node=parent_node,
                )
        else:
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                node=parent_node,
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
                        node=node,
                    )
                    self._emit(Opcode.STORE_VAR, operands=[type_name, reg])

    # -- Go: var declaration ---------------------------------------------------

    def _lower_go_var_decl(self, node):
        specs = [c for c in node.children if c.type == "var_spec"]
        # Handle var (...) block form: var_spec_list contains var_spec children
        spec_list = next(
            (c for c in node.children if c.type == "var_spec_list"),
            None,
        )
        if spec_list is not None:
            specs = [c for c in spec_list.children if c.type == "var_spec"]
        for spec in specs:
            self._lower_var_spec(spec, node)

    def _lower_var_spec(self, spec, parent_node):
        """Lower a single var_spec, supporting multiple names: `var a, b = 1, 2`."""
        names = [c for c in spec.children if c.type == "identifier"]
        value_node = spec.child_by_field_name("value")

        if value_node:
            val_regs = self._lower_expression_list(value_node)
            for name_node, val_reg in zip(names, val_regs):
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[self._node_text(name_node), val_reg],
                    node=parent_node,
                )
            # If more names than values (e.g. `var a, b int`), store None for remainder
            for name_node in names[len(val_regs) :]:
                val_reg = self._fresh_reg()
                self._emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[self.NONE_LITERAL],
                )
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[self._node_text(name_node), val_reg],
                    node=parent_node,
                )
        else:
            for name_node in names:
                val_reg = self._fresh_reg()
                self._emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[self.NONE_LITERAL],
                )
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[self._node_text(name_node), val_reg],
                    node=parent_node,
                )

    # -- Go: composite literal -------------------------------------------------

    def _lower_composite_literal(self, node) -> str:
        """Lower Go composite literal: Point{X: 1} or []int{1, 2, 3}."""
        type_node = node.child_by_field_name("type")
        body_node = node.child_by_field_name("body") or next(
            (c for c in node.children if c.type == "literal_value"), None
        )

        type_name = self._node_text(type_node) if type_node else "Object"
        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=[type_name],
            node=node,
        )

        if not body_node:
            return obj_reg

        elements = [c for c in body_node.children if c.is_named]
        for i, elem in enumerate(elements):
            if elem.type == "keyed_element":
                # Key-value pair: {Key: Value}
                children = [c for c in elem.children if c.is_named]
                key_elem = children[0] if children else None
                val_elem = children[1] if len(children) > 1 else None
                key_name = (
                    self._node_text(
                        next((c for c in key_elem.children if c.is_named), key_elem)
                    )
                    if key_elem
                    else str(i)
                )
                val_reg = (
                    self._lower_expr(
                        next((c for c in val_elem.children if c.is_named), val_elem)
                    )
                    if val_elem
                    else self._fresh_reg()
                )
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, key_name, val_reg],
                    node=elem,
                )
            elif elem.type == "literal_element":
                # Positional element
                inner = next((c for c in elem.children if c.is_named), elem)
                val_reg = self._lower_expr(inner)
                idx_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                    node=elem,
                )
            else:
                # Direct expression element
                val_reg = self._lower_expr(elem)
                idx_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                    node=elem,
                )

        return obj_reg

    # -- Go: type assertion expression -----------------------------------------

    def _lower_type_assertion(self, node) -> str:
        """Lower type_assertion_expression: x.(Type) -> CALL_FUNCTION('type_assert', x, Type)."""
        named_children = [c for c in node.children if c.is_named]
        if not named_children:
            return self._lower_const_literal(node)
        expr_reg = self._lower_expr(named_children[0])
        type_text = (
            self._node_text(named_children[-1])
            if len(named_children) > 1
            else "interface{}"
        )
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["type_assert", expr_reg, type_text],
            node=node,
        )
        return reg

    # -- Go: slice expression --------------------------------------------------

    def _lower_slice_expr(self, node) -> str:
        """Lower slice_expression: a[low:high] -> CALL_FUNCTION('slice', a, low, high)."""
        operand_node = node.child_by_field_name("operand")
        obj_reg = self._lower_expr(operand_node) if operand_node else self._fresh_reg()

        start_node = node.child_by_field_name("start")
        end_node = node.child_by_field_name("end")

        start_reg = (
            self._lower_expr(start_node) if start_node else self._make_const("0")
        )
        end_reg = (
            self._lower_expr(end_node)
            if end_node
            else self._make_const(self.NONE_LITERAL)
        )

        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["slice", obj_reg, start_reg, end_reg],
            node=node,
        )
        return reg

    def _make_const(self, value: str) -> str:
        """Emit a CONST and return its register."""
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[value])
        return reg

    # -- Go: func literal (anonymous function) ---------------------------------

    def _lower_func_literal(self, node) -> str:
        """Lower func_literal as an anonymous function."""
        func_name = f"__anon_{self._label_counter}"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
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

        reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=reg,
            operands=[
                constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)
            ],
        )
        return reg

    # -- Go: defer statement ---------------------------------------------------

    def _lower_defer_stmt(self, node):
        """Lower defer statement: lower call child, then CALL_FUNCTION('defer', call_reg)."""
        call_node = next(
            (c for c in node.children if c.is_named and c.type != "defer"),
            None,
        )
        if not call_node:
            return
        call_reg = self._lower_expr(call_node)
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=self._fresh_reg(),
            operands=["defer", call_reg],
            node=node,
        )

    # -- Go: go statement ------------------------------------------------------

    def _lower_go_stmt(self, node):
        """Lower go statement: lower call child, then CALL_FUNCTION('go', call_reg)."""
        call_node = next(
            (c for c in node.children if c.is_named and c.type != "go"),
            None,
        )
        if not call_node:
            return
        call_reg = self._lower_expr(call_node)
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=self._fresh_reg(),
            operands=["go", call_reg],
            node=node,
        )

    # -- Go: expression switch statement ---------------------------------------

    def _lower_expression_switch(self, node):
        """Lower expression_switch_statement as if/else chain."""
        value_node = node.child_by_field_name("value")
        val_reg = (
            self._lower_expr(value_node)
            if value_node
            else self._make_const(self.TRUE_LITERAL)
        )

        end_label = self._fresh_label("switch_end")
        cases = [
            c for c in node.children if c.type in ("expression_case", "default_case")
        ]

        self._push_loop(end_label, end_label)
        for case in cases:
            if case.type == "default_case":
                body_children = [c for c in case.children if c.is_named]
                for child in body_children:
                    self._lower_stmt(child)
                self._emit(Opcode.BRANCH, label=end_label)
            else:
                value_nodes = [c for c in case.children if c.type == "expression_list"]
                body_label = self._fresh_label("case_body")
                next_label = self._fresh_label("case_next")

                if value_nodes:
                    case_exprs = self._lower_expression_list(value_nodes[0])
                    if case_exprs:
                        cmp_reg = self._fresh_reg()
                        self._emit(
                            Opcode.BINOP,
                            result_reg=cmp_reg,
                            operands=["==", val_reg, case_exprs[0]],
                            node=case,
                        )
                        self._emit(
                            Opcode.BRANCH_IF,
                            operands=[cmp_reg],
                            label=f"{body_label},{next_label}",
                        )
                    else:
                        self._emit(Opcode.BRANCH, label=body_label)
                else:
                    self._emit(Opcode.BRANCH, label=body_label)

                self._emit(Opcode.LABEL, label=body_label)
                body_children = [
                    c
                    for c in case.children
                    if c.is_named and c.type != "expression_list"
                ]
                for child in body_children:
                    self._lower_stmt(child)
                self._emit(Opcode.BRANCH, label=end_label)
                self._emit(Opcode.LABEL, label=next_label)

        self._pop_loop()
        self._emit(Opcode.LABEL, label=end_label)

    # -- Go: type switch statement ---------------------------------------------

    def _lower_type_switch(self, node):
        """Lower type_switch_statement with CALL_FUNCTION('type_check') per case."""
        header = next(
            (c for c in node.children if c.type == "type_switch_header"), None
        )
        expr_reg = self._fresh_reg()
        if header:
            named = [c for c in header.children if c.is_named]
            if named:
                expr_reg = self._lower_expr(named[-1])

        end_label = self._fresh_label("type_switch_end")
        cases = [c for c in node.children if c.type in ("type_case", "default_case")]

        self._push_loop(end_label, end_label)
        for case in cases:
            if case.type == "default_case":
                body_children = [c for c in case.children if c.is_named]
                for child in body_children:
                    self._lower_stmt(child)
                self._emit(Opcode.BRANCH, label=end_label)
            else:
                type_nodes = [
                    c
                    for c in case.children
                    if c.type not in ("case", ":") and c.is_named
                ]
                body_label = self._fresh_label("type_case_body")
                next_label = self._fresh_label("type_case_next")

                if type_nodes:
                    type_text = self._node_text(type_nodes[0])
                    check_reg = self._fresh_reg()
                    self._emit(
                        Opcode.CALL_FUNCTION,
                        result_reg=check_reg,
                        operands=["type_check", expr_reg, type_text],
                        node=case,
                    )
                    self._emit(
                        Opcode.BRANCH_IF,
                        operands=[check_reg],
                        label=f"{body_label},{next_label}",
                    )
                else:
                    self._emit(Opcode.BRANCH, label=body_label)

                self._emit(Opcode.LABEL, label=body_label)
                body_children = type_nodes[1:] if len(type_nodes) > 1 else []
                for child in body_children:
                    self._lower_stmt(child)
                self._emit(Opcode.BRANCH, label=end_label)
                self._emit(Opcode.LABEL, label=next_label)

        self._pop_loop()
        self._emit(Opcode.LABEL, label=end_label)

    # -- Go: select statement --------------------------------------------------

    def _lower_select_stmt(self, node):
        """Lower select_statement: lower each communication_case."""
        end_label = self._fresh_label("select_end")
        cases = [
            c for c in node.children if c.type in ("communication_case", "default_case")
        ]

        for case in cases:
            case_label = self._fresh_label("select_case")
            self._emit(Opcode.LABEL, label=case_label)
            body_children = [c for c in case.children if c.is_named]
            for child in body_children:
                self._lower_stmt(child)
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Go: send statement ----------------------------------------------------

    def _lower_send_stmt(self, node):
        """Lower send_statement: ch <- val -> CALL_FUNCTION('chan_send', ch, val)."""
        channel_node = node.child_by_field_name("channel")
        value_node = node.child_by_field_name("value")
        if not channel_node or not value_node:
            named = [c for c in node.children if c.is_named]
            channel_node = named[0] if named else None
            value_node = named[-1] if len(named) > 1 else None

        chan_reg = self._lower_expr(channel_node) if channel_node else self._fresh_reg()
        val_reg = self._lower_expr(value_node) if value_node else self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=self._fresh_reg(),
            operands=["chan_send", chan_reg, val_reg],
            node=node,
        )

    # -- Go: labeled statement -------------------------------------------------

    def _lower_labeled_stmt(self, node):
        """Lower labeled_statement: LABEL(name) + lower body."""
        label_node = next(
            (c for c in node.children if c.type == "label_name"),
            None,
        )
        label_name = self._node_text(label_node) if label_node else "__label"
        self._emit(Opcode.LABEL, label=label_name)
        body_children = [
            c for c in node.children if c.is_named and c.type != "label_name"
        ]
        for child in body_children:
            self._lower_stmt(child)

    # -- Go: const declaration -------------------------------------------------

    def _lower_go_const_decl(self, node):
        """Lower const_declaration: iterate const_spec children."""
        for child in node.children:
            if child.type == "const_spec":
                self._lower_const_spec(child)

    def _lower_const_spec(self, node):
        """Lower a single const_spec: lower value, STORE_VAR."""
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        if name_node and value_node:
            val_reg = self._lower_expr(value_node)
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(name_node), val_reg],
                node=node,
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
                node=node,
            )

    # -- Go: goto statement ----------------------------------------------------

    def _lower_receive_stmt(self, node):
        """Lower receive_statement: v := <-ch → CALL_FUNCTION('chan_recv', ch) + STORE_VAR."""
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")

        if right:
            chan_reg = self._lower_expr(right)
        else:
            # Bare receive — find the unary_expression child (<-ch)
            unary = next(
                (c for c in node.children if c.type == "unary_expression"),
                None,
            )
            chan_reg = self._lower_expr(unary) if unary else self._fresh_reg()

        recv_reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=recv_reg,
            operands=["chan_recv", chan_reg],
            node=node,
        )

        if left:
            left_names = self._extract_expression_list(left)
            for name in left_names:
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[name, recv_reg],
                    node=node,
                )

    def _lower_goto_stmt(self, node):
        """Lower goto_statement as BRANCH(label_name)."""
        label_node = next(
            (c for c in node.children if c.type == "label_name"),
            None,
        )
        label_name = self._node_text(label_node) if label_node else "__unknown_label"
        self._emit(
            Opcode.BRANCH,
            label=label_name,
            node=node,
        )
