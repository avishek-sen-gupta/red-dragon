# pyright: standard
"""IR shared by the IEEE radixes: a result field, the FPC rounding-mode code, the raised outcome, and the IEEE trap ladder (ruling R43), with a step a radix may apply to the outcome first and an end an instruction may change."""

from collections.abc import Callable
from dataclasses import replace

from interpreter.hlasm.conditional import emit_when
from interpreter.hlasm.data_movement import keep
from interpreter.hlasm.fp_slots import (
    FLAGS_SLOT,
    INEXACT_DXC_SLOT,
    SCALED_DXC_SLOT,
    SCALED_SLOT,
    SCALING_BITS,
    SUPPRESSING_BITS,
    TRAP_SLOT,
)
from interpreter.hlasm.hlasm_constants import BYTE_MASK, FPC_VAR, LIST_GET
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ieee_outcome import IeeeOutcome
from interpreter.hlasm.ladder_end import LadderEnd, ScaledTrap
from interpreter.hlasm.opcodes.floating_point_support import (
    FLAG_SHIFT,
    IEEE_BITS,
    MASK_SHIFT,
    MODE_FIELD,
    emit_data_exception,
)
from interpreter.hlasm.opcodes.fpr_images import list_item
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Deliver = Callable[[Register], None]
type OutcomeStep = Callable[[HlasmEmitter, Register, IeeeOutcome], IeeeOutcome]


def field_at(
    emitter: HlasmEmitter, result: Register, slot: Register, at: int
) -> Register:
    index = emitter.binop(BinopKind.ADD, slot, emitter.int_(at))
    return emitter.call(LIST_GET, (result, index))


def mode_code_of(
    emitter: HlasmEmitter, fpc: Register, shift: int, offset: int
) -> Register:
    moved = emitter.binop(BinopKind.RSHIFT, fpc, emitter.int_(shift)) if shift else fpc
    mode = keep(MODE_FIELD)(emitter, moved)
    return emitter.binop(BinopKind.ADD, mode, emitter.int_(offset))


def fpc_mode_code(emitter: HlasmEmitter, shift: int, offset: int) -> Register:
    return mode_code_of(emitter, emitter.load_var(FPC_VAR), shift, offset)


def outcome_of(emitter: HlasmEmitter, result: Register) -> IeeeOutcome:
    return IeeeOutcome(
        list_item(emitter, result, TRAP_SLOT),
        list_item(emitter, result, FLAGS_SLOT),
        list_item(emitter, result, SCALED_DXC_SLOT),
        list_item(emitter, result, INEXACT_DXC_SLOT),
    )


def without(emitter: HlasmEmitter, outcome: IeeeOutcome, bits: int) -> IeeeOutcome:
    kept = BYTE_MASK ^ bits
    return replace(
        outcome,
        trap=keep(kept)(emitter, outcome.trap),
        flags=keep(kept)(emitter, outcome.flags),
    )


def _any(emitter: HlasmEmitter, value: Register) -> Register:
    return emitter.binop(BinopKind.NE, value, emitter.int_(0))


def enabled_traps(emitter: HlasmEmitter, fpc: Register, trap: Register) -> Register:
    shifted = emitter.binop(BinopKind.RSHIFT, fpc, emitter.int_(MASK_SHIFT))
    return emitter.binop(BinopKind.BIT_AND, trap, keep(IEEE_BITS)(emitter, shifted))


def _untrapped(emitter: HlasmEmitter, flags: Register, enabled: Register) -> Register:
    inverted = emitter.binop(BinopKind.BIT_XOR, enabled, emitter.int_(BYTE_MASK))
    return emitter.binop(BinopKind.BIT_AND, flags, inverted)


def _flagged(emitter: HlasmEmitter, fpc: Register, raised: Register) -> Register:
    moved = emitter.binop(BinopKind.LSHIFT, raised, emitter.int_(FLAG_SHIFT))
    return emitter.binop(BinopKind.BIT_OR, fpc, moved)


def _stored_flags(
    emitter: HlasmEmitter, fpc: Register, flags: Register, enabled: Register
) -> tuple[Register, Register]:
    untrapped = _untrapped(emitter, flags, enabled)
    flagged = _flagged(emitter, fpc, untrapped)
    emitter.emit_inst(StoreVar(name=FPC_VAR, value_reg=flagged))
    return untrapped, flagged


def _when_any(emitter: HlasmEmitter, bits: Register, then: Callable[[], None]) -> None:
    emit_when(emitter, emitter.binop(BinopKind.NE, bits, emitter.int_(0)), then)


def _deliver_once(
    emitter: HlasmEmitter,
    fpc: Register,
    enabled: Register,
    outcome: IeeeOutcome,
    deliver: tuple[Deliver, ScaledTrap],
) -> None:
    store, scaled_trap = deliver
    scaling = keep(SCALING_BITS)(emitter, enabled)
    scaled = emitter.binop(BinopKind.NE, scaling, emitter.int_(0))
    store(emitter.binop(BinopKind.MUL, scaled, emitter.int_(SCALED_SLOT)))
    emit_when(emitter, scaled, lambda: scaled_trap(emitter, fpc, outcome.scaled_dxc))


def as_raised(
    emitter: HlasmEmitter, fpc: Register, outcome: IeeeOutcome
) -> IeeeOutcome:
    return outcome


def _no_cc(emitter: HlasmEmitter, raised: Register) -> None:
    return None


TRAPPING_END = LadderEnd(emit_data_exception, _no_cc)


def emit_ieee_ladder(
    emitter: HlasmEmitter,
    raised: IeeeOutcome,
    deliver: Deliver,
    step: OutcomeStep = as_raised,
    end: LadderEnd = TRAPPING_END,
) -> None:
    fpc = emitter.load_var(FPC_VAR)
    outcome = step(emitter, fpc, raised)
    enabled = enabled_traps(emitter, fpc, outcome.trap)
    suppressing = keep(SUPPRESSING_BITS)(emitter, enabled)
    _when_any(
        emitter, suppressing, lambda: emit_data_exception(emitter, fpc, suppressing)
    )
    _deliver_once(emitter, fpc, enabled, outcome, (deliver, end.scaled_trap))
    untrapped, flagged = _stored_flags(emitter, fpc, outcome.flags, enabled)
    _when_any(
        emitter,
        enabled,
        lambda: emit_data_exception(emitter, flagged, outcome.inexact_dxc),
    )
    end.completed(emitter, untrapped)
