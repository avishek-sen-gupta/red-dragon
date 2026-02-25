"""JavaFrontend — tree-sitter Java AST → IR lowering."""

from __future__ import annotations

from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants


class JavaFrontend(BaseFrontend):
    """Lowers a Java tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "null"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    DEFAULT_RETURN_VALUE = "null"

    ATTRIBUTE_NODE_TYPE = "field_access"
    ATTR_OBJECT_FIELD = "object"
    ATTR_ATTRIBUTE_FIELD = "field"

    COMMENT_TYPES = frozenset({"comment", "line_comment", "block_comment"})
    NOISE_TYPES = frozenset({"\n"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "decimal_integer_literal": self._lower_const_literal,
            "hex_integer_literal": self._lower_const_literal,
            "octal_integer_literal": self._lower_const_literal,
            "binary_integer_literal": self._lower_const_literal,
            "decimal_floating_point_literal": self._lower_const_literal,
            "string_literal": self._lower_const_literal,
            "character_literal": self._lower_const_literal,
            "true": self._lower_const_literal,
            "false": self._lower_const_literal,
            "null_literal": self._lower_const_literal,
            "this": self._lower_identifier,
            "binary_expression": self._lower_binop,
            "unary_expression": self._lower_unop,
            "update_expression": self._lower_update_expr,
            "parenthesized_expression": self._lower_paren,
            "method_invocation": self._lower_method_invocation,
            "object_creation_expression": self._lower_object_creation,
            "field_access": self._lower_field_access,
            "array_access": self._lower_array_access,
            "array_creation_expression": self._lower_array_creation,
            "assignment_expression": self._lower_assignment_expr,
            "cast_expression": self._lower_cast_expr,
            "instanceof_expression": self._lower_instanceof,
            "ternary_expression": self._lower_ternary,
            "type_identifier": self._lower_identifier,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "expression_statement": self._lower_expression_statement,
            "local_variable_declaration": self._lower_local_var_decl,
            "return_statement": self._lower_return,
            "if_statement": self._lower_if,
            "while_statement": self._lower_while,
            "for_statement": self._lower_c_style_for,
            "enhanced_for_statement": self._lower_enhanced_for,
            "method_declaration": self._lower_method_decl,
            "class_declaration": self._lower_class_def,
            "interface_declaration": self._lower_interface_decl,
            "enum_declaration": self._lower_enum_decl,
            "throw_statement": self._lower_throw,
            "block": self._lower_block,
            "import_declaration": lambda _: None,
            "package_declaration": lambda _: None,
            "program": self._lower_block,
            "break_statement": self._lower_break,
            "continue_statement": self._lower_continue,
            "switch_expression": self._lower_java_switch,
        }

    # ── Java: local variable declaration ─────────────────────────

    def _lower_local_var_decl(self, node):
        for child in node.children:
            if child.type == "variable_declarator":
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

    # ── Java: method invocation ──────────────────────────────────

    def _lower_method_invocation(self, node) -> str:
        name_node = node.child_by_field_name("name")
        obj_node = node.child_by_field_name("object")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args_unwrap(args_node) if args_node else []

        if obj_node:
            obj_reg = self._lower_expr(obj_node)
            method_name = self._node_text(name_node) if name_node else "unknown"
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_METHOD,
                result_reg=reg,
                operands=[obj_reg, method_name] + arg_regs,
                source_location=self._source_loc(node),
            )
            return reg

        func_name = self._node_text(name_node) if name_node else "unknown"
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[func_name] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    # ── Java: object creation ────────────────────────────────────

    def _lower_object_creation(self, node) -> str:
        type_node = node.child_by_field_name("type")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args_unwrap(args_node) if args_node else []
        type_name = self._node_text(type_node) if type_node else "Object"
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[type_name] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    # ── Java: field access ───────────────────────────────────────

    def _lower_field_access(self, node) -> str:
        obj_node = node.child_by_field_name("object")
        field_node = node.child_by_field_name("field")
        if obj_node is None or field_node is None:
            return self._lower_const_literal(node)
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

    # ── Java: array access ───────────────────────────────────────

    def _lower_array_access(self, node) -> str:
        arr_node = node.child_by_field_name("array")
        idx_node = node.child_by_field_name("index")
        if arr_node is None or idx_node is None:
            return self._lower_const_literal(node)
        arr_reg = self._lower_expr(arr_node)
        idx_reg = self._lower_expr(idx_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_INDEX,
            result_reg=reg,
            operands=[arr_reg, idx_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # ── Java: array creation ─────────────────────────────────────

    def _lower_array_creation(self, node) -> str:
        reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"new_array:{self._node_text(node)[:60]}"],
            source_location=self._source_loc(node),
        )
        return reg

    # ── Java: assignment expression ──────────────────────────────

    def _lower_assignment_expr(self, node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        val_reg = self._lower_expr(right)
        self._lower_store_target(left, val_reg, node)
        return val_reg

    # ── Java: store target ───────────────────────────────────────

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
        elif target.type == "field_access":
            obj_node = target.child_by_field_name("object")
            field_node = target.child_by_field_name("field")
            if obj_node and field_node:
                obj_reg = self._lower_expr(obj_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(field_node), val_reg],
                    source_location=self._source_loc(parent_node),
                )
        elif target.type == "array_access":
            arr_node = target.child_by_field_name("array")
            idx_node = target.child_by_field_name("index")
            if arr_node and idx_node:
                arr_reg = self._lower_expr(arr_node)
                idx_reg = self._lower_expr(idx_node)
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[arr_reg, idx_reg, val_reg],
                    source_location=self._source_loc(parent_node),
                )
        else:
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )

    # ── Java: cast expression ────────────────────────────────────

    def _lower_cast_expr(self, node) -> str:
        value_node = node.child_by_field_name("value")
        if value_node:
            return self._lower_expr(value_node)
        children = [c for c in node.children if c.is_named]
        if len(children) >= 2:
            return self._lower_expr(children[-1])
        return self._lower_const_literal(node)

    # ── Java: instanceof ────────────────────────────────────────

    def _lower_instanceof(self, node) -> str:
        reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"instanceof:{self._node_text(node)[:60]}"],
            source_location=self._source_loc(node),
        )
        return reg

    # ── Java: ternary ────────────────────────────────────────────

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

    # ── Java: enhanced for ───────────────────────────────────────

    def _lower_enhanced_for(self, node):
        # for (Type var : iterable) { body }
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        body_node = node.child_by_field_name("body")

        iter_reg = self._lower_expr(value_node) if value_node else self._fresh_reg()
        var_name = self._node_text(name_node) if name_node else "__for_var"

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

        # increment
        self._emit(Opcode.LABEL, label=update_label)
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
        self._emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # ── Java: switch expression ──────────────────────────────────

    def _lower_java_switch(self, node):
        """Lower switch(expr) { case ... } as an if/else chain."""
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

        subject_reg = self._lower_expr(cond_node)
        end_label = self._fresh_label("switch_end")

        self._break_target_stack.append(end_label)

        groups = (
            [c for c in body_node.children if c.type == "switch_block_statement_group"]
            if body_node
            else []
        )

        for group in groups:
            label_node = next(
                (c for c in group.children if c.type == "switch_label"), None
            )
            body_stmts = [
                c for c in group.children if c.is_named and c.type != "switch_label"
            ]

            arm_label = self._fresh_label("case_arm")
            next_label = self._fresh_label("case_next")

            is_default = label_node is not None and not any(
                c.is_named for c in label_node.children
            )

            if label_node and not is_default:
                # Extract case value from switch_label's first named child
                case_value = next((c for c in label_node.children if c.is_named), None)
                if case_value:
                    case_reg = self._lower_expr(case_value)
                    cmp_reg = self._fresh_reg()
                    self._emit(
                        Opcode.BINOP,
                        result_reg=cmp_reg,
                        operands=["==", subject_reg, case_reg],
                        source_location=self._source_loc(group),
                    )
                    self._emit(
                        Opcode.BRANCH_IF,
                        operands=[cmp_reg],
                        label=f"{arm_label},{next_label}",
                    )
                else:
                    self._emit(Opcode.BRANCH, label=arm_label)
            else:
                # default case
                self._emit(Opcode.BRANCH, label=arm_label)

            self._emit(Opcode.LABEL, label=arm_label)
            for stmt in body_stmts:
                self._lower_stmt(stmt)
            self._emit(Opcode.BRANCH, label=end_label)
            self._emit(Opcode.LABEL, label=next_label)

        self._break_target_stack.pop()
        self._emit(Opcode.LABEL, label=end_label)

    # ── Java: method declaration ─────────────────────────────────

    def _lower_method_decl(self, node):
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
            self._lower_java_params(params_node)

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

    def _lower_java_params(self, params_node):
        for child in params_node.children:
            if child.type == "formal_parameter":
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
            elif child.type == "spread_parameter":
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

    # ── Java: class ──────────────────────────────────────────────

    def _lower_class_def(self, node):
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
            self._lower_class_body(body_node)
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

    def _lower_class_body(self, node):
        for child in node.children:
            if child.type == "method_declaration":
                self._lower_method_decl(child)
            elif child.type == "constructor_declaration":
                self._lower_constructor_decl(child)
            elif child.type == "field_declaration":
                self._lower_field_decl(child)
            elif child.is_named and child.type not in (
                "modifiers",
                "marker_annotation",
                "annotation",
            ):
                self._lower_stmt(child)

    def _lower_constructor_decl(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = "__init__"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_java_params(params_node)

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

    def _lower_field_decl(self, node):
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node and value_node:
                    val_reg = self._lower_expr(value_node)
                    self._emit(
                        Opcode.STORE_VAR,
                        operands=[self._node_text(name_node), val_reg],
                        source_location=self._source_loc(node),
                    )

    # ── Java: interface/enum ─────────────────────────────────────

    def _lower_interface_decl(self, node):
        name_node = node.child_by_field_name("name")
        if name_node:
            iface_name = self._node_text(name_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=reg,
                operands=[f"interface:{iface_name}"],
                source_location=self._source_loc(node),
            )
            self._emit(Opcode.STORE_VAR, operands=[iface_name, reg])

    def _lower_enum_decl(self, node):
        name_node = node.child_by_field_name("name")
        if name_node:
            enum_name = self._node_text(name_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=reg,
                operands=[f"enum:{enum_name}"],
                source_location=self._source_loc(node),
            )
            self._emit(Opcode.STORE_VAR, operands=[enum_name, reg])

    # ── Java: throw ──────────────────────────────────────────────

    def _lower_throw(self, node):
        self._lower_raise_or_throw(node, keyword="throw")

    # ── Java: if alternative ─────────────────────────────────────

    def _lower_if(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        # Java wraps condition in parenthesized_expression
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
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            # else block or else-if
            for child in alt_node.children:
                if child.type not in ("else",) and child.is_named:
                    self._lower_stmt(child)
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)
