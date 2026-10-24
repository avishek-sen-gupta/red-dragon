# pyright: standard
"""The JSON the che4z bridge exports parses into typed, discriminated models."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import pytest
from pydantic import ValidationError

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.abs_symbol import AbsSymbol
from hlasm_asg.program.addresses_nominal import AddressesNominal
from hlasm_asg.program.addressing_mode import AddressingMode
from hlasm_asg.program.amode_setting import AmodeSetting
from hlasm_asg.program.base_displacement_address import BaseDisplacementAddress
from hlasm_asg.program.ccw_statement import CcwStatement
from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.dc_statement import DcStatement
from hlasm_asg.program.default_entry import DefaultEntry
from hlasm_asg.program.diagnostic import Diagnostic
from hlasm_asg.program.ds_item import DsItem
from hlasm_asg.program.ds_statement import DsStatement
from hlasm_asg.program.external_address import ExternalAddress
from hlasm_asg.program.external_kind import ExternalKind
from hlasm_asg.program.external_symbol import ExternalSymbol
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.length_unit import LengthUnit
from hlasm_asg.program.literal_pool import LiteralPool
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.macro_origin import MacroOrigin
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.mnote_level import MnoteLevel
from hlasm_asg.program.named_entry import NamedEntry
from hlasm_asg.program.omitted_nominal import OmittedNominal
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.per_copy_addresses_nominal import PerCopyAddressesNominal
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.related_location import RelatedLocation
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.reloc_symbol import RelocSymbol
from hlasm_asg.program.residency_mode import ResidencyMode
from hlasm_asg.program.rmode_setting import RmodeSetting
from hlasm_asg.program.section import Section
from hlasm_asg.program.section_kind import SectionKind
from hlasm_asg.program.severity import Severity
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from hlasm_asg.program.storage_operand import StorageOperand
from hlasm_asg.program.string_nominal import StringNominal
from tests.covers import NotLanguageFeature, covers

FIXTURE = Path(__file__).parent / "fixtures" / "hello_program.json"
LOOP_FIXTURE = Path(__file__).parent / "fixtures" / "loop_program.json"
WAVE4_FIXTURE = Path(__file__).parent / "fixtures" / "wave4_exports.json"
WAVE4_SOURCE = "src/wave4.asm"
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


def _storage(
    displacement: int, base: int, written: AbsAddress | RelocAddress
) -> StorageOperand:
    return StorageOperand(
        kind="STORAGE",
        displacement=displacement,
        index=0,
        base=base,
        written=written,
    )


class _Placement(TypedDict):
    length_unit: LengthUnit
    scale: int
    exponent: int
    offset: int
    bit_offset: int


def _placed(offset: int) -> _Placement:
    return _Placement(
        length_unit=LengthUnit.BYTE, scale=0, exponent=0, offset=offset, bit_offset=0
    )


def _absolute(value: int) -> AbsAddress:
    return AbsAddress(kind="ABS", value=value)


def _in_hello(offset: int) -> RelocAddress:
    return RelocAddress(kind="RELOC", section="HELLO", offset=offset)


EXPECTED = HlasmProgram(
    format=2,
    sections=(Section(name="HELLO", kind=SectionKind.CSECT, length=52),),
    symbols=(
        _reloc("EXTR", "EXTR", 0, 1, "T"),
        _reloc("HELLO", "HELLO", 0, 1, "J"),
        _reloc("MSG", "HELLO", 20, 5, "C"),
        _reloc("OUT", "HELLO", 25, 5, "C"),
    ),
    entry=NamedEntry(kind="NAMED", name="HELLO"),
    entries=(),
    externals=(ExternalSymbol(name="EXTR", kind=ExternalKind.EXTRN),),
    statements=(
        _machine(
            0,
            "LA",
            "LA",
            "RX-a",
            4,
            (RegOperand(kind="REG", value=1), _storage(5, 0, _absolute(5))),
            _open(3),
        ),
        _machine(
            4,
            "LA",
            "LA",
            "RX-a",
            4,
            (RegOperand(kind="REG", value=3), _storage(1, 0, _absolute(1))),
            MacroOrigin(kind="MACRO", file=SOURCE, line=4, macro="MYM", depth=1),
        ),
        _machine(
            8,
            "L",
            "L",
            "RX-a",
            4,
            (RegOperand(kind="REG", value=2), _storage(48, 15, _in_hello(48))),
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
                _storage(20, 15, _in_hello(20)),
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
                    **_placed(20),
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
                    **_placed(25),
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
                            ExternalAddress(kind="EXTERNAL", name="EXTR", offset=0),
                        ),
                    ),
                    **_placed(32),
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
                **_placed(48),
            ),
            origin=_open(5),
        ),
    ),
    amodes=(),
    rmodes=(),
    diagnostics=(),
)


def _loop_origin(line: int) -> OpenCodeOrigin:
    return OpenCodeOrigin(kind="OPEN_CODE", file="src/loop.asm", line=line)


LOOP_EXPECTED = HlasmProgram(
    format=2,
    sections=(Section(name="MAIN", kind=SectionKind.CSECT, length=8),),
    symbols=(
        AbsSymbol(kind="ABS", name="FIVE", value=5, type="U", length=1),
        _reloc("LOOP", "MAIN", 0, 4, "I"),
        _reloc("MAIN", "MAIN", 0, 1, "J"),
    ),
    entry=DefaultEntry(kind="DEFAULT"),
    entries=(),
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
    amodes=(),
    rmodes=(),
    diagnostics=(),
)


def _wave4_dc(
    offset: int, label: str, line: int, items: tuple[DcItem, ...]
) -> DcStatement:
    return DcStatement(
        kind="DC",
        section="T",
        offset=offset,
        label=label,
        mnemonic="DC",
        items=items,
        origin=OpenCodeOrigin(kind="OPEN_CODE", file=WAVE4_SOURCE, line=line),
    )


WAVE4_STATEMENTS = (
    _wave4_dc(
        0,
        "",
        10,
        (
            DcItem(
                type="F",
                extension="",
                duplication=0,
                length=4,
                length_unit=LengthUnit.BYTE,
                explicit_length=False,
                scale=0,
                exponent=0,
                offset=0,
                bit_offset=0,
                nominal=OmittedNominal(kind="OMITTED"),
            ),
        ),
    ),
    _wave4_dc(
        0,
        "",
        11,
        (
            DcItem(
                type="B",
                extension="",
                duplication=1,
                length=4,
                length_unit=LengthUnit.BIT,
                explicit_length=True,
                scale=0,
                exponent=0,
                offset=0,
                bit_offset=0,
                nominal=StringNominal(kind="STRING", value="1010"),
            ),
            DcItem(
                type="S",
                extension="",
                duplication=1,
                length=2,
                length_unit=LengthUnit.BYTE,
                explicit_length=False,
                scale=0,
                exponent=0,
                offset=2,
                bit_offset=0,
                nominal=AddressesNominal(
                    kind="ADDRESSES",
                    values=(
                        BaseDisplacementAddress(
                            kind="BASE_DISPLACEMENT", base=12, displacement=16
                        ),
                    ),
                ),
            ),
        ),
    ),
    CcwStatement(
        kind="CCW",
        section="T",
        offset=8,
        label="READ",
        mnemonic="CCW",
        command_code=2,
        address=RelocAddress(kind="RELOC", section="T", offset=16),
        flags=32,
        count=4,
        origin=OpenCodeOrigin(kind="OPEN_CODE", file=WAVE4_SOURCE, line=12),
    ),
    _wave4_dc(
        16,
        "FIELD",
        13,
        (
            DcItem(
                type="F",
                extension="",
                duplication=1,
                length=4,
                length_unit=LengthUnit.BYTE,
                explicit_length=False,
                scale=0,
                exponent=1,
                offset=16,
                bit_offset=0,
                nominal=StringNominal(kind="STRING", value="1"),
            ),
        ),
    ),
    _wave4_dc(
        20,
        "",
        14,
        (
            DcItem(
                type="A",
                extension="",
                duplication=2,
                length=4,
                length_unit=LengthUnit.BYTE,
                explicit_length=False,
                scale=0,
                exponent=0,
                offset=20,
                bit_offset=0,
                nominal=PerCopyAddressesNominal(
                    kind="ADDRESSES_PER_COPY",
                    copies=(
                        (RelocAddress(kind="RELOC", section="T", offset=20),),
                        (RelocAddress(kind="RELOC", section="T", offset=24),),
                    ),
                ),
            ),
        ),
    ),
)


class TestProgramModel:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_operand_placement_modifiers_s_constants_ccw_modes_and_call_stacks_parse(
        self,
    ):
        parsed = HlasmProgram.model_validate_json(WAVE4_FIXTURE.read_text())

        assert parsed.statements == WAVE4_STATEMENTS
        assert parsed.amodes == (AmodeSetting(name="T", mode=AddressingMode.AMODE_31),)
        assert parsed.rmodes == (RmodeSetting(name="T", mode=ResidencyMode.ANY),)
        assert parsed.diagnostics == (
            Diagnostic(
                code="MNOTE",
                severity=Severity.WARNING,
                message="CAREFUL",
                file=WAVE4_SOURCE,
                line=3,
                related=(RelatedLocation(file=WAVE4_SOURCE, line=9),),
                mnote=MnoteLevel(kind="LEVEL", level=4),
            ),
        )

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
                text.replace('"format":2', '"format":2,"x":0')
            )

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_abs_symbol_imm_relative_target_and_default_entry_parse(self):
        parsed = HlasmProgram.model_validate_json(LOOP_FIXTURE.read_text())

        assert parsed == LOOP_EXPECTED
