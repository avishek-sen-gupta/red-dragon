"""RustFrontend -- tree-sitter Rust AST -> IR lowering."""

from __future__ import annotations

import logging
from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)


class RustFrontend(BaseFrontend):
    """Lowers a Rust tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "()"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    DEFAULT_RETURN_VALUE = "()"

    ATTRIBUTE_NODE_TYPE = "field_expression"
    ATTR_OBJECT_FIELD = "value"
    ATTR_ATTRIBUTE_FIELD = "field"

    CALL_FUNCTION_FIELD = "function"
    CALL_ARGUMENTS_FIELD = "arguments"

    ASSIGN_LEFT_FIELD = "left"
    ASSIGN_RIGHT_FIELD = "right"

    COMMENT_TYPES = frozenset({"comment", "line_comment", "block_comment"})
    NOISE_TYPES = frozenset({"\n"})

    BLOCK_NODE_TYPES = frozenset({"block"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "integer_literal": self._lower_const_literal,
            "float_literal": self._lower_const_literal,
            "string_literal": self._lower_const_literal,
            "char_literal": self._lower_const_literal,
            "boolean_literal": self._lower_const_literal,
            "true": self._lower_const_literal,
            "false": self._lower_const_literal,
            "binary_expression": self._lower_binop,
            "unary_expression": self._lower_unop,
            "parenthesized_expression": self._lower_paren,
            "call_expression": self._lower_call,
            "field_expression": self._lower_field_expr,
            "reference_expression": self._lower_reference_expr,
            "dereference_expression": self._lower_deref_expr,
            "assignment_expression": self._lower_assignment_expr,
            "compound_assignment_expr": self._lower_compound_assignment_expr,
            "if_expression": self._lower_if_expr,
            "match_expression": self._lower_match_expr,
            "closure_expression": self._lower_closure_expr,
            "struct_expression": self._lower_struct_instantiation,
            "block": self._lower_block_expr,
            "return_expression": self._lower_return_expr,
            "macro_invocation": self._lower_macro_invocation,
            "type_identifier": self._lower_identifier,
            "self": self._lower_identifier,
            "array_expression": self._lower_list_literal,
            "index_expression": self._lower_index_expr,
            "tuple_expression": self._lower_tuple_expr,
            "else_clause": self._lower_else_clause,
            "expression_statement": self._lower_expr_stmt_as_expr,
            "range_expression": self._lower_symbolic_node,
            "try_expression": self._lower_try_expr,
            "await_expression": self._lower_await_expr,
            "async_block": self._lower_block_expr,
            "unsafe_block": self._lower_block_expr,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "expression_statement": self._lower_expression_statement,
            "let_declaration": self._lower_let_decl,
            "function_item": self._lower_function_def,
            "struct_item": self._lower_struct_def,
            "impl_item": self._lower_impl_item,
            "if_expression": self._lower_if_stmt,
            "while_expression": self._lower_while,
            "loop_expression": self._lower_loop,
            "for_expression": self._lower_for,
            "return_expression": self._lower_return_stmt,
            "block": self._lower_block,
            "source_file": self._lower_block,
            "use_declaration": lambda _: None,
            "attribute_item": lambda _: None,
            "macro_invocation": self._lower_macro_stmt,
            "break_expression": self._lower_break,
            "continue_expression": self._lower_continue,
            "trait_item": self._lower_trait_item,
            "enum_item": self._lower_enum_item,
            "const_item": self._lower_const_item,
            "static_item": self._lower_static_item,
            "type_item": self._lower_type_item,
            "mod_item": self._lower_mod_item,
            "extern_crate_declaration": lambda _: None,
        }

    # -- let declaration ---------------------------------------------------

    def _lower_let_decl(self, node):
        pattern_node = node.child_by_field_name("pattern")
        value_node = node.child_by_field_name("value")
        var_name = self._extract_let_pattern_name(pattern_node)
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

    def _extract_let_pattern_name(self, pattern_node) -> str:
        """Extract identifier from let pattern, handling `mut` wrapper."""
        if pattern_node is None:
            return "__unknown"
        if pattern_node.type == "identifier":
            return self._node_text(pattern_node)
        if pattern_node.type == "mutable_specifier":
            id_child = next(
                (c for c in pattern_node.children if c.type == "identifier"),
                None,
            )
            return self._node_text(id_child) if id_child else "__unknown"
        # mut pattern wrapping: children may contain mutable_specifier + identifier
        id_child = next(
            (c for c in pattern_node.children if c.type == "identifier"),
            None,
        )
        if id_child:
            return self._node_text(id_child)
        return self._node_text(pattern_node)

    # -- assignment expression ---------------------------------------------

    def _lower_assignment_expr(self, node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        val_reg = self._lower_expr(right)
        self._lower_store_target(left, val_reg, node)
        return val_reg

    # -- compound assignment -----------------------------------------------

    def _lower_compound_assignment_expr(self, node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        op_node = node.child_by_field_name("operator")
        op_text = self._node_text(op_node).rstrip("=") if op_node else "+"
        lhs_reg = self._lower_expr(left)
        rhs_reg = self._lower_expr(right)
        result = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=result,
            operands=[op_text, lhs_reg, rhs_reg],
            source_location=self._source_loc(node),
        )
        self._lower_store_target(left, result, node)
        return result

    # -- field expression --------------------------------------------------

    def _lower_field_expr(self, node) -> str:
        value_node = node.child_by_field_name("value")
        field_node = node.child_by_field_name("field")
        if value_node is None or field_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(value_node)
        field_name = self._node_text(field_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, field_name],
            source_location=self._source_loc(node),
        )
        return reg

    # -- reference / dereference -------------------------------------------

    def _lower_reference_expr(self, node) -> str:
        children = [c for c in node.children if c.type not in ("&", "mut")]
        inner = children[0] if children else node
        inner_reg = self._lower_expr(inner)
        reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=reg,
            operands=["&", inner_reg],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_deref_expr(self, node) -> str:
        children = [c for c in node.children if c.type != "*"]
        inner = children[0] if children else node
        inner_reg = self._lower_expr(inner)
        reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=reg,
            operands=["*", inner_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # -- if expression (value-producing) -----------------------------------

    def _lower_if_expr(self, node) -> str:
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        cond_reg = self._lower_expr(cond_node)
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
        true_reg = self._lower_block_expr(body_node)
        self._emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            false_reg = self._lower_expr(alt_node)
            self._emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)
        reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
        return reg

    def _lower_if_stmt(self, node):
        """Lower if as a statement (discard result)."""
        self._lower_if_expr(node)

    def _lower_expr_stmt_as_expr(self, node) -> str:
        """Unwrap expression_statement to its inner expression."""
        named = [c for c in node.children if c.is_named]
        if named:
            return self._lower_expr(named[0])
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
        return reg

    def _lower_else_clause(self, node) -> str:
        """Lower else_clause by extracting its inner block or expression."""
        named = [c for c in node.children if c.is_named]
        if named:
            return self._lower_expr(named[0])
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
        return reg

    # -- while / loop / for ------------------------------------------------

    def _lower_loop(self, node):
        """Lower `loop { ... }` -- infinite loop."""
        body_node = node.child_by_field_name("body")
        loop_label = self._fresh_label("loop_top")
        end_label = self._fresh_label("loop_end")

        self._emit(Opcode.LABEL, label=loop_label)
        self._push_loop(loop_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()
        self._emit(Opcode.BRANCH, label=loop_label)
        self._emit(Opcode.LABEL, label=end_label)

    def _lower_for(self, node):
        """Lower `for pattern in value { body }`."""
        pattern_node = node.child_by_field_name("pattern")
        value_node = node.child_by_field_name("value")
        body_node = node.child_by_field_name("body")

        var_name = self._node_text(pattern_node) if pattern_node else "__for_var"
        iter_reg = self._lower_expr(value_node) if value_node else self._fresh_reg()

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

    # -- return expression -------------------------------------------------

    def _lower_return_expr(self, node) -> str:
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
        return val_reg

    def _lower_return_stmt(self, node):
        self._lower_return_expr(node)

    # -- match expression --------------------------------------------------

    def _lower_match_expr(self, node) -> str:
        value_node = node.child_by_field_name("value")
        body_node = node.child_by_field_name("body")

        val_reg = self._lower_expr(value_node) if value_node else self._fresh_reg()
        result_var = f"__match_result_{self._label_counter}"
        end_label = self._fresh_label("match_end")

        arms = (
            [c for c in body_node.children if c.type == "match_arm"]
            if body_node
            else []
        )

        for arm in arms:
            arm_pattern = next(
                (c for c in arm.children if c.type == "match_pattern"), None
            )
            arm_body_children = [
                c
                for c in arm.children
                if c.type not in ("match_pattern", "=>", ",", "fat_arrow")
                and c.is_named
            ]
            arm_label = self._fresh_label("match_arm")
            next_label = self._fresh_label("match_next")

            if arm_pattern:
                pattern_reg = self._lower_expr(arm_pattern)
                cond_reg = self._fresh_reg()
                self._emit(
                    Opcode.BINOP,
                    result_reg=cond_reg,
                    operands=["==", val_reg, pattern_reg],
                    source_location=self._source_loc(arm),
                )
                self._emit(
                    Opcode.BRANCH_IF,
                    operands=[cond_reg],
                    label=f"{arm_label},{next_label}",
                )
            else:
                self._emit(Opcode.BRANCH, label=arm_label)

            self._emit(Opcode.LABEL, label=arm_label)
            arm_result = self._fresh_reg()
            if arm_body_children:
                arm_result = self._lower_expr(arm_body_children[0])
            else:
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

    # -- block expression --------------------------------------------------

    def _lower_block_expr(self, node) -> str:
        """Lower a block `{ ... }` as an expression (last expr is value)."""
        children = [
            c
            for c in node.children
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

    # -- closure expression ------------------------------------------------

    def _lower_closure_expr(self, node) -> str:
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = f"__closure_{self._label_counter}"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_closure_params(params_node)

        if body_node:
            result_reg = self._lower_expr(body_node)
            self._emit(Opcode.RETURN, operands=[result_reg])
        else:
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

    def _lower_closure_params(self, params_node):
        for child in params_node.children:
            if child.type in ("|", ",", ":"):
                continue
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
            elif child.type == "parameter":
                self._lower_param(child)

    # -- struct definition -------------------------------------------------

    def _lower_struct_def(self, node):
        name_node = node.child_by_field_name("name")
        class_name = self._node_text(name_node) if name_node else "__anon_struct"
        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=class_label)
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

    # -- impl block --------------------------------------------------------

    def _lower_impl_item(self, node):
        type_node = node.child_by_field_name("type")
        body_node = node.child_by_field_name("body")
        impl_name = self._node_text(type_node) if type_node else "__anon_impl"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{impl_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{impl_name}")

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
                constants.CLASS_REF_TEMPLATE.format(name=impl_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[impl_name, cls_reg])

    # -- struct instantiation ----------------------------------------------

    def _lower_struct_instantiation(self, node) -> str:
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        struct_name = self._node_text(name_node) if name_node else "Struct"

        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=[struct_name],
            source_location=self._source_loc(node),
        )

        if body_node:
            for child in body_node.children:
                if child.type == "field_initializer":
                    field_name_node = child.child_by_field_name("field")
                    field_val_node = child.child_by_field_name("value")
                    if field_name_node and field_val_node:
                        val_reg = self._lower_expr(field_val_node)
                        self._emit(
                            Opcode.STORE_FIELD,
                            operands=[
                                obj_reg,
                                self._node_text(field_name_node),
                                val_reg,
                            ],
                        )
                    elif field_name_node:
                        # Shorthand: `Point { x, y }` means `Point { x: x, y: y }`
                        val_reg = self._lower_identifier(field_name_node)
                        self._emit(
                            Opcode.STORE_FIELD,
                            operands=[
                                obj_reg,
                                self._node_text(field_name_node),
                                val_reg,
                            ],
                        )
        return obj_reg

    # -- macro invocation --------------------------------------------------

    def _lower_macro_invocation(self, node) -> str:
        macro_name = self._node_text(node).split("!")[0] + "!"
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[macro_name],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_macro_stmt(self, node):
        self._lower_macro_invocation(node)

    # -- index expression --------------------------------------------------

    def _lower_index_expr(self, node) -> str:
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
            source_location=self._source_loc(node),
        )
        return reg

    # -- tuple expression --------------------------------------------------

    def _lower_tuple_expr(self, node) -> str:
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

    # -- try expression (? operator) ---------------------------------------

    def _lower_try_expr(self, node) -> str:
        """Lower `expr?` as CALL_FUNCTION("try_unwrap", inner)."""
        inner = next(
            (c for c in node.children if c.type != "?" and c.is_named),
            None,
        )
        inner_reg = self._lower_expr(inner) if inner else self._fresh_reg()
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["try_unwrap", inner_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # -- await expression --------------------------------------------------

    def _lower_await_expr(self, node) -> str:
        """Lower `expr.await` as CALL_FUNCTION("await", inner)."""
        inner = next(
            (c for c in node.children if c.type not in (".", "await") and c.is_named),
            None,
        )
        inner_reg = self._lower_expr(inner) if inner else self._fresh_reg()
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["await", inner_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # -- trait item --------------------------------------------------------

    def _lower_trait_item(self, node):
        """Lower `trait Name { ... }` like a class/impl block."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        trait_name = self._node_text(name_node) if name_node else "__anon_trait"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{trait_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{trait_name}")

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
                constants.CLASS_REF_TEMPLATE.format(name=trait_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[trait_name, cls_reg])

    # -- enum item ---------------------------------------------------------

    def _lower_enum_item(self, node):
        """Lower `enum Name { A, B(i32), ... }` as NEW_OBJECT + STORE_FIELD per variant."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        enum_name = self._node_text(name_node) if name_node else "__anon_enum"

        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=[f"enum:{enum_name}"],
            source_location=self._source_loc(node),
        )

        if body_node:
            for child in body_node.children:
                if child.type in ("{", "}", ","):
                    continue
                if not child.is_named:
                    continue
                variant_name = (
                    self._node_text(child).split("(")[0].split("{")[0].strip()
                )
                variant_reg = self._fresh_reg()
                self._emit(
                    Opcode.CONST,
                    result_reg=variant_reg,
                    operands=[variant_name],
                )
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, variant_name, variant_reg],
                )

        self._emit(Opcode.STORE_VAR, operands=[enum_name, obj_reg])

    # -- const item --------------------------------------------------------

    def _lower_const_item(self, node):
        """Lower `const NAME: type = value;`."""
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        var_name = self._node_text(name_node) if name_node else "__const"

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

    # -- static item -------------------------------------------------------

    def _lower_static_item(self, node):
        """Lower `static NAME: type = value;`."""
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        var_name = self._node_text(name_node) if name_node else "__static"

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

    # -- type alias --------------------------------------------------------

    def _lower_type_item(self, node):
        """Lower `type Alias = OriginalType;`."""
        name_node = node.child_by_field_name("name")
        type_node = node.child_by_field_name("type")
        alias_name = self._node_text(name_node) if name_node else "__type_alias"
        type_text = self._node_text(type_node) if type_node else "()"

        val_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=val_reg,
            operands=[type_text],
            source_location=self._source_loc(node),
        )
        self._emit(
            Opcode.STORE_VAR,
            operands=[alias_name, val_reg],
            source_location=self._source_loc(node),
        )

    # -- mod item ----------------------------------------------------------

    def _lower_mod_item(self, node):
        """Lower `mod name { ... }` by lowering the body block."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        logger.debug(
            "Lowering mod_item: %s",
            self._node_text(name_node) if name_node else "<anonymous>",
        )
        if body_node:
            self._lower_block(body_node)

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

    # -- function parameters -----------------------------------------------

    def _extract_param_name(self, child) -> str | None:
        if child.type == "identifier":
            return self._node_text(child)
        if child.type == "self_parameter":
            return "self"
        if child.type == "parameter":
            pattern_node = child.child_by_field_name("pattern")
            if pattern_node:
                return self._extract_let_pattern_name(pattern_node)
        return None

    # -- store target override for field_expression ------------------------

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
        elif target.type == "field_expression":
            value_node = target.child_by_field_name("value")
            field_node = target.child_by_field_name("field")
            if value_node and field_node:
                obj_reg = self._lower_expr(value_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(field_node), val_reg],
                    source_location=self._source_loc(parent_node),
                )
        elif target.type == "index_expression":
            children = [c for c in target.children if c.is_named]
            if len(children) >= 2:
                obj_reg = self._lower_expr(children[0])
                idx_reg = self._lower_expr(children[1])
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                    source_location=self._source_loc(parent_node),
                )
        elif target.type == "dereference_expression":
            inner_children = [c for c in target.children if c.type != "*"]
            if inner_children:
                inner_reg = self._lower_expr(inner_children[0])
                self._emit(
                    Opcode.STORE_VAR,
                    operands=[f"*{self._node_text(inner_children[0])}", val_reg],
                    source_location=self._source_loc(parent_node),
                )
        else:
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
