"""KotlinFrontend -- tree-sitter Kotlin AST -> IR lowering."""

from __future__ import annotations

import logging
from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)


class KotlinFrontend(BaseFrontend):
    """Lowers a Kotlin tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "null"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    DEFAULT_RETURN_VALUE = "null"

    COMMENT_TYPES = frozenset({"comment", "multiline_comment"})
    NOISE_TYPES = frozenset({"\n"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "simple_identifier": self._lower_identifier,
            "integer_literal": self._lower_const_literal,
            "long_literal": self._lower_const_literal,
            "real_literal": self._lower_const_literal,
            "string_literal": self._lower_const_literal,
            "boolean_literal": self._lower_const_literal,
            "null_literal": self._lower_const_literal,
            "additive_expression": self._lower_binop,
            "multiplicative_expression": self._lower_binop,
            "comparison_expression": self._lower_binop,
            "equality_expression": self._lower_binop,
            "conjunction": self._lower_binop,
            "disjunction": self._lower_binop,
            "prefix_expression": self._lower_unop,
            "postfix_expression": self._lower_postfix_expr,
            "parenthesized_expression": self._lower_paren,
            "call_expression": self._lower_kotlin_call,
            "navigation_expression": self._lower_navigation_expr,
            "if_expression": self._lower_if_expr,
            "when_expression": self._lower_when_expr,
            "string_template": self._lower_const_literal,
            "collection_literal": self._lower_list_literal,
            "this_expression": self._lower_identifier,
            "super_expression": self._lower_identifier,
            "lambda_literal": self._lower_lambda_literal,
            "object_literal": self._lower_symbolic_node,
            "range_expression": self._lower_symbolic_node,
            "statements": self._lower_statements_expr,
            "jump_expression": self._lower_jump_as_expr,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "property_declaration": self._lower_property_decl,
            "assignment": self._lower_kotlin_assignment,
            "function_declaration": self._lower_function_decl,
            "class_declaration": self._lower_class_decl,
            "if_expression": self._lower_if_stmt,
            "while_statement": self._lower_while_stmt,
            "for_statement": self._lower_for_stmt,
            "jump_expression": self._lower_jump_expr,
            "expression_statement": self._lower_expression_statement,
            "source_file": self._lower_block,
            "statements": self._lower_block,
            "import_list": lambda _: None,
            "import_header": lambda _: None,
            "package_header": lambda _: None,
        }

    # -- property declaration ----------------------------------------------

    def _lower_property_decl(self, node):
        var_decl = next(
            (c for c in node.children if c.type == "variable_declaration"),
            None,
        )
        var_name = self._extract_property_name(var_decl) if var_decl else "__unknown"

        # Find the value expression: skip keywords, type annotations, '='
        value_node = self._find_property_value(node)

        if value_node:
            val_reg = self._lower_expr(value_node)
        else:
            val_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[self.NONE_LITERAL],
            )
        self._emit(
            Opcode.STORE_VAR,
            operands=[var_name, val_reg],
            source_location=self._source_loc(node),
        )

    def _extract_property_name(self, var_decl_node) -> str:
        """Extract name from variable_declaration -> simple_identifier."""
        id_node = next(
            (c for c in var_decl_node.children if c.type == "simple_identifier"),
            None,
        )
        return self._node_text(id_node) if id_node else "__unknown"

    def _find_property_value(self, node):
        """Find the value expression after '=' in a property_declaration."""
        found_eq = False
        for child in node.children:
            if found_eq and child.is_named:
                return child
            if self._node_text(child) == "=":
                found_eq = True
        return None

    # -- assignment --------------------------------------------------------

    def _lower_kotlin_assignment(self, node):
        left = node.child_by_field_name("directly_assignable_expression")
        right = node.child_by_field_name("expression")
        # Fallback: walk children
        if left is None or right is None:
            named_children = [c for c in node.children if c.is_named]
            if len(named_children) >= 2:
                left = named_children[0]
                right = named_children[-1]
            else:
                return
        val_reg = self._lower_expr(right)
        self._lower_store_target(left, val_reg, node)

    # -- function declaration ----------------------------------------------

    def _lower_function_decl(self, node):
        name_node = next(
            (c for c in node.children if c.type == "simple_identifier"),
            None,
        )
        params_node = next(
            (c for c in node.children if c.type == "function_value_parameters"),
            None,
        )
        body_node = next(
            (c for c in node.children if c.type == "function_body"),
            None,
        )

        func_name = self._node_text(name_node) if name_node else "__anon"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_kotlin_params(params_node)

        if body_node:
            self._lower_function_body(body_node)

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

    def _lower_kotlin_params(self, params_node):
        for child in params_node.children:
            if child.type == "parameter":
                id_node = next(
                    (c for c in child.children if c.type == "simple_identifier"),
                    None,
                )
                if id_node:
                    pname = self._node_text(id_node)
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

    def _lower_function_body(self, body_node):
        """Lower function_body which wraps the actual block or expression."""
        for child in body_node.children:
            if child.type in ("{", "}", "="):
                continue
            if child.is_named:
                self._lower_stmt(child)

    # -- class declaration -------------------------------------------------

    def _lower_class_decl(self, node):
        name_node = next(
            (c for c in node.children if c.type == "type_identifier"),
            None,
        )
        body_node = next(
            (c for c in node.children if c.type == "class_body"),
            None,
        )
        class_name = self._node_text(name_node) if name_node else "__anon_class"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
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

    # -- call expression ---------------------------------------------------

    def _lower_kotlin_call(self, node) -> str:
        """Lower call_expression: first child is callee, call_suffix has args."""
        named_children = [c for c in node.children if c.is_named]
        if not named_children:
            return self._lower_const_literal(node)

        callee_node = named_children[0]
        call_suffix = next(
            (c for c in node.children if c.type == "call_suffix"),
            None,
        )

        args_node = None
        if call_suffix:
            args_node = next(
                (c for c in call_suffix.children if c.type == "value_arguments"),
                None,
            )

        arg_regs = self._extract_kotlin_args(args_node)

        # Method call via navigation_expression
        if callee_node.type == "navigation_expression":
            nav_children = [c for c in callee_node.children if c.is_named]
            if len(nav_children) >= 2:
                obj_reg = self._lower_expr(nav_children[0])
                method_name = self._node_text(nav_children[-1])
                reg = self._fresh_reg()
                self._emit(
                    Opcode.CALL_METHOD,
                    result_reg=reg,
                    operands=[obj_reg, method_name] + arg_regs,
                    source_location=self._source_loc(node),
                )
                return reg

        # Plain function call
        if callee_node.type == "simple_identifier":
            func_name = self._node_text(callee_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=reg,
                operands=[func_name] + arg_regs,
                source_location=self._source_loc(node),
            )
            return reg

        # Dynamic call target
        target_reg = self._lower_expr(callee_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    def _extract_kotlin_args(self, args_node) -> list[str]:
        """Extract argument registers from value_arguments -> value_argument."""
        if args_node is None:
            return []
        regs = []
        for child in args_node.children:
            if child.type == "value_argument":
                inner = next((gc for gc in child.children if gc.is_named), None)
                if inner:
                    regs.append(self._lower_expr(inner))
            elif child.is_named and child.type not in ("(", ")", ","):
                regs.append(self._lower_expr(child))
        return regs

    # -- navigation expression (member access) -----------------------------

    def _lower_navigation_expr(self, node) -> str:
        named_children = [c for c in node.children if c.is_named]
        if len(named_children) < 2:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(named_children[0])
        field_name = self._node_text(named_children[-1])
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, field_name],
            source_location=self._source_loc(node),
        )
        return reg

    # -- if expression (value-producing) -----------------------------------

    def _lower_if_expr(self, node) -> str:
        """Lower Kotlin if as an expression (returns a value)."""
        children = [c for c in node.children if c.is_named]
        # Children layout: condition, consequence, [alternative]
        cond_node = children[0] if children else None
        body_node = children[1] if len(children) > 1 else None
        alt_node = children[2] if len(children) > 2 else None

        cond_reg = self._lower_expr(cond_node) if cond_node else self._fresh_reg()
        true_label = self._fresh_label("if_true")
        false_label = self._fresh_label("if_false")
        end_label = self._fresh_label("if_end")
        result_var = f"__if_result_{self._label_counter}"

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
        true_reg = self._lower_control_body(body_node)
        self._emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            false_reg = self._lower_control_body(alt_node)
            self._emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)
        reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
        return reg

    def _lower_if_stmt(self, node):
        """Lower if as a statement (discard result)."""
        self._lower_if_expr(node)

    def _lower_statements_expr(self, node) -> str:
        """Lower a ``statements`` node in expression context (last child is value)."""
        children = [c for c in node.children if c.is_named]
        if not children:
            reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
            return reg
        for child in children[:-1]:
            self._lower_stmt(child)
        return self._lower_expr(children[-1])

    def _lower_control_body(self, body_node) -> str:
        """Lower control_structure_body or block, returning last expr reg."""
        if body_node is None:
            reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
            return reg
        children = [
            c
            for c in body_node.children
            if c.type not in ("{", "}", ";")
            and c.type not in self.COMMENT_TYPES
            and c.type not in self.NOISE_TYPES
            and c.is_named
        ]
        if not children:
            reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
            return reg
        for child in children[:-1]:
            self._lower_stmt(child)
        return self._lower_expr(children[-1])

    # -- while statement ---------------------------------------------------

    def _lower_while_stmt(self, node):
        named_children = [c for c in node.children if c.is_named]
        # First named child is condition, last is body
        cond_node = named_children[0] if named_children else None
        body_node = (
            next(
                (c for c in node.children if c.type == "control_structure_body"),
                None,
            )
            if len(named_children) > 1
            else None
        )

        loop_label = self._fresh_label("while_cond")
        body_label = self._fresh_label("while_body")
        end_label = self._fresh_label("while_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._lower_expr(cond_node) if cond_node else self._fresh_reg()
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

    # -- for statement -----------------------------------------------------

    def _lower_for_stmt(self, node):
        named_children = [c for c in node.children if c.is_named]
        # Typically: variable_declaration, iterable expression, control_structure_body
        var_node = next(
            (
                c
                for c in named_children
                if c.type in ("variable_declaration", "simple_identifier")
            ),
            None,
        )
        body_node = next(
            (c for c in node.children if c.type == "control_structure_body"),
            None,
        )
        # Iterable is the expression between "in" and body
        iterable_node = self._find_for_iterable(node)

        var_name = self._extract_for_var_name(var_node) if var_node else "__for_var"
        iter_reg = (
            self._lower_expr(iterable_node) if iterable_node else self._fresh_reg()
        )

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

        if body_node:
            self._lower_block(body_node)

        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
        self._emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _find_for_iterable(self, node):
        """Find the iterable expression in a for statement (after 'in' keyword)."""
        found_in = False
        for child in node.children:
            if found_in and child.is_named and child.type != "control_structure_body":
                return child
            if self._node_text(child) == "in":
                found_in = True
        return None

    def _extract_for_var_name(self, var_node) -> str:
        if var_node.type == "simple_identifier":
            return self._node_text(var_node)
        id_node = next(
            (c for c in var_node.children if c.type == "simple_identifier"),
            None,
        )
        return self._node_text(id_node) if id_node else "__for_var"

    # -- when expression ---------------------------------------------------

    def _lower_when_expr(self, node) -> str:
        subject_node = next(
            (c for c in node.children if c.type == "when_subject"),
            None,
        )
        val_reg = self._fresh_reg()
        if subject_node:
            inner = next((c for c in subject_node.children if c.is_named), None)
            if inner:
                val_reg = self._lower_expr(inner)

        result_var = f"__when_result_{self._label_counter}"
        end_label = self._fresh_label("when_end")

        entries = [c for c in node.children if c.type == "when_entry"]
        for entry in entries:
            cond_node = next(
                (c for c in entry.children if c.type == "when_condition"),
                None,
            )
            body_children = [
                c
                for c in entry.children
                if c.type not in ("when_condition", "->", ",")
                and c.is_named
                and c.type != "control_structure_body"
            ]
            body_node = next(
                (c for c in entry.children if c.type == "control_structure_body"),
                None,
            )

            arm_label = self._fresh_label("when_arm")
            next_label = self._fresh_label("when_next")

            if cond_node:
                cond_inner = next((c for c in cond_node.children if c.is_named), None)
                if cond_inner:
                    pattern_reg = self._lower_expr(cond_inner)
                    eq_reg = self._fresh_reg()
                    self._emit(
                        Opcode.BINOP,
                        result_reg=eq_reg,
                        operands=["==", val_reg, pattern_reg],
                        source_location=self._source_loc(entry),
                    )
                    self._emit(
                        Opcode.BRANCH_IF,
                        operands=[eq_reg],
                        label=f"{arm_label},{next_label}",
                    )
                else:
                    # else branch
                    self._emit(Opcode.BRANCH, label=arm_label)
            else:
                # else branch (no condition)
                self._emit(Opcode.BRANCH, label=arm_label)

            self._emit(Opcode.LABEL, label=arm_label)
            if body_node:
                arm_result = self._lower_control_body(body_node)
            elif body_children:
                arm_result = self._lower_expr(body_children[0])
            else:
                arm_result = self._fresh_reg()
                self._emit(
                    Opcode.CONST,
                    result_reg=arm_result,
                    operands=[self.NONE_LITERAL],
                )
            self._emit(Opcode.STORE_VAR, operands=[result_var, arm_result])
            self._emit(Opcode.BRANCH, label=end_label)
            self._emit(Opcode.LABEL, label=next_label)

        self._emit(Opcode.LABEL, label=end_label)
        reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
        return reg

    # -- jump expression (return, break, continue, throw) ------------------

    def _lower_jump_as_expr(self, node) -> str:
        """Lower jump_expression in expression context (emit + return reg)."""
        self._lower_jump_expr(node)
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
        return reg

    def _lower_jump_expr(self, node):
        text = self._node_text(node)
        if text.startswith("return"):
            children = [c for c in node.children if c.type != "return"]
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
        elif text.startswith("throw"):
            self._lower_raise_or_throw(node, keyword="throw")
        else:
            reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=reg,
                operands=[f"jump:{text[:40]}"],
                source_location=self._source_loc(node),
            )

    # -- postfix expression ------------------------------------------------

    def _lower_postfix_expr(self, node) -> str:
        text = self._node_text(node)
        if "++" in text or "--" in text:
            return self._lower_update_expr(node)
        return self._lower_const_literal(node)

    # -- lambda literal ----------------------------------------------------

    def _lower_lambda_literal(self, node) -> str:
        func_name = f"__lambda_{self._label_counter}"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        # Lambda body children (skip braces)
        body_children = [
            c
            for c in node.children
            if c.type not in ("{", "}", "->")
            and c.is_named
            and c.type not in self.COMMENT_TYPES
        ]
        for child in body_children:
            self._lower_stmt(child)

        none_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[self.DEFAULT_RETURN_VALUE],
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

    # -- store target override for navigation_expression -------------------

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "simple_identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
        elif target.type == "navigation_expression":
            named_children = [c for c in target.children if c.is_named]
            if len(named_children) >= 2:
                obj_reg = self._lower_expr(named_children[0])
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[
                        obj_reg,
                        self._node_text(named_children[-1]),
                        val_reg,
                    ],
                    source_location=self._source_loc(parent_node),
                )
            else:
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[self._node_text(target), val_reg],
                    source_location=self._source_loc(parent_node),
                )
        elif target.type == "directly_assignable_expression":
            # Unwrap the inner node
            inner = next((c for c in target.children if c.is_named), None)
            if inner:
                self._lower_store_target(inner, val_reg, parent_node)
            else:
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[self._node_text(target), val_reg],
                    source_location=self._source_loc(parent_node),
                )
        else:
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )

    # -- generic symbolic fallback -----------------------------------------

    def _lower_symbolic_node(self, node) -> str:
        reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"{node.type}:{self._node_text(node)[:60]}"],
            source_location=self._source_loc(node),
        )
        return reg
