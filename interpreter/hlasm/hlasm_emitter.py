# pyright: standard
"""Accumulates HLASM lowering IR and emits reads and writes of the machine state: general and access registers, CC and storage."""

import dataclasses
from itertools import count

from interpreter.func_name import FuncName
from interpreter.hlasm.chain_link import Chain, extended, flattened
from interpreter.hlasm.empty_chain import EmptyChain
from interpreter.hlasm.hlasm_constants import (
    ACCESS_REGISTER_BYTES,
    ACCESS_REGISTERS_VAR,
    BINARY_BYTES_TO_INT,
    BITS_PER_BYTE,
    CC_VAR,
    GPR_BYTES,
    GPRS_VAR,
    INT_TO_BINARY_BYTES,
    LOW_WORD_OFFSET,
    WORD_BYTES,
)
from interpreter.hlasm.located_span import LocatedSpan
from interpreter.instructions import (
    Binop,
    CallFunction,
    Const,
    InstructionBase,
    LoadRegion,
    LoadVar,
    StoreVar,
    WriteRegion,
)
from interpreter.ir import CodeLabel, SourceLocation
from interpreter.operator_kind import BinopKind
from interpreter.register import Register
from interpreter.var_name import VarName


class HlasmEmitter:
    """The lowering's instruction sink; GPR values are unsigned images, stores wrap."""

    def __init__(self, register_prefix: str = "") -> None:
        self._register_prefix = register_prefix
        self._registers = count()
        self._labels = count()
        self._instructions: Chain[InstructionBase] = EmptyChain()
        self._spans: Chain[LocatedSpan] = EmptyChain()

    def instructions(self) -> tuple[InstructionBase, ...]:
        located = {
            index: span.location
            for span in flattened(self._spans)
            for index in span.indices()
        }
        return tuple(
            (
                dataclasses.replace(inst, source_location=located[index])
                if index in located
                else inst
            )
            for index, inst in enumerate(flattened(self._instructions))
        )

    def emitted_count(self) -> int:
        return self._instructions.length

    def fresh_reg(self) -> Register:
        return Register(f"%{self._register_prefix}{next(self._registers)}")

    def fresh_label(self, prefix: str) -> CodeLabel:
        return CodeLabel(f"{prefix}_{next(self._labels)}")

    def emit_inst(self, inst: InstructionBase) -> InstructionBase:
        self._instructions = extended(self._instructions, inst)
        return inst

    def load_gr32(self, r: int) -> Register:
        return self._load(GPR_BYTES * r + LOW_WORD_OFFSET, WORD_BYTES)

    def load_gr64(self, r: int) -> Register:
        return self._load(GPR_BYTES * r, GPR_BYTES)

    def store_gr32(self, r: int, value: Register) -> None:
        self._store(GPR_BYTES * r + LOW_WORD_OFFSET, WORD_BYTES, value)

    def store_gr64(self, r: int, value: Register) -> None:
        self._store(GPR_BYTES * r, GPR_BYTES, value)

    def load_gr_high32(self, r: int) -> Register:
        return self._load(GPR_BYTES * r, WORD_BYTES)

    def store_gr_high32(self, r: int, value: Register) -> None:
        self._store(GPR_BYTES * r, WORD_BYTES, value)

    def load_ar(self, r: int) -> Register:
        return self.load_storage(
            self.load_var(ACCESS_REGISTERS_VAR),
            ACCESS_REGISTER_BYTES * r,
            ACCESS_REGISTER_BYTES,
        )

    def store_ar(self, r: int, value: Register) -> None:
        self.store_storage(
            self.load_var(ACCESS_REGISTERS_VAR),
            ACCESS_REGISTER_BYTES * r,
            ACCESS_REGISTER_BYTES,
            value,
        )

    def set_cc(self, value: Register) -> None:
        self.emit_inst(StoreVar(name=CC_VAR, value_reg=value))

    def int_(self, value: int) -> Register:
        reg = self.fresh_reg()
        self.emit_inst(Const.int_(reg, value))
        return reg

    def str_(self, value: str) -> Register:
        reg = self.fresh_reg()
        self.emit_inst(Const.string(reg, value))
        return reg

    def locate_from(self, start: int, location: SourceLocation) -> None:
        self._spans = extended(
            self._spans, LocatedSpan(start, self._instructions.length, location)
        )

    def unsigned_flag(self) -> Register:
        reg = self.fresh_reg()
        self.emit_inst(Const.bool_(reg, False))
        return reg

    def binop(self, operator: BinopKind, left: Register, right: Register) -> Register:
        reg = self.fresh_reg()
        self.emit_inst(Binop(result_reg=reg, operator=operator, left=left, right=right))
        return reg

    def load_var(self, name: VarName) -> Register:
        reg = self.fresh_reg()
        self.emit_inst(LoadVar(result_reg=reg, name=name))
        return reg

    def _gprs(self) -> Register:
        return self.load_var(GPRS_VAR)

    def call(self, func_name: FuncName, args: tuple[Register, ...]) -> Register:
        reg = self.fresh_reg()
        self.emit_inst(CallFunction(result_reg=reg, func_name=func_name, args=args))
        return reg

    def _load(self, offset: int, width: int) -> Register:
        return self.load_storage(self._gprs(), offset, width)

    def _store(self, offset: int, width: int, value: Register) -> None:
        self.store_storage(self._gprs(), offset, width, value)

    def load_storage(self, region: Register, offset: int, width: int) -> Register:
        image = self.load_bytes(region, self.int_(offset), width)
        return self.call(BINARY_BYTES_TO_INT, (image, self.unsigned_flag()))

    def store_storage(
        self, region: Register, offset: int, width: int, value: Register
    ) -> None:
        wrapped = self.fresh_reg()
        modulus = self.int_(1 << (BITS_PER_BYTE * width))
        self.emit_inst(
            Binop(result_reg=wrapped, operator=BinopKind.MOD, left=value, right=modulus)
        )
        self.write_bytes(region, self.int_(offset), width, self.image(wrapped, width))

    def image(self, value: Register, width: int) -> Register:
        return self.call(
            INT_TO_BINARY_BYTES, (value, self.int_(width), self.unsigned_flag())
        )

    def load_bytes(self, region: Register, offset: Register, width: int) -> Register:
        image = self.fresh_reg()
        self.emit_inst(
            LoadRegion(
                result_reg=image, region_reg=region, offset_reg=offset, length=width
            )
        )
        return image

    def write_bytes(
        self, region: Register, offset: Register, width: int, image: Register
    ) -> None:
        self.emit_inst(
            WriteRegion(
                region_reg=region, offset_reg=offset, length=width, value_reg=image
            )
        )
