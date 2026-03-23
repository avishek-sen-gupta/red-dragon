"""BaseFrontend — language-agnostic tree-sitter AST → IR lowering infrastructure.

Supports two modes:
  1. **Context mode** (new): subclass overrides ``_build_constants()``,
     ``_build_stmt_dispatch()``, ``_build_expr_dispatch()`` returning pure functions.
  2. **Legacy mode**: subclass populates ``_STMT_DISPATCH`` / ``_EXPR_DISPATCH``
     dicts with bound methods in ``__init__``.

Legacy mode is detected automatically when ``_STMT_DISPATCH`` or ``_EXPR_DISPATCH``
is non-empty.  Once all frontends are converted, legacy code will be removed.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from interpreter.frontend import Frontend
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.frontends.base_node_types import BaseNodeType
from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.ir import NO_SOURCE_LOCATION, IRInstruction, Opcode, SourceLocation, CodeLabel, NO_LABEL
from interpreter.register import Register, NO_REGISTER
from interpreter.parser import ParserFactory
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter import constants
from interpreter.constants import CanonicalLiteral, DEFAULT_EXCEPTION_TYPE, Language

logger = logging.getLogger(__name__)


class BaseFrontend(Frontend):
    """Base class for deterministic tree-sitter frontends.

    Converted frontends override ``_build_constants``, ``_build_stmt_dispatch``,
    and ``_build_expr_dispatch``.  Unconverted frontends populate
    ``_STMT_DISPATCH`` and ``_EXPR_DISPATCH`` tables in ``__init__``.
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

    FOR_CONDITION_FIELD: str = "condition"
    FOR_BODY_FIELD: str = "body"
    FOR_UPDATE_FIELD: str = "update"

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

    NONE_LITERAL: str = CanonicalLiteral.NONE
    TRUE_LITERAL: str = CanonicalLiteral.TRUE
    FALSE_LITERAL: str = CanonicalLiteral.FALSE
    DEFAULT_RETURN_VALUE: str = CanonicalLiteral.NONE

    COMMENT_TYPES: frozenset[str] = frozenset({BaseNodeType.COMMENT})
    NOISE_TYPES: frozenset[str] = frozenset(
        {BaseNodeType.NEWLINE, BaseNodeType.NEWLINE_CHAR}
    )

    PAREN_EXPR_TYPE: str = BaseNodeType.PARENTHESIZED_EXPRESSION

    ATTRIBUTE_NODE_TYPE: str = BaseNodeType.ATTRIBUTE

    BLOCK_SCOPED: bool = False

    # ── init ─────────────────────────────────────────────────────

    def __init__(
        self,
        parser_factory: ParserFactory,
        language: Language,
        observer: FrontendObserver = NullFrontendObserver(),
    ):
        self._parser_factory = parser_factory
        self._language = language
        self._observer = observer
        self._type_env_builder: TypeEnvironmentBuilder = TypeEnvironmentBuilder()
        self._func_symbol_table: dict[CodeLabel, FuncRef] = {}
        self._class_symbol_table: dict[CodeLabel, ClassRef] = {}
        self._symbol_table: SymbolTable = SymbolTable.empty()
        # Legacy state (used only by unconverted frontends)
        self._reg_counter: int = 0
        self._label_counter: int = 0
        self._instructions: list[IRInstruction] = []
        self._source: bytes = b""
        self._loop_stack: list[dict[str, str]] = []
        self._break_target_stack: list[str] = []
        self._STMT_DISPATCH: dict[str, Callable] = {}
        self._EXPR_DISPATCH: dict[str, Callable] = {}

    # ── helpers ──────────────────────────────────────────────────

    def _fresh_reg(self) -> Register:
        r = Register(f"%{self._reg_counter}")
        self._reg_counter += 1
        return r

    def _fresh_label(self, prefix: str = "L") -> CodeLabel:
        lbl = CodeLabel(f"{prefix}_{self._label_counter}")
        self._label_counter += 1
        return lbl

    def _emit(
        self,
        opcode: Opcode,
        *,
        result_reg: Register = NO_REGISTER,
        operands: list[Any] = [],
        label: CodeLabel = NO_LABEL,
        branch_targets: list[CodeLabel] = [],
        source_location: SourceLocation = NO_SOURCE_LOCATION,
        node=None,
    ) -> IRInstruction:
        loc = (
            source_location
            if not source_location.is_unknown()
            else (self._source_loc(node) if node else NO_SOURCE_LOCATION)
        )
        inst = IRInstruction(
            opcode=opcode,
            result_reg=result_reg,
            operands=[str(op) if isinstance(op, Register) else op for op in (operands or [])],
            label=label,
            branch_targets=branch_targets,
            source_location=loc,
        )
        self._instructions.append(inst)
        return inst

    def _node_text(self, node) -> str:
        return self._source[node.start_byte : node.end_byte].decode("utf-8")

    def _source_loc(self, node) -> SourceLocation:
        s, e = node.start_point, node.end_point
        return SourceLocation(
            start_line=s[0] + 1,
            start_col=s[1],
            end_line=e[0] + 1,
            end_col=e[1],
        )

    @property
    def type_env_builder(self) -> TypeEnvironmentBuilder:
        return self._type_env_builder

    @property
    def func_symbol_table(self) -> dict[CodeLabel, FuncRef]:
        return self._func_symbol_table

    @property
    def class_symbol_table(self) -> dict[CodeLabel, ClassRef]:
        return self._class_symbol_table

    @property
    def symbol_table(self) -> SymbolTable:
        return self._symbol_table

    def _emit_class_ref(
        self,
        class_name: str,
        class_label: str,
        parents: list[str],
        result_reg: str,
        node=None,
    ) -> IRInstruction:
        """Legacy-mode equivalent of ctx.emit_class_ref().

        Emits the plain class_label as the CONST operand.  The symbol table
        maps class_label -> ClassRef(name, label, parents) for downstream consumers.
        """
        self._class_symbol_table[class_label] = ClassRef(
            name=class_name, label=class_label, parents=tuple(parents)
        )
        return self._emit(
            Opcode.CONST,
            result_reg=result_reg,
            operands=[str(class_label)],
            node=node,
        )

    def _emit_func_ref(
        self, func_name: str, func_label: CodeLabel, result_reg: str, node=None
    ) -> IRInstruction:
        """Legacy-mode equivalent of ctx.emit_func_ref().

        Emits the plain func_label as the CONST operand.  The symbol table
        maps func_label → FuncRef(name, label) for downstream consumers.
        """
        self._func_symbol_table[func_label] = FuncRef(name=func_name, label=func_label)
        return self._emit(
            Opcode.CONST,
            result_reg=result_reg,
            operands=[str(func_label)],
            node=node,
        )

    # ── context-mode hooks (override in subclasses for pure-function dispatch) ──

    def _build_constants(self):
        """Override to return a GrammarConstants for context-mode dispatch."""
        return None

    def _build_stmt_dispatch(self) -> dict[str, Callable]:
        """Override to return stmt dispatch table for context-mode dispatch."""
        return {}

    def _build_expr_dispatch(self) -> dict[str, Callable]:
        """Override to return expr dispatch table for context-mode dispatch."""
        return {}

    def _build_type_map(self) -> dict[str, str]:
        """Override to return a raw-type → canonical-type mapping."""
        return {}

    # ── entry point ──────────────────────────────────────────────

    def lower(self, source: bytes) -> list[IRInstruction]:
        t0 = time.perf_counter()
        parser = self._parser_factory.get_parser(self._language)
        tree = parser.parse(source)
        self._observer.on_parse(time.perf_counter() - t0)

        t1 = time.perf_counter()
        root = tree.root_node

        grammar_constants = self._build_constants()
        if grammar_constants is not None:
            result = self._lower_with_context(source, root)
        else:
            self._reg_counter = 0
            self._label_counter = 0
            self._instructions = []
            self._source = source
            self._loop_stack = []
            self._break_target_stack = []
            self._emit(Opcode.LABEL, label=CodeLabel(constants.CFG_ENTRY_LABEL))
            self._lower_block(root)
            result = self._instructions

        self._observer.on_lower(time.perf_counter() - t1)
        return result

    def _lower_with_context(self, source: bytes, root) -> list[IRInstruction]:
        """Context-mode lowering using TreeSitterEmitContext and pure functions."""
        grammar_constants = self._build_constants()
        symbol_table = self._extract_symbols(root)
        ctx = TreeSitterEmitContext(
            source=source,
            language=self._language,
            observer=self._observer,
            constants=grammar_constants,
            type_map=self._build_type_map(),
            stmt_dispatch=self._build_stmt_dispatch(),
            expr_dispatch=self._build_expr_dispatch(),
            block_scoped=self.BLOCK_SCOPED,
            symbol_table=symbol_table,
        )
        ctx.emit(Opcode.LABEL, label=CodeLabel(constants.CFG_ENTRY_LABEL))
        self._emit_prelude(ctx)
        ctx.lower_block(root)
        self._type_env_builder = ctx.type_env_builder
        self._type_env_builder.var_scope_metadata = dict(ctx.var_scope_metadata)
        self._func_symbol_table = ctx.func_symbol_table
        self._class_symbol_table = ctx.class_symbol_table
        self._symbol_table = ctx.symbol_table
        return ctx.instructions

    def _extract_symbols(self, root) -> SymbolTable:
        """Override in subclasses to extract symbols before lowering."""
        return SymbolTable.empty()

    def _emit_prelude(self, ctx: TreeSitterEmitContext) -> None:
        """Override in subclasses to emit prelude type definitions."""

    # ── dispatchers ──────────────────────────────────────────────

    def _lower_block(self, node):
        """Lower a block of statements (module / suite / body).

        If *node* is itself a known statement whose handler is **not**
        ``_lower_block`` (e.g. a bare ``return_statement`` used as the
        consequence of an ``if``), it is lowered directly rather than
        iterating its children as sub-statements.
        """
        handler = self._STMT_DISPATCH.get(node.type)
        if (
            handler is not None
            and getattr(handler, "__func__", None) is not BaseFrontend._lower_block
        ):
            handler(node)
            return
        for child in node.children:
            if not child.is_named:
                continue
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
            node=node,
        )
        return reg

    # ── common expression lowerers ───────────────────────────────

    def _lower_interpolated_string_parts(self, parts: list[str], node) -> str:
        """Chain a list of string-part registers with BINOP '+' concatenation."""
        if not parts:
            return self._lower_const_literal(node)
        result = parts[0]
        for part in parts[1:]:
            new_reg = self._fresh_reg()
            self._emit(
                Opcode.BINOP,
                result_reg=new_reg,
                operands=["+", result, part],
                node=node,
            )
            result = new_reg
        return result

    def _lower_const_literal(self, node) -> str:
        reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=reg,
            operands=[self._node_text(node)],
            node=node,
        )
        return reg

    def _lower_canonical_none(self, node) -> str:
        """Emit canonical ``CONST "None"`` for any language's null/nil/undefined."""
        reg = self._fresh_reg()
        self._emit(
            Opcode.CONST, result_reg=reg, operands=[self.NONE_LITERAL], node=node
        )
        return reg

    def _lower_canonical_true(self, node) -> str:
        """Emit canonical ``CONST "True"``."""
        reg = self._fresh_reg()
        self._emit(
            Opcode.CONST, result_reg=reg, operands=[self.TRUE_LITERAL], node=node
        )
        return reg

    def _lower_canonical_false(self, node) -> str:
        """Emit canonical ``CONST "False"``."""
        reg = self._fresh_reg()
        self._emit(
            Opcode.CONST, result_reg=reg, operands=[self.FALSE_LITERAL], node=node
        )
        return reg

    def _lower_canonical_bool(self, node) -> str:
        """Emit canonical ``CONST "True"`` or ``CONST "False"`` based on node text."""
        text = self._node_text(node).strip().lower()
        if text == "true":
            return self._lower_canonical_true(node)
        return self._lower_canonical_false(node)

    def _lower_identifier(self, node) -> str:
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_VAR,
            result_reg=reg,
            operands=[self._node_text(node)],
            node=node,
        )
        return reg

    def _lower_paren(self, node) -> str:
        inner = next(
            (
                c
                for c in node.children
                if c.type not in (BaseNodeType.OPEN_PAREN, BaseNodeType.CLOSE_PAREN)
            ),
            None,
        )
        if inner is None:
            return self._lower_const_literal(node)
        return self._lower_expr(inner)

    def _lower_binop(self, node) -> str:
        children = [
            c
            for c in node.children
            if c.type not in (BaseNodeType.OPEN_PAREN, BaseNodeType.CLOSE_PAREN)
        ]
        lhs_reg = self._lower_expr(children[0])
        op = self._node_text(children[1])
        rhs_reg = self._lower_expr(children[2])
        reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=reg,
            operands=[op, lhs_reg, rhs_reg],
            node=node,
        )
        return reg

    def _lower_comparison(self, node) -> str:
        children = [
            c
            for c in node.children
            if c.type not in (BaseNodeType.OPEN_PAREN, BaseNodeType.CLOSE_PAREN)
        ]
        lhs_reg = self._lower_expr(children[0])
        op = self._node_text(children[1])
        rhs_reg = self._lower_expr(children[2])
        reg = self._fresh_reg()
        self._emit(
            Opcode.BINOP,
            result_reg=reg,
            operands=[op, lhs_reg, rhs_reg],
            node=node,
        )
        return reg

    def _lower_unop(self, node) -> str:
        children = [
            c
            for c in node.children
            if c.type not in (BaseNodeType.OPEN_PAREN, BaseNodeType.CLOSE_PAREN)
        ]
        op = self._node_text(children[0])
        operand_reg = self._lower_expr(children[1])
        reg = self._fresh_reg()
        self._emit(
            Opcode.UNOP,
            result_reg=reg,
            operands=[op, operand_reg],
            node=node,
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
            BaseNodeType.MEMBER_EXPRESSION,
            BaseNodeType.SELECTOR_EXPRESSION,
            BaseNodeType.MEMBER_ACCESS_EXPRESSION,
            BaseNodeType.FIELD_ACCESS,
            BaseNodeType.METHOD_INDEX_EXPRESSION,
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
                    node=node,
                )
                return reg

        # Plain function call
        if func_node and func_node.type == BaseNodeType.IDENTIFIER:
            func_name = self._node_text(func_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=reg,
                operands=[func_name] + arg_regs,
                node=node,
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
            node=node,
        )
        return reg

    def _extract_call_args(self, args_node) -> list[str]:
        """Extract argument registers from a call arguments node."""
        if args_node is None:
            return []
        return [
            self._lower_expr(c)
            for c in args_node.children
            if c.type
            not in (
                BaseNodeType.OPEN_PAREN,
                BaseNodeType.CLOSE_PAREN,
                BaseNodeType.COMMA,
                BaseNodeType.ARGUMENT,
                BaseNodeType.VALUE_ARGUMENT,
            )
            and c.is_named
        ]

    def _extract_call_args_unwrap(self, args_node) -> list[str]:
        """Extract args, unwrapping wrapper nodes like 'argument'."""
        if args_node is None:
            return []
        regs = []
        for c in args_node.children:
            if c.type in (
                BaseNodeType.OPEN_PAREN,
                BaseNodeType.CLOSE_PAREN,
                BaseNodeType.COMMA,
            ):
                continue
            if c.type in (BaseNodeType.ARGUMENT, BaseNodeType.VALUE_ARGUMENT):
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
            node=node,
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
            node=node,
        )
        return reg

    # ── common store target ──────────────────────────────────────

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == BaseNodeType.IDENTIFIER:
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                node=parent_node,
            )
        elif target.type in (
            self.ATTRIBUTE_NODE_TYPE,
            BaseNodeType.MEMBER_EXPRESSION,
            BaseNodeType.SELECTOR_EXPRESSION,
            BaseNodeType.MEMBER_ACCESS_EXPRESSION,
            BaseNodeType.FIELD_ACCESS,
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
                    node=parent_node,
                )
        elif target.type == BaseNodeType.SUBSCRIPT:
            obj_node = target.child_by_field_name(self.SUBSCRIPT_VALUE_FIELD)
            idx_node = target.child_by_field_name(self.SUBSCRIPT_INDEX_FIELD)
            if obj_node and idx_node:
                obj_reg = self._lower_expr(obj_node)
                idx_reg = self._lower_expr(idx_node)
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                    node=parent_node,
                )
        else:
            # Fallback: just store to the text of the target
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                node=parent_node,
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
            node=node,
        )
        self._lower_store_target(left, result, node)

    def _lower_return(self, node):
        """Lower a return statement. Override for language-specific keyword."""
        children = [c for c in node.children if c.type != BaseNodeType.RETURN]
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
                branch_targets=[true_label, false_label],
                node=node,
            )
        else:
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                branch_targets=[true_label, end_label],
                node=node,
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
        if alt_type in (BaseNodeType.ELIF_CLAUSE,):
            self._lower_elif(alt_node, end_label)
        elif alt_type in (BaseNodeType.ELSE_CLAUSE, BaseNodeType.ELSE):
            body = alt_node.child_by_field_name("body")
            if body:
                self._lower_block(body)
            else:
                for child in alt_node.children:
                    if child.type not in (
                        BaseNodeType.ELSE,
                        BaseNodeType.COLON,
                        BaseNodeType.OPEN_BRACE,
                        BaseNodeType.CLOSE_BRACE,
                    ):
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
            branch_targets=[true_label, false_label],
            node=node,
        )

        self._emit(Opcode.LABEL, label=true_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            self._lower_alternative(alt_node, end_label)
            self._emit(Opcode.BRANCH, label=end_label)

    def _lower_break(self, node):
        """Lower break statement as BRANCH to innermost break target."""
        if self._break_target_stack:
            self._emit(
                Opcode.BRANCH,
                label=self._break_target_stack[-1],
                node=node,
            )
        else:
            reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=reg,
                operands=["break_outside_loop_or_switch"],
                node=node,
            )

    def _lower_continue(self, node):
        """Lower continue statement as BRANCH to innermost loop continue label."""
        if self._loop_stack:
            self._emit(
                Opcode.BRANCH,
                label=self._loop_stack[-1]["continue_label"],
                node=node,
            )
        else:
            reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=reg,
                operands=["continue_outside_loop"],
                node=node,
            )

    def _push_loop(self, continue_label: str, end_label: str):
        """Push a loop context onto both the loop stack and break target stack."""
        self._loop_stack.append(
            {"continue_label": continue_label, "end_label": end_label}
        )
        self._break_target_stack.append(end_label)

    def _pop_loop(self):
        """Pop a loop context from both stacks."""
        self._loop_stack.pop()
        self._break_target_stack.pop()

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
            branch_targets=[body_label, end_label],
            node=node,
        )

        self._emit(Opcode.LABEL, label=body_label)
        self._push_loop(loop_label, end_label)
        self._lower_block(body_node)
        self._pop_loop()
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_c_style_for(self, node):
        """Lower a C-style for(init; cond; update) loop."""
        init_node = node.child_by_field_name("initializer")
        cond_node = node.child_by_field_name(self.FOR_CONDITION_FIELD)
        update_node = node.child_by_field_name(self.FOR_UPDATE_FIELD)
        body_node = node.child_by_field_name(self.FOR_BODY_FIELD)

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
                branch_targets=[body_label, end_label],
                node=node,
            )
        else:
            self._emit(Opcode.BRANCH, label=body_label)

        self._emit(Opcode.LABEL, label=body_label)
        update_label = self._fresh_label("for_update") if update_node else loop_label
        self._push_loop(update_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()
        if update_node:
            self._emit(Opcode.LABEL, label=update_label)
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

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_params(params_node)

        if body_node:
            self._lower_block(body_node)

        # Implicit return at end of function
        none_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[self.DEFAULT_RETURN_VALUE],
            node=node,
        )
        self._emit(Opcode.RETURN, operands=[none_reg], node=node)

        self._emit(Opcode.LABEL, label=end_label)

        func_reg = self._fresh_reg()
        self._emit_func_ref(func_name, func_label, result_reg=func_reg, node=node)
        self._emit(Opcode.DECL_VAR, operands=[func_name, func_reg], node=node)

    def _lower_params(self, params_node):
        """Lower function parameters. Override for language-specific param shapes."""
        for child in params_node.children:
            self._lower_param(child)

    def _lower_param(self, child):
        """Lower a single function parameter to SYMBOLIC + DECL_VAR."""
        if child.type in (
            BaseNodeType.OPEN_PAREN,
            BaseNodeType.CLOSE_PAREN,
            BaseNodeType.COMMA,
            BaseNodeType.COLON,
            BaseNodeType.ARROW,
        ):
            return
        pname = self._extract_param_name(child)
        if pname is None:
            return
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=self._fresh_reg(),
            operands=[f"{constants.PARAM_PREFIX}{pname}"],
            node=child,
        )
        self._emit(
            Opcode.DECL_VAR,
            operands=[pname, f"%{self._reg_counter - 1}"],
            node=child,
        )

    def _extract_param_name(self, child) -> str | None:
        """Extract parameter name from a parameter node. Override per language."""
        if child.type == BaseNodeType.IDENTIFIER:
            return self._node_text(child)
        # Try common field names
        for field in ("name", "pattern"):
            name_node = child.child_by_field_name(field)
            if name_node:
                return self._node_text(name_node)
        # Try first identifier child
        id_node = next(
            (sub for sub in child.children if sub.type == BaseNodeType.IDENTIFIER),
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

        self._emit(Opcode.BRANCH, label=end_label, node=node)
        self._emit(Opcode.LABEL, label=class_label)
        if body_node:
            self._lower_block(body_node)
        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit_class_ref(class_name, class_label, [], result_reg=cls_reg)
        self._emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])

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
            node=node,
        )

    def _lower_list_literal(self, node) -> str:
        elems = [
            c
            for c in node.children
            if c.type
            not in (
                BaseNodeType.OPEN_BRACKET,
                BaseNodeType.CLOSE_BRACKET,
                BaseNodeType.COMMA,
            )
        ]
        arr_reg = self._fresh_reg()
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
        self._emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["list", size_reg],
            node=node,
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
            node=node,
        )
        for child in node.children:
            if child.type == BaseNodeType.PAIR:
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
            node=node,
        )
        self._lower_store_target(operand, result_reg, node)
        return result_reg

    def _lower_try_catch(
        self,
        node,
        body_node,
        catch_clauses: list[dict],
        finally_node=None,
        else_node=None,
    ):
        """Lower try/catch/finally into labeled blocks connected by BRANCH.

        Each catch dict: {"body": node, "variable": str|None, "type": str|None}
        """
        try_body_label = self._fresh_label("try_body")
        catch_labels = [
            self._fresh_label(f"catch_{i}") for i in range(len(catch_clauses))
        ]
        finally_label = self._fresh_label("try_finally") if finally_node else NO_LABEL
        else_label = self._fresh_label("try_else") if else_node else NO_LABEL
        end_label = self._fresh_label("try_end")

        exit_target = finally_label if finally_label.is_present() else end_label

        # ── push exception handler ──
        self._emit(
            Opcode.TRY_PUSH,
            operands=[
                catch_labels,
                finally_label,
                end_label,
            ],
        )

        # ── try body ──
        self._emit(Opcode.LABEL, label=try_body_label)
        if body_node:
            self._lower_block(body_node)
        # ── pop exception handler (normal exit) ──
        self._emit(Opcode.TRY_POP)
        # After try body: jump to else (if present), then finally/end
        if else_label:
            self._emit(Opcode.BRANCH, label=else_label)
        else:
            self._emit(Opcode.BRANCH, label=exit_target)

        # ── catch clauses ──
        for i, clause in enumerate(catch_clauses):
            self._emit(Opcode.LABEL, label=catch_labels[i])
            exc_type = (
                clause.get("type", DEFAULT_EXCEPTION_TYPE) or DEFAULT_EXCEPTION_TYPE
            )
            exc_reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=exc_reg,
                operands=[f"{constants.CAUGHT_EXCEPTION_PREFIX}:{exc_type}"],
                node=node,
            )
            exc_var = clause.get("variable")
            if exc_var:
                self._emit(
                    Opcode.DECL_VAR,
                    operands=[exc_var, exc_reg],
                    node=node,
                )
            catch_body = clause.get("body")
            if catch_body:
                self._lower_block(catch_body)
            self._emit(Opcode.BRANCH, label=exit_target)

        # ── else clause (Python/Ruby) ──
        if else_node:
            self._emit(Opcode.LABEL, label=else_label)
            self._lower_block(else_node)
            self._emit(Opcode.BRANCH, label=finally_label if finally_label.is_present() else end_label)

        # ── finally clause ──
        if finally_node:
            self._emit(Opcode.LABEL, label=finally_label)
            self._lower_block(finally_node)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_expression_statement(self, node):
        """Lower an expression statement (unwrap and lower the inner expr).

        If the inner node is a known statement (e.g. ``while_expression`` in
        Rust), dispatch via ``_lower_stmt`` so statement-only handlers are
        reachable.
        """
        for child in node.children:
            if child.type not in (BaseNodeType.SEMICOLON,) and child.is_named:
                self._lower_stmt(child)
                return
        for child in node.children:
            if child.is_named:
                self._lower_stmt(child)

    def _lower_var_declaration(self, node):
        """Lower a variable declaration with name/value fields or declarators."""
        for child in node.children:
            if child.type == BaseNodeType.VARIABLE_DECLARATOR:
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node and value_node:
                    val_reg = self._lower_expr(value_node)
                    self._emit(
                        Opcode.DECL_VAR,
                        operands=[self._node_text(name_node), val_reg],
                        node=node,
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
                        Opcode.DECL_VAR,
                        operands=[self._node_text(name_node), val_reg],
                        node=node,
                    )
