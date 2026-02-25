"""LuaFrontend — tree-sitter Lua AST -> IR lowering."""

from __future__ import annotations

import logging
from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)


class LuaFrontend(BaseFrontend):
    """Lowers a Lua tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "nil"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    DEFAULT_RETURN_VALUE = "nil"

    FUNC_NAME_FIELD = "name"
    FUNC_PARAMS_FIELD = "parameters"
    FUNC_BODY_FIELD = "body"

    ATTR_OBJECT_FIELD = "table"
    ATTR_ATTRIBUTE_FIELD = "field"

    BLOCK_NODE_TYPES = frozenset({"block"})

    COMMENT_TYPES = frozenset({"comment"})
    NOISE_TYPES = frozenset({"hash_bang_line", "\n"})

    PAREN_EXPR_TYPE = "parenthesized_expression"

    _OPERATOR_MAP: dict[str, str] = {
        "and": "and",
        "or": "or",
        "not": "not",
        "..": "..",
        "#": "#",
    }

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "number": self._lower_const_literal,
            "string": self._lower_const_literal,
            "true": self._lower_const_literal,
            "false": self._lower_const_literal,
            "nil": self._lower_const_literal,
            "binary_expression": self._lower_binop,
            "unary_expression": self._lower_unop,
            "parenthesized_expression": self._lower_paren,
            "function_call": self._lower_lua_call,
            "dot_index_expression": self._lower_dot_index,
            "bracket_index_expression": self._lower_bracket_index,
            "table_constructor": self._lower_table_constructor,
            "expression_list": self._lower_expression_list,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "chunk": self._lower_block,
            "block": self._lower_block,
            "variable_declaration": self._lower_lua_variable_declaration,
            "assignment_statement": self._lower_lua_assignment,
            "function_declaration": self._lower_lua_function_declaration,
            "if_statement": self._lower_lua_if,
            "while_statement": self._lower_lua_while,
            "for_statement": self._lower_lua_for,
            "repeat_statement": self._lower_lua_repeat,
            "return_statement": self._lower_lua_return,
            "do_statement": self._lower_lua_do,
            "expression_statement": self._lower_expression_statement,
        }

    # -- Lua: entry point override --------------------------------------------------

    def lower(self, tree, source: bytes):
        """Override to handle Lua's chunk root node."""
        self._reg_counter = 0
        self._label_counter = 0
        self._instructions = []
        self._source = source
        root = tree.root_node
        self._emit(Opcode.LABEL, label=constants.CFG_ENTRY_LABEL)
        self._lower_block(root)
        return self._instructions

    # -- Lua: variable declaration (local x = expr) --------------------------------

    def _lower_lua_variable_declaration(self, node):
        """Lower `local x = expr` — variable_declaration wraps assignment_statement."""
        for child in node.children:
            if child.type == "assignment_statement":
                self._lower_lua_assignment(child)
                return
        # Local declaration without assignment: local x
        for child in node.children:
            if child.type == "identifier":
                val_reg = self._fresh_reg()
                self._emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[self.NONE_LITERAL],
                )
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[self._node_text(child), val_reg],
                    source_location=self._source_loc(node),
                )

    # -- Lua: assignment (a, b = expr1, expr2) -------------------------------------

    def _lower_lua_assignment(self, node):
        """Lower assignment_statement with variable_list and expression_list."""
        # Find the variable_list and expression_list by type (not field name,
        # because child_by_field_name("name"/"value") returns inner elements).
        var_list_node = next(
            (c for c in node.children if c.type == "variable_list"), None
        )
        expr_list_node = next(
            (c for c in node.children if c.type == "expression_list"), None
        )

        if var_list_node is None or expr_list_node is None:
            # Fallback: try positional named children
            named = [c for c in node.children if c.is_named]
            if len(named) >= 2:
                var_list_node, expr_list_node = named[0], named[1]
            else:
                logger.warning(
                    "Lua assignment missing variable_list or expression_list at %s",
                    self._source_loc(node),
                )
                return

        targets = [c for c in var_list_node.children if c.is_named]
        values = [c for c in expr_list_node.children if c.is_named]

        val_regs = [self._lower_expr(v) for v in values]

        for i, target in enumerate(targets):
            val_reg = val_regs[i] if i < len(val_regs) else self._fresh_reg()
            if i >= len(val_regs):
                self._emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[self.NONE_LITERAL],
                )
            self._lower_store_target(target, val_reg, node)

    # -- Lua: store target (supports dot/bracket index) ----------------------------

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
        elif target.type == "dot_index_expression":
            obj_node = target.child_by_field_name("table")
            field_node = target.child_by_field_name("field")
            if obj_node and field_node:
                obj_reg = self._lower_expr(obj_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(field_node), val_reg],
                    source_location=self._source_loc(parent_node),
                )
        elif target.type == "bracket_index_expression":
            obj_node = target.child_by_field_name("table")
            idx_node = target.child_by_field_name("field")
            if obj_node and idx_node:
                obj_reg = self._lower_expr(obj_node)
                idx_reg = self._lower_expr(idx_node)
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

    # -- Lua: function declaration -------------------------------------------------

    def _lower_lua_function_declaration(self, node):
        """Lower function_declaration with name, parameters, body fields."""
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
            self._lower_params(params_node)

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

    # -- Lua: call lowering (function_call) ----------------------------------------

    def _lower_lua_call(self, node) -> str:
        """Lower function_call — name field is identifier or method_index_expression."""
        name_node = node.child_by_field_name("name")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args(args_node) if args_node else []

        if name_node is None:
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

        # Method call: obj:method(args)
        if name_node.type == "method_index_expression":
            table_node = name_node.child_by_field_name("table")
            method_node = name_node.child_by_field_name("method")
            if table_node and method_node:
                obj_reg = self._lower_expr(table_node)
                method_name = self._node_text(method_node)
                reg = self._fresh_reg()
                self._emit(
                    Opcode.CALL_METHOD,
                    result_reg=reg,
                    operands=[obj_reg, method_name] + arg_regs,
                    source_location=self._source_loc(node),
                )
                return reg

        # Dot-indexed call: obj.method(args)
        if name_node.type == "dot_index_expression":
            table_node = name_node.child_by_field_name("table")
            field_node = name_node.child_by_field_name("field")
            if table_node and field_node:
                obj_reg = self._lower_expr(table_node)
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
        if name_node.type == "identifier":
            func_name = self._node_text(name_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=reg,
                operands=[func_name] + arg_regs,
                source_location=self._source_loc(node),
            )
            return reg

        # Dynamic call target
        target_reg = self._lower_expr(name_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    # -- Lua: dot index expression (obj.field) -------------------------------------

    def _lower_dot_index(self, node) -> str:
        table_node = node.child_by_field_name("table")
        field_node = node.child_by_field_name("field")
        if table_node is None or field_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(table_node)
        field_name = self._node_text(field_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, field_name],
            source_location=self._source_loc(node),
        )
        return reg

    # -- Lua: bracket index expression (obj[key]) ----------------------------------

    def _lower_bracket_index(self, node) -> str:
        table_node = node.child_by_field_name("table")
        key_node = node.child_by_field_name("field")
        if table_node is None or key_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(table_node)
        key_reg = self._lower_expr(key_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_INDEX,
            result_reg=reg,
            operands=[obj_reg, key_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # -- Lua: table constructor ({key=val, ...}) -----------------------------------

    def _lower_table_constructor(self, node) -> str:
        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=["table"],
            source_location=self._source_loc(node),
        )
        positional_idx = 1
        for child in node.children:
            if child.type == "field":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node and value_node:
                    key_reg = self._fresh_reg()
                    self._emit(
                        Opcode.CONST,
                        result_reg=key_reg,
                        operands=[self._node_text(name_node)],
                    )
                    val_reg = self._lower_expr(value_node)
                    self._emit(
                        Opcode.STORE_INDEX,
                        operands=[obj_reg, key_reg, val_reg],
                    )
                elif value_node:
                    # Positional entry (array-like)
                    idx_reg = self._fresh_reg()
                    self._emit(
                        Opcode.CONST,
                        result_reg=idx_reg,
                        operands=[str(positional_idx)],
                    )
                    val_reg = self._lower_expr(value_node)
                    self._emit(
                        Opcode.STORE_INDEX,
                        operands=[obj_reg, idx_reg, val_reg],
                    )
                    positional_idx += 1
        return obj_reg

    # -- Lua: if statement ---------------------------------------------------------

    def _lower_lua_if(self, node):
        """Lower if_statement with elseif_statement and else_statement children."""
        condition_node = node.child_by_field_name("condition")
        consequence_node = node.child_by_field_name("consequence")

        cond_reg = self._lower_expr(condition_node)
        true_label = self._fresh_label("if_true")
        end_label = self._fresh_label("if_end")

        elseif_nodes = [c for c in node.children if c.type == "elseif_statement"]
        else_node = next((c for c in node.children if c.type == "else_statement"), None)
        has_alternative = len(elseif_nodes) > 0 or else_node is not None
        false_label = self._fresh_label("if_false") if has_alternative else end_label

        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
            source_location=self._source_loc(node),
        )

        self._emit(Opcode.LABEL, label=true_label)
        if consequence_node:
            self._lower_block(consequence_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if has_alternative:
            self._emit(Opcode.LABEL, label=false_label)
            self._lower_lua_elseif_chain(elseif_nodes, else_node, end_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_lua_elseif_chain(self, elseif_nodes, else_node, end_label: str):
        """Lower a chain of elseif_statement nodes followed by optional else."""
        if not elseif_nodes:
            if else_node:
                for child in else_node.children:
                    if child.is_named and child.type not in ("else",):
                        self._lower_block(child)
            return

        current = elseif_nodes[0]
        remaining = elseif_nodes[1:]

        cond_node = current.child_by_field_name("condition")
        body_node = current.child_by_field_name("consequence")

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("elseif_true")
        has_more = len(remaining) > 0 or else_node is not None
        false_label = self._fresh_label("elseif_false") if has_more else end_label

        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
            source_location=self._source_loc(current),
        )

        self._emit(Opcode.LABEL, label=true_label)
        if body_node:
            self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if has_more:
            self._emit(Opcode.LABEL, label=false_label)
            self._lower_lua_elseif_chain(remaining, else_node, end_label)

    # -- Lua: while statement ------------------------------------------------------

    def _lower_lua_while(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

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
        if body_node:
            self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Lua: for statement (numeric and generic) ----------------------------------

    def _lower_lua_for(self, node):
        """Lower for_statement — dispatches on for_numeric_clause vs for_generic_clause."""
        numeric_clause = next(
            (c for c in node.children if c.type == "for_numeric_clause"), None
        )
        generic_clause = next(
            (c for c in node.children if c.type == "for_generic_clause"), None
        )
        body_node = node.child_by_field_name("body")

        if numeric_clause:
            self._lower_lua_for_numeric(numeric_clause, body_node, node)
        elif generic_clause:
            self._lower_lua_for_generic(generic_clause, body_node, node)
        else:
            reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=reg,
                operands=["unsupported:for_statement_unknown_clause"],
                source_location=self._source_loc(node),
            )

    def _lower_lua_for_numeric(self, clause, body_node, for_node):
        """Lower for i = start, end [, step] do ... end."""
        name_node = clause.child_by_field_name("name")
        start_node = clause.child_by_field_name("start")
        end_node = clause.child_by_field_name("end")
        step_node = clause.child_by_field_name("step")

        var_name = self._node_text(name_node) if name_node else "__for_var"
        start_reg = self._lower_expr(start_node) if start_node else self._fresh_reg()
        end_reg = self._lower_expr(end_node) if end_node else self._fresh_reg()

        self._emit(Opcode.STORE_VAR, operands=[var_name, start_reg])

        step_reg = self._fresh_reg()
        if step_node:
            step_reg = self._lower_expr(step_node)
        else:
            self._emit(Opcode.CONST, result_reg=step_reg, operands=["1"])

        loop_label = self._fresh_label("for_cond")
        body_label = self._fresh_label("for_body")
        end_label = self._fresh_label("for_end")

        self._emit(Opcode.LABEL, label=loop_label)
        current_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=current_reg, operands=[var_name])
        cond_reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=cond_reg,
            operands=["<=", current_reg, end_reg],
        )
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
            source_location=self._source_loc(for_node),
        )

        self._emit(Opcode.LABEL, label=body_label)
        if body_node:
            self._lower_block(body_node)

        next_reg = self._fresh_reg()
        cur_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=cur_reg, operands=[var_name])
        self._emit(
            Opcode.BINOP,
            result_reg=next_reg,
            operands=["+", cur_reg, step_reg],
        )
        self._emit(Opcode.STORE_VAR, operands=[var_name, next_reg])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_lua_for_generic(self, clause, body_node, for_node):
        """Lower for k, v in pairs(t) do ... end — emit as SYMBOLIC iteration."""
        reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=["generic_for_iteration"],
            source_location=self._source_loc(for_node),
        )
        if body_node:
            self._lower_block(body_node)

    # -- Lua: repeat-until (do-while) ----------------------------------------------

    def _lower_lua_repeat(self, node):
        """Lower repeat ... until cond (execute body first, then check)."""
        body_node = node.child_by_field_name("body")
        cond_node = node.child_by_field_name("condition")

        body_label = self._fresh_label("repeat_body")
        end_label = self._fresh_label("repeat_end")

        self._emit(Opcode.LABEL, label=body_label)
        if body_node:
            self._lower_block(body_node)

        cond_reg = self._lower_expr(cond_node)
        # repeat-until: loop continues while condition is FALSE
        negated_reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=negated_reg,
            operands=["not", cond_reg],
            source_location=self._source_loc(node),
        )
        self._emit(
            Opcode.BRANCH_IF,
            operands=[negated_reg],
            label=f"{body_label},{end_label}",
            source_location=self._source_loc(node),
        )

        self._emit(Opcode.LABEL, label=end_label)

    # -- Lua: return statement -----------------------------------------------------

    def _lower_lua_return(self, node):
        children = [c for c in node.children if c.type != "return" and c.is_named]
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

    # -- Lua: expression_list unwrap -----------------------------------------------

    def _lower_expression_list(self, node) -> str:
        """Unwrap expression_list to its first named child."""
        named = [c for c in node.children if c.is_named]
        if named:
            return self._lower_expr(named[0])
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[self.DEFAULT_RETURN_VALUE])
        return reg

    # -- Lua: do ... end block -----------------------------------------------------

    def _lower_lua_do(self, node):
        """Lower do ... end as a plain block."""
        body_node = node.child_by_field_name("body")
        if body_node:
            self._lower_block(body_node)
        else:
            for child in node.children:
                if child.is_named and child.type not in ("do", "end"):
                    self._lower_stmt(child)
