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
            "array_initializer": self._lower_array_creation,
            "assignment_expression": self._lower_assignment_expr,
            "cast_expression": self._lower_cast_expr,
            "instanceof_expression": self._lower_instanceof,
            "ternary_expression": self._lower_ternary,
            "type_identifier": self._lower_identifier,
            "method_reference": self._lower_method_reference,
            "lambda_expression": self._lower_lambda,
            "class_literal": self._lower_class_literal,
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
            "try_statement": self._lower_try,
            "try_with_resources_statement": self._lower_try,
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

    # ── Java: method reference ──────────────────────────────────

    def _lower_method_reference(self, node) -> str:
        """Lower method_reference: Type::method or obj::method or Type::new.

        Children are positional: [object_or_type, ::, method_or_new].
        Emits LOAD_FIELD to resolve the callable on the left-hand side.
        """
        obj_node = node.children[0]
        method_node = node.children[-1]
        obj_reg = self._lower_expr(obj_node)
        method_name = self._node_text(method_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, method_name],
            source_location=self._source_loc(node),
        )
        return reg

    # ── Java: class literal ───────────────────────────────────

    def _lower_class_literal(self, node) -> str:
        """Lower class_literal: Type.class → LOAD_FIELD(type_reg, 'class').

        Children are positional: [type_identifier, ., class].
        """
        type_node = node.children[0]
        type_reg = self._lower_expr(type_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[type_reg, "class"],
            source_location=self._source_loc(node),
        )
        return reg

    # ── Java: lambda expression ────────────────────────────────

    def _lower_lambda(self, node) -> str:
        """Lower lambda_expression: (params) -> expr or (params) -> { body }.

        Parameters field is 'formal_parameters' (typed) or 'inferred_parameters' (untyped).
        Body field is either a block or an expression.
        """
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}__lambda")
        end_label = self._fresh_label("lambda_end")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=func_label)

        params_node = node.child_by_field_name("parameters")
        if params_node:
            self._lower_lambda_params(params_node)

        body_node = node.child_by_field_name("body")
        if body_node and body_node.type == "block":
            self._lower_block(body_node)
            none_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST, result_reg=none_reg, operands=[self.DEFAULT_RETURN_VALUE]
            )
            self._emit(Opcode.RETURN, operands=[none_reg])
        elif body_node:
            body_reg = self._lower_expr(body_node)
            self._emit(Opcode.RETURN, operands=[body_reg])

        self._emit(Opcode.LABEL, label=end_label)

        ref_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=ref_reg,
            operands=[
                constants.FUNC_REF_TEMPLATE.format(name="__lambda", label=func_label)
            ],
            source_location=self._source_loc(node),
        )
        return ref_reg

    def _lower_lambda_params(self, params_node):
        """Lower parameters for lambda expressions.

        Handles both formal_parameters (typed: (int a, int b))
        and inferred_parameters (untyped: (a, b)).
        """
        if params_node.type == "formal_parameters":
            self._lower_java_params(params_node)
        else:
            for child in params_node.children:
                if child.type == "identifier":
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
        """Lower array_creation_expression or standalone array_initializer.

        With initializer: NEW_ARRAY + STORE_INDEX per element.
        Without initializer (sized): just NEW_ARRAY with size.
        """
        # Handle standalone array_initializer: {1, 2, 3}
        if node.type == "array_initializer":
            elements = [c for c in node.children if c.is_named]
            size_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elements))])
            arr_reg = self._fresh_reg()
            self._emit(
                Opcode.NEW_ARRAY,
                result_reg=arr_reg,
                operands=["array", size_reg],
                source_location=self._source_loc(node),
            )
            for i, elem in enumerate(elements):
                idx_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
                val_reg = self._lower_expr(elem)
                self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
            return arr_reg

        # array_creation_expression: look for array_initializer child
        init_node = next(
            (c for c in node.children if c.type == "array_initializer"),
            None,
        )
        if init_node is not None:
            elements = [c for c in init_node.children if c.is_named]
            size_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elements))])
            arr_reg = self._fresh_reg()
            self._emit(
                Opcode.NEW_ARRAY,
                result_reg=arr_reg,
                operands=["array", size_reg],
                source_location=self._source_loc(node),
            )
            for i, elem in enumerate(elements):
                idx_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
                val_reg = self._lower_expr(elem)
                self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
            return arr_reg

        # Sized array without initializer: new int[5]
        dims_node = next(
            (c for c in node.children if c.type == "dimensions_expr"),
            None,
        )
        if dims_node:
            dim_children = [c for c in dims_node.children if c.is_named]
            size_reg = (
                self._lower_expr(dim_children[0]) if dim_children else self._fresh_reg()
            )
        else:
            size_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=size_reg, operands=["0"])
        arr_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["array", size_reg],
            source_location=self._source_loc(node),
        )
        return arr_reg

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
        """Lower instanceof_expression: operand instanceof Type.

        Emits: lower_expr(operand) -> CONST type_name -> CALL_FUNCTION instanceof(obj, type)
        """
        named_children = [c for c in node.children if c.is_named]
        operand_node = named_children[0] if named_children else None
        type_node = named_children[1] if len(named_children) > 1 else None

        obj_reg = self._lower_expr(operand_node) if operand_node else self._fresh_reg()
        type_reg = self._fresh_reg()
        type_name = self._node_text(type_node) if type_node else "Object"
        self._emit(Opcode.CONST, result_reg=type_reg, operands=[type_name])
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["instanceof", obj_reg, type_reg],
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
        """Lower interface_declaration as NEW_OBJECT with STORE_INDEX per member."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        iface_name = self._node_text(name_node)
        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=[f"interface:{iface_name}"],
            source_location=self._source_loc(node),
        )
        body_node = node.child_by_field_name("body")
        if body_node:
            for i, child in enumerate(c for c in body_node.children if c.is_named):
                member_name_node = child.child_by_field_name("name")
                member_name = (
                    self._node_text(member_name_node)
                    if member_name_node
                    else self._node_text(child)[:40]
                )
                key_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
                val_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
                self._emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
        self._emit(Opcode.STORE_VAR, operands=[iface_name, obj_reg])

    def _lower_enum_decl(self, node):
        """Lower enum_declaration as NEW_OBJECT with STORE_INDEX per member."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        if name_node:
            enum_name = self._node_text(name_node)
            obj_reg = self._fresh_reg()
            self._emit(
                Opcode.NEW_OBJECT,
                result_reg=obj_reg,
                operands=[f"enum:{enum_name}"],
                source_location=self._source_loc(node),
            )
            if body_node:
                for i, child in enumerate(
                    c for c in body_node.children if c.type == "enum_constant"
                ):
                    member_name_node = child.child_by_field_name("name")
                    member_name = (
                        self._node_text(member_name_node)
                        if member_name_node
                        else self._node_text(child)
                    )
                    key_reg = self._fresh_reg()
                    self._emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
                    val_reg = self._fresh_reg()
                    self._emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
                    self._emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
            self._emit(Opcode.STORE_VAR, operands=[enum_name, obj_reg])

    # ── Java: try/catch/finally ─────────────────────────────────

    def _lower_try(self, node):
        body_node = node.child_by_field_name("body")
        catch_clauses = []
        finally_node = None
        for child in node.children:
            if child.type == "catch_clause":
                param_node = next(
                    (c for c in child.children if c.type == "catch_formal_parameter"),
                    None,
                )
                exc_var = None
                exc_type = None
                if param_node:
                    name_node = param_node.child_by_field_name("name")
                    exc_var = self._node_text(name_node) if name_node else None
                    # catch_type is the first named child that isn't the name
                    type_nodes = [
                        c for c in param_node.children if c.is_named and c != name_node
                    ]
                    if type_nodes:
                        exc_type = self._node_text(type_nodes[0])
                catch_body = child.child_by_field_name("body")
                catch_clauses.append(
                    {"body": catch_body, "variable": exc_var, "type": exc_type}
                )
            elif child.type == "finally_clause":
                finally_node = child.child_by_field_name("body") or next(
                    (c for c in child.children if c.type == "block"),
                    None,
                )
        self._lower_try_catch(node, body_node, catch_clauses, finally_node)

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
