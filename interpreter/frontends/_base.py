"""BaseFrontend — language-agnostic tree-sitter AST → IR lowering infrastructure."""

from __future__ import annotations

import logging
from typing import Any, Callable

from ..frontend import Frontend
from ..ir import IRInstruction, Opcode
from .. import constants

logger = logging.getLogger(__name__)


class BaseFrontend(Frontend):
    """Base class for deterministic tree-sitter frontends.

    Subclasses populate ``_STMT_DISPATCH`` and ``_EXPR_DISPATCH`` tables and
    override field-name / literal constants where the grammar differs from
    the defaults.
    """

    # ── overridable constants ────────────────────────────────────

    FUNC_NAME_FIELD: str = "name"
    FUNC_PARAMS_FIELD: str = "parameters"
    FUNC_BODY_FIELD: str = "body"

    IF_CONDITION_FIELD: str = "condition"
    IF_CONSEQUENCE_FIELD: str = "consequence"
    IF_ALTERNATIVE_FIELD: str = "alternative"

    WHILE_CONDITION_FIELD: str = "condition"
    WHILE_BODY_FIELD: str = "body"

    CALL_FUNCTION_FIELD: str = "function"
    CALL_ARGUMENTS_FIELD: str = "arguments"

    CLASS_NAME_FIELD: str = "name"
    CLASS_BODY_FIELD: str = "body"

    ATTR_OBJECT_FIELD: str = "object"
    ATTR_ATTRIBUTE_FIELD: str = "attribute"

    SUBSCRIPT_VALUE_FIELD: str = "value"
    SUBSCRIPT_INDEX_FIELD: str = "subscript"

    ASSIGN_LEFT_FIELD: str = "left"
    ASSIGN_RIGHT_FIELD: str = "right"

    BLOCK_NODE_TYPES: frozenset[str] = frozenset()

    NONE_LITERAL: str = "None"
    TRUE_LITERAL: str = "true"
    FALSE_LITERAL: str = "false"
    DEFAULT_RETURN_VALUE: str = "None"

    COMMENT_TYPES: frozenset[str] = frozenset({"comment"})
    NOISE_TYPES: frozenset[str] = frozenset({"newline", "\n"})

    PAREN_EXPR_TYPE: str = "parenthesized_expression"

    ATTRIBUTE_NODE_TYPE: str = "attribute"

    # ── init ─────────────────────────────────────────────────────

    def __init__(self):
        self._reg_counter: int = 0
        self._label_counter: int = 0
        self._instructions: list[IRInstruction] = []
        self._source: bytes = b""
        self._STMT_DISPATCH: dict[str, Callable] = {}
        self._EXPR_DISPATCH: dict[str, Callable] = {}

    # ── helpers ──────────────────────────────────────────────────

    def _fresh_reg(self) -> str:
        r = f"%{self._reg_counter}"
        self._reg_counter += 1
        return r

    def _fresh_label(self, prefix: str = "L") -> str:
        lbl = f"{prefix}_{self._label_counter}"
        self._label_counter += 1
        return lbl

    def _emit(
        self,
        opcode: Opcode,
        *,
        result_reg: str = "",
        operands: list[Any] = [],
        label: str = "",
        source_location: str = "",
    ) -> IRInstruction:
        inst = IRInstruction(
            opcode=opcode,
            result_reg=result_reg or None,
            operands=operands or [],
            label=label or None,
            source_location=source_location or None,
        )
        self._instructions.append(inst)
        return inst

    def _node_text(self, node) -> str:
        return self._source[node.start_byte : node.end_byte].decode("utf-8")

    def _source_loc(self, node) -> str:
        return f"{node.start_point[0] + 1}:{node.start_point[1]}"

    # ── entry point ──────────────────────────────────────────────

    def lower(self, tree, source: bytes) -> list[IRInstruction]:
        self._reg_counter = 0
        self._label_counter = 0
        self._instructions = []
        self._source = source
        root = tree.root_node
        self._emit(Opcode.LABEL, label=constants.CFG_ENTRY_LABEL)
        self._lower_block(root)
        return self._instructions

    # ── dispatchers ──────────────────────────────────────────────

    def _lower_block(self, node):
        """Lower a block of statements (module / suite / body)."""
        for child in node.children:
            self._lower_stmt(child)

    def _lower_stmt(self, node):
        ntype = node.type
        if ntype in self.COMMENT_TYPES or ntype in self.NOISE_TYPES:
            return
        handler = self._STMT_DISPATCH.get(ntype)
        if handler:
            handler(node)
            return
        # Fallback: try as expression
        self._lower_expr(node)

    def _lower_expr(self, node) -> str:
        """Lower an expression, return the register holding its value."""
        handler = self._EXPR_DISPATCH.get(node.type)
        if handler:
            return handler(node)
        # Fallback: symbolic
        reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"unsupported:{node.type}"],
            source_location=self._source_loc(node),
        )
        return reg

    # ── common expression lowerers ───────────────────────────────

    def _lower_const_literal(self, node) -> str:
        reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=reg,
            operands=[self._node_text(node)],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_identifier(self, node) -> str:
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_VAR,
            result_reg=reg,
            operands=[self._node_text(node)],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_paren(self, node) -> str:
        inner = next(
            (c for c in node.children if c.type not in ("(", ")")),
            None,
        )
        if inner is None:
            return self._lower_const_literal(node)
        return self._lower_expr(inner)

    def _lower_binop(self, node) -> str:
        children = [c for c in node.children if c.type not in ("(", ")")]
        lhs_reg = self._lower_expr(children[0])
        op = self._node_text(children[1])
        rhs_reg = self._lower_expr(children[2])
        reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=reg,
            operands=[op, lhs_reg, rhs_reg],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_comparison(self, node) -> str:
        children = [c for c in node.children if c.type not in ("(", ")")]
        lhs_reg = self._lower_expr(children[0])
        op = self._node_text(children[1])
        rhs_reg = self._lower_expr(children[2])
        reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=reg,
            operands=[op, lhs_reg, rhs_reg],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_unop(self, node) -> str:
        children = [c for c in node.children if c.type not in ("(", ")")]
        op = self._node_text(children[0])
        operand_reg = self._lower_expr(children[1])
        reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=reg,
            operands=[op, operand_reg],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_call(self, node) -> str:
        func_node = node.child_by_field_name(self.CALL_FUNCTION_FIELD)
        args_node = node.child_by_field_name(self.CALL_ARGUMENTS_FIELD)
        return self._lower_call_impl(func_node, args_node, node)

    def _lower_call_impl(self, func_node, args_node, node) -> str:
        arg_regs = self._extract_call_args(args_node)

        # Method call: obj.method(...)
        if func_node and func_node.type in (
            self.ATTRIBUTE_NODE_TYPE,
            "member_expression",
            "selector_expression",
            "member_access_expression",
            "field_access",
            "method_index_expression",
        ):
            obj_node = func_node.child_by_field_name(self.ATTR_OBJECT_FIELD)
            attr_node = func_node.child_by_field_name(self.ATTR_ATTRIBUTE_FIELD)
            if obj_node is None:
                obj_node = func_node.children[0] if func_node.children else None
            if attr_node is None:
                attr_node = (
                    func_node.children[-1] if len(func_node.children) > 1 else None
                )
            if obj_node and attr_node:
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
        if func_node:
            target_reg = self._lower_expr(func_node)
        else:
            target_reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=target_reg,
                operands=["unknown_call_target"],
            )
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    def _extract_call_args(self, args_node) -> list[str]:
        """Extract argument registers from a call arguments node."""
        if args_node is None:
            return []
        return [
            self._lower_expr(c)
            for c in args_node.children
            if c.type not in ("(", ")", ",", "argument", "value_argument")
            and c.is_named
        ]

    def _extract_call_args_unwrap(self, args_node) -> list[str]:
        """Extract args, unwrapping wrapper nodes like 'argument'."""
        if args_node is None:
            return []
        regs = []
        for c in args_node.children:
            if c.type in ("(", ")", ","):
                continue
            if c.type in ("argument", "value_argument"):
                inner = next(
                    (gc for gc in c.children if gc.is_named),
                    None,
                )
                if inner:
                    regs.append(self._lower_expr(inner))
            elif c.is_named:
                regs.append(self._lower_expr(c))
        return regs

    def _lower_attribute(self, node) -> str:
        obj_node = node.child_by_field_name(self.ATTR_OBJECT_FIELD)
        attr_node = node.child_by_field_name(self.ATTR_ATTRIBUTE_FIELD)
        if obj_node is None:
            obj_node = node.children[0] if node.children else None
        if attr_node is None:
            attr_node = node.children[-1] if len(node.children) > 1 else None
        if obj_node is None or attr_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(obj_node)
        field_name = self._node_text(attr_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, field_name],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_subscript(self, node) -> str:
        obj_node = node.child_by_field_name(self.SUBSCRIPT_VALUE_FIELD)
        idx_node = node.child_by_field_name(self.SUBSCRIPT_INDEX_FIELD)
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

    # ── common store target ──────────────────────────────────────

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
        elif target.type in (
            self.ATTRIBUTE_NODE_TYPE,
            "member_expression",
            "selector_expression",
            "member_access_expression",
            "field_access",
        ):
            obj_node = target.child_by_field_name(self.ATTR_OBJECT_FIELD)
            attr_node = target.child_by_field_name(self.ATTR_ATTRIBUTE_FIELD)
            if obj_node is None:
                obj_node = target.children[0] if target.children else None
            if attr_node is None:
                attr_node = target.children[-1] if len(target.children) > 1 else None
            if obj_node and attr_node:
                obj_reg = self._lower_expr(obj_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(attr_node), val_reg],
                    source_location=self._source_loc(parent_node),
                )
        elif target.type == "subscript":
            obj_node = target.child_by_field_name(self.SUBSCRIPT_VALUE_FIELD)
            idx_node = target.child_by_field_name(self.SUBSCRIPT_INDEX_FIELD)
            if obj_node and idx_node:
                obj_reg = self._lower_expr(obj_node)
                idx_reg = self._lower_expr(idx_node)
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                    source_location=self._source_loc(parent_node),
                )
        else:
            # Fallback: just store to the text of the target
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )

    # ── common statement lowerers ────────────────────────────────

    def _lower_assignment(self, node):
        left = node.child_by_field_name(self.ASSIGN_LEFT_FIELD)
        right = node.child_by_field_name(self.ASSIGN_RIGHT_FIELD)
        val_reg = self._lower_expr(right)
        self._lower_store_target(left, val_reg, node)

    def _lower_augmented_assignment(self, node):
        left = node.child_by_field_name(self.ASSIGN_LEFT_FIELD)
        right = node.child_by_field_name(self.ASSIGN_RIGHT_FIELD)
        op_node = [c for c in node.children if c.type not in (left.type, right.type)][0]
        op_text = self._node_text(op_node).rstrip("=")
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

    def _lower_return(self, node):
        """Lower a return statement. Override for language-specific keyword."""
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

    def _lower_if(self, node):
        cond_node = node.child_by_field_name(self.IF_CONDITION_FIELD)
        body_node = node.child_by_field_name(self.IF_CONSEQUENCE_FIELD)
        alt_node = node.child_by_field_name(self.IF_ALTERNATIVE_FIELD)

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
            self._lower_alternative(alt_node, end_label)
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_alternative(self, alt_node, end_label: str):
        """Lower an else/elif/else-if alternative block."""
        alt_type = alt_node.type
        if alt_type in ("elif_clause",):
            self._lower_elif(alt_node, end_label)
        elif alt_type in ("else_clause", "else"):
            body = alt_node.child_by_field_name("body")
            if body:
                self._lower_block(body)
            else:
                for child in alt_node.children:
                    if child.type not in ("else", ":", "{", "}"):
                        self._lower_stmt(child)
        else:
            self._lower_block(alt_node)

    def _lower_elif(self, node, end_label: str):
        cond_node = node.child_by_field_name(self.IF_CONDITION_FIELD)
        body_node = node.child_by_field_name(self.IF_CONSEQUENCE_FIELD)
        alt_node = node.child_by_field_name(self.IF_ALTERNATIVE_FIELD)

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("elif_true")
        false_label = self._fresh_label("elif_false") if alt_node else end_label

        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
            source_location=self._source_loc(node),
        )

        self._emit(Opcode.LABEL, label=true_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            self._lower_alternative(alt_node, end_label)
            self._emit(Opcode.BRANCH, label=end_label)

    def _lower_while(self, node):
        cond_node = node.child_by_field_name(self.WHILE_CONDITION_FIELD)
        body_node = node.child_by_field_name(self.WHILE_BODY_FIELD)

        loop_label = self._fresh_label("while_cond")
        body_label = self._fresh_label("while_body")
        end_label = self._fresh_label("while_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._lower_expr(cond_node)
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
            source_location=self._source_loc(node),
        )

        self._emit(Opcode.LABEL, label=body_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_c_style_for(self, node):
        """Lower a C-style for(init; cond; update) loop."""
        init_node = node.child_by_field_name("initializer")
        cond_node = node.child_by_field_name("condition")
        update_node = node.child_by_field_name("update")
        body_node = node.child_by_field_name("body")

        if init_node:
            self._lower_stmt(init_node)

        loop_label = self._fresh_label("for_cond")
        body_label = self._fresh_label("for_body")
        end_label = self._fresh_label("for_end")

        self._emit(Opcode.LABEL, label=loop_label)
        if cond_node:
            cond_reg = self._lower_expr(cond_node)
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{body_label},{end_label}",
            )
        else:
            self._emit(Opcode.BRANCH, label=body_label)

        self._emit(Opcode.LABEL, label=body_label)
        if body_node:
            self._lower_block(body_node)
        if update_node:
            self._lower_expr(update_node)
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_function_def(self, node):
        name_node = node.child_by_field_name(self.FUNC_NAME_FIELD)
        params_node = node.child_by_field_name(self.FUNC_PARAMS_FIELD)
        body_node = node.child_by_field_name(self.FUNC_BODY_FIELD)

        func_name = self._node_text(name_node)
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_params(params_node)

        if body_node:
            self._lower_block(body_node)

        # Implicit return at end of function
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

    def _lower_params(self, params_node):
        """Lower function parameters. Override for language-specific param shapes."""
        for child in params_node.children:
            self._lower_param(child)

    def _lower_param(self, child):
        """Lower a single function parameter to SYMBOLIC + STORE_VAR."""
        if child.type in ("(", ")", ",", ":", "->"):
            return
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

    def _extract_param_name(self, child) -> str | None:
        """Extract parameter name from a parameter node. Override per language."""
        if child.type == "identifier":
            return self._node_text(child)
        # Try common field names
        for field in ("name", "pattern"):
            name_node = child.child_by_field_name(field)
            if name_node:
                return self._node_text(name_node)
        # Try first identifier child
        id_node = next(
            (sub for sub in child.children if sub.type == "identifier"),
            None,
        )
        if id_node:
            return self._node_text(id_node)
        return None

    def _lower_class_def(self, node):
        name_node = node.child_by_field_name(self.CLASS_NAME_FIELD)
        body_node = node.child_by_field_name(self.CLASS_BODY_FIELD)
        class_name = self._node_text(name_node)

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

    def _lower_raise_or_throw(self, node, keyword: str = "raise"):
        children = [c for c in node.children if c.type != keyword]
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
            source_location=self._source_loc(node),
        )

    def _lower_list_literal(self, node) -> str:
        elems = [c for c in node.children if c.type not in ("[", "]", ",")]
        arr_reg = self._fresh_reg()
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
        self._emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["list", size_reg],
            source_location=self._source_loc(node),
        )
        for i, elem in enumerate(elems):
            val_reg = self._lower_expr(elem)
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    def _lower_dict_literal(self, node) -> str:
        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=["dict"],
            source_location=self._source_loc(node),
        )
        for child in node.children:
            if child.type == "pair":
                key_node = child.child_by_field_name("key")
                val_node = child.child_by_field_name("value")
                key_reg = self._lower_expr(key_node)
                val_reg = self._lower_expr(val_node)
                self._emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
        return obj_reg

    def _lower_update_expr(self, node) -> str:
        """Lower i++ / i-- / ++i / --i update expressions."""
        children = [c for c in node.children if c.is_named]
        if not children:
            return self._lower_const_literal(node)
        operand = children[0]
        text = self._node_text(node)
        op = "+" if "++" in text else "-"
        operand_reg = self._lower_expr(operand)
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        result_reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=result_reg,
            operands=[op, operand_reg, one_reg],
            source_location=self._source_loc(node),
        )
        self._lower_store_target(operand, result_reg, node)
        return result_reg

    def _lower_expression_statement(self, node):
        """Lower an expression statement (unwrap and lower the inner expr)."""
        for child in node.children:
            if child.type not in (";",) and child.is_named:
                self._lower_expr(child)
                return
        # Fallback: lower all children
        for child in node.children:
            if child.is_named:
                self._lower_expr(child)

    def _lower_var_declaration(self, node):
        """Lower a variable declaration with name/value fields or declarators."""
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
                    # Declaration without initializer
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
