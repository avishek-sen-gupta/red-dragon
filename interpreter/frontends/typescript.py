"""TypeScriptFrontend — tree-sitter TypeScript AST → IR lowering."""

from __future__ import annotations

from typing import Callable

from .javascript import JavaScriptFrontend
from ..ir import Opcode
from .. import constants


class TypeScriptFrontend(JavaScriptFrontend):
    """Lowers TypeScript AST to IR. Extends JavaScriptFrontend, skipping type annotations."""

    COMMENT_TYPES = frozenset({"comment"})
    NOISE_TYPES = frozenset({"\n"})

    def __init__(self):
        super().__init__()
        # Additional TS expression types
        self._EXPR_DISPATCH.update(
            {
                "type_identifier": self._lower_identifier,
                "predefined_type": self._lower_const_literal,
                "as_expression": self._lower_as_expression,
                "non_null_expression": self._lower_non_null_expr,
                "satisfies_expression": self._lower_satisfies_expr,
            }
        )
        # Additional TS statement types
        self._STMT_DISPATCH.update(
            {
                "interface_declaration": self._lower_interface_decl,
                "enum_declaration": self._lower_enum_decl,
                "type_alias_declaration": lambda _: None,  # skip type aliases
                "export_statement": self._lower_export_statement,
                "import_statement": lambda _: None,
                "abstract_class_declaration": self._lower_class_def,
            }
        )

    # ── TS: skip type annotations in params ──────────────────────

    def _lower_param(self, child):
        if child.type in ("(", ")", ",", ":", "type_annotation"):
            return
        if child.type == "required_parameter":
            pname_node = child.child_by_field_name("pattern")
            if pname_node is None:
                pname_node = next(
                    (c for c in child.children if c.type == "identifier"), None
                )
            if pname_node:
                pname = self._node_text(pname_node)
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
            return
        if child.type == "optional_parameter":
            pname_node = child.child_by_field_name("pattern")
            if pname_node is None:
                pname_node = next(
                    (c for c in child.children if c.type == "identifier"), None
                )
            if pname_node:
                pname = self._node_text(pname_node)
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
            return
        super()._lower_param(child)

    # ── TS: as expression (type cast) ────────────────────────────

    def _lower_as_expression(self, node) -> str:
        # x as Type → just lower x, ignore the type
        children = [c for c in node.children if c.is_named]
        if children:
            return self._lower_expr(children[0])
        return self._lower_const_literal(node)

    def _lower_non_null_expr(self, node) -> str:
        # x! → just lower x
        children = [c for c in node.children if c.is_named]
        if children:
            return self._lower_expr(children[0])
        return self._lower_const_literal(node)

    def _lower_satisfies_expr(self, node) -> str:
        children = [c for c in node.children if c.is_named]
        if children:
            return self._lower_expr(children[0])
        return self._lower_const_literal(node)

    # ── TS: interface → symbolic class ───────────────────────────

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
            node=node,
        )
        body_node = node.child_by_field_name("body")
        if body_node:
            for i, child in enumerate(c for c in body_node.children if c.is_named):
                member_name_node = child.child_by_field_name("name")
                member_name = (
                    self._node_text(member_name_node)
                    if member_name_node
                    else self._node_text(child).split(":")[0].strip()
                )
                key_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
                val_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
                self._emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
        self._emit(Opcode.STORE_VAR, operands=[iface_name, obj_reg])

    # ── TS: enum → symbolic values ───────────────────────────────

    def _lower_enum_decl(self, node):
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        if name_node:
            enum_name = self._node_text(name_node)
            obj_reg = self._fresh_reg()
            self._emit(
                Opcode.NEW_OBJECT,
                result_reg=obj_reg,
                operands=[f"enum:{enum_name}"],
                node=node,
            )
            if body_node:
                for i, child in enumerate(c for c in body_node.children if c.is_named):
                    member_name = self._node_text(child).split("=")[0].strip()
                    key_reg = self._fresh_reg()
                    self._emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
                    val_reg = self._fresh_reg()
                    self._emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
                    self._emit(
                        Opcode.STORE_INDEX,
                        operands=[obj_reg, key_reg, val_reg],
                    )
            self._emit(Opcode.STORE_VAR, operands=[enum_name, obj_reg])

    # ── TS: export statement → unwrap ────────────────────────────

    def _lower_export_statement(self, node):
        for child in node.children:
            if child.is_named and child.type != "export":
                self._lower_stmt(child)
