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
            "string": self._lower_ruby_string,
            "true": self._lower_canonical_true,
            "false": self._lower_canonical_false,
            "nil": self._lower_canonical_none,
            "binary": self._lower_binop,
            "call": self._lower_ruby_call,
            "parenthesized_expression": self._lower_paren,
            "parenthesized_statements": self._lower_paren,
            "array": self._lower_list_literal,
            "hash": self._lower_ruby_hash,
            "argument_list": self._lower_ruby_argument_list,
            "simple_symbol": self._lower_const_literal,
            "hash_key_symbol": self._lower_const_literal,
            "range": self._lower_ruby_range,
            "regex": self._lower_const_literal,
            "lambda": self._lower_ruby_lambda,
            "string_array": self._lower_ruby_word_array,
            "symbol_array": self._lower_ruby_word_array,
            "global_variable": self._lower_identifier,
            "class_variable": self._lower_identifier,
            "heredoc_body": self._lower_ruby_heredoc_body,
            "element_reference": self._lower_element_reference,
        }
        self._EXPR_DISPATCH["conditional"] = self._lower_ruby_conditional
        self._EXPR_DISPATCH["unary"] = self._lower_unop
        self._EXPR_DISPATCH["self"] = self._lower_ruby_self
        self._EXPR_DISPATCH["super"] = self._lower_ruby_super
        self._EXPR_DISPATCH["yield"] = self._lower_ruby_yield

        self._STMT_DISPATCH: dict[str, Callable] = {
            "expression_statement": self._lower_expression_statement,
            "assignment": self._lower_assignment,
            "operator_assignment": self._lower_augmented_assignment,
            "return": self._lower_ruby_return,
            "return_statement": self._lower_ruby_return,
            "if": self._lower_if,
            "if_modifier": self._lower_ruby_if_modifier,
            "unless": self._lower_unless,
            "unless_modifier": self._lower_ruby_unless_modifier,
            "elsif": self._lower_ruby_elsif_stmt,
            "while": self._lower_while,
            "while_modifier": self._lower_ruby_while_modifier,
            "until": self._lower_until,
            "until_modifier": self._lower_ruby_until_modifier,
            "for": self._lower_ruby_for,
            "method": self._lower_ruby_method,
            "singleton_method": self._lower_ruby_singleton_method,
            "class": self._lower_ruby_class,
            "singleton_class": self._lower_ruby_singleton_class,
            "program": self._lower_block,
            "body_statement": self._lower_block,
            "do_block": self._lower_symbolic_block,
            "block": self._lower_symbolic_block,
            "break": self._lower_break,
            "next": self._lower_continue,
            "begin": self._lower_begin,
            "case": self._lower_case,
            "module": self._lower_ruby_module,
            "super": self._lower_ruby_super_stmt,
            "yield": self._lower_ruby_yield_stmt,
        }

    # -- Ruby: element_reference (array indexing) --------------------------------

    def _lower_element_reference(self, node) -> str:
        """Lower `arr[idx]` (element_reference) as LOAD_INDEX."""
        named_children = [c for c in node.children if c.is_named]
        if not named_children:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(named_children[0])
        idx_reg = (
            self._lower_expr(named_children[1])
            if len(named_children) > 1
            else self._fresh_reg()
        )
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_INDEX,
            result_reg=reg,
            operands=[obj_reg, idx_reg],
            node=node,
        )
        return reg

    # -- Ruby: argument_list unwrap -------------------------------------------

    def _lower_ruby_argument_list(self, node) -> str:
        """Unwrap argument_list to its first named child (e.g. return value)."""
        named = [c for c in node.children if c.is_named]
        if named:
            return self._lower_expr(named[0])
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[self.DEFAULT_RETURN_VALUE])
        return reg

    # -- Ruby: string interpolation --------------------------------------------

    def _lower_ruby_string(self, node) -> str:
        """Lower Ruby string, decomposing interpolation into CONST + LOAD_VAR + BINOP '+'."""
        has_interpolation = any(c.type == "interpolation" for c in node.children)
        if not has_interpolation:
            return self._lower_const_literal(node)

        parts: list[str] = []
        for child in node.children:
            if child.type == "string_content":
                frag_reg = self._fresh_reg()
                self._emit(
                    Opcode.CONST,
                    result_reg=frag_reg,
                    operands=[self._node_text(child)],
                    node=child,
                )
                parts.append(frag_reg)
            elif child.type == "interpolation":
                named = [c for c in child.children if c.is_named]
                if named:
                    parts.append(self._lower_expr(named[0]))
            # skip punctuation: ", #{, }
        return self._lower_interpolated_string_parts(parts, node)

    def _lower_ruby_heredoc_body(self, node) -> str:
        """Lower Ruby heredoc body, decomposing interpolation like _lower_ruby_string."""
        has_interpolation = any(c.type == "interpolation" for c in node.children)
        if not has_interpolation:
            return self._lower_const_literal(node)

        parts: list[str] = []
        for child in node.children:
            if child.type == "heredoc_content":
                frag_reg = self._fresh_reg()
                self._emit(
                    Opcode.CONST,
                    result_reg=frag_reg,
                    operands=[self._node_text(child)],
                    node=child,
                )
                parts.append(frag_reg)
            elif child.type == "interpolation":
                named = [c for c in child.children if c.is_named]
                if named:
                    parts.append(self._lower_expr(named[0]))
            # skip heredoc_end and punctuation
        return self._lower_interpolated_string_parts(parts, node)

    # -- Ruby: call lowering ---------------------------------------------------

    def _lower_ruby_call(self, node) -> str:
        receiver_node = node.child_by_field_name("receiver")
        method_node = node.child_by_field_name("method")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args(args_node) if args_node else []

        # Detect block/do_block child and lower it as a closure argument
        block_node = next(
            (c for c in node.children if c.type in ("block", "do_block")),
            None,
        )
        if block_node:
            block_reg = self._lower_ruby_block(block_node)
            arg_regs = arg_regs + [block_reg]

        # Method call on receiver: obj.method(...)
        if receiver_node and method_node:
            obj_reg = self._lower_expr(receiver_node)
            method_name = self._node_text(method_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_METHOD,
                result_reg=reg,
                operands=[obj_reg, method_name] + arg_regs,
                node=node,
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
                node=node,
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
            node=node,
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
            node=node,
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
            node=node,
        )

        true_label = self._fresh_label("unless_true")
        false_label = self._fresh_label("unless_false")
        end_label = self._fresh_label("unless_end")

        if alt_node:
            self._emit(
                Opcode.BRANCH_IF,
                operands=[negated_reg],
                label=f"{true_label},{false_label}",
                node=node,
            )
        else:
            self._emit(
                Opcode.BRANCH_IF,
                operands=[negated_reg],
                label=f"{true_label},{end_label}",
                node=node,
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
            node=node,
        )
        self._emit(
            Opcode.BRANCH_IF,
            operands=[negated_reg],
            label=f"{body_label},{end_label}",
            node=node,
        )

        self._emit(Opcode.LABEL, label=body_label)
        self._push_loop(loop_label, end_label)
        self._lower_block(body_node)
        self._pop_loop()
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

        update_label = self._fresh_label("for_update")
        self._push_loop(update_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()

        self._emit(Opcode.LABEL, label=update_label)
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

        self._emit(Opcode.BRANCH, label=end_label, node=node)
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
                node=child,
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

        self._emit(Opcode.BRANCH, label=end_label, node=node)
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
            node=node,
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
        if target.type in (
            "identifier",
            "instance_variable",
            "constant",
            "global_variable",
            "class_variable",
        ):
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                node=parent_node,
            )
        elif target.type == "element_reference":
            named_children = [c for c in target.children if c.is_named]
            if len(named_children) >= 2:
                obj_reg = self._lower_expr(named_children[0])
                idx_reg = self._lower_expr(named_children[1])
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                    node=parent_node,
                )
            else:
                super()._lower_store_target(target, val_reg, parent_node)
        else:
            super()._lower_store_target(target, val_reg, parent_node)

    # -- Ruby: hash literal ----------------------------------------------------

    def _lower_ruby_hash(self, node) -> str:
        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=["hash"],
            node=node,
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

    # -- Ruby: begin/rescue/else/ensure ----------------------------------------

    def _lower_begin(self, node):
        """Lower begin...rescue...else...ensure...end."""
        # The begin node's children are: "begin" keyword, body stmts, rescue, else, ensure, "end"
        # OR it wraps a body_statement. Either way, collect from the node's children directly.
        container = node
        body_stmt = next(
            (c for c in node.children if c.type == "body_statement"),
            None,
        )
        if body_stmt is not None:
            container = body_stmt

        body_children = []
        catch_clauses = []
        finally_node = None
        else_node = None

        for child in container.children:
            if child.type == "rescue":
                exc_var = None
                exc_type = None
                exceptions_node = next(
                    (c for c in child.children if c.type == "exceptions"),
                    None,
                )
                if exceptions_node:
                    exc_type = self._node_text(exceptions_node)
                var_node = next(
                    (c for c in child.children if c.type == "exception_variable"),
                    None,
                )
                if var_node:
                    # exception_variable contains => and identifier
                    id_node = next(
                        (c for c in var_node.children if c.type == "identifier"),
                        None,
                    )
                    exc_var = self._node_text(id_node) if id_node else None
                rescue_body = child.child_by_field_name("body") or next(
                    (c for c in child.children if c.type == "then"),
                    None,
                )
                catch_clauses.append(
                    {"body": rescue_body, "variable": exc_var, "type": exc_type}
                )
            elif child.type == "ensure":
                # ensure children: "ensure" keyword + body statements
                finally_node = child
            elif child.type == "else":
                else_node = child
            else:
                body_children.append(child)

        # We need a synthetic "body" to pass to _lower_try_catch.
        # Use body_stmt as the body_node but only lower the body_children.
        # Instead, lower body inline and pass None as body_node.
        # Build catch clauses from rescue blocks.

        # Use body_stmt for source location, but emit body children manually
        self._lower_try_catch_ruby(
            node, body_children, catch_clauses, finally_node, else_node
        )

    def _lower_try_catch_ruby(
        self, node, body_children, catch_clauses, finally_node, else_node
    ):
        """Ruby-specific try/catch lowering (body is a list of children, not a single node)."""
        from .. import constants

        try_body_label = self._fresh_label("try_body")
        catch_labels = [
            self._fresh_label(f"catch_{i}") for i in range(len(catch_clauses))
        ]
        finally_label = self._fresh_label("try_finally") if finally_node else ""
        else_label = self._fresh_label("try_else") if else_node else ""
        end_label = self._fresh_label("try_end")

        exit_target = finally_label or end_label

        # try body
        self._emit(Opcode.LABEL, label=try_body_label)
        for child in body_children:
            if (
                child.is_named
                and child.type not in self.COMMENT_TYPES
                and child.type not in self.NOISE_TYPES
            ):
                self._lower_stmt(child)
        if else_label:
            self._emit(Opcode.BRANCH, label=else_label)
        else:
            self._emit(Opcode.BRANCH, label=exit_target)

        # catch clauses
        for i, clause in enumerate(catch_clauses):
            self._emit(Opcode.LABEL, label=catch_labels[i])
            exc_type = clause.get("type", "StandardError") or "StandardError"
            exc_reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=exc_reg,
                operands=[f"{constants.CAUGHT_EXCEPTION_PREFIX}:{exc_type}"],
                node=node,
            )
            exc_var = clause.get("variable")
            if exc_var:
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[exc_var, exc_reg],
                    node=node,
                )
            catch_body = clause.get("body")
            if catch_body:
                self._lower_block(catch_body)
            self._emit(Opcode.BRANCH, label=exit_target)

        # else clause
        if else_node:
            self._emit(Opcode.LABEL, label=else_label)
            self._lower_block(else_node)
            self._emit(Opcode.BRANCH, label=finally_label or end_label)

        # finally (ensure)
        if finally_node:
            self._emit(Opcode.LABEL, label=finally_label)
            self._lower_block(finally_node)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Ruby: block / do_block as inline closure --------------------------------

    def _lower_ruby_block(self, node) -> str:
        """Lower a Ruby block (curly brace) or do_block (do/end) as inline closure.

        BRANCH end → LABEL block_ → params → body → CONST nil → RETURN → LABEL end → CONST func:label
        """
        block_label = self._fresh_label("block")
        end_label = self._fresh_label("block_end")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=block_label)

        # Lower block parameters from block_parameters or |x, y| syntax
        params_node = next(
            (c for c in node.children if c.type == "block_parameters"),
            None,
        )
        if params_node:
            self._lower_ruby_params(params_node)

        # Lower block body
        body_node = next(
            (c for c in node.children if c.type in ("block_body", "body_statement")),
            None,
        )
        if body_node:
            self._lower_block(body_node)
        else:
            # Inline body: lower all named children except params and delimiters
            for child in node.children:
                if (
                    child.is_named
                    and child.type not in ("block_parameters", "{", "}", "do", "end")
                    and child.type not in self.NOISE_TYPES
                    and child.type not in self.COMMENT_TYPES
                ):
                    self._lower_stmt(child)

        nil_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=nil_reg,
            operands=[self.DEFAULT_RETURN_VALUE],
        )
        self._emit(Opcode.RETURN, operands=[nil_reg])

        self._emit(Opcode.LABEL, label=end_label)

        ref_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=ref_reg,
            operands=[f"func:{block_label}"],
            node=node,
        )
        return ref_reg

    def _lower_symbolic_block(self, node):
        """Backward-compat: lower block/do_block appearing as statement."""
        self._lower_ruby_block(node)

    # -- Ruby: super and yield -------------------------------------------------

    def _lower_ruby_super(self, node) -> str:
        """Lower `super` or `super(args)` as CALL_FUNCTION("super", ...args)."""
        args_node = next(
            (c for c in node.children if c.type == "argument_list"),
            None,
        )
        arg_regs = self._extract_call_args(args_node) if args_node else []
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["super"] + arg_regs,
            node=node,
        )
        return reg

    def _lower_ruby_super_stmt(self, node):
        """Lower super as a statement."""
        self._lower_ruby_super(node)

    def _lower_ruby_yield(self, node) -> str:
        """Lower `yield` or `yield expr` as CALL_FUNCTION("yield", ...args)."""
        args_node = next(
            (c for c in node.children if c.type == "argument_list"),
            None,
        )
        arg_regs = self._extract_call_args(args_node) if args_node else []
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["yield"] + arg_regs,
            node=node,
        )
        return reg

    def _lower_ruby_yield_stmt(self, node):
        """Lower yield as a statement."""
        self._lower_ruby_yield(node)

    # -- Ruby: range expression ------------------------------------------------

    def _lower_ruby_range(self, node) -> str:
        """Lower `a..b` or `a...b` as CALL_FUNCTION("range", start, end)."""
        named = [c for c in node.children if c.is_named]
        start_reg = self._lower_expr(named[0]) if len(named) > 0 else self._fresh_reg()
        end_reg = self._lower_expr(named[1]) if len(named) > 1 else self._fresh_reg()
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["range", start_reg, end_reg],
            node=node,
        )
        return reg

    # -- Ruby: lambda ----------------------------------------------------------

    def _lower_ruby_lambda(self, node) -> str:
        """Lower `-> (params) { body }` as anonymous function."""
        func_name = f"__lambda_{self._label_counter}"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        params_node = node.child_by_field_name("parameters")
        if params_node:
            self._lower_ruby_params(params_node)

        body_node = node.child_by_field_name("body")
        if body_node:
            self._lower_block(body_node)
        else:
            # Inline body: lower named children except params and delimiters
            for child in node.children:
                if (
                    child.is_named
                    and child.type
                    not in ("lambda_parameters", "block_parameters", "->")
                    and child.type not in self.NOISE_TYPES
                    and child.type not in self.COMMENT_TYPES
                ):
                    self._lower_stmt(child)

        nil_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=nil_reg,
            operands=[self.DEFAULT_RETURN_VALUE],
        )
        self._emit(Opcode.RETURN, operands=[nil_reg])
        self._emit(Opcode.LABEL, label=end_label)

        ref_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=ref_reg,
            operands=[
                constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)
            ],
        )
        return ref_reg

    # -- Ruby: string_array / symbol_array (%w, %i) ----------------------------

    def _lower_ruby_word_array(self, node) -> str:
        """Lower `%w[a b c]` or `%i[a b c]` as NEW_ARRAY + STORE_INDEX per element."""
        elems = [
            c
            for c in node.children
            if c.is_named and c.type not in ("{", "}", "[", "]")
        ]
        arr_reg = self._fresh_reg()
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
        self._emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["list", size_reg],
            node=node,
        )
        for i, elem in enumerate(elems):
            val_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[self._node_text(elem)],
            )
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    # -- Ruby: case/when -------------------------------------------------------

    def _lower_case(self, node):
        """Lower `case expr; when val; ...; else; ...; end` as if/else chain."""
        value_node = node.child_by_field_name("value")
        val_reg = self._lower_expr(value_node) if value_node else ""

        when_clauses = [c for c in node.children if c.type == "when"]
        else_clause = next(
            (c for c in node.children if c.type == "else"),
            None,
        )
        end_label = self._fresh_label("case_end")

        for when_node in when_clauses:
            when_label = self._fresh_label("when_body")
            next_label = self._fresh_label("when_next")

            # Extract pattern(s) and body from when clause
            pattern_node = next(
                (c for c in when_node.children if c.type == "pattern"),
                None,
            )
            when_patterns = [
                c
                for c in when_node.children
                if c.is_named
                and c.type not in ("when", "then", "pattern", "body_statement")
            ]
            body_node = when_node.child_by_field_name("body")

            # If there's a pattern node, use it; otherwise use the first named child
            if pattern_node:
                pattern_reg = self._lower_expr(pattern_node)
            elif when_patterns:
                pattern_reg = self._lower_expr(when_patterns[0])
            else:
                self._emit(Opcode.BRANCH, label=when_label)
                self._emit(Opcode.LABEL, label=when_label)
                if body_node:
                    self._lower_block(body_node)
                self._emit(Opcode.BRANCH, label=end_label)
                self._emit(Opcode.LABEL, label=next_label)
                continue

            if val_reg:
                cond_reg = self._fresh_reg()
                self._emit(
                    Opcode.BINOP,
                    result_reg=cond_reg,
                    operands=["==", val_reg, pattern_reg],
                    node=when_node,
                )
            else:
                cond_reg = pattern_reg

            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{when_label},{next_label}",
                node=when_node,
            )

            self._emit(Opcode.LABEL, label=when_label)
            if body_node:
                self._lower_block(body_node)
            self._emit(Opcode.BRANCH, label=end_label)
            self._emit(Opcode.LABEL, label=next_label)

        if else_clause:
            self._lower_block(else_clause)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Ruby: module ----------------------------------------------------------

    def _lower_ruby_module(self, node):
        """Lower `module Name; ...; end` like a class."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        module_name = self._node_text(name_node) if name_node else "__anon_module"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{module_name}")
        end_label = self._fresh_label(
            f"{constants.END_CLASS_LABEL_PREFIX}{module_name}"
        )

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=class_label)
        if body_node:
            self._lower_block(body_node)
        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=cls_reg,
            operands=[
                constants.CLASS_REF_TEMPLATE.format(name=module_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[module_name, cls_reg])

    # -- Ruby: if_modifier (body if condition) ---------------------------------

    def _lower_ruby_if_modifier(self, node):
        """Lower `body if condition` — modifier-form if."""
        named = [c for c in node.children if c.is_named]
        if len(named) < 2:
            logger.warning(
                "if_modifier with fewer than 2 children: %s", self._node_text(node)[:40]
            )
            return
        body_node = named[0]
        cond_node = named[1]

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("ifmod_true")
        end_label = self._fresh_label("ifmod_end")

        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{end_label}",
            node=node,
        )
        self._emit(Opcode.LABEL, label=true_label)
        self._lower_stmt(body_node)
        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=end_label)

    # -- Ruby: unless_modifier (body unless condition) -------------------------

    def _lower_ruby_unless_modifier(self, node):
        """Lower `body unless condition` — inverted modifier-form if."""
        named = [c for c in node.children if c.is_named]
        if len(named) < 2:
            logger.warning(
                "unless_modifier with fewer than 2 children: %s",
                self._node_text(node)[:40],
            )
            return
        body_node = named[0]
        cond_node = named[1]

        cond_reg = self._lower_expr(cond_node)
        negated_reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=negated_reg,
            operands=["!", cond_reg],
            node=node,
        )
        true_label = self._fresh_label("unlessmod_true")
        end_label = self._fresh_label("unlessmod_end")

        self._emit(
            Opcode.BRANCH_IF,
            operands=[negated_reg],
            label=f"{true_label},{end_label}",
            node=node,
        )
        self._emit(Opcode.LABEL, label=true_label)
        self._lower_stmt(body_node)
        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=end_label)

    # -- Ruby: while_modifier (body while condition) ---------------------------

    def _lower_ruby_while_modifier(self, node):
        """Lower `body while condition` — modifier-form while loop."""
        named = [c for c in node.children if c.is_named]
        if len(named) < 2:
            logger.warning(
                "while_modifier with fewer than 2 children: %s",
                self._node_text(node)[:40],
            )
            return
        body_node = named[0]
        cond_node = named[1]

        loop_label = self._fresh_label("whilemod_cond")
        body_label = self._fresh_label("whilemod_body")
        end_label = self._fresh_label("whilemod_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._lower_expr(cond_node)
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
            node=node,
        )

        self._emit(Opcode.LABEL, label=body_label)
        self._push_loop(loop_label, end_label)
        self._lower_stmt(body_node)
        self._pop_loop()
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Ruby: until_modifier (body until condition) ---------------------------

    def _lower_ruby_until_modifier(self, node):
        """Lower `body until condition` — inverted modifier-form while loop."""
        named = [c for c in node.children if c.is_named]
        if len(named) < 2:
            logger.warning(
                "until_modifier with fewer than 2 children: %s",
                self._node_text(node)[:40],
            )
            return
        body_node = named[0]
        cond_node = named[1]

        loop_label = self._fresh_label("untilmod_cond")
        body_label = self._fresh_label("untilmod_body")
        end_label = self._fresh_label("untilmod_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._lower_expr(cond_node)
        negated_reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=negated_reg,
            operands=["!", cond_reg],
            node=node,
        )
        self._emit(
            Opcode.BRANCH_IF,
            operands=[negated_reg],
            label=f"{body_label},{end_label}",
            node=node,
        )

        self._emit(Opcode.LABEL, label=body_label)
        self._push_loop(loop_label, end_label)
        self._lower_stmt(body_node)
        self._pop_loop()
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Ruby: conditional (ternary) -------------------------------------------

    def _lower_ruby_conditional(self, node) -> str:
        """Lower `condition ? true_expr : false_expr` as ternary."""
        cond_node = node.child_by_field_name("condition")
        true_node = node.child_by_field_name("consequence")
        false_node = node.child_by_field_name("alternative")

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("ternary_true")
        false_label = self._fresh_label("ternary_false")
        end_label = self._fresh_label("ternary_end")

        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
        )

        self._emit(Opcode.LABEL, label=true_label)
        true_reg = self._lower_expr(true_node) if true_node else self._fresh_reg()
        result_var = f"__ternary_{self._label_counter}"
        self._emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=false_label)
        false_reg = self._lower_expr(false_node) if false_node else self._fresh_reg()
        self._emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)
        result_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=result_reg, operands=[result_var])
        return result_reg

    # -- Ruby: self keyword ----------------------------------------------------

    def _lower_ruby_self(self, node) -> str:
        """Lower `self` as LOAD_VAR('self')."""
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_VAR,
            result_reg=reg,
            operands=["self"],
            node=node,
        )
        return reg

    # -- Ruby: singleton_class (class << obj) ----------------------------------

    def _lower_ruby_singleton_class(self, node):
        """Lower `class << obj ... end` — lower the body."""
        body_node = node.child_by_field_name("body")
        value_node = node.child_by_field_name("value")

        class_label = self._fresh_label("singleton_class")
        end_label = self._fresh_label("singleton_class_end")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=class_label)

        if value_node:
            self._lower_expr(value_node)

        if body_node:
            self._lower_block(body_node)

        self._emit(Opcode.LABEL, label=end_label)

    # -- Ruby: singleton_method (def obj.method) -------------------------------

    def _lower_ruby_singleton_method(self, node):
        """Lower `def self.method_name(...) ... end` — like a regular method."""
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")
        object_node = node.child_by_field_name("object")

        object_name = self._node_text(object_node) if object_node else "self"
        method_name = self._node_text(name_node) if name_node else "__anon"
        func_name = f"{object_name}.{method_name}"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
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
