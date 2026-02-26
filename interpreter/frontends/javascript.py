"""JavaScriptFrontend — tree-sitter JavaScript AST → IR lowering."""

from __future__ import annotations

from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants


class JavaScriptFrontend(BaseFrontend):
    """Lowers a JavaScript tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "undefined"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    DEFAULT_RETURN_VALUE = "undefined"

    ATTRIBUTE_NODE_TYPE = "member_expression"
    ATTR_OBJECT_FIELD = "object"
    ATTR_ATTRIBUTE_FIELD = "property"

    SUBSCRIPT_VALUE_FIELD = "object"
    SUBSCRIPT_INDEX_FIELD = "index"

    IF_CONDITION_FIELD = "condition"
    IF_CONSEQUENCE_FIELD = "consequence"
    IF_ALTERNATIVE_FIELD = "alternative"

    COMMENT_TYPES = frozenset({"comment"})
    NOISE_TYPES = frozenset({"\n"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "number": self._lower_const_literal,
            "string": self._lower_const_literal,
            "template_string": self._lower_template_string,
            "template_substitution": self._lower_template_substitution,
            "true": self._lower_const_literal,
            "false": self._lower_const_literal,
            "null": self._lower_const_literal,
            "undefined": self._lower_const_literal,
            "binary_expression": self._lower_binop,
            "augmented_assignment_expression": self._lower_binop,
            "unary_expression": self._lower_unop,
            "update_expression": self._lower_update_expr,
            "call_expression": self._lower_call,
            "new_expression": self._lower_new_expression,
            "member_expression": self._lower_attribute,
            "subscript_expression": self._lower_js_subscript,
            "parenthesized_expression": self._lower_paren,
            "array": self._lower_list_literal,
            "object": self._lower_js_object_literal,
            "assignment_expression": self._lower_assignment_expr,
            "arrow_function": self._lower_arrow_function,
            "ternary_expression": self._lower_ternary,
            "this": self._lower_identifier,
            "super": self._lower_identifier,
            "property_identifier": self._lower_identifier,
            "shorthand_property_identifier": self._lower_identifier,
            "await_expression": self._lower_await_expression,
            "yield_expression": self._lower_yield_expression,
            "regex": self._lower_const_literal,
            "sequence_expression": self._lower_sequence_expression,
            "spread_element": self._lower_spread_element,
            "function": self._lower_function_expression,
            "function_expression": self._lower_function_expression,
            "generator_function": self._lower_function_expression,
            "generator_function_declaration": self._lower_function_def,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "expression_statement": self._lower_expression_statement,
            "lexical_declaration": self._lower_var_declaration,
            "variable_declaration": self._lower_var_declaration,
            "return_statement": self._lower_return,
            "if_statement": self._lower_if,
            "while_statement": self._lower_while,
            "for_statement": self._lower_c_style_for,
            "for_in_statement": self._lower_for_in,
            "function_declaration": self._lower_function_def,
            "class_declaration": self._lower_class_def,
            "throw_statement": self._lower_throw,
            "statement_block": self._lower_block,
            "empty_statement": lambda _: None,
            "break_statement": self._lower_break,
            "continue_statement": self._lower_continue,
            "try_statement": self._lower_try,
            "switch_statement": self._lower_switch_statement,
            "do_statement": self._lower_do_statement,
            "labeled_statement": self._lower_labeled_statement,
            "import_statement": lambda _: None,
            "export_statement": self._lower_export_statement,
        }

    # ── JS var declaration with destructuring ───────────────────

    def _lower_var_declaration(self, node):
        """Lower lexical_declaration / variable_declaration, handling destructuring."""
        for child in node.children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node is None:
                continue

            if name_node.type == "object_pattern" and value_node:
                val_reg = self._lower_expr(value_node)
                self._lower_object_destructure(name_node, val_reg, node)
            elif name_node.type == "array_pattern" and value_node:
                val_reg = self._lower_expr(value_node)
                self._lower_array_destructure(name_node, val_reg, node)
            elif value_node:
                val_reg = self._lower_expr(value_node)
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[self._node_text(name_node), val_reg],
                    source_location=self._source_loc(node),
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
                    operands=[self._node_text(name_node), val_reg],
                    source_location=self._source_loc(node),
                )

    def _lower_object_destructure(self, pattern_node, val_reg: str, parent_node):
        """Lower { a, b } = obj or { x: localX } = obj."""
        for child in pattern_node.children:
            if child.type == "shorthand_property_identifier_pattern":
                prop_name = self._node_text(child)
                field_reg = self._fresh_reg()
                self._emit(
                    Opcode.LOAD_FIELD,
                    result_reg=field_reg,
                    operands=[val_reg, prop_name],
                    source_location=self._source_loc(child),
                )
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[prop_name, field_reg],
                    source_location=self._source_loc(parent_node),
                )
            elif child.type == "pair_pattern":
                key_node = child.child_by_field_name("key")
                value_child = child.child_by_field_name("value")
                if key_node and value_child:
                    key_name = self._node_text(key_node)
                    local_name = self._node_text(value_child)
                    field_reg = self._fresh_reg()
                    self._emit(
                        Opcode.LOAD_FIELD,
                        result_reg=field_reg,
                        operands=[val_reg, key_name],
                        source_location=self._source_loc(child),
                    )
                    self._emit(
                        Opcode.STORE_VAR,
                        operands=[local_name, field_reg],
                        source_location=self._source_loc(parent_node),
                    )

    def _lower_array_destructure(self, pattern_node, val_reg: str, parent_node):
        """Lower [a, b] = arr."""
        for i, child in enumerate(c for c in pattern_node.children if c.is_named):
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            elem_reg = self._fresh_reg()
            self._emit(
                Opcode.LOAD_INDEX,
                result_reg=elem_reg,
                operands=[val_reg, idx_reg],
                source_location=self._source_loc(child),
            )
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(child), elem_reg],
                source_location=self._source_loc(parent_node),
            )

    # ── JS attribute access ──────────────────────────────────────

    def _lower_attribute(self, node) -> str:
        obj_node = node.child_by_field_name("object")
        prop_node = node.child_by_field_name("property")
        if obj_node is None or prop_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(obj_node)
        field_name = self._node_text(prop_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, field_name],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_js_subscript(self, node) -> str:
        obj_node = node.child_by_field_name("object")
        idx_node = node.child_by_field_name("index")
        if obj_node is None or idx_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(obj_node)
        idx_reg = self._lower_expr(idx_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_INDEX,
            result_reg=reg,
            operands=[obj_reg, idx_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # ── JS call ──────────────────────────────────────────────────

    def _lower_call(self, node) -> str:
        func_node = node.child_by_field_name("function")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args(args_node) if args_node else []

        if func_node and func_node.type == "member_expression":
            obj_node = func_node.child_by_field_name("object")
            prop_node = func_node.child_by_field_name("property")
            if obj_node and prop_node:
                obj_reg = self._lower_expr(obj_node)
                method_name = self._node_text(prop_node)
                reg = self._fresh_reg()
                self._emit(
                    Opcode.CALL_METHOD,
                    result_reg=reg,
                    operands=[obj_reg, method_name] + arg_regs,
                    source_location=self._source_loc(node),
                )
                return reg

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

        target_reg = self._lower_expr(func_node) if func_node else self._fresh_reg()
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    def _extract_call_args(self, args_node) -> list[str]:
        if args_node is None:
            return []
        return [
            self._lower_expr(c)
            for c in args_node.children
            if c.type not in ("(", ")", ",") and c.is_named
        ]

    # ── JS store target ──────────────────────────────────────────

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
        elif target.type == "member_expression":
            obj_node = target.child_by_field_name("object")
            prop_node = target.child_by_field_name("property")
            if obj_node and prop_node:
                obj_reg = self._lower_expr(obj_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(prop_node), val_reg],
                    source_location=self._source_loc(parent_node),
                )
        elif target.type == "subscript_expression":
            obj_node = target.child_by_field_name("object")
            idx_node = target.child_by_field_name("index")
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

    # ── JS assignment expression ─────────────────────────────────

    def _lower_assignment_expr(self, node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        val_reg = self._lower_expr(right)
        self._lower_store_target(left, val_reg, node)
        return val_reg

    # ── JS object literal ────────────────────────────────────────

    def _lower_js_object_literal(self, node) -> str:
        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=["object"],
            source_location=self._source_loc(node),
        )
        for child in node.children:
            if child.type == "pair":
                key_node = child.child_by_field_name("key")
                val_node = child.child_by_field_name("value")
                if key_node and val_node:
                    key_reg = self._lower_const_literal(key_node)
                    val_reg = self._lower_expr(val_node)
                    self._emit(
                        Opcode.STORE_INDEX,
                        operands=[obj_reg, key_reg, val_reg],
                    )
            elif child.type == "shorthand_property_identifier":
                key_reg = self._lower_const_literal(child)
                val_reg = self._lower_identifier(child)
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, key_reg, val_reg],
                )
        return obj_reg

    # ── JS arrow function ────────────────────────────────────────

    def _lower_arrow_function(self, node) -> str:
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = f"__arrow_{self._label_counter}"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            if params_node.type == "identifier":
                self._lower_param(params_node)
            else:
                self._lower_params(params_node)

        if body_node:
            if body_node.type == "statement_block":
                self._lower_block(body_node)
            else:
                # Expression body: implicit return
                val_reg = self._lower_expr(body_node)
                self._emit(Opcode.RETURN, operands=[val_reg])

        none_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[self.DEFAULT_RETURN_VALUE],
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
        return func_reg

    # ── JS ternary ───────────────────────────────────────────────

    def _lower_ternary(self, node) -> str:
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
        true_reg = self._lower_expr(true_node)
        result_var = f"__ternary_{self._label_counter}"
        self._emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=false_label)
        false_reg = self._lower_expr(false_node)
        self._emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)
        result_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=result_reg, operands=[result_var])
        return result_reg

    # ── JS for-in / for-of ───────────────────────────────────────

    def _lower_for_in(self, node):
        # for (let x in/of obj) { body }
        operator_node = node.child_by_field_name("operator")
        is_for_of = operator_node is not None and self._node_text(operator_node) == "of"

        if is_for_of:
            self._lower_for_of(node)
            return

        # for...in — model as: keys(obj) → index-based loop over keys array
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        body_node = node.child_by_field_name("body")

        obj_reg = self._lower_expr(right)
        keys_reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=keys_reg,
            operands=["keys", obj_reg],
            source_location=self._source_loc(node),
        )

        var_name = self._extract_var_name(left) if left else "__for_in_var"

        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=len_reg,
            operands=["len", keys_reg],
        )

        loop_label = self._fresh_label("for_in_cond")
        body_label = self._fresh_label("for_in_body")
        end_label = self._fresh_label("for_in_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=cond_reg,
            operands=["<", idx_reg, len_reg],
        )
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
        )

        self._emit(Opcode.LABEL, label=body_label)
        elem_reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_INDEX,
            result_reg=elem_reg,
            operands=[keys_reg, idx_reg],
        )
        if var_name:
            self._emit(Opcode.STORE_VAR, operands=[var_name, elem_reg])

        update_label = self._fresh_label("for_in_update")
        self._push_loop(update_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()

        self._emit(Opcode.LABEL, label=update_label)
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=new_idx,
            operands=["+", idx_reg, one_reg],
        )
        self._emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_for_of(self, node):
        """Lower for (const x of iterable) as index-based iteration."""
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        body_node = node.child_by_field_name("body")

        iter_reg = self._lower_expr(right)
        var_name = self._extract_var_name(left) if left else "__for_of_var"

        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

        loop_label = self._fresh_label("for_of_cond")
        body_label = self._fresh_label("for_of_body")
        end_label = self._fresh_label("for_of_end")

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
        if var_name:
            self._emit(Opcode.STORE_VAR, operands=[var_name, elem_reg])

        update_label = self._fresh_label("for_of_update")
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

    def _extract_var_name(self, node) -> str | None:
        """Extract variable name from a declaration or identifier."""
        if node.type == "identifier":
            return self._node_text(node)
        if node.type in ("lexical_declaration", "variable_declaration"):
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        return self._node_text(name_node)
        return None

    # ── JS param handling ────────────────────────────────────────

    def _lower_param(self, child):
        if child.type in ("(", ")", ","):
            return
        if child.type == "identifier":
            pname = self._node_text(child)
        elif child.type in (
            "assignment_pattern",
            "object_pattern",
            "array_pattern",
        ):
            pname = self._node_text(child)
        else:
            pname = self._extract_param_name(child)
            if pname is None:
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

    # ── JS try/catch/finally ────────────────────────────────────

    def _lower_try(self, node):
        body_node = node.child_by_field_name("body")
        handler = node.child_by_field_name("handler")
        finalizer = node.child_by_field_name("finalizer")
        catch_clauses = []
        if handler:
            # catch_clause: parameter field has the variable, body field has the block
            param_node = handler.child_by_field_name("parameter")
            exc_var = self._node_text(param_node) if param_node else None
            catch_body = handler.child_by_field_name("body")
            catch_clauses.append(
                {"body": catch_body, "variable": exc_var, "type": None}
            )
        finally_node = finalizer.child_by_field_name("body") if finalizer else None
        self._lower_try_catch(node, body_node, catch_clauses, finally_node)

    # ── JS throw ─────────────────────────────────────────────────

    def _lower_throw(self, node):
        self._lower_raise_or_throw(node, keyword="throw")

    # ── JS if alternative ────────────────────────────────────────

    def _lower_alternative(self, alt_node, end_label: str):
        alt_type = alt_node.type
        if alt_type == "else_clause":
            for child in alt_node.children:
                if child.type not in ("else",):
                    self._lower_stmt(child)
        elif alt_type == "if_statement":
            self._lower_if(alt_node)
        else:
            self._lower_block(alt_node)

    # ── JS class body handling ───────────────────────────────────

    def _lower_class_def(self, node):
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        class_name = self._node_text(name_node)

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=class_label)

        if body_node:
            for child in body_node.children:
                if child.type == "method_definition":
                    self._lower_method_def(child)
                elif child.type == "class_static_block":
                    self._lower_class_static_block(child)
                elif child.is_named:
                    self._lower_stmt(child)

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

    def _lower_method_def(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = self._node_text(name_node)
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_params(params_node)

        if body_node:
            self._lower_block(body_node)

        none_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[self.DEFAULT_RETURN_VALUE],
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

    # ── JS new expression ────────────────────────────────────────

    def _lower_new_expression(self, node) -> str:
        """Lower `new Foo(args)` → NEW_OBJECT(class) + CALL_METHOD('constructor', args)."""
        constructor_node = node.child_by_field_name("constructor")
        args_node = node.child_by_field_name("arguments")
        class_name = self._node_text(constructor_node) if constructor_node else "Object"
        arg_regs = self._extract_call_args(args_node) if args_node else []

        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=[class_name],
            source_location=self._source_loc(node),
        )
        result_reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_METHOD,
            result_reg=result_reg,
            operands=[obj_reg, "constructor"] + arg_regs,
            source_location=self._source_loc(node),
        )
        return result_reg

    # ── JS await expression ──────────────────────────────────────

    def _lower_await_expression(self, node) -> str:
        """Lower `await expr` → CALL_FUNCTION('await', expr)."""
        children = [c for c in node.children if c.is_named]
        expr_reg = self._lower_expr(children[0]) if children else self._fresh_reg()
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["await", expr_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # ── JS yield expression ──────────────────────────────────────

    def _lower_yield_expression(self, node) -> str:
        """Lower `yield expr` or bare `yield` → CALL_FUNCTION('yield', expr)."""
        children = [c for c in node.children if c.is_named]
        if children:
            expr_reg = self._lower_expr(children[0])
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=reg,
                operands=["yield", expr_reg],
                source_location=self._source_loc(node),
            )
            return reg
        # Bare yield
        none_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[self.NONE_LITERAL],
        )
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["yield", none_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # ── JS sequence expression ───────────────────────────────────

    def _lower_sequence_expression(self, node) -> str:
        """Lower `(a, b, c)` → evaluate all, return last register."""
        children = [c for c in node.children if c.is_named]
        if not children:
            return self._lower_const_literal(node)
        last_reg = self._lower_expr(children[0])
        for child in children[1:]:
            last_reg = self._lower_expr(child)
        return last_reg

    # ── JS spread element ────────────────────────────────────────

    def _lower_spread_element(self, node) -> str:
        """Lower `...expr` → CALL_FUNCTION('spread', expr)."""
        children = [c for c in node.children if c.is_named]
        expr_reg = self._lower_expr(children[0]) if children else self._fresh_reg()
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["spread", expr_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # ── JS function expression (anonymous) ───────────────────────

    def _lower_function_expression(self, node) -> str:
        """Lower anonymous function expression: same as function_declaration but anonymous."""
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = (
            self._node_text(name_node) if name_node else f"__anon_{self._label_counter}"
        )
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_params(params_node)

        if body_node:
            self._lower_block(body_node)

        none_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[self.DEFAULT_RETURN_VALUE],
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
        return func_reg

    # ── JS template string with substitutions ────────────────────

    def _lower_template_string(self, node) -> str:
        """Lower template string, descending into template_substitution children."""
        has_substitution = any(c.type == "template_substitution" for c in node.children)
        if not has_substitution:
            return self._lower_const_literal(node)

        # Build by concatenating literal fragments and substitution expressions
        parts: list[str] = []
        for child in node.children:
            if child.type == "template_substitution":
                parts.append(self._lower_template_substitution(child))
            elif child.is_named:
                parts.append(self._lower_expr(child))
            elif child.type not in ("`",):
                # String fragment
                frag_reg = self._fresh_reg()
                self._emit(
                    Opcode.CONST,
                    result_reg=frag_reg,
                    operands=[self._node_text(child)],
                )
                parts.append(frag_reg)

        if not parts:
            return self._lower_const_literal(node)
        result = parts[0]
        for part in parts[1:]:
            new_reg = self._fresh_reg()
            self._emit(
                Opcode.BINOP,
                result_reg=new_reg,
                operands=["+", result, part],
                source_location=self._source_loc(node),
            )
            result = new_reg
        return result

    def _lower_template_substitution(self, node) -> str:
        """Lower ${expr} inside a template string."""
        children = [c for c in node.children if c.is_named]
        if children:
            return self._lower_expr(children[0])
        return self._lower_const_literal(node)

    # ── JS switch statement ──────────────────────────────────────

    def _lower_switch_statement(self, node):
        """Lower switch(x) { case a: ... default: ... } as if/else chain."""
        value_node = node.child_by_field_name("value")
        body_node = node.child_by_field_name("body")

        disc_reg = self._lower_expr(value_node) if value_node else self._fresh_reg()
        end_label = self._fresh_label("switch_end")

        self._break_target_stack.append(end_label)

        if body_node:
            cases = [
                c
                for c in body_node.children
                if c.type in ("switch_case", "switch_default")
            ]
            for case_node in cases:
                if case_node.type == "switch_case":
                    value_child = case_node.child_by_field_name("value")
                    if value_child:
                        case_reg = self._lower_expr(value_child)
                        cond_reg = self._fresh_reg()
                        self._emit(
                            Opcode.BINOP,
                            result_reg=cond_reg,
                            operands=["===", disc_reg, case_reg],
                            source_location=self._source_loc(case_node),
                        )
                        body_label = self._fresh_label("case_body")
                        next_label = self._fresh_label("case_next")
                        self._emit(
                            Opcode.BRANCH_IF,
                            operands=[cond_reg],
                            label=f"{body_label},{next_label}",
                        )
                        self._emit(Opcode.LABEL, label=body_label)
                        self._lower_switch_case_body(case_node)
                        self._emit(Opcode.BRANCH, label=end_label)
                        self._emit(Opcode.LABEL, label=next_label)
                elif case_node.type == "switch_default":
                    self._lower_switch_case_body(case_node)

        self._break_target_stack.pop()
        self._emit(Opcode.LABEL, label=end_label)

    def _lower_switch_case_body(self, case_node):
        """Lower the body statements of a switch case/default clause."""
        for child in case_node.children:
            if child.is_named and child.type not in ("switch_case", "switch_default"):
                self._lower_stmt(child)

    # ── JS do...while statement ──────────────────────────────────

    def _lower_do_statement(self, node):
        """Lower do { body } while (cond)."""
        body_node = node.child_by_field_name("body")
        cond_node = node.child_by_field_name("condition")

        body_label = self._fresh_label("do_body")
        cond_label = self._fresh_label("do_cond")
        end_label = self._fresh_label("do_end")

        self._emit(Opcode.LABEL, label=body_label)

        self._push_loop(cond_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()

        self._emit(Opcode.LABEL, label=cond_label)
        cond_reg = self._lower_expr(cond_node) if cond_node else self._fresh_reg()
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
            source_location=self._source_loc(node),
        )
        self._emit(Opcode.LABEL, label=end_label)

    # ── JS labeled statement ─────────────────────────────────────

    def _lower_labeled_statement(self, node):
        """Lower `label: stmt` → LABEL(name) + lower body."""
        label_node = node.child_by_field_name("label")
        body_node = node.child_by_field_name("body")

        label_name = self._node_text(label_node) if label_node else "unknown_label"
        label = self._fresh_label(label_name)
        self._emit(Opcode.LABEL, label=label)

        if body_node:
            self._lower_stmt(body_node)

    # ── JS export statement ───────────────────────────────────────

    def _lower_export_statement(self, node):
        """Lower `export ...` by unwrapping and lowering the inner declaration."""
        for child in node.children:
            if child.is_named and child.type not in ("export", "default"):
                self._lower_stmt(child)

    # ── JS class static block ────────────────────────────────────

    def _lower_class_static_block(self, node):
        """Lower `static { ... }` inside a class body."""
        body_node = node.child_by_field_name("body")
        if body_node:
            self._lower_block(body_node)
            return
        # Fallback: lower all named children as statements
        for child in node.children:
            if child.is_named and child.type not in ("static",):
                self._lower_stmt(child)
