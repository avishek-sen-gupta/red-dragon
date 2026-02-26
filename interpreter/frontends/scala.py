"""ScalaFrontend -- tree-sitter Scala AST -> IR lowering."""

from __future__ import annotations

import logging
from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)


class ScalaFrontend(BaseFrontend):
    """Lowers a Scala tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "null"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    DEFAULT_RETURN_VALUE = "()"

    CALL_FUNCTION_FIELD = "function"
    CALL_ARGUMENTS_FIELD = "arguments"

    ATTR_OBJECT_FIELD = "value"
    ATTR_ATTRIBUTE_FIELD = "field"
    ATTRIBUTE_NODE_TYPE = "field_expression"

    ASSIGN_LEFT_FIELD = "left"
    ASSIGN_RIGHT_FIELD = "right"

    COMMENT_TYPES = frozenset({"comment", "block_comment"})
    NOISE_TYPES = frozenset({"\n"})

    BLOCK_NODE_TYPES = frozenset({"block"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "integer_literal": self._lower_const_literal,
            "floating_point_literal": self._lower_const_literal,
            "string": self._lower_const_literal,
            "boolean_literal": self._lower_const_literal,
            "null_literal": self._lower_const_literal,
            "unit": self._lower_const_literal,
            "infix_expression": self._lower_binop,
            "prefix_expression": self._lower_unop,
            "parenthesized_expression": self._lower_paren,
            "call_expression": self._lower_call,
            "field_expression": self._lower_field_expr,
            "if_expression": self._lower_if_expr,
            "match_expression": self._lower_match_expr,
            "block": self._lower_block_expr,
            "assignment_expression": self._lower_assignment_expr,
            "return_expression": self._lower_return_expr,
            "this": self._lower_identifier,
            "super": self._lower_identifier,
            "wildcard": self._lower_wildcard,
            "tuple_expression": self._lower_tuple_expr,
            "string_literal": self._lower_const_literal,
            "interpolated_string": self._lower_const_literal,
            "lambda_expression": self._lower_lambda_expr,
            "instance_expression": self._lower_new_expr,
            "generic_type": self._lower_symbolic_node,
            "type_identifier": self._lower_identifier,
            "try_expression": self._lower_try_expr,
            "throw_expression": self._lower_throw_expr,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "val_definition": self._lower_val_def,
            "var_definition": self._lower_var_def,
            "function_definition": self._lower_function_def,
            "class_definition": self._lower_class_def,
            "object_definition": self._lower_object_def,
            "if_expression": self._lower_if_stmt,
            "while_expression": self._lower_while,
            "match_expression": self._lower_match_stmt,
            "expression_statement": self._lower_expression_statement,
            "block": self._lower_block,
            "template_body": self._lower_block,
            "compilation_unit": self._lower_block,
            "import_declaration": lambda _: None,
            "package_clause": lambda _: None,
            "break_expression": self._lower_break,
            "continue_expression": self._lower_continue,
            "try_expression": self._lower_try_stmt,
            "for_expression": self._lower_for_expr,
            "trait_definition": self._lower_trait_def,
            "case_class_definition": self._lower_class_def,
            "lazy_val_definition": self._lower_val_def,
            "do_while_expression": self._lower_do_while,
            "type_definition": lambda _: None,
        }

    # -- val / var definition ----------------------------------------------

    def _lower_val_def(self, node):
        pattern_node = node.child_by_field_name("pattern")
        value_node = node.child_by_field_name("value")
        var_name = self._extract_pattern_name(pattern_node)
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

    def _lower_var_def(self, node):
        pattern_node = node.child_by_field_name("pattern")
        value_node = node.child_by_field_name("value")
        var_name = self._extract_pattern_name(pattern_node)
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

    def _extract_pattern_name(self, pattern_node) -> str:
        """Extract name from a pattern node (identifier, typed_pattern, etc.)."""
        if pattern_node is None:
            return "__unknown"
        if pattern_node.type == "identifier":
            return self._node_text(pattern_node)
        # typed_pattern or other wrapper: find the identifier inside
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
            node=node,
        )
        return reg

    # -- if expression (value-producing) -----------------------------------

    def _lower_if_expr(self, node) -> str:
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

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
        true_reg = self._lower_body_as_expr(body_node)
        self._emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            false_reg = self._lower_body_as_expr(alt_node)
            self._emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)
        reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
        return reg

    def _lower_if_stmt(self, node):
        """Lower if as a statement (discard result)."""
        self._lower_if_expr(node)

    def _lower_body_as_expr(self, body_node) -> str:
        """Lower a body node as an expression, returning the last expression's reg."""
        if body_node is None:
            reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
            return reg
        if body_node.type == "block":
            return self._lower_block_expr(body_node)
        return self._lower_expr(body_node)

    # -- while expression --------------------------------------------------

    def _lower_while(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

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
        if body_node:
            self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- match expression --------------------------------------------------

    def _lower_match_expr(self, node) -> str:
        value_node = node.child_by_field_name("value")
        body_node = node.child_by_field_name("body")

        val_reg = self._lower_expr(value_node) if value_node else self._fresh_reg()
        result_var = f"__match_result_{self._label_counter}"
        end_label = self._fresh_label("match_end")

        clauses = (
            [c for c in body_node.children if c.type == "case_clause"]
            if body_node
            else []
        )

        for clause in clauses:
            pattern_node = clause.child_by_field_name("pattern")
            body_child = clause.child_by_field_name("body")

            arm_label = self._fresh_label("case_arm")
            next_label = self._fresh_label("case_next")

            if pattern_node and pattern_node.type == "wildcard":
                # Default case: _ => ...
                self._emit(Opcode.BRANCH, label=arm_label)
            elif pattern_node:
                pattern_reg = self._lower_expr(pattern_node)
                cond_reg = self._fresh_reg()
                self._emit(
                    Opcode.BINOP,
                    result_reg=cond_reg,
                    operands=["==", val_reg, pattern_reg],
                    node=clause,
                )
                self._emit(
                    Opcode.BRANCH_IF,
                    operands=[cond_reg],
                    label=f"{arm_label},{next_label}",
                )
            else:
                self._emit(Opcode.BRANCH, label=arm_label)

            self._emit(Opcode.LABEL, label=arm_label)
            if body_child:
                arm_result = self._lower_body_as_expr(body_child)
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

    def _lower_match_stmt(self, node):
        """Lower match as a statement (discard result)."""
        self._lower_match_expr(node)

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

    # -- function definition -----------------------------------------------

    def _lower_function_def(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = self._node_text(name_node) if name_node else "__anon"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_scala_params(params_node)

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

    def _lower_scala_params(self, params_node):
        for child in params_node.children:
            if child.type == "parameter":
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

    # -- class definition --------------------------------------------------

    def _lower_class_def(self, node):
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

    # -- object definition (singleton) -------------------------------------

    def _lower_object_def(self, node):
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        obj_name = self._node_text(name_node) if name_node else "__anon_object"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{obj_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{obj_name}")

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
                constants.CLASS_REF_TEMPLATE.format(name=obj_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[obj_name, cls_reg])

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
            node=node,
        )
        return val_reg

    # -- wildcard ----------------------------------------------------------

    def _lower_wildcard(self, node) -> str:
        reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=["wildcard:_"],
            node=node,
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
            node=node,
        )
        for i, elem in enumerate(elems):
            val_reg = self._lower_expr(elem)
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    # -- lambda expression -------------------------------------------------

    def _lower_lambda_expr(self, node) -> str:
        func_name = f"__lambda_{self._label_counter}"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        # Lambda params and body: children vary, lower all named children
        named_children = [
            c for c in node.children if c.is_named and c.type not in self.COMMENT_TYPES
        ]
        for child in named_children:
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

    # -- new expression ----------------------------------------------------

    def _lower_new_expr(self, node) -> str:
        named_children = [c for c in node.children if c.is_named]
        if named_children:
            type_name = self._node_text(named_children[0])
        else:
            type_name = "Object"
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[type_name],
            node=node,
        )
        return reg

    # -- for expression (for-comprehension) --------------------------------

    def _lower_for_expr(self, node):
        """Lower for-comprehension: for (generators) body / for (generators) yield body."""
        enumerators_node = next(
            (c for c in node.children if c.type == "enumerators"), None
        )
        # Body is the last named child (after the enumerators and yield keyword)
        named_children = [c for c in node.children if c.is_named]
        body_node = named_children[-1] if named_children else None
        # Don't use enumerators_node as body
        if body_node is enumerators_node:
            body_node = None

        generators = (
            [c for c in enumerators_node.children if c.type == "enumerator"]
            if enumerators_node
            else []
        )
        guards = (
            [c for c in enumerators_node.children if c.type == "guard"]
            if enumerators_node
            else []
        )

        loop_label = self._fresh_label("for_comp_loop")
        end_label = self._fresh_label("for_comp_end")

        # Lower each generator: extract binding + iterable from children
        for gen in generators:
            gen_children = [c for c in gen.children if c.is_named]
            # First named child is the binding, last is the iterable
            binding_node = gen_children[0] if gen_children else None
            iterable_node = gen_children[-1] if len(gen_children) > 1 else None
            var_name = self._node_text(binding_node) if binding_node else "__for_var"
            iter_reg = (
                self._lower_expr(iterable_node) if iterable_node else self._fresh_reg()
            )
            iter_fn_reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=iter_fn_reg,
                operands=["iter", iter_reg],
                node=gen,
            )

        self._emit(Opcode.LABEL, label=loop_label)

        for gen in generators:
            gen_children = [c for c in gen.children if c.is_named]
            binding_node = gen_children[0] if gen_children else None
            var_name = self._node_text(binding_node) if binding_node else "__for_var"
            next_reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=next_reg,
                operands=["next"],
                node=gen,
            )
            self._emit(
                Opcode.STORE_VAR,
                operands=[var_name, next_reg],
                node=gen,
            )

        # Lower guards as BRANCH_IF
        for guard in guards:
            guard_children = [c for c in guard.children if c.is_named]
            if guard_children:
                guard_reg = self._lower_expr(guard_children[0])
                continue_label = self._fresh_label("for_guard_ok")
                self._emit(
                    Opcode.BRANCH_IF,
                    operands=[guard_reg],
                    label=f"{continue_label},{loop_label}",
                )
                self._emit(Opcode.LABEL, label=continue_label)

        if body_node:
            self._lower_stmt(body_node)

        self._emit(Opcode.BRANCH, label=loop_label)
        self._emit(Opcode.LABEL, label=end_label)

    # -- trait definition --------------------------------------------------

    def _lower_trait_def(self, node):
        """Lower trait_definition like class_definition."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        trait_name = self._node_text(name_node) if name_node else "__anon_trait"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{trait_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{trait_name}")

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
                constants.CLASS_REF_TEMPLATE.format(name=trait_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[trait_name, cls_reg])

    # -- do-while expression -----------------------------------------------

    def _lower_do_while(self, node):
        """Lower do { body } while (condition)."""
        body_node = node.child_by_field_name("body")
        cond_node = node.child_by_field_name("condition")

        body_label = self._fresh_label("do_body")
        end_label = self._fresh_label("do_end")

        self._emit(Opcode.LABEL, label=body_label)
        if body_node:
            self._lower_block(body_node)

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

    # -- store target override for field_expression ------------------------

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                node=parent_node,
            )
        elif target.type == "field_expression":
            value_node = target.child_by_field_name("value")
            field_node = target.child_by_field_name("field")
            if value_node and field_node:
                obj_reg = self._lower_expr(value_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(field_node), val_reg],
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
        body_node = node.child_by_field_name("body")
        catch_clauses = []
        finally_node = None
        for child in node.children:
            if child.type == "catch_clause":
                # Scala catch clause has a body with case_clause entries
                catch_body_node = child.child_by_field_name("body")
                if catch_body_node:
                    # Each case_clause in the catch body is a separate handler
                    cases = [
                        c for c in catch_body_node.children if c.type == "case_clause"
                    ]
                    if cases:
                        for case in cases:
                            pattern = case.child_by_field_name("pattern")
                            case_body = case.child_by_field_name("body")
                            exc_var = None
                            exc_type = None
                            if pattern:
                                # typed_pattern: identifier : Type
                                id_node = next(
                                    (
                                        c
                                        for c in pattern.children
                                        if c.type == "identifier"
                                    ),
                                    None,
                                )
                                exc_var = self._node_text(id_node) if id_node else None
                                type_node = next(
                                    (
                                        c
                                        for c in pattern.children
                                        if c.type == "type_identifier"
                                    ),
                                    None,
                                )
                                exc_type = (
                                    self._node_text(type_node)
                                    if type_node
                                    else self._node_text(pattern)
                                )
                            catch_clauses.append(
                                {
                                    "body": case_body,
                                    "variable": exc_var,
                                    "type": exc_type,
                                }
                            )
                    else:
                        # Catch body without case clauses: lower entire body
                        catch_clauses.append(
                            {"body": catch_body_node, "variable": None, "type": None}
                        )
            elif child.type == "finally_clause":
                finally_node = child.child_by_field_name("body")
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

    # -- throw expression --------------------------------------------------

    def _lower_throw_expr(self, node) -> str:
        """Lower throw_expression: throw expr -> lower expr, emit THROW, return reg."""
        children = [c for c in node.children if c.type != "throw" and c.is_named]
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
            Opcode.THROW,
            operands=[val_reg],
            node=node,
        )
        return val_reg

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
