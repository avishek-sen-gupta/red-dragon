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

    COMMENT_TYPES = frozenset({"comment", "multiline_comment", "line_comment"})
    NOISE_TYPES = frozenset({"\n"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "simple_identifier": self._lower_identifier,
            "integer_literal": self._lower_const_literal,
            "long_literal": self._lower_const_literal,
            "real_literal": self._lower_const_literal,
            "character_literal": self._lower_const_literal,
            "string_literal": self._lower_kotlin_string_literal,
            "boolean_literal": self._lower_canonical_bool,
            "null_literal": self._lower_canonical_none,
            "additive_expression": self._lower_binop,
            "multiplicative_expression": self._lower_binop,
            "comparison_expression": self._lower_binop,
            "equality_expression": self._lower_binop,
            "conjunction_expression": self._lower_binop,
            "disjunction_expression": self._lower_binop,
            "prefix_expression": self._lower_unop,
            "postfix_expression": self._lower_postfix_expr,
            "parenthesized_expression": self._lower_paren,
            "call_expression": self._lower_kotlin_call,
            "navigation_expression": self._lower_navigation_expr,
            "if_expression": self._lower_if_expr,
            "when_expression": self._lower_when_expr,
            "collection_literal": self._lower_list_literal,
            "this_expression": self._lower_identifier,
            "super_expression": self._lower_identifier,
            "lambda_literal": self._lower_lambda_literal,
            "object_literal": self._lower_object_literal,
            "range_expression": self._lower_range_expr,
            "statements": self._lower_statements_expr,
            "jump_expression": self._lower_jump_as_expr,
            "assignment": self._lower_kotlin_assignment_expr,
            "check_expression": self._lower_check_expr,
            "try_expression": self._lower_try_expr,
            "hex_literal": self._lower_const_literal,
            "elvis_expression": self._lower_elvis_expr,
            "infix_expression": self._lower_infix_expr,
            "indexing_expression": self._lower_indexing_expr,
            "as_expression": self._lower_as_expr,
            "while_statement": self._lower_loop_as_expr,
            "for_statement": self._lower_loop_as_expr,
            "do_while_statement": self._lower_loop_as_expr,
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
            "source_file": self._lower_block,
            "statements": self._lower_block,
            "import_list": lambda _: None,
            "import_header": lambda _: None,
            "package_header": lambda _: None,
            "do_while_statement": self._lower_do_while_stmt,
            "object_declaration": self._lower_object_decl,
            "try_expression": self._lower_try_stmt,
            "type_alias": lambda _: None,
        }

    # -- property declaration ----------------------------------------------

    def _lower_property_decl(self, node):
        multi_var_decl = next(
            (c for c in node.children if c.type == "multi_variable_declaration"),
            None,
        )

        if multi_var_decl is not None:
            self._lower_multi_variable_destructure(multi_var_decl, node)
            return

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
            node=node,
        )

    def _lower_multi_variable_destructure(self, multi_var_node, parent_node):
        """Lower `val (a, b) = expr` — emit LOAD_INDEX + STORE_VAR per element."""
        value_node = self._find_property_value(parent_node)
        if value_node:
            val_reg = self._lower_expr(value_node)
        else:
            val_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[self.NONE_LITERAL],
            )

        var_decls = [
            c for c in multi_var_node.children if c.type == "variable_declaration"
        ]
        for i, var_decl in enumerate(var_decls):
            var_name = self._extract_property_name(var_decl)
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            elem_reg = self._fresh_reg()
            self._emit(
                Opcode.LOAD_INDEX,
                result_reg=elem_reg,
                operands=[val_reg, idx_reg],
                node=var_decl,
            )
            self._emit(
                Opcode.STORE_VAR,
                operands=[var_name, elem_reg],
                node=parent_node,
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

        self._emit(Opcode.BRANCH, label=end_label, node=node)
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
                        node=child,
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
            (c for c in node.children if c.type in ("class_body", "enum_class_body")),
            None,
        )
        class_name = self._node_text(name_node) if name_node else "__anon_class"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=class_label)
        if body_node:
            if body_node.type == "enum_class_body":
                self._lower_enum_class_body(body_node)
            else:
                self._lower_class_body_with_companions(body_node)
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

    def _lower_class_body_with_companions(self, node):
        """Lower class_body, handling companion_object children specially."""
        for child in node.children:
            if not child.is_named:
                continue
            if child.type == "companion_object":
                self._lower_companion_object(child)
            else:
                self._lower_stmt(child)

    # -- string interpolation ----------------------------------------------

    def _lower_kotlin_string_literal(self, node) -> str:
        """Lower Kotlin string literal, decomposing $var / ${expr} interpolation."""
        has_interpolation = any(
            c.type in ("interpolated_identifier", "interpolated_expression")
            for c in node.children
        )
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
            elif child.type == "interpolated_identifier":
                parts.append(self._lower_identifier(child))
            elif child.type == "interpolated_expression":
                named = [c for c in child.children if c.is_named]
                if named:
                    parts.append(self._lower_expr(named[0]))
            # skip punctuation: ", $, ${, }
        return self._lower_interpolated_string_parts(parts, node)

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
                    node=node,
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
                node=node,
            )
            return reg

        # Dynamic call target
        target_reg = self._lower_expr(callee_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            node=node,
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
            node=node,
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

    def _lower_loop_as_expr(self, node) -> str:
        """Lower while/for/do-while in expression position (returns unit)."""
        self._lower_stmt(node)
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
        return reg

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
            node=node,
        )

        self._emit(Opcode.LABEL, label=body_label)
        self._push_loop(loop_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()
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
                        node=entry,
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

    def _lower_kotlin_assignment_expr(self, node) -> str:
        """Lower assignment in expression context (e.g. last expr in block)."""
        self._lower_kotlin_assignment(node)
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
        return reg

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
                node=node,
            )
        elif text.startswith("throw"):
            self._lower_raise_or_throw(node, keyword="throw")
        elif text.startswith("break"):
            self._lower_break(node)
        elif text.startswith("continue"):
            self._lower_continue(node)
        else:
            logger.warning("Unrecognised jump expression: %s", text[:40])

    # -- postfix expression ------------------------------------------------

    def _lower_postfix_expr(self, node) -> str:
        text = self._node_text(node)
        if "++" in text or "--" in text:
            return self._lower_update_expr(node)
        if text.endswith("!!"):
            return self._lower_not_null_assertion(node)
        return self._lower_const_literal(node)

    def _lower_not_null_assertion(self, node) -> str:
        """Lower not-null assertion (expr!!) as UNOP('!!', expr)."""
        named_children = [c for c in node.children if c.is_named]
        if not named_children:
            return self._lower_const_literal(node)
        expr_reg = self._lower_expr(named_children[0])
        reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=reg,
            operands=["!!", expr_reg],
            node=node,
        )
        return reg

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
                node=parent_node,
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
                    node=parent_node,
                )
            else:
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[self._node_text(target), val_reg],
                    node=parent_node,
                )
        elif target.type == "indexing_expression":
            named_children = [c for c in target.children if c.is_named]
            if named_children:
                obj_reg = self._lower_expr(named_children[0])
                suffix_node = next(
                    (c for c in target.children if c.type == "indexing_suffix"),
                    None,
                )
                if suffix_node:
                    idx_children = [c for c in suffix_node.children if c.is_named]
                    idx_reg = (
                        self._lower_expr(idx_children[0])
                        if idx_children
                        else self._fresh_reg()
                    )
                else:
                    idx_reg = self._fresh_reg()
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
        elif target.type == "directly_assignable_expression":
            # Check for indexing: simple_identifier + indexing_suffix
            suffix_node = next(
                (c for c in target.children if c.type == "indexing_suffix"),
                None,
            )
            if suffix_node:
                id_node = next(
                    (c for c in target.children if c.type == "simple_identifier"),
                    None,
                )
                obj_reg = self._lower_expr(id_node) if id_node else self._fresh_reg()
                idx_children = [c for c in suffix_node.children if c.is_named]
                idx_reg = (
                    self._lower_expr(idx_children[0])
                    if idx_children
                    else self._fresh_reg()
                )
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                    node=parent_node,
                )
            else:
                # Unwrap the inner node
                inner = next((c for c in target.children if c.is_named), None)
                if inner:
                    self._lower_store_target(inner, val_reg, parent_node)
                else:
                    self._emit(
                        Opcode.STORE_VAR,
                        operands=[self._node_text(target), val_reg],
                        node=parent_node,
                    )
        else:
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                node=parent_node,
            )

    # -- try/catch/finally -------------------------------------------------

    def _extract_try_parts(self, node):
        """Extract body, catch clauses, and finally from a try_expression."""
        # First named child that's a statements block is the body
        body_node = next(
            (
                c
                for c in node.children
                if c.type in ("statements", "control_structure_body")
            ),
            None,
        )
        catch_clauses = []
        finally_node = None
        for child in node.children:
            if child.type == "catch_block":
                # catch_block children: "catch", "(", annotation*, simple_identifier (type), simple_identifier (var), ")", statements
                ids = [c for c in child.children if c.type == "simple_identifier"]
                exc_type = self._node_text(ids[0]) if ids else None
                exc_var = self._node_text(ids[1]) if len(ids) > 1 else None
                catch_body = next(
                    (
                        c
                        for c in child.children
                        if c.type in ("statements", "control_structure_body")
                    ),
                    None,
                )
                catch_clauses.append(
                    {"body": catch_body, "variable": exc_var, "type": exc_type}
                )
            elif child.type == "finally_block":
                finally_node = next(
                    (
                        c
                        for c in child.children
                        if c.type in ("statements", "control_structure_body")
                    ),
                    None,
                )
        return body_node, catch_clauses, finally_node

    def _lower_try_stmt(self, node):
        body_node, catch_clauses, finally_node = self._extract_try_parts(node)
        self._lower_try_catch(node, body_node, catch_clauses, finally_node)

    def _lower_try_expr(self, node) -> str:
        """Lower try_expression in expression context (returns a register)."""
        self._lower_try_stmt(node)
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
        return reg

    # -- check expression (is / !is) --------------------------------------

    def _lower_check_expr(self, node) -> str:
        """Lower check_expression (is/!is) as CALL_FUNCTION('is', expr, type_text)."""
        named_children = [c for c in node.children if c.is_named]
        if len(named_children) < 2:
            return self._lower_const_literal(node)
        expr_reg = self._lower_expr(named_children[0])
        type_text = self._node_text(named_children[-1])
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["is", expr_reg, type_text],
            node=node,
        )
        return reg

    # -- do-while statement ------------------------------------------------

    def _lower_do_while_stmt(self, node):
        """Lower do { body } while (cond) loop."""
        body_node = next(
            (c for c in node.children if c.type == "control_structure_body"),
            None,
        )
        # Condition is a named child that's not the body
        cond_node = next(
            (
                c
                for c in node.children
                if c.is_named and c.type != "control_structure_body"
            ),
            None,
        )

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
            node=node,
        )
        self._emit(Opcode.LABEL, label=end_label)

    # -- object declaration (singleton) ------------------------------------

    def _lower_object_decl(self, node):
        """Lower object declaration (Kotlin singleton) like a class."""
        name_node = next(
            (c for c in node.children if c.type == "type_identifier"),
            None,
        )
        body_node = next(
            (c for c in node.children if c.type == "class_body"),
            None,
        )
        obj_name = self._node_text(name_node) if name_node else "__anon_object"

        obj_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{obj_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{obj_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=obj_label)
        if body_node:
            self._lower_block(body_node)
        self._emit(Opcode.LABEL, label=end_label)

        inst_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=inst_reg,
            operands=[obj_name],
            node=node,
        )
        self._emit(Opcode.STORE_VAR, operands=[obj_name, inst_reg])

    # -- object literal (anonymous object expression) ------------------------

    def _lower_object_literal(self, node) -> str:
        """Lower `object : Type { ... }` as NEW_OBJECT + body lowering."""
        delegation = next(
            (c for c in node.children if c.type == "delegation_specifier"),
            None,
        )
        body_node = next(
            (c for c in node.children if c.type == "class_body"),
            None,
        )
        type_name = self._node_text(delegation) if delegation else "__anon_object"

        obj_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{type_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{type_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=obj_label)
        if body_node:
            self._lower_block(body_node)
        self._emit(Opcode.LABEL, label=end_label)

        inst_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=inst_reg,
            operands=[type_name],
            node=node,
        )
        return inst_reg

    # -- companion object --------------------------------------------------

    def _lower_companion_object(self, node):
        """Lower companion object by lowering its class_body child as a block."""
        body_node = next(
            (c for c in node.children if c.type == "class_body"),
            None,
        )
        if body_node:
            self._lower_block(body_node)

    # -- enum class body + enum entry --------------------------------------

    def _lower_enum_class_body(self, node):
        """Lower enum_class_body: create NEW_OBJECT + STORE_VAR for each entry."""
        for child in node.children:
            if child.type == "enum_entry":
                self._lower_enum_entry(child)
            elif child.is_named and child.type not in ("{", "}", ",", ";"):
                self._lower_stmt(child)

    def _lower_enum_entry(self, node):
        """Lower a single enum_entry as NEW_OBJECT('enum:Name') + STORE_VAR."""
        name_node = next(
            (c for c in node.children if c.type == "simple_identifier"),
            None,
        )
        entry_name = self._node_text(name_node) if name_node else "__unknown_enum"
        reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=reg,
            operands=[f"enum:{entry_name}"],
            node=node,
        )
        self._emit(Opcode.STORE_VAR, operands=[entry_name, reg])

    # -- elvis expression (?:) ---------------------------------------------

    def _lower_elvis_expr(self, node) -> str:
        """Lower `x ?: default` as BINOP('?:', left, right)."""
        named_children = [c for c in node.children if c.is_named]
        if len(named_children) < 2:
            return self._lower_const_literal(node)
        left_reg = self._lower_expr(named_children[0])
        right_reg = self._lower_expr(named_children[-1])
        reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=reg,
            operands=["?:", left_reg, right_reg],
            node=node,
        )
        return reg

    # -- infix expression --------------------------------------------------

    def _lower_infix_expr(self, node) -> str:
        """Lower `a to b`, `x until y` as CALL_FUNCTION(infix_name, left, right)."""
        named_children = [c for c in node.children if c.is_named]
        if len(named_children) < 3:
            return self._lower_const_literal(node)
        left_reg = self._lower_expr(named_children[0])
        func_name = self._node_text(named_children[1])
        right_reg = self._lower_expr(named_children[2])
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[func_name, left_reg, right_reg],
            node=node,
        )
        return reg

    # -- indexing expression -----------------------------------------------

    def _lower_indexing_expr(self, node) -> str:
        """Lower `collection[index]` as LOAD_INDEX."""
        named_children = [c for c in node.children if c.is_named]
        if not named_children:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(named_children[0])
        # The index is inside indexing_suffix
        suffix_node = next(
            (c for c in node.children if c.type == "indexing_suffix"),
            None,
        )
        if suffix_node is None:
            return obj_reg
        idx_children = [c for c in suffix_node.children if c.is_named]
        if not idx_children:
            return obj_reg
        idx_reg = self._lower_expr(idx_children[0])
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_INDEX,
            result_reg=reg,
            operands=[obj_reg, idx_reg],
            node=node,
        )
        return reg

    # -- as expression (type cast) -----------------------------------------

    def _lower_as_expr(self, node) -> str:
        """Lower `expr as Type` as CALL_FUNCTION('as', expr, type_name)."""
        named_children = [c for c in node.children if c.is_named]
        if len(named_children) < 2:
            return self._lower_const_literal(node)
        expr_reg = self._lower_expr(named_children[0])
        type_name = self._node_text(named_children[-1])
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["as", expr_reg, type_name],
            node=node,
        )
        return reg

    # -- range expression --------------------------------------------------

    def _lower_range_expr(self, node) -> str:
        """Lower `1..10` as CALL_FUNCTION("range", start, end)."""
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

    # -- generic symbolic fallback -----------------------------------------

    def _lower_symbolic_node(self, node) -> str:
        reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"{node.type}:{self._node_text(node)[:60]}"],
            node=node,
        )
        return reg
