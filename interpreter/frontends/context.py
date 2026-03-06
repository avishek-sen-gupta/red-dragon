"""TreeSitterEmitContext — shared mutable state for tree-sitter IR lowering.

Analogous to COBOL's EmitContext. Holds registers, labels, instructions,
dispatch tables, and grammar constants. Passed as first argument to all
pure-function lowerers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from interpreter import constants
from interpreter.constants import Language
from interpreter.frontend_observer import FrontendObserver
from interpreter.ir import NO_SOURCE_LOCATION, IRInstruction, Opcode, SourceLocation
from interpreter.type_environment_builder import TypeEnvironmentBuilder

logger = logging.getLogger(__name__)


@dataclass
class GrammarConstants:
    """Overridable grammar field names and literal strings per language."""

    # Function definition
    func_name_field: str = "name"
    func_params_field: str = "parameters"
    func_body_field: str = "body"

    # If statement
    if_condition_field: str = "condition"
    if_consequence_field: str = "consequence"
    if_alternative_field: str = "alternative"

    # While loop
    while_condition_field: str = "condition"
    while_body_field: str = "body"

    # Call expression
    call_function_field: str = "function"
    call_arguments_field: str = "arguments"

    # Class definition
    class_name_field: str = "name"
    class_body_field: str = "body"

    # Attribute access
    attr_object_field: str = "object"
    attr_attribute_field: str = "attribute"

    # Subscript access
    subscript_value_field: str = "value"
    subscript_index_field: str = "subscript"

    # Assignment
    assign_left_field: str = "left"
    assign_right_field: str = "right"

    # Block node types (types treated as iterate-children by lower_block)
    block_node_types: frozenset[str] = frozenset()

    # Canonical literals
    none_literal: str = "None"
    true_literal: str = "True"
    false_literal: str = "False"
    default_return_value: str = "None"

    # Filtering
    comment_types: frozenset[str] = frozenset({"comment"})
    noise_types: frozenset[str] = frozenset({"newline", "\n"})

    # Expression node types
    paren_expr_type: str = "parenthesized_expression"
    attribute_node_type: str = "attribute"


@dataclass
class TreeSitterEmitContext:
    """Shared mutable state for tree-sitter IR lowering.

    All pure-function lowerers receive this as their first argument.
    """

    source: bytes
    language: Language
    observer: FrontendObserver
    constants: GrammarConstants

    # Mutable state
    reg_counter: int = 0
    label_counter: int = 0
    instructions: list[IRInstruction] = field(default_factory=list)
    loop_stack: list[dict[str, str]] = field(default_factory=list)
    break_target_stack: list[str] = field(default_factory=list)

    # Per-language type map: raw type string -> canonical TypeName
    type_map: dict[str, str] = field(default_factory=dict)

    # Dispatch tables: node_type -> Callable[[TreeSitterEmitContext, node], ...]
    stmt_dispatch: dict[str, Callable] = field(default_factory=dict)
    expr_dispatch: dict[str, Callable] = field(default_factory=dict)

    # Type environment builder — accumulates type seeds during lowering
    type_env_builder: TypeEnvironmentBuilder = field(
        default_factory=TypeEnvironmentBuilder
    )
    _current_func_label: str = ""

    # ── utility methods ──────────────────────────────────────────

    def fresh_reg(self) -> str:
        r = f"%{self.reg_counter}"
        self.reg_counter += 1
        return r

    def fresh_label(self, prefix: str = "L") -> str:
        lbl = f"{prefix}_{self.label_counter}"
        self.label_counter += 1
        return lbl

    def emit(
        self,
        opcode: Opcode,
        *,
        result_reg: str = "",
        operands: list[Any] = [],
        label: str = "",
        source_location: SourceLocation = NO_SOURCE_LOCATION,
        node=None,
        type_hint: str = "",
    ) -> IRInstruction:
        loc = (
            source_location
            if not source_location.is_unknown()
            else (self.source_loc(node) if node else NO_SOURCE_LOCATION)
        )
        resolved_operands = operands or []
        inst = IRInstruction(
            opcode=opcode,
            result_reg=result_reg or None,
            operands=resolved_operands,
            label=label or None,
            source_location=loc,
        )
        self._route_type_hint(opcode, result_reg, resolved_operands, label, type_hint)
        self.instructions.append(inst)
        return inst

    def _route_type_hint(
        self,
        opcode: Opcode,
        result_reg: str,
        operands: list[Any],
        label: str,
        type_hint: str,
    ) -> None:
        """Route a type_hint to the appropriate slot in the builder."""
        if opcode == Opcode.LABEL:
            if label and label.startswith(constants.FUNC_LABEL_PREFIX):
                self._current_func_label = label
                self.type_env_builder.func_param_types.setdefault(label, [])
                if type_hint:
                    self.type_env_builder.func_return_types[label] = type_hint
            elif (
                label
                and label.startswith(constants.CLASS_LABEL_PREFIX)
                and not label.startswith(constants.END_CLASS_LABEL_PREFIX)
            ):
                self._current_func_label = ""
            else:
                self._current_func_label = ""
            return

        if opcode == Opcode.SYMBOLIC:
            if type_hint and result_reg:
                self.type_env_builder.register_types[result_reg] = type_hint
            if self._current_func_label and operands:
                operand = str(operands[0])
                if operand.startswith("param:"):
                    param_name = operand[len("param:") :]
                    self.type_env_builder.func_param_types[
                        self._current_func_label
                    ].append((param_name, type_hint or ""))
            return

        if opcode == Opcode.STORE_VAR and type_hint and operands:
            self.type_env_builder.var_types[str(operands[0])] = type_hint
            return

        if opcode == Opcode.CALL_FUNCTION and type_hint and result_reg:
            self.type_env_builder.register_types[result_reg] = type_hint
            return

    def node_text(self, node) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8")

    def source_loc(self, node) -> SourceLocation:
        s, e = node.start_point, node.end_point
        return SourceLocation(
            start_line=s[0] + 1,
            start_col=s[1],
            end_line=e[0] + 1,
            end_col=e[1],
        )

    # ── recursive descent entry points ───────────────────────────

    def lower_block(self, node) -> None:
        """Lower a block of statements (module / suite / body).

        If *node* is itself a known statement whose handler is NOT a
        block-iterate handler, it is lowered directly.
        """
        ntype = node.type
        handler = self.stmt_dispatch.get(ntype)
        if handler is not None and ntype not in self.constants.block_node_types:
            handler(self, node)
            return
        for child in node.children:
            if not child.is_named:
                continue
            self.lower_stmt(child)

    def lower_stmt(self, node) -> None:
        ntype = node.type
        if ntype in self.constants.comment_types or ntype in self.constants.noise_types:
            return
        handler = self.stmt_dispatch.get(ntype)
        if handler:
            handler(self, node)
            return
        # Fallback: try as expression
        self.lower_expr(node)

    def lower_expr(self, node) -> str:
        """Lower an expression, return the register holding its value."""
        handler = self.expr_dispatch.get(node.type)
        if handler:
            return handler(self, node)
        # Fallback: symbolic
        reg = self.fresh_reg()
        self.emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"unsupported:{node.type}"],
            node=node,
        )
        return reg

    # ── loop stack management ────────────────────────────────────

    def push_loop(self, continue_label: str, end_label: str) -> None:
        self.loop_stack.append(
            {"continue_label": continue_label, "end_label": end_label}
        )
        self.break_target_stack.append(end_label)

    def pop_loop(self) -> None:
        self.loop_stack.pop()
        self.break_target_stack.pop()
