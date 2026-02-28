"""CFrontend — tree-sitter C AST -> IR lowering."""

from __future__ import annotations

import logging
from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)

PREPROC_NOISE_TYPES = frozenset(
    {
        "preproc_include",
        "preproc_define",
        "preproc_ifdef",
        "preproc_ifndef",
        "preproc_if",
        "preproc_else",
        "preproc_elif",
        "preproc_endif",
        "preproc_call",
        "preproc_def",
    }
)


class CFrontend(BaseFrontend):
    """Lowers a C tree-sitter AST into flattened TAC IR."""

    DEFAULT_RETURN_VALUE = "0"

    ATTR_OBJECT_FIELD = "argument"
    ATTR_ATTRIBUTE_FIELD = "field"
    ATTRIBUTE_NODE_TYPE = "field_expression"

    SUBSCRIPT_VALUE_FIELD = "argument"
    SUBSCRIPT_INDEX_FIELD = "index"

    COMMENT_TYPES = frozenset({"comment"})
    NOISE_TYPES = frozenset({"\n"}) | PREPROC_NOISE_TYPES

    BLOCK_NODE_TYPES = frozenset({"compound_statement"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "number_literal": self._lower_const_literal,
            "string_literal": self._lower_const_literal,
            "char_literal": self._lower_const_literal,
            "true": self._lower_canonical_true,
            "false": self._lower_canonical_false,
            "null": self._lower_canonical_none,
            "binary_expression": self._lower_binop,
            "unary_expression": self._lower_unop,
            "update_expression": self._lower_update_expr,
            "parenthesized_expression": self._lower_paren,
            "call_expression": self._lower_call,
            "field_expression": self._lower_field_expr,
            "subscript_expression": self._lower_subscript_expr,
            "assignment_expression": self._lower_assignment_expr,
            "cast_expression": self._lower_cast_expr,
            "pointer_expression": self._lower_pointer_expr,
            "sizeof_expression": self._lower_sizeof,
            "conditional_expression": self._lower_ternary,
            "comma_expression": self._lower_comma_expr,
            "concatenated_string": self._lower_const_literal,
            "type_identifier": self._lower_identifier,
            "compound_literal_expression": self._lower_compound_literal,
            "preproc_arg": self._lower_const_literal,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "expression_statement": self._lower_expression_statement,
            "declaration": self._lower_declaration,
            "return_statement": self._lower_return,
            "if_statement": self._lower_if,
            "while_statement": self._lower_while,
            "for_statement": self._lower_c_style_for,
            "do_statement": self._lower_do_while,
            "function_definition": self._lower_function_def_c,
            "struct_specifier": self._lower_struct_def,
            "compound_statement": self._lower_block,
            "switch_statement": self._lower_switch,
            "goto_statement": self._lower_goto,
            "labeled_statement": self._lower_labeled_stmt,
            "break_statement": self._lower_break,
            "continue_statement": self._lower_continue,
            "translation_unit": self._lower_block,
            "type_definition": self._lower_typedef,
            "enum_specifier": self._lower_enum_def,
            "union_specifier": self._lower_union_def,
            "preproc_function_def": self._lower_preproc_function_def,
        }
        self._EXPR_DISPATCH["initializer_list"] = self._lower_initializer_list
        self._EXPR_DISPATCH["initializer_pair"] = self._lower_initializer_pair

    # -- C: declaration ------------------------------------------------

    def _lower_declaration(self, node):
        """Lower a C declaration: type declarator(s) with optional initializers."""
        for child in node.children:
            if child.type == "init_declarator":
                self._lower_init_declarator(child)
            elif child.type == "identifier":
                # Declaration without initializer: int x;
                var_name = self._node_text(child)
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

    def _lower_init_declarator(self, node):
        """Lower init_declarator (fields: declarator, value)."""
        decl_node = node.child_by_field_name("declarator")
        value_node = node.child_by_field_name("value")

        var_name = self._extract_declarator_name(decl_node) if decl_node else "__anon"

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

    def _extract_declarator_name(self, decl_node) -> str:
        """Extract the variable name from a declarator, handling pointer declarators."""
        if decl_node.type == "identifier":
            return self._node_text(decl_node)
        # pointer_declarator, array_declarator, etc.
        inner = decl_node.child_by_field_name("declarator")
        if inner:
            return self._extract_declarator_name(inner)
        # Fallback: first identifier child
        id_node = next((c for c in decl_node.children if c.type == "identifier"), None)
        if id_node:
            return self._node_text(id_node)
        return self._node_text(decl_node)

    # -- C: function definition ----------------------------------------

    def _lower_function_def_c(self, node):
        """Lower function_definition with nested function_declarator."""
        declarator_node = node.child_by_field_name("declarator")
        body_node = node.child_by_field_name("body")

        func_name = "__anon"
        params_node = None

        if declarator_node:
            # function_declarator has fields: declarator (name), parameters
            if declarator_node.type == "function_declarator":
                name_node = declarator_node.child_by_field_name("declarator")
                params_node = declarator_node.child_by_field_name("parameters")
                func_name = (
                    self._extract_declarator_name(name_node) if name_node else "__anon"
                )
            else:
                # Could be pointer_declarator wrapping function_declarator
                func_decl = self._find_function_declarator(declarator_node)
                if func_decl:
                    name_node = func_decl.child_by_field_name("declarator")
                    params_node = func_decl.child_by_field_name("parameters")
                    func_name = (
                        self._extract_declarator_name(name_node)
                        if name_node
                        else "__anon"
                    )
                else:
                    func_name = self._extract_declarator_name(declarator_node)

        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_c_params(params_node)

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

    def _find_function_declarator(self, node):
        """Recursively find function_declarator inside pointer/other declarators."""
        if node.type == "function_declarator":
            return node
        for child in node.children:
            result = self._find_function_declarator(child)
            if result:
                return result
        return None

    def _lower_c_params(self, params_node):
        """Lower C function parameters (parameter_declaration nodes)."""
        for child in params_node.children:
            if child.type == "parameter_declaration":
                decl_node = child.child_by_field_name("declarator")
                if decl_node:
                    pname = self._extract_declarator_name(decl_node)
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

    # -- C: struct definition ------------------------------------------

    def _lower_struct_def(self, node):
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")

        if name_node is None and body_node is None:
            # Forward declaration or anonymous struct used as type
            return

        struct_name = self._node_text(name_node) if name_node else "__anon_struct"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{struct_name}")
        end_label = self._fresh_label(
            f"{constants.END_CLASS_LABEL_PREFIX}{struct_name}"
        )

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=class_label)
        if body_node:
            self._lower_struct_body(body_node)
        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=cls_reg,
            operands=[
                constants.CLASS_REF_TEMPLATE.format(name=struct_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[struct_name, cls_reg])

    def _lower_struct_body(self, node):
        """Lower struct field_declaration_list."""
        for child in node.children:
            if child.type == "field_declaration":
                self._lower_struct_field(child)
            elif child.is_named and child.type not in ("{", "}"):
                self._lower_stmt(child)

    def _lower_struct_field(self, node):
        """Lower a struct field declaration as STORE_FIELD on this.

        Emits: LOAD_VAR this -> CONST default -> STORE_FIELD this, field_name, default
        """
        declarators = [
            c for c in node.children if c.type in ("field_identifier", "identifier")
        ]
        for decl in declarators:
            fname = self._node_text(decl)
            this_reg = self._fresh_reg()
            self._emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
            default_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST,
                result_reg=default_reg,
                operands=["0"],
                node=node,
            )
            self._emit(
                Opcode.STORE_FIELD,
                operands=[this_reg, fname, default_reg],
                node=node,
            )

    # -- C: field expression -------------------------------------------

    def _lower_field_expr(self, node) -> str:
        """Lower field_expression (e.g., obj.field or ptr->field)."""
        obj_node = node.child_by_field_name("argument")
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
            node=node,
        )
        return reg

    # -- C: subscript expression ---------------------------------------

    def _lower_subscript_expr(self, node) -> str:
        """Lower subscript_expression (arr[idx])."""
        arr_node = node.child_by_field_name("argument")
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
            node=node,
        )
        return reg

    # -- C: assignment expression --------------------------------------

    def _lower_assignment_expr(self, node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        val_reg = self._lower_expr(right)
        self._lower_store_target(left, val_reg, node)
        return val_reg

    # -- C: store target override --------------------------------------

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                node=parent_node,
            )
        elif target.type == "field_expression":
            obj_node = target.child_by_field_name("argument")
            field_node = target.child_by_field_name("field")
            if obj_node and field_node:
                obj_reg = self._lower_expr(obj_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(field_node), val_reg],
                    node=parent_node,
                )
        elif target.type == "subscript_expression":
            arr_node = target.child_by_field_name("argument")
            idx_node = target.child_by_field_name("index")
            if arr_node and idx_node:
                arr_reg = self._lower_expr(arr_node)
                idx_reg = self._lower_expr(idx_node)
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[arr_reg, idx_reg, val_reg],
                    node=parent_node,
                )
        elif target.type == "pointer_expression":
            # *ptr = val -> lower_expr(ptr_operand) -> STORE_FIELD ptr_reg, "*", val_reg
            operand_node = target.child_by_field_name("argument")
            if operand_node is None:
                operand_node = next((c for c in target.children if c.is_named), None)
            ptr_reg = (
                self._lower_expr(operand_node) if operand_node else self._fresh_reg()
            )
            self._emit(
                Opcode.STORE_FIELD,
                operands=[ptr_reg, "*", val_reg],
                node=parent_node,
            )
        else:
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                node=parent_node,
            )

    # -- C: cast expression --------------------------------------------

    def _lower_cast_expr(self, node) -> str:
        value_node = node.child_by_field_name("value")
        if value_node:
            return self._lower_expr(value_node)
        children = [c for c in node.children if c.is_named]
        if len(children) >= 2:
            return self._lower_expr(children[-1])
        return self._lower_const_literal(node)

    # -- C: pointer expression -----------------------------------------

    def _lower_pointer_expr(self, node) -> str:
        """Lower pointer dereference (*p) as LOAD_FIELD or address-of (&x) as UNOP."""
        operand_node = node.child_by_field_name("argument")
        # Detect operator: first non-named child is '*' or '&'
        op_char = next(
            (
                self._node_text(c)
                for c in node.children
                if not c.is_named and self._node_text(c) in ("*", "&")
            ),
            "*",
        )
        if operand_node is None:
            operand_node = next((c for c in node.children if c.is_named), None)

        inner_reg = (
            self._lower_expr(operand_node) if operand_node else self._fresh_reg()
        )

        if op_char == "&":
            reg = self._fresh_reg()
            self._emit(
                Opcode.UNOP,
                result_reg=reg,
                operands=["&", inner_reg],
                node=node,
            )
            return reg

        # Dereference: *ptr -> LOAD_FIELD ptr, "*"
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[inner_reg, "*"],
            node=node,
        )
        return reg

    # -- C: sizeof -----------------------------------------------------

    def _lower_sizeof(self, node) -> str:
        """Lower sizeof(type) or sizeof(expr) as CALL_FUNCTION sizeof(arg)."""
        # Find the type_descriptor or expression child
        type_node = next(
            (c for c in node.children if c.type == "type_descriptor"),
            None,
        )
        if type_node:
            arg_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST,
                result_reg=arg_reg,
                operands=[self._node_text(type_node)],
            )
        else:
            # sizeof applied to an expression
            expr_node = next(
                (c for c in node.children if c.is_named and c.type != "sizeof"),
                None,
            )
            arg_reg = self._lower_expr(expr_node) if expr_node else self._fresh_reg()

        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["sizeof", arg_reg],
            node=node,
        )
        return reg

    # -- C: ternary (conditional_expression) ---------------------------

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

    # -- C: comma expression -------------------------------------------

    def _lower_comma_expr(self, node) -> str:
        """Lower comma expression (a, b) -- evaluate both, return last."""
        children = [c for c in node.children if c.is_named]
        reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL])
        for child in children:
            reg = self._lower_expr(child)
        return reg

    # -- C: compound literal -------------------------------------------

    def _lower_compound_literal(self, node) -> str:
        """Lower (type){elem1, elem2, ...} as NEW_OBJECT + STORE_INDEX per element."""
        type_node = next(
            (c for c in node.children if c.type == "type_descriptor"),
            None,
        )
        init_node = next(
            (c for c in node.children if c.type == "initializer_list"),
            None,
        )
        type_name = self._node_text(type_node) if type_node else "compound"
        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=[type_name],
            node=node,
        )
        if init_node:
            elements = [c for c in init_node.children if c.is_named]
            for i, elem in enumerate(elements):
                idx_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
                val_reg = self._lower_expr(elem)
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                )
        return obj_reg

    # -- C: do-while ---------------------------------------------------

    def _lower_do_while(self, node):
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

    # -- C: switch as if/else chain ------------------------------------

    def _lower_switch(self, node):
        """Lower switch(expr) { case ... } as an if/else chain."""
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

        subject_reg = self._lower_expr(cond_node)
        end_label = self._fresh_label("switch_end")

        self._break_target_stack.append(end_label)

        cases = (
            [c for c in body_node.children if c.type == "case_statement"]
            if body_node
            else []
        )

        for case in cases:
            value_node = case.child_by_field_name("value")
            body_stmts = [
                c
                for c in case.children
                if c.is_named and c.type not in ("case", "default") and c != value_node
            ]

            arm_label = self._fresh_label("case_arm")
            next_label = self._fresh_label("case_next")

            if value_node:
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
                # default case
                self._emit(Opcode.BRANCH, label=arm_label)

            self._emit(Opcode.LABEL, label=arm_label)
            for stmt in body_stmts:
                self._lower_stmt(stmt)
            self._emit(Opcode.BRANCH, label=end_label)
            self._emit(Opcode.LABEL, label=next_label)

        self._break_target_stack.pop()
        self._emit(Opcode.LABEL, label=end_label)

    # -- C: goto / labeled statement / break / continue ----------------

    def _lower_goto(self, node):
        """Lower goto_statement as BRANCH user_{label}.

        The labeled_statement handler emits LABEL user_{label}, so this
        creates a matching branch target.
        """
        label_node = next(
            (c for c in node.children if c.type == "statement_identifier"), None
        )
        if label_node:
            target_label = f"user_{self._node_text(label_node)}"
            self._emit(
                Opcode.BRANCH,
                label=target_label,
                node=node,
            )
        else:
            logger.warning("goto without label: %s", self._node_text(node)[:40])

    def _lower_labeled_stmt(self, node):
        """Lower labeled_statement: emit label then lower the inner statement."""
        label_node = next(
            (c for c in node.children if c.type == "statement_identifier"), None
        )
        if label_node:
            self._emit(Opcode.LABEL, label=f"user_{self._node_text(label_node)}")
        # Lower the actual statement within the label
        for child in node.children:
            if child.is_named and child.type != "statement_identifier":
                self._lower_stmt(child)

    # break_statement and continue_statement are handled by
    # BaseFrontend._lower_break / _lower_continue via _STMT_DISPATCH

    # -- C: enum specifier ---------------------------------------------

    def _lower_enum_def(self, node):
        """Lower enum_specifier as NEW_OBJECT + STORE_FIELD per enumerator."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")

        if name_node is None and body_node is None:
            return

        enum_name = self._node_text(name_node) if name_node else "__anon_enum"

        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=[f"enum:{enum_name}"],
            node=node,
        )

        if body_node:
            enumerators = [c for c in body_node.children if c.type == "enumerator"]
            for i, enumerator in enumerate(enumerators):
                name_child = enumerator.child_by_field_name("name")
                value_child = enumerator.child_by_field_name("value")
                member_name = (
                    self._node_text(name_child) if name_child else f"__enum_{i}"
                )
                if value_child:
                    val_reg = self._lower_expr(value_child)
                else:
                    val_reg = self._fresh_reg()
                    self._emit(
                        Opcode.CONST,
                        result_reg=val_reg,
                        operands=[str(i)],
                    )
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, member_name, val_reg],
                    node=enumerator,
                )

        self._emit(
            Opcode.STORE_VAR,
            operands=[enum_name, obj_reg],
            node=node,
        )

    # -- C: union specifier --------------------------------------------

    def _lower_union_def(self, node):
        """Lower union_specifier like struct_specifier (reuse _lower_struct_body)."""
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")

        if name_node is None and body_node is None:
            return

        union_name = self._node_text(name_node) if name_node else "__anon_union"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{union_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{union_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=class_label)
        if body_node:
            self._lower_struct_body(body_node)
        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=cls_reg,
            operands=[
                constants.CLASS_REF_TEMPLATE.format(name=union_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[union_name, cls_reg])

    # -- C: initializer list -------------------------------------------

    def _lower_initializer_list(self, node) -> str:
        """Lower initializer_list {a, b, c} as NEW_ARRAY + STORE_INDEX per element."""
        elements = [c for c in node.children if c.is_named]
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
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            val_reg = self._lower_expr(elem)
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    # -- C: designated initializer pair ----------------------------------

    def _lower_initializer_pair(self, node) -> str:
        """Lower `.field = value` as lowering the value (field binding handled by parent)."""
        designator = next(
            (c for c in node.children if c.type == "field_designator"),
            None,
        )
        value_node = next(
            (c for c in node.children if c.is_named and c.type != "field_designator"),
            None,
        )
        if value_node:
            return self._lower_expr(value_node)
        return self._lower_const_literal(node)

    # -- C: typedef (skip) ---------------------------------------------

    def _lower_preproc_function_def(self, node):
        """Lower `#define MAX(a, b) ((a) > (b) ? (a) : (b))` as function stub."""
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        func_name = self._node_text(name_node) if name_node else "__macro"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=func_label)

        # Lower parameters from preproc_params child if present
        params_node = node.child_by_field_name("parameters")
        if params_node:
            self._lower_c_params(params_node)

        if value_node:
            val_reg = self._lower_expr(value_node)
            self._emit(Opcode.RETURN, operands=[val_reg])
        else:
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

    def _lower_typedef(self, node):
        """Lower type_definition as CONST type_name -> STORE_VAR alias.

        The alias (type_identifier) is stored as a variable pointing to the
        original type name, enabling data-flow tracking through type aliases.
        """
        named_children = [c for c in node.children if c.is_named]
        alias_node = next(
            (c for c in reversed(named_children) if c.type == "type_identifier"),
            None,
        )
        type_nodes = [
            c for c in named_children if c != alias_node and c.type != "type_identifier"
        ]
        type_name = self._node_text(type_nodes[0]) if type_nodes else "unknown_type"
        alias_name = self._node_text(alias_node) if alias_node else "unknown_alias"

        type_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=type_reg,
            operands=[type_name],
            node=node,
        )
        self._emit(
            Opcode.STORE_VAR,
            operands=[alias_name, type_reg],
            node=node,
        )
