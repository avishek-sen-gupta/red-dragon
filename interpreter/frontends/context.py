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
from interpreter.constants import CanonicalLiteral, Language
from interpreter.frontend_observer import FrontendObserver
from interpreter.ir import NO_SOURCE_LOCATION, IRInstruction, Opcode, SourceLocation
from interpreter.class_ref import ClassRef
from interpreter.func_ref import FuncRef
from interpreter.type_environment_builder import TypeEnvironmentBuilder
from interpreter.var_scope_info import VarScopeInfo
from interpreter.type_expr import TypeExpr

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

    # For loop
    for_initializer_field: str = "initializer"
    for_condition_field: str = "condition"
    for_body_field: str = "body"
    for_update_field: str = "update"

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
    none_literal: str = CanonicalLiteral.NONE
    true_literal: str = CanonicalLiteral.TRUE
    false_literal: str = CanonicalLiteral.FALSE
    default_return_value: str = CanonicalLiteral.NONE

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
    switch_result_stack: list[str] = field(default_factory=list)

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
    _current_class_name: str = ""

    # When True, lower_block() auto-enters/exits block scopes
    block_scoped: bool = False

    # Block-scope tracking (LLVM-style: frontends disambiguate at emission time)
    _block_scope_stack: list[dict[str, str]] = field(default_factory=list)
    _scope_counter: int = 0
    _var_scope_metadata: dict[str, VarScopeInfo] = field(default_factory=dict)
    _base_declared_vars: set[str] = field(default_factory=set)

    # Function reference symbol table: func_label -> FuncRef
    func_symbol_table: dict[str, FuncRef] = field(default_factory=dict)

    # Class reference symbol table: class_label -> ClassRef
    class_symbol_table: dict[str, ClassRef] = field(default_factory=dict)

    # Byref parameter tracking (C# out/ref/in)
    byref_params: set[str] = field(default_factory=set)

    # Field names for the current class — used to detect implicit this in constructors
    _class_field_names: set[str] = field(default_factory=set)

    # Kotlin property accessors: class_name → {prop_name → {"get", "set"}}
    property_accessors: dict[str, dict[str, set[str]]] = field(default_factory=dict)

    # Temporary context for the `field` keyword inside getter/setter bodies
    _accessor_backing_field: str = ""

    # Default parameter resolution helper — lazily emitted
    _resolve_default_emitted: bool = False

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
        self._track_label(opcode, label)
        self.instructions.append(inst)
        return inst

    def emit_decl_var(self, name: str, val_reg: str, *, node=None) -> IRInstruction:
        """Emit DECL_VAR: declare a new variable in the current scope."""
        return self.emit(Opcode.DECL_VAR, operands=[name, val_reg], node=node)

    def emit_func_ref(
        self,
        func_name: str,
        func_label: str,
        result_reg: str,
        node=None,
    ) -> IRInstruction:
        """Register a function reference in the symbol table and emit CONST.

        Emits the plain func_label as the CONST operand.  The symbol table
        maps func_label → FuncRef(name, label) for downstream consumers.
        """
        self.func_symbol_table[func_label] = FuncRef(name=func_name, label=func_label)
        return self.emit(
            Opcode.CONST,
            result_reg=result_reg,
            operands=[func_label],
            node=node,
        )

    def emit_class_ref(
        self,
        class_name: str,
        class_label: str,
        parents: list[str],
        result_reg: str,
        node=None,
    ) -> IRInstruction:
        """Register a class reference in the symbol table and emit CONST.

        Emits the plain class_label as the CONST operand.  The symbol table
        maps class_label -> ClassRef(name, label, parents) for downstream consumers.
        """
        self.class_symbol_table[class_label] = ClassRef(
            name=class_name, label=class_label, parents=tuple(parents)
        )
        return self.emit(
            Opcode.CONST,
            result_reg=result_reg,
            operands=[class_label],
            node=node,
        )

    def _track_label(self, opcode: Opcode, label: str) -> None:
        """Track current function/class label for param type association."""
        if opcode != Opcode.LABEL:
            return
        if label and label.startswith(constants.FUNC_LABEL_PREFIX):
            self._current_func_label = label
            self.type_env_builder.func_param_types.setdefault(label, [])
        elif (
            label
            and label.startswith(constants.CLASS_LABEL_PREFIX)
            and not label.startswith(constants.END_CLASS_LABEL_PREFIX)
        ):
            self._current_class_name = label.removeprefix(
                constants.CLASS_LABEL_PREFIX
            ).rsplit("_", 1)[0]
            self._current_func_label = ""
        elif label and label.startswith(constants.END_CLASS_LABEL_PREFIX):
            self._current_class_name = ""
            self._current_func_label = ""
        else:
            self._current_func_label = ""

    def seed_func_return_type(self, func_label: str, return_type: TypeExpr) -> None:
        """Seed the return type for a function label."""
        if return_type:
            self.type_env_builder.func_return_types[func_label] = return_type

    def seed_register_type(self, reg: str, type_name: TypeExpr) -> None:
        """Seed the type for a register."""
        if reg and type_name:
            self.type_env_builder.register_types[reg] = type_name

    def seed_var_type(self, var_name: str, type_name: TypeExpr) -> None:
        """Seed the type for a variable."""
        if var_name and type_name:
            self.type_env_builder.var_types[var_name] = type_name

    def seed_interface_impl(self, class_name: str, interface_name: str) -> None:
        """Seed that a class implements an interface."""
        if class_name and interface_name:
            self.type_env_builder.interface_implementations.setdefault(
                class_name, []
            ).append(interface_name)

    def seed_type_alias(self, alias_name: str, target_type: TypeExpr) -> None:
        """Seed a type alias (e.g., typedef int UserId → alias UserId = Int)."""
        if alias_name and target_type:
            self.type_env_builder.type_aliases[alias_name] = target_type

    def seed_param_type(self, param_name: str, type_hint: TypeExpr) -> None:
        """Seed a parameter type for the current function."""
        if self._current_func_label:
            self.type_env_builder.func_param_types[self._current_func_label].append(
                (param_name, type_hint)
            )

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

        When ``block_scoped`` is True and *node* is a block node type,
        a new block scope is entered before lowering and exited after.
        """
        ntype = node.type
        handler = self.stmt_dispatch.get(ntype)
        if handler is not None and ntype not in self.constants.block_node_types:
            handler(self, node)
            return
        scope_entered = self.block_scoped and ntype in self.constants.block_node_types
        if scope_entered:
            self.enter_block_scope()
        for child in node.children:
            if not child.is_named:
                continue
            self.lower_stmt(child)
        if scope_entered:
            self.exit_block_scope()

    def lower_stmt(self, node) -> None:
        ntype = node.type
        if ntype in self.constants.comment_types or ntype in self.constants.noise_types:
            return
        handler = self.stmt_dispatch.get(ntype)
        if handler:
            handler(self, node)
            return
        if ntype in self.constants.block_node_types:
            self.lower_block(node)
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

    # ── block-scope tracking (LLVM-style) ─────────────────────────

    @property
    def var_scope_metadata(self) -> dict[str, VarScopeInfo]:
        """Metadata for mangled variable names: mangled_name → VarScopeInfo."""
        return self._var_scope_metadata

    def enter_block_scope(self) -> None:
        """Push a new block scope onto the scope stack."""
        self._block_scope_stack.append({})

    def exit_block_scope(self) -> None:
        """Pop the innermost block scope."""
        self._block_scope_stack.pop()

    def declare_block_var(self, name: str) -> str:
        """Declare a variable in the current block scope.

        If *name* shadows a variable from an outer scope, returns a mangled
        name (e.g. ``x$1``) and records VarScopeInfo metadata. Otherwise
        returns *name* unchanged.
        """
        # Check if name exists in any outer scope (stack entries or base)
        shadows_outer = (
            any(name in scope for scope in self._block_scope_stack[:-1])
            if self._block_scope_stack
            else False
        )

        # Also check if name was declared at base level (before any scope)
        if not shadows_outer and self._block_scope_stack:
            # Base-level vars are tracked as entries in an implicit scope 0
            # We detect them by checking if name appears in an earlier scope
            # or was declared at scope depth 0 (tracked via metadata lookup)
            shadows_outer = (
                any(name in scope for scope in self._block_scope_stack[:-1])
                or any(
                    info.original_name == name
                    for info in self._var_scope_metadata.values()
                )
                or name in self._base_declared_vars
            )

        if shadows_outer:
            self._scope_counter += 1
            mangled = f"{name}${self._scope_counter}"
            depth = len(self._block_scope_stack)
            self._var_scope_metadata[mangled] = VarScopeInfo(
                original_name=name, scope_depth=depth
            )
            if self._block_scope_stack:
                self._block_scope_stack[-1][name] = mangled
            return mangled

        # No shadowing — record in current scope (if any) or base
        if self._block_scope_stack:
            self._block_scope_stack[-1][name] = name
        else:
            self._base_declared_vars.add(name)
        return name

    def resolve_var(self, name: str) -> str:
        """Resolve a variable name through the block scope stack.

        Walks from innermost to outermost scope, returning the mangled
        name if found. Falls back to the original name.
        """
        for scope in reversed(self._block_scope_stack):
            if name in scope:
                return scope[name]
        return name

    def reset_block_scopes(self) -> None:
        """Clear all block scopes (used at function boundaries)."""
        self._block_scope_stack.clear()
        self._base_declared_vars.clear()
