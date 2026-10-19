"""EmitContext — shared mutable state and emit primitives for COBOL lowering.

All lowering functions receive an EmitContext and operate on it.  The context
holds the instruction buffer, register/label counters, the procedure
labels, and convenience methods for emitting IR.

Circular dependency between lowering functions and the statement dispatcher
is broken by injecting a *dispatch callback* at construction time.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any

from interpreter.cobol.compile_options import CompileOptions

if TYPE_CHECKING:
    from cobol_asg.cobol_expression import ExprNode

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_statements import ProcedureRef
from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_asg.nonnumeric_literal import literal_characters
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.source_span import SourceSpan
from cobol_memory.field_extent import FieldExtent, Precision
from cobol_memory.region_id import RegionId
from cobol_numeric.number import from_literal, is_cobol_number
from interpreter.cobol.alter_table import AlterTable
from interpreter.cobol.alterable_goto import AlterableGoto
from interpreter.cobol.alphanumeric import (
    decode_alphanumeric,
    encode_hex_literal,
    parse_hex_literal,
)
from interpreter.cobol.binary_digits_ir import build_binary_picture_digits_ir
from interpreter.cobol.class_name_index import ClassNameIndex
from interpreter.cobol.cobol_constants import BuiltinName, ByteConstants, CobolEncoding
from interpreter.cobol.collating_sequences import collating_sequence_of
from interpreter.cobol.condition_name_index import ConditionNameIndex
from interpreter.cobol.data_layout import DataItemMatch, DataLayout, FieldLayout
from interpreter.cobol.field_resolution import ResolvedFieldRef, field_access_extent
from interpreter.cobol.program_object import program_name
from interpreter.cobol.figurative_constants import FIGURATIVE_ZEROS
from interpreter.cobol.ir_encoders import (
    build_decode_alphanumeric_ir,
    build_decode_binary_ir,
    build_decode_comp3_ir,
    build_decode_float_ir,
    build_decode_zoned_ir,
    build_decode_zoned_separate_ir,
    build_encode_alphanumeric_ir,
    build_encode_alphanumeric_justified_ir,
    build_encode_binary_ir,
    build_encode_comp3_ir,
    build_encode_float_ir,
    build_encode_zoned_ir,
    build_encode_zoned_separate_ir,
)
from interpreter.cobol.odo_tail import OdoTail
from interpreter.cobol.pic_scale import encode_digits
from interpreter.cobol.procedure_labels import ProcedureLabels
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.source_spans import to_source_location
from interpreter.cobol.switch_index import SwitchIndex
from interpreter.cobol.undeclared_data_name import UndeclaredDataName
from interpreter.cobol.undeclared_data_name_error import UndeclaredDataNameError
from interpreter.constants import FoundationTypeName
from interpreter.continuation_name import ContinuationName
from interpreter.frontend_extension_lowering import RedDragonExtensionLoweringStrategy
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    CallFunction,
    Const,
    InstructionBase,
    Label_,
    LoadRegion,
    Return_,
    WriteRegion,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.register import NO_REGISTER, Register
from interpreter.types.type_expr import array_of, scalar

logger = logging.getLogger(__name__)


# Type alias for the dispatch callback signature.
# Any is CobolStatementType — avoided here to prevent a circular import via statement_dispatch.
DispatchFn = Callable[
    ["EmitContext", Any, "MaterialisedSectionedLayout"], None
]  # Any: CobolStatementType, circular-import boundary


def _decode_ir(fl: FieldLayout) -> list[InstructionBase]:
    td = fl.type_descriptor
    if td.holds_characters or td.category == CobolDataCategory.NUMERIC_EDITED:
        # The FILE-section region holds the file's raw bytes; a real dataset
        # is EBCDIC, exactly like WS/LS/LK regions — so alphanumeric FD
        # fields decode as EBCDIC too. Decoding them as LATIN-1 (the removed
        # f6d84cfb branch) matched only an ASCII stub and mangled real EBCDIC
        # files, breaking e.g. FUNCTION UPPER-CASE(FD-record) (red-dragon-uxpp).
        return build_decode_alphanumeric_ir(f"dec_alpha_{fl.name}")
    return _NUMERIC_DECODE_IR[td.category](fl)


def _decode_zoned_ir(fl: FieldLayout) -> list[InstructionBase]:
    td = fl.type_descriptor
    if td.sign_separate:
        return build_decode_zoned_separate_ir(
            f"dec_zoned_sep_{fl.name}",
            td.total_digits,
            td.decimal_digits,
            sign_leading=td.sign_leading,
        )
    return build_decode_zoned_ir(
        f"dec_zoned_{fl.name}",
        td.total_digits,
        td.decimal_digits,
        sign_leading=td.sign_leading,
    )


def _decode_binary_ir(fl: FieldLayout) -> list[InstructionBase]:
    td = fl.type_descriptor
    return build_decode_binary_ir(
        f"dec_bin_{fl.name}", td.byte_length, td.decimal_digits, td.signed
    )


def _decode_float_ir(fl: FieldLayout) -> list[InstructionBase]:
    return build_decode_float_ir(f"dec_float_{fl.name}", fl.type_descriptor.byte_length)


def _decode_comp3_ir(fl: FieldLayout) -> list[InstructionBase]:
    td = fl.type_descriptor
    return build_decode_comp3_ir(
        f"dec_comp3_{fl.name}", td.total_digits, td.decimal_digits
    )


_NUMERIC_DECODE_IR: Mapping[
    CobolDataCategory, Callable[[FieldLayout], list[InstructionBase]]
] = {
    CobolDataCategory.ZONED_DECIMAL: _decode_zoned_ir,
    CobolDataCategory.BINARY: _decode_binary_ir,
    CobolDataCategory.COMP1: _decode_float_ir,
    CobolDataCategory.COMP2: _decode_float_ir,
    CobolDataCategory.COMP3: _decode_comp3_ir,
}


_NULL_OBSERVER = NullFrontendObserver()
_NO_CONDITION_NAMES = ConditionNameIndex({})
_EMPTY_ASG = CobolASG()
_DEFAULT_OPTIONS = CompileOptions()


class EmitContext:
    """Shared state and emit primitives for COBOL IR lowering."""

    def __init__(
        self,
        dispatch_fn: DispatchFn,
        observer: FrontendObserver = _NULL_OBSERVER,
        condition_index: ConditionNameIndex = _NO_CONDITION_NAMES,
        extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
        asg: CobolASG = _EMPTY_ASG,
        options: CompileOptions = _DEFAULT_OPTIONS,
    ) -> None:
        self._dispatch_fn = dispatch_fn
        self.addressing_mode = options.addressing_mode
        # Opt-in: skip (with a WARNING) statements whose lowering raises, e.g.
        # references to fields from missing/stub copybooks. Off by default so
        # lowering errors (ambiguous references etc.) surface.
        self._tolerant = options.tolerant
        self._compiled_at = options.clock.now()
        self._observer = observer
        self._condition_index = condition_index
        self._extension_strategies = tuple(extension_strategies)
        self._asg: CobolASG = asg
        self.collating_sequence = collating_sequence_of(asg.collating_sequence)
        self.alphabets = tuple(asg.alphabets)
        self.switches = SwitchIndex(asg.switches)
        self.class_names = ClassNameIndex(asg.classes)
        self.figuratives = self.collating_sequence.figuratives()
        self._instructions: list[InstructionBase] = []
        self._reg_counter: int = 0
        self._label_counter: int = 0
        self._procedures: ProcedureLabels = ProcedureLabels()
        self._paragraph: str = ""
        self._section: str = ""
        self._requested_exits: set[CodeLabel] = set()
        self._alters: AlterTable = AlterTable()
        self._sentence: CodeLabel = CodeLabel("")
        self._perform_scopes: int = 0
        self._perform_leave: CodeLabel = CodeLabel("")
        self._perform_cycle: CodeLabel = CodeLabel("")

    # ── Properties ────────────────────────────────────────────────

    @property
    def instructions(self) -> list[InstructionBase]:
        return self._instructions

    @property
    def procedures(self) -> ProcedureLabels:
        return self._procedures

    @property
    def compiled_at(self) -> datetime:
        return self._compiled_at

    @property
    def condition_index(self) -> ConditionNameIndex:
        return self._condition_index

    @procedures.setter
    def procedures(self, value: ProcedureLabels) -> None:
        self._procedures = value

    def procedure_label(self, ref: ProcedureRef) -> CodeLabel:
        return self._procedures.procedure(ref.paragraph, ref.section, self._section)

    def procedure_end(self, ref: ProcedureRef) -> ContinuationName:
        return self._procedures.procedure_end(ref.paragraph, ref.section, self._section)

    @property
    def section(self) -> str:
        return self._section

    @property
    def extension_strategies(self) -> tuple[RedDragonExtensionLoweringStrategy, ...]:
        return self._extension_strategies

    # ── Enclosing paragraph and section ───────────────────────────

    @contextmanager
    def in_paragraph(self, name: str) -> Iterator[None]:
        enclosing = self._paragraph
        self._paragraph = name
        try:
            yield
        finally:
            self._paragraph = enclosing

    @contextmanager
    def in_section(self, name: str) -> Iterator[None]:
        enclosing = self._section
        self._section = name
        try:
            yield
        finally:
            self._section = enclosing

    @contextmanager
    def in_sentence(self, exit_label: CodeLabel) -> Iterator[None]:
        enclosing = self._sentence
        self._sentence = exit_label
        try:
            yield
        finally:
            self._sentence = enclosing

    @contextmanager
    def in_inline_perform(self) -> Iterator[CodeLabel]:
        """An inline PERFORM's landing after END-PERFORM, for EXIT PERFORM.

        Numbered from a count of its own, not fresh_label's, so no other label is
        renumbered; it reaches the IR only when an EXIT PERFORM asked for it.
        """
        enclosing = self._perform_leave
        self._perform_leave = CodeLabel(f"perform_leave_{self._next_perform_scope()}")
        try:
            yield self._perform_leave
        finally:
            self._perform_leave = enclosing

    @contextmanager
    def in_perform_body(self) -> Iterator[CodeLabel]:
        """The landing after one iteration of an inline body, for EXIT PERFORM CYCLE:
        what follows it is the loop's own step."""
        enclosing = self._perform_cycle
        self._perform_cycle = CodeLabel(f"perform_cycle_{self._next_perform_scope()}")
        try:
            yield self._perform_cycle
        finally:
            self._perform_cycle = enclosing

    def _next_perform_scope(self) -> int:
        scope = self._perform_scopes
        self._perform_scopes = scope + 1
        return scope

    def perform_leave(self) -> CodeLabel:
        if not str(self._perform_leave):
            raise NotImplementedError("EXIT PERFORM outside an inline PERFORM")
        return self._request_exit(self._perform_leave)

    def perform_cycle(self) -> CodeLabel:
        if not str(self._perform_cycle):
            raise NotImplementedError("EXIT PERFORM CYCLE outside an inline PERFORM")
        return self._request_exit(self._perform_cycle)

    def sentence_exit(self) -> CodeLabel:
        """The label NEXT SENTENCE branches to, recorded so the sentence emits it."""
        if not str(self._sentence):
            raise NotImplementedError("NEXT SENTENCE outside a paragraph's sentences")
        return self._request_exit(self._sentence)

    def paragraph_exit(self) -> CodeLabel:
        """The label EXIT PARAGRAPH branches to, recorded so the paragraph emits it."""
        if not self._paragraph:
            raise NotImplementedError("EXIT PARAGRAPH outside a named paragraph")
        return self._request_exit(
            self._procedures.paragraph_exit(self._paragraph, self._section)
        )

    def section_exit(self) -> CodeLabel:
        """The label EXIT SECTION branches to, recorded so the section emits it."""
        if not self._section:
            raise NotImplementedError("EXIT SECTION outside a section")
        return self._request_exit(self._procedures.section_exit(self._section))

    def exit_requested(self, label: CodeLabel) -> bool:
        return label in self._requested_exits

    def _request_exit(self, label: CodeLabel) -> CodeLabel:
        self._requested_exits = self._requested_exits | {label}
        return label

    @property
    def alters(self) -> AlterTable:
        return self._alters

    def record_alterable_goto(self, goto: AlterableGoto) -> None:
        self._alters = self._alters.with_goto(goto)

    def record_alter(self, paragraph: CodeLabel, target: CodeLabel) -> int:
        self._alters = self._alters.with_target(paragraph, target)
        return self._alters.ordinal(paragraph, target)

    # ── Core Primitives ───────────────────────────────────────────

    def fresh_reg(self) -> Register:
        name = Register(f"%{self._reg_counter}")
        self._reg_counter += 1
        return name

    def fresh_label(self, prefix: str) -> CodeLabel:
        name = CodeLabel(f"{prefix}_{self._label_counter}")
        self._label_counter += 1
        return name

    def fresh_name(self, prefix: str) -> str:
        """Generate a unique name string (for variables, not labels)."""
        name = f"{prefix}_{self._label_counter}"
        self._label_counter += 1
        return name

    def emit_inst(
        self, inst: InstructionBase, *, span: SourceSpan | None = None
    ) -> InstructionBase:
        """Emit a typed instruction directly.

        ``span`` is the COBOL construct this instruction was lowered from.
        Precedence matches the tree-sitter frontends' ``node=`` parameter
        (``frontends/context.py:219-222``): a source location already on
        the instruction wins, then ``span``, then unknown.
        """
        if inst.source_location.is_unknown() and span is not None:
            inst = dataclasses.replace(inst, source_location=to_source_location(span))
        self._instructions.append(inst)
        return inst

    def _emit_load_region(
        self,
        result_reg: Register,
        region_reg: Register,
        offset_reg: Register,
        length: int,
        extent: FieldExtent,
        *,
        span: SourceSpan | None = None,
    ) -> None:
        """Emit a region read of ``length`` bytes."""
        self.emit_inst(
            LoadRegion(
                result_reg=result_reg,
                region_reg=region_reg,
                offset_reg=offset_reg,
                length=length,
            ),
            span=span,
        )

    def _emit_write_region(
        self,
        region_reg: Register,
        offset_reg: Register,
        value_reg: Register,
        length: int,
        extent: FieldExtent,
        *,
        span: SourceSpan | None = None,
    ) -> None:
        """Emit a region write of ``length`` bytes."""
        self.emit_inst(
            WriteRegion(
                region_reg=region_reg,
                offset_reg=offset_reg,
                length=length,
                value_reg=value_reg,
            ),
            span=span,
        )

    def _materialise_offset(
        self,
        fl: FieldLayout,
        offset_reg: Register,
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """Emit the base-offset CONST when the caller passed no offset register.

        Emits an instruction, so it must be called at exactly the point in the
        instruction stream where that CONST belongs.
        """
        if offset_reg.is_present():
            return offset_reg
        offset_reg = self.fresh_reg()
        self.emit_inst(Const.int_(offset_reg, fl.offset), span=span)
        return offset_reg

    def const_to_reg(self, value: Any, *, span: SourceSpan | None = None) -> Register:
        """Emit a typed CONST for a Python literal and return its register."""
        reg = self.fresh_reg()
        if isinstance(value, bool):
            inst = Const.bool_(reg, value)
        elif isinstance(value, int):
            inst = Const.int_(reg, value)
        elif isinstance(value, float):
            inst = Const.float_(reg, value)
        elif is_cobol_number(value):
            inst = Const.decimal_(reg, value)
        elif value is None:
            inst = Const.null_(reg)
        else:
            inst = Const.string(reg, str(value))
        self.emit_inst(inst, span=span)
        return reg

    def inline_ir(
        self,
        ir_instructions: Sequence[InstructionBase],
        param_regs: dict[str, Register],
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """Inline a generated IR function body, mapping parameter registers.

        Returns the register holding the return value.
        """
        reg_map: dict[str, Register] = dict(param_regs)
        return_reg: Register = NO_REGISTER

        def remap(r: Register) -> Register:
            mapped = reg_map.get(str(r))
            return mapped if mapped is not None else r

        for inst in ir_instructions:
            if isinstance(inst, Label_):
                continue
            if isinstance(inst, Return_):
                if inst.value_reg is not None:
                    resolved = remap(inst.value_reg)
                    resolved_str = str(resolved)
                    if resolved_str.startswith("%"):
                        return_reg = resolved
                    else:
                        return_reg = self.const_to_reg(resolved_str, span=span)
                continue

            # Allocate fresh result register and record the mapping
            if inst.result_reg.is_present():
                new_result = self.fresh_reg()
                reg_map[str(inst.result_reg)] = new_result
            else:
                new_result = NO_REGISTER

            # Remap all register operands, then override result_reg with the fresh one
            remapped = inst.map_registers(remap)
            remapped = dataclasses.replace(remapped, result_reg=new_result)
            self.emit_inst(remapped, span=span)

        return return_reg

    # ── Statement Dispatch ────────────────────────────────────────

    def lower_statement(
        self, stmt: Any, materialised: MaterialisedSectionedLayout
    ) -> None:  # Any: CobolStatementType, circular-import boundary
        """Dispatch a statement through the injected callback."""
        if not self._tolerant:
            try:
                self._dispatch_fn(self, stmt, materialised)
            except UndeclaredDataName as missing:
                raise UndeclaredDataNameError(missing.name, stmt.span) from missing
            return
        try:
            self._dispatch_fn(self, stmt, materialised)
        except Exception as exc:
            logger.warning("skipped %s: %s", type(stmt).__name__, exc)

    # ── Field Reference Resolution ────────────────────────────────

    def resolve_field_ref(
        self,
        name: str,
        materialised: MaterialisedSectionedLayout,
        qualifiers: tuple[str, ...] = (),
        subscripts: tuple[ExprNode, ...] = (),
        *,
        span: SourceSpan | None = None,
    ) -> tuple[ResolvedFieldRef, Register]:
        """Resolve a field reference that may contain subscript notation.

        Returns (ResolvedFieldRef, region_register) — the region register is
        determined by which DATA DIVISION section owns the field.

        ``qualifiers`` (``OF``/``IN`` ancestor group names) disambiguate a
        duplicated elementary name (CardDemo CSUTLDTC's two Vstring groups).

        ``name`` is always the bare base name (both feeders — the ProLeap bridge
        and the CICS parser — emit structured subscripts, never ``"NAME(SUB)"``
        strings). ``subscripts`` carries the index expressions as structured
        ``ExprNode``s (literal / field-ref / binop / ...); each is evaluated by the
        expression lowerer, so arithmetic and nested subscripts resolve to their
        real value rather than the old default-1 string-parse fallback
        (red-dragon-l445). One or more dimensions are supported: a single subscript
        uses a fast ``(idx-1)*stride + base`` form, while multiple subscripts
        accumulate per-dimension OCCURS strides (red-dragon-1wy3). A subscript count
        exceeding the field's OCCURS dimensions raises ``ValueError``. See
        red-dragon-6ddr.
        """
        # Deferred import: condition_lowering imports EmitContext, so a top-level
        # import would cycle.
        from interpreter.cobol.condition_lowering import lower_expr_node
        from interpreter.cobol.lowering_scope import LoweringScope

        scope = LoweringScope(self, materialised, span)
        base_name = name
        match, region_reg, region = materialised.resolve_match(base_name, qualifiers)
        fl = match.storage

        if not subscripts:
            storage = self._with_current_length(match, materialised, span=span)
            offset_reg = self._field_offset(storage, region, materialised, span=span)
            extent = field_access_extent(
                name=base_name,
                fl=storage,
                region=region,
                subscripts=(),
                tables=(),
                record=None,
                access_len=storage.byte_length,
            )
            return (
                ResolvedFieldRef(fl=storage, offset_reg=offset_reg, extent=extent),
                region_reg,
            )

        # ── subscripted access (1-D or multi-D) ──────────────────────────────
        # Subscript stride vs. accessed-element width.
        #  * stride: how far apart successive occurrences sit.
        #  * access_len: how many bytes one occurrence of THIS field spans.
        # A field that itself carries OCCURS strides by (and accesses) its own
        # element_size. A leaf nested inside an OCCURS group strides by the
        # group's element_size (e.g. CDEMO-MENU-OPT-PGMNAME(idx) strides by the
        # whole CDEMO-MENU-OPT entry, 46 bytes) but accesses only the leaf's own
        # width (8 bytes for PGMNAME X(8)).
        if fl.occurs_count > 0 and fl.element_size > 0:
            access_len = fl.element_size
        else:
            access_len = fl.byte_length

        tables = match.tables
        if len(subscripts) == 1:
            strides = [tables[-1].element_size if tables else fl.byte_length]
        else:
            strides = [table.element_size for table in tables]
            if len(subscripts) > len(strides):
                raise ValueError(
                    f"subscript count {len(subscripts)} exceeds OCCURS dimensions "
                    f"{len(strides)} for {name!r} (red-dragon-1wy3)"
                )

        one_reg = self.const_to_reg(1, span=span)

        if len(subscripts) == 1:
            # Single subscript — original 3-BINOP form: (idx-1)*stride + base.
            idx_reg = lower_expr_node(scope, subscripts[0])
            idx_minus_one = self.fresh_reg()
            self.emit_inst(
                Binop(
                    result_reg=idx_minus_one,
                    operator=resolve_binop("-"),
                    left=idx_reg,
                    right=one_reg,
                ),
                span=span,
            )
            stride_reg = self.const_to_reg(strides[0], span=span)
            displacement = self.fresh_reg()
            self.emit_inst(
                Binop(
                    result_reg=displacement,
                    operator=resolve_binop("*"),
                    left=idx_minus_one,
                    right=stride_reg,
                ),
                span=span,
            )
            base_offset_reg = self._field_offset(fl, region, materialised, span=span)
            final_offset_reg = self.fresh_reg()
            self.emit_inst(
                Binop(
                    result_reg=final_offset_reg,
                    operator=resolve_binop("+"),
                    left=base_offset_reg,
                    right=displacement,
                ),
                span=span,
            )
        else:
            # Multi-dimensional: accumulate sum of (idx_k - 1) * stride_k, then
            # add the field's base offset once at the end.
            total_disp_reg = self.const_to_reg(0, span=span)
            for sub_node, stride_k in zip(subscripts, strides, strict=False):
                idx_reg = lower_expr_node(scope, sub_node)
                idx_minus_one = self.fresh_reg()
                self.emit_inst(
                    Binop(
                        result_reg=idx_minus_one,
                        operator=resolve_binop("-"),
                        left=idx_reg,
                        right=one_reg,
                    ),
                    span=span,
                )
                stride_reg = self.const_to_reg(stride_k, span=span)
                disp_k = self.fresh_reg()
                self.emit_inst(
                    Binop(
                        result_reg=disp_k,
                        operator=resolve_binop("*"),
                        left=idx_minus_one,
                        right=stride_reg,
                    ),
                    span=span,
                )
                new_total = self.fresh_reg()
                self.emit_inst(
                    Binop(
                        result_reg=new_total,
                        operator=resolve_binop("+"),
                        left=total_disp_reg,
                        right=disp_k,
                    ),
                    span=span,
                )
                total_disp_reg = new_total

            base_offset_reg = self._field_offset(fl, region, materialised, span=span)
            final_offset_reg = self.fresh_reg()
            self.emit_inst(
                Binop(
                    result_reg=final_offset_reg,
                    operator=resolve_binop("+"),
                    left=base_offset_reg,
                    right=total_disp_reg,
                ),
                span=span,
            )

        # For subscripted access, use element-level FieldLayout
        element_fl = FieldLayout(
            name=fl.name,
            type_descriptor=fl.type_descriptor,
            offset=fl.offset,
            byte_length=access_len,
            redefines=fl.redefines,
            value=fl.value,
            span=fl.span,
        )
        # The extent is parallel, statically-known information — it is derived
        # from the SAME strides the register arithmetic above used, but from
        # the structured subscript nodes rather than from the emitted BINOPs.
        extent = field_access_extent(
            name=base_name,
            fl=fl,
            region=region,
            subscripts=subscripts,
            tables=tables,
            record=match.record_extent,
            access_len=access_len,
        )
        return (
            ResolvedFieldRef(fl=element_fl, offset_reg=final_offset_reg, extent=extent),
            region_reg,
        )

    def has_field(self, name: str, materialised: MaterialisedSectionedLayout) -> bool:
        """Check if a name (possibly subscripted) refers to a known field."""
        return materialised.has_field(name)

    def group_leaf_names(
        self, group_name: str, materialised: MaterialisedSectionedLayout
    ) -> list[str]:
        """Leaf field names of a symbolic-map group (for SEND/RECEIVE MAP lowering)."""
        return materialised.group_leaf_names(group_name)

    def emit_length_of(
        self,
        name: str,
        materialised: MaterialisedSectionedLayout,
        qualifiers: tuple[str, ...] = (),
        *,
        span: SourceSpan | None,
    ) -> Register:
        """LENGTH OF an item: its byte length, or the current length an item
        ending in an OCCURS DEPENDING ON table has from its object's value."""
        ref, _ = self.resolve_field_ref(name, materialised, qualifiers, span=span)
        if ref.fl.current_length.is_present():
            return ref.fl.current_length
        return self.const_to_reg(ref.fl.byte_length, span=span)

    def _with_current_length(
        self,
        match: DataItemMatch,
        materialised: MaterialisedSectionedLayout,
        *,
        span: SourceSpan | None,
    ) -> FieldLayout:
        """The item's storage, with its current length when it ends in an
        OCCURS DEPENDING ON table: the maximum less the inactive occurrences."""
        fl = match.storage
        item = match.item
        tail = (
            item.odo_tail()
            if isinstance(item, DataLayout)
            else OdoTail(fl.occurs_depending_on, fl.element_size, fl.occurs_count)
        )
        if not tail.is_present():
            return fl
        object_ref, object_region = self.resolve_field_ref(
            tail.depending_on.name,
            materialised,
            tail.depending_on.qualifiers,
            span=span,
        )
        current_count = self.emit_decode_field(
            object_region,
            object_ref.fl,
            object_ref.offset_reg,
            extent=object_ref.extent,
            span=span,
        )
        inactive = self._emit_binop(
            "-",
            self.const_to_reg(tail.max_count, span=span),
            current_count,
            span=span,
        )
        shrink = self._emit_binop(
            "*",
            inactive,
            self.const_to_reg(tail.element_size, span=span),
            span=span,
        )
        return dataclasses.replace(
            fl,
            current_length=self._emit_binop(
                "-",
                self.const_to_reg(fl.byte_length, span=span),
                shrink,
                span=span,
            ),
            receives_at_maximum=isinstance(item, DataLayout)
            and item.exists(tail.depending_on.name),
        )

    def _emit_binop(
        self, op: str, left: Register, right: Register, *, span: SourceSpan | None
    ) -> Register:
        result = self.fresh_reg()
        self.emit_inst(
            Binop(
                result_reg=result, operator=resolve_binop(op), left=left, right=right
            ),
            span=span,
        )
        return result

    def resolve_field_ref_from(
        self,
        fl: FieldLayout,
        region_reg: Register,
        region: RegionId,
        materialised: MaterialisedSectionedLayout,
        *,
        span: SourceSpan | None = None,
    ) -> ResolvedFieldRef:
        """Resolve a FieldLayout to a ResolvedFieldRef without a name lookup.

        Used when the FieldLayout is already known (e.g. MOVE CORRESPONDING).
        There is no name to look up and therefore no region to derive, so the
        caller — which found the FieldLayout in a particular section's layout —
        must say which region it came from. Always EXACT: the access is the
        field's whole declared extent, with no subscript in play.
        """
        offset_reg = self._field_offset(fl, region, materialised, span=span)
        extent = FieldExtent(
            region, fl.offset, fl.byte_length, Precision.EXACT, fl.name
        )
        return ResolvedFieldRef(fl=fl, offset_reg=offset_reg, extent=extent)

    def _field_offset(
        self,
        fl: FieldLayout,
        region: RegionId,
        materialised: MaterialisedSectionedLayout,
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """The field's offset in its region at run time: a LINKAGE field moves by
        its 01's shift, an EXTERNAL field sits at its offset in its own area, every
        other field sits at its static offset."""
        if region is RegionId.EXTERNAL:
            start = materialised.external_binding(fl).area.start
            return self.const_to_reg(fl.offset - start, span=span)
        static = self.const_to_reg(fl.offset, span=span)
        if region is not RegionId.LINKAGE:
            return static
        shifted = self.fresh_reg()
        self.emit_inst(
            Binop(
                result_reg=shifted,
                operator=resolve_binop("+"),
                left=static,
                right=materialised.linkage_binding(fl).delta_reg,
            ),
            span=span,
        )
        return shifted

    # ── Field Encode / Decode ─────────────────────────────────────

    def emit_field_encode(
        self,
        region_reg: Register,
        fl: FieldLayout,
        value: str,
        offset_reg: Register = NO_REGISTER,
        *,
        extent: FieldExtent,
        span: SourceSpan | None = None,
    ) -> None:
        """Emit IR to encode a value and write it to the region."""
        encoded_reg = self.emit_encode_value(fl, value, span=span)
        offset_reg = self._materialise_offset(fl, offset_reg, span=span)
        self._emit_write_region(
            region_reg=region_reg,
            offset_reg=offset_reg,
            value_reg=encoded_reg,
            length=fl.byte_length,
            extent=extent,
            span=span,
        )

    def emit_encode_value(
        self, fl: FieldLayout, value: str, *, span: SourceSpan | None = None
    ) -> Register:
        """Emit inline IR to encode a value per the field's type. Returns result register."""
        td = fl.type_descriptor
        if td.category == CobolDataCategory.NUMERIC_EDITED and fl.value_is_numeric:
            return self._emit_numeric_edit(
                fl, self.const_to_reg(from_literal(value), span=span), span=span
            )
        if (
            td.category == CobolDataCategory.NUMERIC_EDITED
            and self._is_figurative_zero(fl, value)
        ):
            return self._emit_numeric_edit(
                fl, self.const_to_reg(from_literal("0"), span=span), span=span
            )
        if td.holds_characters or td.category == CobolDataCategory.NUMERIC_EDITED:
            return self._emit_encode_character_value(fl, value, span=span)
        if td.category in (CobolDataCategory.COMP1, CobolDataCategory.COMP2):
            return self.emit_encode_float(fl.name, value, td, span=span)
        return self.emit_encode_numeric(fl.name, value, td, span=span)

    def _is_figurative_zero(self, fl: FieldLayout, value: str) -> bool:
        return fl.value_is_figurative and value in FIGURATIVE_ZEROS

    def _emit_encode_character_value(
        self, fl: FieldLayout, value: str, *, span: SourceSpan | None = None
    ) -> Register:
        """Encode a VALUE literal stored as its characters, unedited."""
        td = fl.type_descriptor
        raw = parse_hex_literal(value)
        if raw is not None:
            return self._emit_hex_literal_bytes(raw, fl.byte_length, span=span)
        figurative = fl.value_is_figurative and value in self.figuratives.characters
        text = (
            self.figuratives.characters[value] * fl.byte_length if figurative else value
        )
        return self.emit_encode_alphanumeric(fl.name, text, td.total_digits, span=span)

    def _emit_hex_literal_bytes(
        self, raw: bytes, byte_length: int, *, span: SourceSpan | None = None
    ) -> Register:
        """Emit a Const holding raw hex-literal bytes padded to the field length.

        COBOL hex literals (X'nn') denote raw bytes and bypass ASCII→EBCDIC
        translation; they are stored verbatim into the field region.
        """
        padded = encode_hex_literal(raw, byte_length)
        result = self.fresh_reg()
        self.emit_inst(
            Const(
                result_reg=result,
                value=list(padded),
                type_expr=array_of(scalar(FoundationTypeName.INT)),
            ),
            span=span,
        )
        return result

    def emit_fill_raw_byte(
        self,
        region_reg: Register,
        fl: FieldLayout,
        fill_byte: int,
        offset_reg: Register = NO_REGISTER,
        *,
        extent: FieldExtent,
        span: SourceSpan | None = None,
    ) -> None:
        """Fill a field's whole region slot with a single raw byte, verbatim.

        Used for MOVE HIGH-VALUES / LOW-VALUES, whose semantics are raw 0xFF /
        0x00 in every receiver position whatever its category — the character
        path would convert them per the receiver's PICTURE, so a numeric
        receiver would get a number. The byte is written as a literal list of
        ``byte_length`` copies (red-dragon-raxa).
        """
        result = self.fresh_reg()
        self.emit_inst(
            Const(
                result_reg=result,
                value=[fill_byte] * fl.byte_length,
                type_expr=array_of(scalar(FoundationTypeName.INT)),
            ),
            span=span,
        )
        offset_reg = self._materialise_offset(fl, offset_reg, span=span)
        self._emit_write_region(
            region_reg=region_reg,
            offset_reg=offset_reg,
            value_reg=result,
            length=fl.byte_length,
            extent=extent,
            span=span,
        )

    def emit_encode_alphanumeric(
        self,
        field_name: str,
        value: str,
        length: int,
        justified_right: bool = False,
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """Emit inline alphanumeric encoding IR. Returns result register."""
        value_reg = self.fresh_reg()
        self.emit_inst(Const.string(value_reg, value), span=span)

        if justified_right:
            ir = build_encode_alphanumeric_justified_ir(
                f"enc_alpha_just_{field_name}", length
            )
        else:
            ir = build_encode_alphanumeric_ir(f"enc_alpha_{field_name}", length)
        return self.inline_ir(ir, {"%p_value": value_reg}, span=span)

    def emit_encode_float(
        self,
        field_name: str,
        value: str,
        td: CobolTypeDescriptor,
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """Emit inline float encoding IR for COMP-1/COMP-2. Returns result register."""
        float_val = float(value)
        value_reg = self.fresh_reg()
        self.emit_inst(Const.float_(value_reg, float_val), span=span)

        ir = build_encode_float_ir(f"enc_float_{field_name}", td.byte_length)
        return self.inline_ir(ir, {"%p_float_value": value_reg}, span=span)

    def emit_encode_numeric(
        self,
        field_name: str,
        value: str,
        td: CobolTypeDescriptor,
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """Emit inline numeric encoding IR. Returns result register."""
        negative, digit_str = encode_digits(
            value, td.total_digits, td.decimal_digits, td.scale
        )

        digits = [int(ch) if ch.isdigit() else 0 for ch in digit_str]

        if not td.signed:
            sign_nibble = ByteConstants.SIGN_NIBBLE_UNSIGNED
        elif negative:
            sign_nibble = ByteConstants.SIGN_NIBBLE_NEGATIVE
        else:
            sign_nibble = ByteConstants.SIGN_NIBBLE_POSITIVE

        digits_reg = self.fresh_reg()
        self.emit_inst(
            Const(
                result_reg=digits_reg,
                value=digits,
                type_expr=array_of(scalar(FoundationTypeName.INT)),
            ),
            span=span,
        )

        sign_reg = self.fresh_reg()
        self.emit_inst(Const.int_(sign_reg, sign_nibble), span=span)

        if td.category == CobolDataCategory.ZONED_DECIMAL:
            if td.sign_separate:
                ir = build_encode_zoned_separate_ir(
                    f"enc_zoned_sep_{field_name}",
                    td.total_digits,
                    sign_leading=td.sign_leading,
                )
            else:
                ir = build_encode_zoned_ir(
                    f"enc_zoned_{field_name}",
                    td.total_digits,
                    sign_leading=td.sign_leading,
                )
        elif td.category == CobolDataCategory.BINARY:
            ir = build_encode_binary_ir(
                f"enc_bin_{field_name}",
                td.total_digits,
                td.byte_length,
                td.signed,
            )
        else:
            ir = build_encode_comp3_ir(f"enc_comp3_{field_name}", td.total_digits)

        return self.inline_ir(
            ir, {"%p_digits": digits_reg, "%p_sign_nibble": sign_reg}, span=span
        )

    def emit_decode_field(
        self,
        region_reg: Register,
        fl: FieldLayout,
        offset_reg: Register = NO_REGISTER,
        *,
        extent: FieldExtent,
        span: SourceSpan | None = None,
    ) -> Register:
        """Emit IR to load and decode a field from the region. Returns decoded value register."""
        offset_reg = self._materialise_offset(fl, offset_reg, span=span)

        data_reg = self.fresh_reg()
        self._emit_load_region(
            result_reg=data_reg,
            region_reg=region_reg,
            offset_reg=offset_reg,
            length=fl.byte_length,
            extent=extent,
            span=span,
        )

        td = fl.type_descriptor
        ir = _decode_ir(fl)

        decoded = self.inline_ir(ir, {"%p_data": data_reg}, span=span)
        if fl.current_length.is_present():
            return self._emit_slice(
                decoded,
                self.const_to_reg(0, span=span),
                fl.current_length,
                span=span,
            )
        if not td.scale or td.category == CobolDataCategory.NUMERIC_EDITED:
            return decoded
        # PIC P: the stored digits are the value divided by the scaling factor,
        # so reading multiplies back. Applied HERE rather than inside the four
        # build_decode_*_ir builders — one site instead of four, and those
        # builders keep their existing signatures (red-dragon-qhtv). A
        # numeric-edited item's content is its edited characters, never scaled.
        scaled = self.fresh_reg()
        scale_reg = self.const_to_reg(td.scale, span=span)
        self.emit_inst(
            CallFunction(
                result_reg=scaled,
                func_name=FuncName(BuiltinName.COBOL_SCALE_BY),
                args=(decoded, scale_reg),
            ),
            span=span,
        )
        return scaled

    def emit_decode_zoned_display(
        self,
        region_reg: Register,
        fl: FieldLayout,
        offset_reg: Register = NO_REGISTER,
        *,
        extent: FieldExtent,
        span: SourceSpan | None = None,
    ) -> Register:
        """Emit IR to read a zoned (USAGE DISPLAY) numeric field's raw character
        representation, decoded as alphanumeric (its zoned digit characters).

        Unlike emit_decode_field — which decodes a zoned field to a numeric value
        and so loses leading zeros/width — this returns the sending field's actual
        digit characters (e.g. PIC 9(11) value 11 -> "00000000011"). Used by MOVE
        when a numeric-DISPLAY source feeds an alphanumeric receiver, where COBOL
        moves the sending field's characters left-justified (red-dragon-0fqr).
        """
        offset_reg = self._materialise_offset(fl, offset_reg, span=span)

        data_reg = self.fresh_reg()
        self._emit_load_region(
            result_reg=data_reg,
            region_reg=region_reg,
            offset_reg=offset_reg,
            length=fl.byte_length,
            extent=extent,
            span=span,
        )
        ir = build_decode_alphanumeric_ir(f"dec_zoned_disp_{fl.name}")
        return self.inline_ir(ir, {"%p_data": data_reg}, span=span)

    def emit_decode_field_characters(
        self,
        region_reg: Register,
        fl: FieldLayout,
        offset_reg: Register = NO_REGISTER,
        *,
        extent: FieldExtent,
        span: SourceSpan | None = None,
    ) -> Register:
        """Emit IR for a field's CHARACTER image — what a character-consuming
        context (DISPLAY, reference modification, a STRING sending operand) reads.

        An unsigned zoned (USAGE DISPLAY) numeric item is a fixed-width field of
        exactly PICTURE-many bytes, so its character image is those bytes, leading
        zeros and all. Decoding it to a number and formatting the number back
        silently narrows the field, and any reference modification then slices at
        offsets that have all slid left — PIC 9(09) holding 020973888 renders the
        CardDemo SSN as 209-73-888 (red-dragon-wlms).

        Signed zoned items keep the decoded-number reading: their last byte carries
        a sign overpunch, whose faithful character image is a letter rather than a
        digit, and that is a separate semantic decision (red-dragon-b1ba).

        Every other category already decodes to its character form or has no
        meaningful one, so this routes them through emit_decode_field unchanged.
        """
        td = fl.type_descriptor
        if td.category == CobolDataCategory.ZONED_DECIMAL and not td.signed:
            return self.emit_decode_zoned_display(
                region_reg, fl, offset_reg, extent=extent, span=span
            )
        decoded = self.emit_decode_field(
            region_reg, fl, offset_reg, extent=extent, span=span
        )
        return self.emit_to_string(decoded, span=span)

    def emit_stored_characters(
        self, region_reg: Register, ref: ResolvedFieldRef, *, span: SourceSpan | None
    ) -> Register:
        if ref.fl.type_descriptor.category == CobolDataCategory.ZONED_DECIMAL:
            return self.emit_decode_zoned_display(
                region_reg, ref.fl, ref.offset_reg, extent=ref.extent, span=span
            )
        return self.emit_decode_field_characters(
            region_reg, ref.fl, ref.offset_reg, extent=ref.extent, span=span
        )

    def emit_decoded_is_numeric(
        self, region_reg: Register, ref: ResolvedFieldRef, *, span: SourceSpan | None
    ) -> Register:
        text = self.emit_to_string(
            self.emit_decode_field(
                region_reg, ref.fl, ref.offset_reg, extent=ref.extent, span=span
            ),
            span=span,
        )
        result = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=result,
                func_name=FuncName(BuiltinName.IS_NUMERIC),
                args=(text,),
            ),
            span=span,
        )
        return result

    def emit_load_field_bytes(
        self, region_reg: Register, ref: ResolvedFieldRef, *, span: SourceSpan | None
    ) -> Register:
        data_reg = self.fresh_reg()
        self._emit_load_region(
            result_reg=data_reg,
            region_reg=region_reg,
            offset_reg=ref.offset_reg,
            length=ref.fl.byte_length,
            extent=ref.extent,
            span=span,
        )
        return data_reg

    def emit_write_field_bytes(
        self,
        region_reg: Register,
        ref: ResolvedFieldRef,
        value_reg: Register,
        *,
        span: SourceSpan | None,
    ) -> None:
        self._emit_write_region(
            region_reg=region_reg,
            offset_reg=ref.offset_reg,
            value_reg=value_reg,
            length=ref.fl.byte_length,
            extent=ref.extent,
            span=span,
        )

    # ── Byte-faithful (raw) region read/write ─────────────────────

    def emit_read_region_raw(
        self,
        region_reg: Register,
        fl: FieldLayout,
        offset_reg: Register = NO_REGISTER,
        *,
        extent: FieldExtent,
        span: SourceSpan | None = None,
    ) -> Register:
        """Read a region slot as its verbatim byte-image (LATIN1 identity).

        Returns a latin-1 str whose code points are the raw region bytes 1:1, so
        binary subfields (COMP-3 packed decimal, COMP binary) survive unchanged.
        Used for byte-faithful WRITE/REWRITE of an FD record GROUP, where running
        the group through the EBCDIC→ASCII alphanumeric decoder would mangle
        packed bytes (red-dragon-zwzg).
        """
        offset_reg = self._materialise_offset(fl, offset_reg, span=span)
        data_reg = self.fresh_reg()
        self._emit_load_region(
            result_reg=data_reg,
            region_reg=region_reg,
            offset_reg=offset_reg,
            length=fl.byte_length,
            extent=extent,
            span=span,
        )
        encoding_reg = self.const_to_reg(CobolEncoding.LATIN1.value, span=span)
        result = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=result,
                func_name=FuncName(BuiltinName.BYTES_TO_STRING),
                args=(data_reg, encoding_reg),
            ),
            span=span,
        )
        return result

    def emit_write_region_raw(
        self,
        region_reg: Register,
        fl: FieldLayout,
        value_str_reg: Register,
        offset_reg: Register = NO_REGISTER,
        *,
        extent: FieldExtent,
        span: SourceSpan | None = None,
    ) -> None:
        """Write a latin-1 str's verbatim bytes into a region slot (no PICTURE
        encode). The byte-faithful inverse of ``emit_read_region_raw``: used for
        byte-faithful READ, landing the file's raw bytes into the FD record region
        unchanged (red-dragon-zwzg)."""
        encoding_reg = self.const_to_reg(CobolEncoding.LATIN1.value, span=span)
        bytes_reg = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=bytes_reg,
                func_name=FuncName(BuiltinName.STRING_TO_BYTES),
                args=(value_str_reg, encoding_reg),
            ),
            span=span,
        )
        offset_reg = self._materialise_offset(fl, offset_reg, span=span)
        self._emit_write_region(
            region_reg=region_reg,
            offset_reg=offset_reg,
            value_reg=bytes_reg,
            length=fl.byte_length,
            extent=extent,
            span=span,
        )

    # ── String Conversion Helpers ─────────────────────────────────

    def emit_to_string(
        self, value_reg: Register, *, span: SourceSpan | None = None
    ) -> Register:
        """Emit IR converting a COBOL value to its text (numbers rendered plainly)."""
        result = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=result,
                func_name=FuncName(BuiltinName.COBOL_TO_TEXT),
                args=(value_reg,),
            ),
            span=span,
        )
        return result

    def _emit_blank_when_zero_wrap(
        self,
        encoded_reg: Register,
        value_str_reg: Register,
        byte_length: int,
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """Wrap encoded bytes with BLANK WHEN ZERO check via builtin."""
        result = self.fresh_reg()
        length_reg = self.const_to_reg(byte_length, span=span)
        self.emit_inst(
            CallFunction(
                result_reg=result,
                func_name=FuncName(BuiltinName.COBOL_BLANK_WHEN_ZERO),
                args=(encoded_reg, value_str_reg, length_reg),
            ),
            span=span,
        )
        return result

    def _emit_numeric_edit(
        self,
        fl: FieldLayout,
        value_reg: Register,
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """Edit a number by the item's PICTURE; the edited characters are its content."""
        from interpreter.cobol.ir_emitter import IrEmitter
        from interpreter.cobol.numeric_edit_ir import emit_numeric_edit

        td = fl.type_descriptor
        formatted_reg = emit_numeric_edit(IrEmitter(ctx=self, span=span), value_reg, td)
        ir = build_encode_alphanumeric_ir(f"enc_edited_{fl.name}", td.total_digits)
        return self.inline_ir(ir, {"%p_value": formatted_reg}, span=span)

    def emit_encode_from_string(
        self,
        fl: FieldLayout,
        value_str_reg: Register,
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """Emit encoding IR from a string value register."""
        td = fl.type_descriptor
        if td.category == CobolDataCategory.NUMERIC_EDITED:
            edited = self._emit_numeric_edit(fl, value_str_reg, span=span)
            if td.blank_when_zero:
                return self._emit_blank_when_zero_wrap(
                    edited, value_str_reg, fl.byte_length, span=span
                )
            return edited

        if td.category == CobolDataCategory.ALPHANUMERIC_EDITED:
            # Insertion editing: the sender's characters go into the A/X/9
            # positions and each B/0/'/' position emits its insertion character.
            # The result IS the field's content, so it stores as alphanumeric —
            # already aligned by the formatter, hence the unjustified encoder
            # even when JUSTIFIED RIGHT is in force.
            formatted_reg = self.fresh_reg()
            pic_reg = self.const_to_reg(td.pic_string, span=span)
            justified_reg = self.const_to_reg(int(td.justified_right), span=span)
            self.emit_inst(
                CallFunction(
                    result_reg=formatted_reg,
                    func_name=FuncName(BuiltinName.COBOL_APPLY_ALPHANUMERIC_EDIT),
                    args=(value_str_reg, pic_reg, justified_reg),
                ),
                span=span,
            )
            ir = build_encode_alphanumeric_ir(
                f"enc_an_edited_{fl.name}", td.total_digits
            )
            return self.inline_ir(ir, {"%p_value": formatted_reg}, span=span)

        if td.category == CobolDataCategory.ALPHANUMERIC:
            if td.justified_right:
                ir = build_encode_alphanumeric_justified_ir(
                    f"enc_alpha_just_{fl.name}", td.total_digits
                )
            else:
                ir = build_encode_alphanumeric_ir(
                    f"enc_alpha_{fl.name}", td.total_digits
                )
            return self.inline_ir(ir, {"%p_value": value_str_reg}, span=span)

        if td.category in (CobolDataCategory.COMP1, CobolDataCategory.COMP2):
            # Convert string to float, then encode
            float_reg = self.fresh_reg()
            self.emit_inst(
                CallFunction(
                    result_reg=float_reg,
                    func_name=FuncName("float"),
                    args=(value_str_reg,),
                ),
                span=span,
            )
            ir = build_encode_float_ir(f"enc_float_{fl.name}", td.byte_length)
            encoded = self.inline_ir(ir, {"%p_float_value": float_reg}, span=span)
            if td.blank_when_zero:
                return self._emit_blank_when_zero_wrap(
                    encoded, value_str_reg, fl.byte_length, span=span
                )
            return encoded

        if td.category == CobolDataCategory.BINARY:
            int_reg = self.emit_binary_unscaled(value_str_reg, td, span=span)
            signed_reg = self.const_to_reg(td.signed, span=span)
            byte_count_reg = self.const_to_reg(td.byte_length, span=span)
            result = self.fresh_reg()
            self.emit_inst(
                CallFunction(
                    result_reg=result,
                    func_name=FuncName(BuiltinName.INT_TO_BINARY_BYTES),
                    args=(int_reg, byte_count_reg, signed_reg),
                ),
                span=span,
            )
            return result

        encoded = self.emit_numeric_encode_from_string(fl, value_str_reg, span=span)
        if td.blank_when_zero:
            return self._emit_blank_when_zero_wrap(
                encoded, value_str_reg, fl.byte_length, span=span
            )
        return encoded

    def emit_binary_unscaled(
        self,
        value_reg: Register,
        td: CobolTypeDescriptor,
        *,
        span: SourceSpan | None,
    ) -> Register:
        unscaled = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=unscaled,
                func_name=FuncName(BuiltinName.COBOL_BINARY_UNSCALED),
                args=(
                    value_reg,
                    self.const_to_reg(td.decimal_digits, span=span),
                    self.const_to_reg(td.scale, span=span),
                ),
            ),
            span=span,
        )
        return self.inline_ir(
            build_binary_picture_digits_ir("binary_digits", td.total_digits, td.signed),
            {"%p_value": unscaled},
            span=span,
        )

    def emit_numeric_encode_from_string(
        self,
        fl: FieldLayout,
        value_str_reg: Register,
        *,
        span: SourceSpan | None = None,
    ) -> Register:
        """Emit IR to parse a string into digits + sign, then encode numerically."""
        td = fl.type_descriptor
        total_digits_reg = self.const_to_reg(td.total_digits, span=span)
        decimal_digits_reg = self.const_to_reg(td.decimal_digits, span=span)
        signed_reg = self.const_to_reg(td.signed, span=span)
        scale_reg = self.const_to_reg(td.scale, span=span)
        digits_reg = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=digits_reg,
                func_name=FuncName(BuiltinName.COBOL_PREPARE_DIGITS),
                args=(
                    value_str_reg,
                    total_digits_reg,
                    decimal_digits_reg,
                    signed_reg,
                    scale_reg,
                ),
            ),
            span=span,
        )

        signed_reg2 = self.const_to_reg(td.signed, span=span)
        sign_reg = self.fresh_reg()
        self.emit_inst(
            CallFunction(
                result_reg=sign_reg,
                func_name=FuncName(BuiltinName.COBOL_PREPARE_SIGN),
                args=(value_str_reg, signed_reg2),
            ),
            span=span,
        )

        if td.category == CobolDataCategory.ZONED_DECIMAL:
            if td.sign_separate:
                ir = build_encode_zoned_separate_ir(
                    f"enc_zoned_sep_{fl.name}",
                    td.total_digits,
                    sign_leading=td.sign_leading,
                )
            else:
                ir = build_encode_zoned_ir(
                    f"enc_zoned_{fl.name}",
                    td.total_digits,
                    sign_leading=td.sign_leading,
                )
        elif td.category == CobolDataCategory.BINARY:
            ir = build_encode_binary_ir(
                f"enc_bin_{fl.name}",
                td.total_digits,
                td.byte_length,
                td.signed,
            )
        else:
            ir = build_encode_comp3_ir(f"enc_comp3_{fl.name}", td.total_digits)

        return self.inline_ir(
            ir, {"%p_digits": digits_reg, "%p_sign_nibble": sign_reg}, span=span
        )

    def emit_encode_and_write(
        self,
        region_reg: Register,
        fl: FieldLayout,
        value_str_reg: Register,
        offset_reg: Register = NO_REGISTER,
        *,
        extent: FieldExtent,
        span: SourceSpan | None = None,
    ) -> None:
        """Encode a string value and write it to the field's region slot."""
        offset_reg = self._materialise_offset(fl, offset_reg, span=span)
        stored_value_reg = (
            self._emit_keep_inactive_tail(
                region_reg,
                ResolvedFieldRef(fl=fl, offset_reg=offset_reg, extent=extent),
                value_str_reg,
                span=span,
            )
            if fl.current_length.is_present() and not fl.receives_at_maximum
            else value_str_reg
        )
        encoded_reg = self.emit_encode_from_string(fl, stored_value_reg, span=span)
        self._emit_write_region(
            region_reg=region_reg,
            offset_reg=offset_reg,
            value_reg=encoded_reg,
            length=fl.byte_length,
            extent=extent,
            span=span,
        )

    def _emit_keep_inactive_tail(
        self,
        region_reg: Register,
        ref: ResolvedFieldRef,
        value_str_reg: Register,
        *,
        span: SourceSpan | None,
    ) -> Register:
        """The item's new image: the value over its current length, then the
        bytes already stored past it, which the move does not reach."""
        fl = ref.fl
        stored = self.emit_decode_field(
            region_reg,
            dataclasses.replace(fl, current_length=NO_REGISTER),
            ref.offset_reg,
            extent=ref.extent,
            span=span,
        )
        padded = self.emit_pad_to(value_str_reg, stored, span=span)
        head = self._emit_slice(
            padded, self.const_to_reg(0, span=span), fl.current_length, span=span
        )
        tail = self._emit_slice(
            stored,
            fl.current_length,
            self.const_to_reg(fl.byte_length, span=span),
            span=span,
        )
        return self._emit_call(BuiltinName.STRING_CONCAT_PAIR, (head, tail), span=span)

    def emit_pad_to(
        self, value: Register, other: Register, *, span: SourceSpan | None
    ) -> Register:
        """``value`` extended on the right with spaces to the length of
        ``other``; a longer value is left whole. The spaces are a list of
        space bytes as long as the shortfall, which is empty when there is none."""
        shortfall = self.fresh_reg()
        self.emit_inst(
            Binop(
                result_reg=shortfall,
                operator=resolve_binop("-"),
                left=self._emit_call(BuiltinName.LENGTH, (other,), span=span),
                right=self._emit_call(BuiltinName.LENGTH, (value,), span=span),
            ),
            span=span,
        )
        spaces = self._emit_call(
            BuiltinName.BYTES_TO_STRING,
            (
                self._emit_call(
                    BuiltinName.MAKE_LIST,
                    (
                        shortfall,
                        self.const_to_reg(ByteConstants.LATIN1_SPACE, span=span),
                    ),
                    span=span,
                ),
                self.const_to_reg(CobolEncoding.LATIN1.value, span=span),
            ),
            span=span,
        )
        return self._emit_call(
            BuiltinName.STRING_CONCAT_PAIR, (value, spaces), span=span
        )

    def _emit_slice(
        self,
        value: Register,
        start: Register,
        length: Register,
        *,
        span: SourceSpan | None,
    ) -> Register:
        return self._emit_call(
            BuiltinName.STRING_SLICE, (value, start, length), span=span
        )

    def _emit_call(
        self, builtin: str, args: tuple[Register, ...], *, span: SourceSpan | None
    ) -> Register:
        result = self.fresh_reg()
        self.emit_inst(
            CallFunction(result_reg=result, func_name=FuncName(builtin), args=args),
            span=span,
        )
        return result

    # ── File I/O Status Helper ────────────────────────────────────

    def emit_file_status_update(
        self,
        file_name: str,
        status_reg: Register,
        materialised: MaterialisedSectionedLayout,
        *,
        span: SourceSpan | None = None,
    ) -> None:
        """Write the I-O status to the FILE STATUS item of the file's SELECT, if it
        names one: an item of the program whose SELECT it is, which for a GLOBAL
        file of a containing program is that program's, global or not."""
        from interpreter.cobol.global_names import file_owner, visible_file_entries

        entries = visible_file_entries(self._asg)
        if file_name not in entries or not entries[file_name].file_status_var.name:
            return
        status_item = entries[file_name].file_status_var
        owner = program_name(file_owner(self._asg, file_name))
        if owner != program_name(self._asg):
            owned_ref, owned_rr = self._resolve_owned_status(
                owner, status_item, materialised, span=span
            )
            self._emit_status_write(owned_ref, owned_rr, status_reg, span=span)
            return
        if not materialised.has_field(status_item.name):
            return
        target_ref, target_rr = self.resolve_field_ref(
            status_item.name,
            materialised,
            status_item.qualifiers,
            status_item.subscripts,
            span=span,
        )
        self._emit_status_write(target_ref, target_rr, status_reg, span=span)

    def _resolve_owned_status(
        self,
        owner: str,
        status_item: RefModOperand,
        materialised: MaterialisedSectionedLayout,
        *,
        span: SourceSpan | None,
    ) -> tuple[ResolvedFieldRef, Register]:
        match, region_reg, region = next(
            materialised.owner_scope(owner).owned_matches(
                status_item.name, status_item.qualifiers
            )
        )
        target_ref = self.resolve_field_ref_from(
            match.storage, region_reg, region, materialised, span=span
        )
        return target_ref, region_reg

    def _emit_status_write(
        self,
        target_ref: ResolvedFieldRef,
        target_rr: Register,
        status_reg: Register,
        *,
        span: SourceSpan | None,
    ) -> None:
        str_reg = self.emit_to_string(status_reg, span=span)
        self.emit_encode_and_write(
            target_rr,
            target_ref.fl,
            str_reg,
            target_ref.offset_reg,
            extent=target_ref.extent,
            span=span,
        )

    # ── Parse Literal ─────────────────────────────────────────────

    def parse_literal(self, text: str) -> Any:
        """Parse a literal value from condition text.

        If the raw value has COBOL quote delimiters (``'...'`` or ``"..."``),
        it is an ALPHANUMERIC literal: strip the delimiters and return the
        contents as a ``str`` unconditionally — no numeric coercion.

        Only when the raw value has NO surrounding delimiters (i.e. it is a
        bare numeric token such as ``10`` or ``3.14``) is int→exact number→str
        coercion attempted.

        A hexadecimal literal ``X'C1F2'`` stands for the characters its bytes
        encode, ``A2``, decoded as a data item's bytes are.
        """
        match parse_hex_literal(text):
            case bytes() as hex_bytes:
                return decode_alphanumeric(hex_bytes)
            case None:
                pass
        stripped = literal_characters(text)
        is_quoted = stripped != text
        if is_quoted:
            # Quoted literal: alphanumeric — never coerce to int/float.
            return stripped
        # Bare (unquoted) literal: attempt numeric coercion.
        try:
            return int(stripped)
        except ValueError:
            pass
        try:
            return from_literal(stripped)
        except ValueError:
            pass
        # COBOL floating-point literal (1.5E3): not a fixed-point value, so it
        # stays an IEEE float and makes its whole expression floating —
        # arithmetic_scale.expression_is_floating recognises the same form.
        if "e" in stripped.lower():
            try:
                return float(stripped)
            except ValueError:
                pass
        return stripped
