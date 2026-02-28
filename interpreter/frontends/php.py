"""PhpFrontend — tree-sitter PHP AST -> IR lowering."""

from __future__ import annotations

import logging
from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)


class PhpFrontend(BaseFrontend):
    """Lowers a PHP tree-sitter AST into flattened TAC IR."""

    ATTRIBUTE_NODE_TYPE = "member_access_expression"
    ATTR_OBJECT_FIELD = "object"
    ATTR_ATTRIBUTE_FIELD = "name"

    COMMENT_TYPES = frozenset({"comment"})
    NOISE_TYPES = frozenset({"php_tag", "text_interpolation", "php_end_tag", "\n"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "variable_name": self._lower_php_variable,
            "name": self._lower_identifier,
            "integer": self._lower_const_literal,
            "float": self._lower_const_literal,
            "string": self._lower_const_literal,
            "encapsed_string": self._lower_const_literal,
            "boolean": self._lower_canonical_bool,
            "null": self._lower_canonical_none,
            "binary_expression": self._lower_binop,
            "unary_op_expression": self._lower_unop,
            "update_expression": self._lower_update_expr,
            "function_call_expression": self._lower_php_func_call,
            "member_call_expression": self._lower_php_method_call,
            "member_access_expression": self._lower_php_member_access,
            "subscript_expression": self._lower_php_subscript,
            "parenthesized_expression": self._lower_paren,
            "array_creation_expression": self._lower_php_array,
            "assignment_expression": self._lower_php_assignment_expr,
            "augmented_assignment_expression": self._lower_php_augmented_assignment_expr,
            "cast_expression": self._lower_php_cast,
            "conditional_expression": self._lower_php_ternary,
            "throw_expression": self._lower_php_throw_expr,
            "object_creation_expression": self._lower_php_object_creation,
            "match_expression": self._lower_php_match_expression,
            "arrow_function": self._lower_php_arrow_function,
            "scoped_call_expression": self._lower_php_scoped_call,
            "anonymous_function": self._lower_php_anonymous_function,
            "nullsafe_member_access_expression": self._lower_php_nullsafe_member_access,
            "class_constant_access_expression": self._lower_php_class_constant_access,
            "scoped_property_access_expression": self._lower_php_scoped_property_access,
            "yield_expression": self._lower_php_yield,
            "reference_assignment_expression": self._lower_php_reference_assignment,
            "heredoc": self._lower_const_literal,
            "nowdoc": self._lower_const_literal,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "expression_statement": self._lower_expression_statement,
            "return_statement": self._lower_php_return,
            "echo_statement": self._lower_php_echo,
            "if_statement": self._lower_php_if,
            "while_statement": self._lower_while,
            "for_statement": self._lower_c_style_for,
            "foreach_statement": self._lower_php_foreach,
            "function_definition": self._lower_php_func_def,
            "method_declaration": self._lower_php_method_decl,
            "class_declaration": self._lower_php_class,
            "throw_expression": self._lower_php_throw,
            "compound_statement": self._lower_php_compound,
            "program": self._lower_block,
            "break_statement": self._lower_break,
            "continue_statement": self._lower_continue,
            "try_statement": self._lower_try,
            "switch_statement": self._lower_php_switch,
            "do_statement": self._lower_php_do,
            "namespace_definition": self._lower_php_namespace,
            "interface_declaration": self._lower_php_interface,
            "trait_declaration": self._lower_php_trait,
            "function_static_declaration": self._lower_php_function_static,
            "enum_declaration": self._lower_php_enum,
            "named_label_statement": self._lower_php_named_label,
            "goto_statement": self._lower_php_goto,
            "property_declaration": self._lower_php_property_declaration,
            "use_declaration": self._lower_php_use_declaration,
            "namespace_use_declaration": self._lower_php_namespace_use_declaration,
            "enum_case": self._lower_php_enum_case,
        }

    # -- PHP: compound statement (block with braces) ---------------------------

    def _lower_php_compound(self, node):
        for child in node.children:
            if child.type not in ("{", "}") and child.is_named:
                self._lower_stmt(child)

    # -- PHP: variable ($x) ---------------------------------------------------

    def _lower_php_variable(self, node) -> str:
        var_name = self._node_text(node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_VAR,
            result_reg=reg,
            operands=[var_name],
            node=node,
        )
        return reg

    # -- PHP: function call expression -----------------------------------------

    def _lower_php_func_call(self, node) -> str:
        func_node = node.child_by_field_name("function")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args_unwrap(args_node) if args_node else []

        if func_node and func_node.type in ("name", "qualified_name"):
            func_name = self._node_text(func_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=reg,
                operands=[func_name] + arg_regs,
                node=node,
            )
            return reg

        # Dynamic call target
        target_reg = self._lower_expr(func_node) if func_node else self._fresh_reg()
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            node=node,
        )
        return reg

    # -- PHP: method call expression ($obj->method(...)) -----------------------

    def _lower_php_method_call(self, node) -> str:
        obj_node = node.child_by_field_name("object")
        name_node = node.child_by_field_name("name")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args_unwrap(args_node) if args_node else []

        obj_reg = self._lower_expr(obj_node) if obj_node else self._fresh_reg()
        method_name = self._node_text(name_node) if name_node else "unknown"
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_METHOD,
            result_reg=reg,
            operands=[obj_reg, method_name] + arg_regs,
            node=node,
        )
        return reg

    # -- PHP: member access ($obj->field) --------------------------------------

    def _lower_php_member_access(self, node) -> str:
        obj_node = node.child_by_field_name("object")
        name_node = node.child_by_field_name("name")
        if obj_node is None or name_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(obj_node)
        field_name = self._node_text(name_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, field_name],
            node=node,
        )
        return reg

    # -- PHP: subscript ($arr[idx]) --------------------------------------------

    def _lower_php_subscript(self, node) -> str:
        children = [c for c in node.children if c.is_named]
        if len(children) < 2:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(children[0])
        idx_reg = self._lower_expr(children[1])
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_INDEX,
            result_reg=reg,
            operands=[obj_reg, idx_reg],
            node=node,
        )
        return reg

    # -- PHP: assignment expression --------------------------------------------

    def _lower_php_assignment_expr(self, node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        val_reg = self._lower_expr(right)
        self._lower_store_target(left, val_reg, node)
        return val_reg

    # -- PHP: augmented assignment expression ----------------------------------

    def _lower_php_augmented_assignment_expr(self, node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        op_node = [c for c in node.children if c.type not in (left.type, right.type)][0]
        op_text = self._node_text(op_node).rstrip("=")
        lhs_reg = self._lower_expr(left)
        rhs_reg = self._lower_expr(right)
        result = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=result,
            operands=[op_text, lhs_reg, rhs_reg],
            node=node,
        )
        self._lower_store_target(left, result, node)
        return result

    # -- PHP: return statement -------------------------------------------------

    def _lower_php_return(self, node):
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
            node=node,
        )

    # -- PHP: echo statement ---------------------------------------------------

    def _lower_php_echo(self, node):
        children = [c for c in node.children if c.type != "echo" and c.is_named]
        arg_regs = [self._lower_expr(c) for c in children]
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["echo"] + arg_regs,
            node=node,
        )

    # -- PHP: if statement -----------------------------------------------------

    def _lower_php_if(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("if_true")
        end_label = self._fresh_label("if_end")

        # Collect else_clause children
        else_clauses = [
            c for c in node.children if c.type in ("else_clause", "else_if_clause")
        ]

        if else_clauses:
            false_label = self._fresh_label("if_false")
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
            self._lower_php_compound(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if else_clauses:
            self._emit(Opcode.LABEL, label=false_label)
            for clause in else_clauses:
                self._lower_php_else_clause(clause, end_label)
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_php_else_clause(self, node, end_label: str):
        if node.type == "else_if_clause":
            cond_node = node.child_by_field_name("condition")
            body_node = node.child_by_field_name("body")
            cond_reg = self._lower_expr(cond_node)
            true_label = self._fresh_label("elseif_true")
            false_label = self._fresh_label("elseif_false")

            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{true_label},{false_label}",
                node=node,
            )

            self._emit(Opcode.LABEL, label=true_label)
            if body_node:
                self._lower_php_compound(body_node)
            self._emit(Opcode.BRANCH, label=end_label)

            self._emit(Opcode.LABEL, label=false_label)
        elif node.type == "else_clause":
            for child in node.children:
                if child.type not in ("else", "{", "}") and child.is_named:
                    if child.type == "compound_statement":
                        self._lower_php_compound(child)
                    else:
                        self._lower_stmt(child)

    # -- PHP: foreach statement ------------------------------------------------

    def _lower_php_foreach(self, node):
        """Lower foreach ($arr as $v) or foreach ($arr as $k => $v) as index-based loop."""
        body_node = node.child_by_field_name("body")

        # Extract iterable, value var, and optional key var from children
        named_children = [c for c in node.children if c.is_named]
        # named_children[0] = iterable ($arr)
        # named_children[1] = value var ($v) or pair ($k => $v)
        # named_children[2] = body (compound_statement)
        iterable_node = named_children[0] if named_children else None
        binding_node = named_children[1] if len(named_children) > 1 else None

        iter_reg = (
            self._lower_expr(iterable_node) if iterable_node else self._fresh_reg()
        )

        key_var = None
        value_var = None
        if binding_node and binding_node.type == "pair":
            # $k => $v
            pair_named = [c for c in binding_node.children if c.is_named]
            key_var = self._node_text(pair_named[0]) if pair_named else None
            value_var = self._node_text(pair_named[1]) if len(pair_named) > 1 else None
        elif binding_node:
            value_var = self._node_text(binding_node)

        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

        loop_label = self._fresh_label("foreach_cond")
        body_label = self._fresh_label("foreach_body")
        end_label = self._fresh_label("foreach_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
        )

        self._emit(Opcode.LABEL, label=body_label)
        # Store key variable (index) if present
        if key_var:
            self._emit(Opcode.STORE_VAR, operands=[key_var, idx_reg])
        # Store value variable (element at index)
        if value_var:
            elem_reg = self._fresh_reg()
            self._emit(
                Opcode.LOAD_INDEX,
                result_reg=elem_reg,
                operands=[iter_reg, idx_reg],
            )
            self._emit(Opcode.STORE_VAR, operands=[value_var, elem_reg])

        update_label = self._fresh_label("foreach_update")
        self._push_loop(update_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()

        self._emit(Opcode.LABEL, label=update_label)
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
        self._emit(Opcode.STORE_VAR, operands=["__foreach_idx", new_idx])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- PHP: function definition ----------------------------------------------

    def _lower_php_func_def(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = self._node_text(name_node) if name_node else "__anon"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_php_params(params_node)

        if body_node:
            self._lower_php_compound(body_node)

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

    # -- PHP: method declaration -----------------------------------------------

    def _lower_php_method_decl(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = self._node_text(name_node) if name_node else "__anon"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_php_params(params_node)

        if body_node:
            self._lower_php_compound(body_node)

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

    def _lower_php_params(self, params_node):
        for child in params_node.children:
            if child.type in ("(", ")", ","):
                continue
            if child.type == "simple_parameter":
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
            elif child.type == "variadic_parameter":
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
            elif child.type == "variable_name":
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

    # -- PHP: class declaration ------------------------------------------------

    def _lower_php_class(self, node):
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        class_name = self._node_text(name_node) if name_node else "__anon_class"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=class_label)

        if body_node:
            self._lower_php_class_body(body_node)

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

    def _lower_php_class_body(self, node):
        """Lower declaration_list body of a PHP class."""
        for child in node.children:
            if child.type == "method_declaration":
                self._lower_php_method_decl(child)
            elif child.type == "property_declaration":
                self._lower_php_property_declaration(child)
            elif child.is_named and child.type not in (
                "visibility_modifier",
                "static_modifier",
                "abstract_modifier",
                "final_modifier",
                "{",
                "}",
            ):
                self._lower_stmt(child)

    def _lower_php_property_decl(self, node):
        for child in node.children:
            if child.type == "property_element":
                name_node = next(
                    (c for c in child.children if c.type == "variable_name"), None
                )
                value_node = next(
                    (
                        c
                        for c in child.children
                        if c.is_named and c.type != "variable_name"
                    ),
                    None,
                )
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

    # -- PHP: store target with variable_name ----------------------------------

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type in ("variable_name", "name"):
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                node=parent_node,
            )
        elif target.type == "member_access_expression":
            obj_node = target.child_by_field_name("object")
            name_node = target.child_by_field_name("name")
            if obj_node and name_node:
                obj_reg = self._lower_expr(obj_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(name_node), val_reg],
                    node=parent_node,
                )
        elif target.type == "subscript_expression":
            children = [c for c in target.children if c.is_named]
            if len(children) >= 2:
                obj_reg = self._lower_expr(children[0])
                idx_reg = self._lower_expr(children[1])
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

    # -- PHP: try/catch/finally ------------------------------------------------

    def _lower_try(self, node):
        body_node = node.child_by_field_name("body")
        catch_clauses = []
        finally_node = None
        for child in node.children:
            if child.type == "catch_clause":
                # PHP catch_clause: type(s) and variable_name
                type_node = next(
                    (
                        c
                        for c in child.children
                        if c.type in ("named_type", "name", "qualified_name")
                    ),
                    None,
                )
                var_node = next(
                    (c for c in child.children if c.type == "variable_name"),
                    None,
                )
                exc_type = self._node_text(type_node) if type_node else None
                exc_var = self._node_text(var_node) if var_node else None
                catch_body = child.child_by_field_name("body") or next(
                    (c for c in child.children if c.type == "compound_statement"),
                    None,
                )
                catch_clauses.append(
                    {"body": catch_body, "variable": exc_var, "type": exc_type}
                )
            elif child.type == "finally_clause":
                finally_node = next(
                    (c for c in child.children if c.type == "compound_statement"),
                    None,
                )
        self._lower_try_catch(node, body_node, catch_clauses, finally_node)

    # -- PHP: throw expression -------------------------------------------------

    def _lower_php_throw(self, node):
        self._lower_raise_or_throw(node, keyword="throw")

    def _lower_php_throw_expr(self, node) -> str:
        """Lower throw_expression when it appears in expression context."""
        self._lower_raise_or_throw(node, keyword="throw")
        reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=reg,
            operands=[self.NONE_LITERAL],
        )
        return reg

    # -- PHP: object creation (new ClassName(...)) -----------------------------

    def _lower_php_object_creation(self, node) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            name_node = next((c for c in node.children if c.type == "name"), None)
        args_node = next((c for c in node.children if c.type == "arguments"), None)
        arg_regs = self._extract_call_args_unwrap(args_node) if args_node else []
        type_name = self._node_text(name_node) if name_node else "Object"
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[type_name] + arg_regs,
            node=node,
        )
        return reg

    # -- PHP: array creation ---------------------------------------------------

    def _lower_php_array(self, node) -> str:
        """Lower array_creation_expression: array(1, 2) or [1, 2] or ['k' => 'v'].

        Value-only elements: NEW_ARRAY + STORE_INDEX per element.
        Key-value elements: NEW_OBJECT + STORE_INDEX with key.
        """
        elements = [c for c in node.children if c.type == "array_element_initializer"]

        # Determine if associative (any element has =>)
        is_associative = any(
            any(self._node_text(sub) == "=>" for sub in elem.children)
            for elem in elements
        )

        if is_associative:
            obj_reg = self._fresh_reg()
            self._emit(
                Opcode.NEW_OBJECT,
                result_reg=obj_reg,
                operands=["array"],
                node=node,
            )
            for elem in elements:
                named = [c for c in elem.children if c.is_named]
                if len(named) >= 2:
                    key_reg = self._lower_expr(named[0])
                    val_reg = self._lower_expr(named[1])
                    self._emit(
                        Opcode.STORE_INDEX,
                        operands=[obj_reg, key_reg, val_reg],
                    )
                elif named:
                    idx_reg = self._fresh_reg()
                    self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
                    val_reg = self._lower_expr(named[0])
                    self._emit(
                        Opcode.STORE_INDEX,
                        operands=[obj_reg, idx_reg, val_reg],
                    )
            return obj_reg

        # Value-only: indexed array
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elements))])
        arr_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["array", size_reg],
            node=node,
        )
        for i, elem in enumerate(elements):
            named = [c for c in elem.children if c.is_named]
            val_reg = self._lower_expr(named[0]) if named else self._fresh_reg()
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    # -- PHP: cast expression --------------------------------------------------

    def _lower_php_cast(self, node) -> str:
        children = [c for c in node.children if c.is_named]
        if children:
            return self._lower_expr(children[-1])
        return self._lower_const_literal(node)

    # -- PHP: ternary / conditional expression ---------------------------------

    def _lower_php_ternary(self, node) -> str:
        cond_node = node.child_by_field_name("condition")
        true_node = node.child_by_field_name("body")
        false_node = node.child_by_field_name("alternative")

        if cond_node is None:
            return self._lower_const_literal(node)

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
        true_reg = self._lower_expr(true_node) if true_node else cond_reg
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

    # -- PHP: match expression -------------------------------------------------

    def _lower_php_match_expression(self, node) -> str:
        """Lower match(subject) { pattern => expr, default => expr } as if/else chain."""
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

        subject_reg = self._lower_expr(cond_node) if cond_node else self._fresh_reg()
        end_label = self._fresh_label("match_end")
        result_var = f"__match_{self._label_counter}"

        arms = (
            [c for c in body_node.children if c.type == "match_conditional_expression"]
            if body_node
            else []
        )
        default_arm = (
            next(
                (c for c in body_node.children if c.type == "match_default_expression"),
                None,
            )
            if body_node
            else None
        )

        for arm in arms:
            cond_list = arm.child_by_field_name("conditional_expressions")
            return_expr = arm.child_by_field_name("return_expression")

            arm_label = self._fresh_label("match_arm")
            next_label = self._fresh_label("match_next")

            if cond_list:
                patterns = [c for c in cond_list.children if c.is_named]
                if patterns:
                    pattern_reg = self._lower_expr(patterns[0])
                    cmp_reg = self._fresh_reg()
                    self._emit(
                        Opcode.BINOP,
                        result_reg=cmp_reg,
                        operands=["===", subject_reg, pattern_reg],
                        node=arm,
                    )
                    self._emit(
                        Opcode.BRANCH_IF,
                        operands=[cmp_reg],
                        label=f"{arm_label},{next_label}",
                    )
                else:
                    self._emit(Opcode.BRANCH, label=arm_label)
            else:
                self._emit(Opcode.BRANCH, label=arm_label)

            self._emit(Opcode.LABEL, label=arm_label)
            if return_expr:
                val_reg = self._lower_expr(return_expr)
                self._emit(Opcode.STORE_VAR, operands=[result_var, val_reg])
            self._emit(Opcode.BRANCH, label=end_label)
            self._emit(Opcode.LABEL, label=next_label)

        if default_arm:
            default_body = default_arm.child_by_field_name("return_expression")
            if default_body:
                val_reg = self._lower_expr(default_body)
                self._emit(Opcode.STORE_VAR, operands=[result_var, val_reg])
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)
        result_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=result_reg, operands=[result_var])
        return result_reg

    # -- PHP: arrow function (fn($x) => expr) ---------------------------------

    def _lower_php_arrow_function(self, node) -> str:
        """Lower fn($x) => expr as a function definition with implicit return."""
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = f"__arrow_{self._label_counter}"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_php_params(params_node)

        if body_node:
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

    # -- PHP: scoped call expression (ClassName::method(args)) -----------------

    def _lower_php_scoped_call(self, node) -> str:
        """Lower ClassName::method(args) as CALL_FUNCTION with qualified name."""
        scope_node = node.child_by_field_name("scope")
        name_node = node.child_by_field_name("name")
        args_node = node.child_by_field_name("arguments")

        scope_name = self._node_text(scope_node) if scope_node else "Unknown"
        method_name = self._node_text(name_node) if name_node else "unknown"
        qualified_name = f"{scope_name}::{method_name}"

        arg_regs = self._extract_call_args_unwrap(args_node) if args_node else []

        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[qualified_name] + arg_regs,
            node=node,
        )
        return reg

    # -- PHP: switch statement -------------------------------------------------

    def _lower_php_switch(self, node):
        """Lower switch(expr) { case ... } as an if/else chain."""
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

        subject_reg = self._lower_expr(cond_node) if cond_node else self._fresh_reg()
        end_label = self._fresh_label("switch_end")

        self._break_target_stack.append(end_label)

        cases = (
            [
                c
                for c in body_node.children
                if c.type in ("case_statement", "default_statement")
            ]
            if body_node
            else []
        )

        for case in cases:
            is_default = case.type == "default_statement"
            value_node = case.child_by_field_name("value")
            body_stmts = [c for c in case.children if c.is_named and c != value_node]

            arm_label = self._fresh_label("case_arm")
            next_label = self._fresh_label("case_next")

            if not is_default and value_node:
                case_reg = self._lower_expr(value_node)
                cmp_reg = self._fresh_reg()
                self._emit(
                    Opcode.BINOP,
                    result_reg=cmp_reg,
                    operands=["==", subject_reg, case_reg],
                    node=case,
                )
                self._emit(
                    Opcode.BRANCH_IF,
                    operands=[cmp_reg],
                    label=f"{arm_label},{next_label}",
                )
            else:
                self._emit(Opcode.BRANCH, label=arm_label)

            self._emit(Opcode.LABEL, label=arm_label)
            for stmt in body_stmts:
                self._lower_stmt(stmt)
            self._emit(Opcode.BRANCH, label=end_label)
            self._emit(Opcode.LABEL, label=next_label)

        self._break_target_stack.pop()
        self._emit(Opcode.LABEL, label=end_label)

    # -- PHP: do-while statement -----------------------------------------------

    def _lower_php_do(self, node):
        """Lower do { body } while (condition);"""
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
        if cond_node:
            cond_reg = self._lower_expr(cond_node)
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{body_label},{end_label}",
                node=node,
            )
        else:
            self._emit(Opcode.BRANCH, label=body_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- PHP: namespace definition ---------------------------------------------

    def _lower_php_namespace(self, node):
        """Lower namespace definition: just lower the body compound_statement."""
        body_node = next(
            (c for c in node.children if c.type == "compound_statement"), None
        )
        if body_node:
            self._lower_php_compound(body_node)

    # -- PHP: interface declaration --------------------------------------------

    def _lower_php_interface(self, node):
        """Lower interface_declaration like a class: BRANCH, LABEL, body, end."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        iface_name = self._node_text(name_node) if name_node else "__anon_interface"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{iface_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{iface_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=class_label)

        if body_node:
            self._lower_php_class_body(body_node)

        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=cls_reg,
            operands=[
                constants.CLASS_REF_TEMPLATE.format(name=iface_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[iface_name, cls_reg])

    # -- PHP: trait declaration ------------------------------------------------

    def _lower_php_trait(self, node):
        """Lower trait_declaration like a class: BRANCH, LABEL, body, end."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        trait_name = self._node_text(name_node) if name_node else "__anon_trait"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{trait_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{trait_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=class_label)

        if body_node:
            self._lower_php_class_body(body_node)

        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=cls_reg,
            operands=[
                constants.CLASS_REF_TEMPLATE.format(name=trait_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[trait_name, cls_reg])

    # -- PHP: function static declaration --------------------------------------

    def _lower_php_function_static(self, node):
        """Lower static $x = val; declarations inside functions."""
        for child in node.children:
            if child.type == "static_variable_declaration":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node and value_node:
                    val_reg = self._lower_expr(value_node)
                    self._emit(
                        Opcode.STORE_VAR,
                        operands=[self._node_text(name_node), val_reg],
                        node=child,
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
                        node=child,
                    )

    # -- PHP: enum declaration -------------------------------------------------

    def _lower_php_enum(self, node):
        """Lower enum_declaration like a class: BRANCH, LABEL, body, end."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        enum_name = self._node_text(name_node) if name_node else "__anon_enum"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{enum_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{enum_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=class_label)

        if body_node:
            self._lower_php_class_body(body_node)

        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=cls_reg,
            operands=[
                constants.CLASS_REF_TEMPLATE.format(name=enum_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[enum_name, cls_reg])

    # -- PHP: named label statement --------------------------------------------

    def _lower_php_named_label(self, node):
        """Lower name: as LABEL user_{name}."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            name_node = next((c for c in node.children if c.type == "name"), None)
        if name_node:
            label_name = f"user_{self._node_text(name_node)}"
            self._emit(
                Opcode.LABEL,
                label=label_name,
                node=node,
            )
        else:
            logger.warning(
                "named_label_statement without name: %s", self._node_text(node)[:40]
            )

    # -- PHP: goto statement ---------------------------------------------------

    def _lower_php_goto(self, node):
        """Lower goto name; as BRANCH user_{name}."""
        name_node = node.child_by_field_name("label")
        if not name_node:
            name_node = next((c for c in node.children if c.type == "name"), None)
        if name_node:
            target_label = f"user_{self._node_text(name_node)}"
            self._emit(
                Opcode.BRANCH,
                label=target_label,
                node=node,
            )
        else:
            logger.warning(
                "goto_statement without label: %s", self._node_text(node)[:40]
            )

    # -- PHP: anonymous function (closure) -------------------------------------

    def _lower_php_anonymous_function(self, node) -> str:
        """Lower function($x) use ($y) { body } as anonymous function."""
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = f"__anon_{self._label_counter}"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_php_params(params_node)

        if body_node:
            self._lower_php_compound(body_node)

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

    # -- PHP: nullsafe member access ($obj?->field) ----------------------------

    def _lower_php_nullsafe_member_access(self, node) -> str:
        """Lower $obj?->field as LOAD_FIELD (null-safety is semantic)."""
        obj_node = node.child_by_field_name("object")
        name_node = node.child_by_field_name("name")
        if obj_node is None or name_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(obj_node)
        field_name = self._node_text(name_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, field_name],
            node=node,
        )
        return reg

    # -- PHP: class constant access (ClassName::CONST) -------------------------

    def _lower_php_class_constant_access(self, node) -> str:
        """Lower ClassName::CONST as LOAD_FIELD on the class."""
        named = [c for c in node.children if c.is_named]
        if len(named) < 2:
            return self._lower_const_literal(node)
        class_reg = self._lower_expr(named[0])
        const_name = self._node_text(named[1])
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[class_reg, const_name],
            node=node,
        )
        return reg

    # -- PHP: scoped property access (ClassName::$prop) ------------------------

    def _lower_php_scoped_property_access(self, node) -> str:
        """Lower ClassName::$prop as LOAD_FIELD on the class."""
        named = [c for c in node.children if c.is_named]
        if len(named) < 2:
            return self._lower_const_literal(node)
        class_reg = self._lower_expr(named[0])
        prop_name = self._node_text(named[1])
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[class_reg, prop_name],
            node=node,
        )
        return reg

    # -- PHP: yield expression -------------------------------------------------

    def _lower_php_yield(self, node) -> str:
        """Lower yield $value as CALL_FUNCTION('yield', expr)."""
        named = [c for c in node.children if c.is_named]
        arg_regs = [self._lower_expr(c) for c in named]
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["yield"] + arg_regs,
            node=node,
        )
        return reg

    # -- PHP: reference assignment ($x = &$y) ----------------------------------

    def _lower_php_reference_assignment(self, node) -> str:
        """Lower $x = &$y as STORE_VAR (ignore reference semantics)."""
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        val_reg = self._lower_expr(right) if right else self._fresh_reg()
        if left:
            self._lower_store_target(left, val_reg, node)
        return val_reg

    # -- PHP: property declaration (class property) ----------------------------

    def _lower_php_property_declaration(self, node):
        """Lower property declarations inside classes, e.g. public $x = 10;"""
        for child in node.children:
            if child.type == "property_element":
                name_node = next(
                    (c for c in child.children if c.type == "variable_name"), None
                )
                value_node = next(
                    (
                        c
                        for c in child.children
                        if c.is_named and c.type != "variable_name"
                    ),
                    None,
                )
                if name_node and value_node:
                    val_reg = self._lower_expr(value_node)
                    self._emit(
                        Opcode.STORE_FIELD,
                        operands=["self", self._node_text(name_node), val_reg],
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
                        Opcode.STORE_FIELD,
                        operands=["self", self._node_text(name_node), val_reg],
                        node=node,
                    )

    # -- PHP: use declaration (trait use) --------------------------------------

    def _lower_php_use_declaration(self, node):
        """Lower `use SomeTrait;` inside classes — no-op / SYMBOLIC."""
        named = [c for c in node.children if c.is_named]
        trait_names = [self._node_text(c) for c in named]
        for trait_name in trait_names:
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=self._fresh_reg(),
                operands=[f"use_trait:{trait_name}"],
                node=node,
            )

    # -- PHP: namespace use declaration ----------------------------------------

    def _lower_php_namespace_use_declaration(self, node):
        """Lower `use Some\\Namespace;` — no-op."""
        pass

    # -- PHP: enum case --------------------------------------------------------

    def _lower_php_enum_case(self, node):
        """Lower enum case inside an enum_declaration as STORE_FIELD."""
        name_node = node.child_by_field_name("name")
        value_node = next(
            (c for c in node.children if c.is_named and c.type not in ("name",)),
            None,
        )
        if name_node:
            case_name = self._node_text(name_node)
            if value_node:
                val_reg = self._lower_expr(value_node)
            else:
                val_reg = self._fresh_reg()
                self._emit(
                    Opcode.CONST,
                    result_reg=val_reg,
                    operands=[case_name],
                )
            self._emit(
                Opcode.STORE_FIELD,
                operands=["self", case_name, val_reg],
                node=node,
            )
