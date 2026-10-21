# pyright: standard
"""The JSON the che4z bridge exports parses into typed, discriminated models."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.abs_symbol import AbsSymbol
from hlasm_asg.program.addresses_nominal import AddressesNominal
from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.dc_statement import DcStatement
from hlasm_asg.program.default_entry import DefaultEntry
from hlasm_asg.program.ds_item import DsItem
from hlasm_asg.program.ds_statement import DsStatement
from hlasm_asg.program.external_address import ExternalAddress
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.literal_pool import LiteralPool
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.macro_origin import MacroOrigin
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.named_entry import NamedEntry
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.reloc_symbol import RelocSymbol
from hlasm_asg.program.section import Section
from hlasm_asg.program.section_kind import SectionKind
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from hlasm_asg.program.storage_operand import StorageOperand
from hlasm_asg.program.string_nominal import StringNominal
from tests.covers import NotLanguageFeature, covers

FIXTURE = Path(__file__).parent / "fixtures" / "hello_program.json"
LOOP_FIXTURE = Path(__file__).parent / "fixtures" / "loop_program.json"
SOURCE = "file:///work/hello.asm"


def _open(line: int) -> OpenCodeOrigin:
    return OpenCodeOrigin(kind="OPEN_CODE", file=SOURCE, line=line)


def _machine(
    offset: int,
    mnemonic: str,
    base_mnemonic: str,
    format: str,
    length: int,
    operands: tuple[
        RegOperand | MaskOperand | StorageOperand | StorageLengthOperand, ...
    ],
    origin: OpenCodeOrigin | MacroOrigin,
) -> MachineStatement:
    return MachineStatement(
        kind="MACHINE",
        section="HELLO",
        offset=offset,
        label="",
        mnemonic=mnemonic,
        base_mnemonic=base_mnemonic,
        format=format,
        length=length,
        operands=operands,
        origin=origin,
    )


def _reloc(name: str, section: str, offset: int, length: int, type: str) -> RelocSymbol:
    return RelocSymbol(
        kind="RELOC",
        name=name,
        section=section,
        offset=offset,
        type=type,
        length=length,
    )


def _storage(displacement: int, base: int) -> StorageOperand:
    return StorageOperand(kind="STORAGE", displacement=displacement, index=0, base=base)


EXPECTED = HlasmProgram(
    format=1,
    sections=(Section(name="HELLO", kind=SectionKind.CSECT, length=52),),
    symbols=(
        _reloc("EXTR", "EXTR", 0, 1, "T"),
        _reloc("HELLO", "HELLO", 0, 1, "J"),
        _reloc("MSG", "HELLO", 20, 5, "C"),
        _reloc("OUT", "HELLO", 25, 5, "C"),
    ),
    entry=NamedEntry(kind="NAMED", name="HELLO"),
    externals=("EXTR",),
    statements=(
        _machine(
            0,
            "LA",
            "LA",
            "RX-a",
            4,
            (RegOperand(kind="REG", value=1), _storage(5, 0)),
            _open(3),
        ),
        _machine(
            4,
            "LA",
            "LA",
            "RX-a",
            4,
            (RegOperand(kind="REG", value=3), _storage(1, 0)),
            MacroOrigin(kind="MACRO", file=SOURCE, line=4, macro="MYM", depth=1),
        ),
        _machine(
            8,
            "L",
            "L",
            "RX-a",
            4,
            (RegOperand(kind="REG", value=2), _storage(48, 15)),
            _open(5),
        ),
        _machine(
            12,
            "MVC",
            "MVC",
            "SS-a",
            6,
            (
                StorageLengthOperand(
                    kind="STORAGE_LENGTH", displacement=25, length=5, base=15
                ),
                _storage(20, 15),
            ),
            _open(6),
        ),
        _machine(
            18,
            "BR",
            "BCR",
            "RR",
            2,
            (MaskOperand(kind="MASK", value=15), RegOperand(kind="REG", value=14)),
            _open(7),
        ),
        DcStatement(
            kind="DC",
            section="HELLO",
            offset=20,
            label="MSG",
            mnemonic="DC",
            items=(
                DcItem(
                    type="C",
                    extension="",
                    duplication=1,
                    length=5,
                    explicit_length=False,
                    nominal=StringNominal(kind="STRING", value="HELLO"),
                ),
            ),
            origin=_open(8),
        ),
        DsStatement(
            kind="DS",
            section="HELLO",
            offset=25,
            label="OUT",
            mnemonic="DS",
            items=(
                DsItem(
                    type="C",
                    extension="",
                    duplication=1,
                    length=5,
                    explicit_length=True,
                ),
            ),
            origin=_open(9),
        ),
        DcStatement(
            kind="DC",
            section="HELLO",
            offset=32,
            label="",
            mnemonic="DC",
            items=(
                DcItem(
                    type="A",
                    extension="",
                    duplication=1,
                    length=4,
                    explicit_length=False,
                    nominal=AddressesNominal(
                        kind="ADDRESSES",
                        values=(
                            RelocAddress(kind="RELOC", section="HELLO", offset=20),
                            AbsAddress(kind="ABS", value=0),
                            ExternalAddress(kind="EXTERNAL", name="EXTR"),
                        ),
                    ),
                ),
            ),
            origin=_open(10),
        ),
    ),
    literals=(
        LiteralPool(
            section="HELLO",
            offset=48,
            item=DcItem(
                type="F",
                extension="",
                duplication=1,
                length=4,
                explicit_length=False,
                nominal=StringNominal(kind="STRING", value="7"),
            ),
        ),
    ),
    diagnostics=(),
)


def _loop_origin(line: int) -> OpenCodeOrigin:
    return OpenCodeOrigin(kind="OPEN_CODE", file="src/loop.asm", line=line)


LOOP_EXPECTED = HlasmProgram(
    format=1,
    sections=(Section(name="MAIN", kind=SectionKind.CSECT, length=8),),
    symbols=(
        AbsSymbol(kind="ABS", name="FIVE", value=5, type="U", length=1),
        _reloc("LOOP", "MAIN", 0, 4, "I"),
        _reloc("MAIN", "MAIN", 0, 1, "J"),
    ),
    entry=DefaultEntry(kind="DEFAULT"),
    externals=(),
    statements=(
        MachineStatement(
            kind="MACHINE",
            section="MAIN",
            offset=0,
            label="LOOP",
            mnemonic="AHI",
            base_mnemonic="AHI",
            format="RI-a",
            length=4,
            operands=(
                RegOperand(kind="REG", value=3),
                ImmOperand(kind="IMM", value=5),
            ),
            origin=_loop_origin(3),
        ),
        MachineStatement(
            kind="MACHINE",
            section="MAIN",
            offset=4,
            label="",
            mnemonic="J",
            base_mnemonic="BRC",
            format="RI-c",
            length=4,
            operands=(
                MaskOperand(kind="MASK", value=15),
                RelocImmOperand(kind="RELOC_IMM", section="MAIN", offset=0),
            ),
            origin=_loop_origin(4),
        ),
    ),
    literals=(),
    diagnostics=(),
)


class TestProgramModel:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_program_json_parses_into_models(self):
        parsed = HlasmProgram.model_validate_json(FIXTURE.read_text())
        assert parsed == EXPECTED

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_unknown_kind_and_extra_fields_are_refused(self):
        text = FIXTURE.read_text()
        with pytest.raises(ValidationError, match="ELSEWHERE"):
            HlasmProgram.model_validate_json(text.replace('"OPEN_CODE"', '"ELSEWHERE"'))
        with pytest.raises(ValidationError, match="Extra inputs"):
            HlasmProgram.model_validate_json(
                text.replace('"format":1', '"format":1,"x":0')
            )

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_abs_symbol_imm_relative_target_and_default_entry_parse(self):
        parsed = HlasmProgram.model_validate_json(LOOP_FIXTURE.read_text())

        assert parsed == LOOP_EXPECTED
