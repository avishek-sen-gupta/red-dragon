"""PythonFrontend — tree-sitter Python AST → IR lowering."""

from __future__ import annotations

from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants


class PythonFrontend(BaseFrontend):
    """Lowers a Python tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "None"
    TRUE_LITERAL = "True"
    FALSE_LITERAL = "False"
    DEFAULT_RETURN_VALUE = "None"

    PAREN_EXPR_TYPE = "parenthesized_expression"
    ATTRIBUTE_NODE_TYPE = "attribute"

    SUBSCRIPT_VALUE_FIELD = "value"
    SUBSCRIPT_INDEX_FIELD = "subscript"

    COMMENT_TYPES = frozenset({"comment"})
    NOISE_TYPES = frozenset({"newline", "\n"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "integer": self._lower_const_literal,
            "float": self._lower_const_literal,
            "string": self._lower_const_literal,
            "concatenated_string": self._lower_const_literal,
            "true": self._lower_const_literal,
            "false": self._lower_const_literal,
            "none": self._lower_const_literal,
            "binary_operator": self._lower_binop,
            "boolean_operator": self._lower_binop,
            "comparison_operator": self._lower_comparison,
            "unary_operator": self._lower_unop,
            "not_operator": self._lower_unop,
            "call": self._lower_call,
            "attribute": self._lower_attribute,
            "subscript": self._lower_subscript,
            "parenthesized_expression": self._lower_paren,
            "list": self._lower_list_literal,
            "dictionary": self._lower_dict_literal,
            "tuple": self._lower_tuple_literal,
            "conditional_expression": self._lower_conditional_expr,
            "list_comprehension": self._lower_list_comprehension,
            "dictionary_comprehension": self._lower_dict_comprehension,
            "lambda": self._lower_lambda,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "expression_statement": self._lower_expression_statement,
            "assignment": self._lower_assignment,
            "augmented_assignment": self._lower_augmented_assignment,
            "return_statement": self._lower_return,
            "if_statement": self._lower_if,
            "while_statement": self._lower_while,
            "for_statement": self._lower_for,
            "function_definition": self._lower_function_def,
            "class_definition": self._lower_class_def,
            "raise_statement": self._lower_raise,
            "try_statement": self._lower_try,
            "pass_statement": lambda _: None,
            "break_statement": self._lower_break,
            "continue_statement": self._lower_continue,
            "with_statement": self._lower_with,
            "decorated_definition": self._lower_decorated_def,
        }

    # ── Python-specific call lowering ────────────────────────────

    def _lower_call(self, node) -> str:
        func_node = node.child_by_field_name("function")
        args_node = node.child_by_field_name("arguments")

        arg_regs = (
            [
                self._lower_expr(c)
                for c in args_node.children
                if c.type not in ("(", ")", ",")
            ]
            if args_node
            else []
        )

        # Method call: obj.method(...)
        if func_node and func_node.type == "attribute":
            obj_node = func_node.child_by_field_name("object")
            attr_node = func_node.child_by_field_name("attribute")
            obj_reg = self._lower_expr(obj_node)
            method_name = self._node_text(attr_node)
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

        # Dynamic / unknown call target
        target_reg = self._lower_expr(func_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    # ── Python-specific: for loop ────────────────────────────────

    def _lower_for(self, node):
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        body_node = node.child_by_field_name("body")

        iter_reg = self._lower_expr(right)
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
        self._lower_store_target(left, elem_reg, node)

        update_label = self._fresh_label("for_update")
        self._push_loop(update_label, end_label)
        self._lower_block(body_node)
        self._pop_loop()

        self._emit(Opcode.LABEL, label=update_label)
        self._emit_for_increment(idx_reg, loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _emit_for_increment(self, idx_reg: str, loop_label: str):
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
        self._emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
        idx_reload = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=idx_reload, operands=["__for_idx"])
        self._emit(Opcode.BRANCH, label=loop_label)

    # ── Python-specific: parameters ──────────────────────────────

    def _lower_param(self, child):
        if child.type in ("(", ")", ",", ":"):
            return

        if child.type == "identifier":
            pname = self._node_text(child)
        elif child.type == "default_parameter":
            pname_node = child.child_by_field_name("name")
            if not pname_node:
                return
            pname = self._node_text(pname_node)
        elif child.type == "typed_parameter":
            id_node = next(
                (sub for sub in child.children if sub.type == "identifier"),
                None,
            )
            if not id_node:
                return
            pname = self._node_text(id_node)
        elif child.type == "typed_default_parameter":
            pname_node = child.child_by_field_name("name")
            if not pname_node:
                return
            pname = self._node_text(pname_node)
        else:
            return

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

    # ── Python-specific: raise ───────────────────────────────────

    def _lower_raise(self, node):
        self._lower_raise_or_throw(node, keyword="raise")

    # ── Python-specific: try/except/else/finally ──────────────────

    def _lower_try(self, node):
        body_node = node.child_by_field_name("body")
        catch_clauses = []
        finally_node = None
        else_node = None
        for child in node.children:
            if child.type == "except_clause":
                exc_var = None
                exc_type = None
                # except ExcType as var: ...
                for sub in child.children:
                    if sub.type == "as_pattern":
                        # as_pattern children: type, "as", name
                        parts = [c for c in sub.children if c.is_named]
                        if parts:
                            exc_type = self._node_text(parts[0])
                        if len(parts) >= 2:
                            exc_var = self._node_text(parts[-1])
                    elif sub.type == "identifier" and exc_type is None:
                        exc_type = self._node_text(sub)
                exc_body = next((c for c in child.children if c.type == "block"), None)
                catch_clauses.append(
                    {"body": exc_body, "variable": exc_var, "type": exc_type}
                )
            elif child.type == "finally_clause":
                finally_node = next(
                    (c for c in child.children if c.type == "block"), None
                )
            elif child.type == "else_clause":
                else_node = child.child_by_field_name("body") or next(
                    (c for c in child.children if c.type == "block"), None
                )
        self._lower_try_catch(node, body_node, catch_clauses, finally_node, else_node)

    # ── Python-specific: tuple ───────────────────────────────────

    def _lower_tuple_literal(self, node) -> str:
        elems = [c for c in node.children if c.type not in ("(", ")", ",")]
        arr_reg = self._fresh_reg()
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
        self._emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["tuple", size_reg],
            source_location=self._source_loc(node),
        )
        for i, elem in enumerate(elems):
            val_reg = self._lower_expr(elem)
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    # ── Python-specific: conditional expression ──────────────────

    def _lower_conditional_expr(self, node) -> str:
        children = [c for c in node.children if c.type not in ("if", "else")]
        true_expr = children[0]
        cond_expr = children[1]
        false_expr = children[2]

        cond_reg = self._lower_expr(cond_expr)
        true_label = self._fresh_label("ternary_true")
        false_label = self._fresh_label("ternary_false")
        end_label = self._fresh_label("ternary_end")

        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
        )

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
        self._emit(Opcode.LOAD_VAR, result_reg=result_reg, operands=[result_var])
        return result_reg

    # ── Python-specific: tuple unpack ────────────────────────────

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type in ("pattern_list", "tuple_pattern"):
            self._lower_tuple_unpack(target, val_reg, parent_node)
            return
        super()._lower_store_target(target, val_reg, parent_node)

    def _lower_tuple_unpack(self, target, val_reg: str, parent_node):
        for i, child in enumerate(c for c in target.children if c.type != ","):
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            elem_reg = self._fresh_reg()
            self._emit(
                Opcode.LOAD_INDEX,
                result_reg=elem_reg,
                operands=[val_reg, idx_reg],
            )
            self._lower_store_target(child, elem_reg, parent_node)

    # ── Python-specific: list comprehension ──────────────────────

    def _lower_list_comprehension(self, node) -> str:
        """Desugar [expr for var in iterable if cond] into index-based loop.

        Supports nested comprehensions via recursive helper.
        """
        children = [c for c in node.children if c.is_named]
        body_expr = children[0] if children else None
        for_clauses = [c for c in children if c.type == "for_in_clause"]
        if_clauses = [c for c in children if c.type == "if_clause"]

        # Create result array
        result_arr = self._fresh_reg()
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=["0"])
        self._emit(
            Opcode.NEW_ARRAY,
            result_reg=result_arr,
            operands=["list", size_reg],
            source_location=self._source_loc(node),
        )

        # Result index counter
        result_idx = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=result_idx, operands=["0"])

        end_label = self._fresh_label("comp_end")

        self._lower_comprehension_loop(
            for_clauses, if_clauses, body_expr, result_arr, result_idx, node, end_label
        )

        self._emit(Opcode.LABEL, label=end_label)
        return result_arr

    def _lower_comprehension_loop(
        self,
        for_clauses,
        if_clauses,
        body_expr,
        result_arr,
        result_idx,
        node,
        end_label,
    ):
        """Recursive helper: emit one level of comprehension loop."""
        if not for_clauses:
            return

        for_clause = for_clauses[0]
        remaining_fors = for_clauses[1:]

        clause_named = [c for c in for_clause.children if c.is_named]
        loop_var = clause_named[0] if clause_named else None
        iterable_node = clause_named[1] if len(clause_named) > 1 else None

        iter_reg = (
            self._lower_expr(iterable_node) if iterable_node else self._fresh_reg()
        )
        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

        loop_label = self._fresh_label("comp_cond")
        body_label = self._fresh_label("comp_body")
        loop_end_label = self._fresh_label("comp_loop_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{loop_end_label}",
        )

        self._emit(Opcode.LABEL, label=body_label)
        elem_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[iter_reg, idx_reg])
        self._lower_store_target(loop_var, elem_reg, node)

        if remaining_fors:
            # Recurse for nested for-clauses (filters apply at innermost level)
            self._lower_comprehension_loop(
                remaining_fors,
                if_clauses,
                body_expr,
                result_arr,
                result_idx,
                node,
                end_label,
            )
        else:
            # Innermost loop: apply filters and store body
            store_label = self._fresh_label("comp_store")
            skip_label = self._fresh_label("comp_skip") if if_clauses else None
            if if_clauses:
                filter_expr = next(
                    (c for c in if_clauses[0].children if c.is_named), None
                )
                filter_reg = self._lower_expr(filter_expr)
                self._emit(
                    Opcode.BRANCH_IF,
                    operands=[filter_reg],
                    label=f"{store_label},{skip_label}",
                )

            self._emit(Opcode.LABEL, label=store_label)
            val_reg = self._lower_expr(body_expr)
            self._emit(Opcode.STORE_INDEX, operands=[result_arr, result_idx, val_reg])
            one_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
            new_result_idx = self._fresh_reg()
            self._emit(
                Opcode.BINOP,
                result_reg=new_result_idx,
                operands=["+", result_idx, one_reg],
            )
            self._emit(Opcode.STORE_VAR, operands=["__comp_result_idx", new_result_idx])

            if skip_label:
                self._emit(Opcode.LABEL, label=skip_label)

        # Increment source index
        self._emit_for_increment(idx_reg, loop_label)

        self._emit(Opcode.LABEL, label=loop_end_label)

    # ── Python-specific: dict comprehension ──────────────────────

    def _lower_dict_comprehension(self, node) -> str:
        """Desugar {k: v for var in iterable if cond} into loop."""
        children = [c for c in node.children if c.is_named]
        # children: pair (k: v), for_in_clause, optional if_clause(s)
        pair_node = next((c for c in children if c.type == "pair"), None)
        for_clause = next((c for c in children if c.type == "for_in_clause"), None)
        if_clauses = [c for c in children if c.type == "if_clause"]

        # Create result object
        result_obj = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=result_obj,
            operands=["dict"],
            source_location=self._source_loc(node),
        )

        # Extract loop var and iterable from for_in_clause
        clause_named = [c for c in for_clause.children if c.is_named]
        loop_var = clause_named[0] if clause_named else None
        iterable_node = clause_named[1] if len(clause_named) > 1 else None

        iter_reg = (
            self._lower_expr(iterable_node) if iterable_node else self._fresh_reg()
        )
        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

        loop_label = self._fresh_label("dcomp_cond")
        body_label = self._fresh_label("dcomp_body")
        end_label = self._fresh_label("dcomp_end")

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
        self._lower_store_target(loop_var, elem_reg, node)

        # Handle if clause (filter)
        store_label = self._fresh_label("dcomp_store")
        skip_label = self._fresh_label("dcomp_skip") if if_clauses else None
        if if_clauses:
            filter_expr = next((c for c in if_clauses[0].children if c.is_named), None)
            filter_reg = self._lower_expr(filter_expr)
            self._emit(
                Opcode.BRANCH_IF,
                operands=[filter_reg],
                label=f"{store_label},{skip_label}",
            )

        self._emit(Opcode.LABEL, label=store_label)
        # Evaluate key and value from pair
        key_node = pair_node.child_by_field_name("key") if pair_node else None
        val_node = pair_node.child_by_field_name("value") if pair_node else None
        key_reg = self._lower_expr(key_node) if key_node else self._fresh_reg()
        val_reg = self._lower_expr(val_node) if val_node else self._fresh_reg()
        self._emit(Opcode.STORE_INDEX, operands=[result_obj, key_reg, val_reg])

        if skip_label:
            self._emit(Opcode.LABEL, label=skip_label)

        # Increment source index
        self._emit_for_increment(idx_reg, loop_label)

        self._emit(Opcode.LABEL, label=end_label)
        return result_obj

    # ── Python-specific: with statement ──────────────────────────

    def _lower_with(self, node):
        """Lower `with ctx as var: body` → __enter__/__exit__ calls."""
        with_clause = next((c for c in node.children if c.type == "with_clause"), None)
        body_node = node.child_by_field_name("body")

        with_items = (
            [c for c in with_clause.children if c.type == "with_item"]
            if with_clause
            else []
        )

        # Collect enter results for nested exit calls
        enter_info: list[tuple[str, str | None]] = []  # (ctx_reg, var_name or None)

        for item in with_items:
            as_pat = next((c for c in item.children if c.type == "as_pattern"), None)
            if as_pat:
                named = [c for c in as_pat.children if c.is_named]
                ctx_expr = named[0]
                target_node = named[-1] if len(named) >= 2 else None
                # as_pattern_target wraps the identifier
                var_name = (
                    self._node_text(
                        next(
                            (c for c in target_node.children if c.type == "identifier"),
                            target_node,
                        )
                    )
                    if target_node
                    else None
                )
            else:
                # No 'as' — the with_item's first named child is the context expr
                ctx_expr = next((c for c in item.children if c.is_named), None)
                var_name = None

            ctx_reg = self._lower_expr(ctx_expr)
            enter_reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_METHOD,
                result_reg=enter_reg,
                operands=[ctx_reg, "__enter__"],
                source_location=self._source_loc(item),
            )
            if var_name:
                self._emit(Opcode.STORE_VAR, operands=[var_name, enter_reg])
            enter_info.append((ctx_reg, var_name))

        self._lower_block(body_node)

        # Exit in reverse order (LIFO)
        for ctx_reg, _ in reversed(enter_info):
            exit_reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_METHOD,
                result_reg=exit_reg,
                operands=[ctx_reg, "__exit__"],
                source_location=self._source_loc(node),
            )

    # ── Python-specific: decorated definition ────────────────────

    def _lower_decorated_def(self, node):
        """Lower @dec def/class → define, then wrap with decorator calls."""
        decorators = [c for c in node.children if c.type == "decorator"]
        definition = next(
            (
                c
                for c in node.children
                if c.type in ("function_definition", "class_definition")
            ),
            None,
        )

        # Lower the inner definition normally
        self._lower_stmt(definition)

        # Extract the defined name
        name_node = definition.child_by_field_name("name")
        func_name = self._node_text(name_node)

        # Apply decorators bottom-up (last decorator applied first)
        for dec in reversed(decorators):
            # Decorator expression is the first named child (skip '@')
            dec_expr = next((c for c in dec.children if c.is_named), None)
            if not dec_expr:
                continue

            func_reg = self._fresh_reg()
            self._emit(Opcode.LOAD_VAR, result_reg=func_reg, operands=[func_name])
            dec_reg = self._lower_expr(dec_expr)
            result_reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=result_reg,
                operands=[dec_reg, func_reg],
                source_location=self._source_loc(dec),
            )
            self._emit(Opcode.STORE_VAR, operands=[func_name, result_reg])

    # ── Python-specific: lambda ──────────────────────────────────

    def _lower_lambda(self, node) -> str:
        """Lower `lambda x, y: expr` → inline function definition."""
        func_label = self._fresh_label("lambda")
        end_label = self._fresh_label("lambda_end")

        # Branch past the function body
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=func_label)

        # Lower parameters
        params_node = next(
            (c for c in node.children if c.type == "lambda_parameters"), None
        )
        if params_node:
            for child in params_node.children:
                self._lower_param(child)

        # Lower body expression and return
        body_node = node.child_by_field_name("body") or next(
            (
                c
                for c in node.children
                if c.is_named and c.type not in ("lambda_parameters",)
            ),
            None,
        )
        body_reg = self._lower_expr(body_node)
        self._emit(Opcode.RETURN, operands=[body_reg])

        self._emit(Opcode.LABEL, label=end_label)

        # Reference to the lambda function
        ref_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=ref_reg,
            operands=[f"func:{func_label}"],
            source_location=self._source_loc(node),
        )
        return ref_reg
