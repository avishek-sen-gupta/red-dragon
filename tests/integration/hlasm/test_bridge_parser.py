# pyright: standard
"""The real che4z bridge, run through HlasmBridgeParser."""

from __future__ import annotations

from pathlib import Path

import pytest

from hlasm_asg.hlasm_bridge_parser import make_hlasm_parser
from hlasm_asg.hlasm_parse_error import HlasmParseError
from hlasm_asg.program.addresses_nominal import AddressesNominal
from hlasm_asg.program.addressing_mode import AddressingMode
from hlasm_asg.program.amode_setting import AmodeSetting
from hlasm_asg.program.base_displacement_address import BaseDisplacementAddress
from hlasm_asg.program.ccw_statement import CcwStatement
from hlasm_asg.program.dc_statement import DcStatement
from hlasm_asg.program.diagnostic import Diagnostic
from hlasm_asg.program.length_unit import LengthUnit
from hlasm_asg.program.macro_origin import MacroOrigin
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.related_location import RelatedLocation
from hlasm_asg.program.reloc_address import RelocAddress
from hlasm_asg.program.residency_mode import ResidencyMode
from hlasm_asg.program.rmode_setting import RmodeSetting
from hlasm_asg.program.severity import Severity
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import BARE_ASSEMBLY

MACRO_SOURCE = b"HELLO    CSECT\n         MYM\n         BR    14\n         END\n"
MACRO_LIBRARY = b"         MACRO\n         MYM\n         LA    3,1\n         MEND\n"


SOURCE_NAME = "src/hello.asm"

EXPORTS_SOURCE = b"""\
         MACRO
         WARN
         MNOTE 4,'CAREFUL'
         MEND
T        CSECT
T        AMODE 31
T        RMODE ANY
         USING T,12
         WARN
         DC    BL.4'1010',S(FIELD)
         CCW1  X'02',FIELD,X'20',4
FIELD    DC    FE1'1',FS2'1'
         END
"""


@pytest.fixture
def syslib(tmp_path: Path) -> Path:
    directory = tmp_path / "lib"
    directory.mkdir()
    (directory / "MYM").write_bytes(MACRO_LIBRARY)
    return directory


class TestBridgeParser:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_bridge_parses_hello_and_keeps_macro_origin(
        self, tmp_path: Path, syslib: Path
    ):
        parser = make_hlasm_parser([syslib])

        out = parser.parse_to_file(
            MACRO_SOURCE, SOURCE_NAME, tmp_path / "program.json", BARE_ASSEMBLY
        )
        program = parser.read(out)

        macro_origin, open_origin = [s.origin for s in program.statements]
        assert macro_origin == MacroOrigin(
            kind="MACRO", file=SOURCE_NAME, line=2, macro="MYM", depth=1
        )
        assert open_origin == OpenCodeOrigin(kind="OPEN_CODE", file=SOURCE_NAME, line=3)
        assert [section.name for section in program.sections] == ["HELLO"]

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_bridge_exports_placement_modifiers_s_constants_ccw_modes_and_call_stacks(
        self, tmp_path: Path
    ):
        parser = make_hlasm_parser()

        program = parser.read(
            parser.parse_to_file(
                EXPORTS_SOURCE, SOURCE_NAME, tmp_path / "p.json", BARE_ASSEMBLY
            )
        )

        bits, ccw, field = program.statements
        assert isinstance(bits, DcStatement) and isinstance(field, DcStatement)
        assert [
            (
                i.type,
                i.offset,
                i.bit_offset,
                i.length,
                i.length_unit,
                i.scale,
                i.exponent,
            )
            for i in (*bits.items, *field.items)
        ] == [
            ("B", 0, 0, 4, LengthUnit.BIT, 0, 0),
            ("S", 2, 0, 2, LengthUnit.BYTE, 0, 0),
            ("F", 16, 0, 4, LengthUnit.BYTE, 0, 1),
            ("F", 20, 0, 4, LengthUnit.BYTE, 2, 0),
        ]
        assert bits.items[1].nominal == AddressesNominal(
            kind="ADDRESSES",
            values=(
                BaseDisplacementAddress(
                    kind="BASE_DISPLACEMENT", base=12, displacement=16
                ),
            ),
        )
        assert ccw == CcwStatement(
            kind="CCW",
            section="T",
            offset=8,
            label="",
            mnemonic="CCW1",
            command_code=2,
            address=RelocAddress(kind="RELOC", section="T", offset=16),
            flags=32,
            count=4,
            origin=OpenCodeOrigin(kind="OPEN_CODE", file=SOURCE_NAME, line=11),
        )
        assert (program.amodes, program.rmodes) == (
            (AmodeSetting(name="T", mode=AddressingMode.AMODE_31),),
            (RmodeSetting(name="T", mode=ResidencyMode.ANY),),
        )
        assert program.diagnostics == (
            Diagnostic(
                code="MNOTE",
                severity=Severity.WARNING,
                message="CAREFUL",
                file=SOURCE_NAME,
                line=3,
                related=(RelatedLocation(file=SOURCE_NAME, line=9),),
            ),
        )

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_bridge_refuses_assembly_errors(self, tmp_path: Path):
        parser = make_hlasm_parser()

        with pytest.raises(HlasmParseError, match="M120 line 1") as refused:
            parser.parse_to_file(
                b"         LA    99,0\n",
                SOURCE_NAME,
                tmp_path / "program.json",
                BARE_ASSEMBLY,
            )

        (diagnostic,) = refused.value.diagnostics
        assert diagnostic == Diagnostic(
            code="M120",
            severity=Severity.ERROR,
            message="Error at LA instruction: register operand absolute value must be between 0 and 15",
            file=SOURCE_NAME,
            line=1,
            related=(),
        )
        assert not (tmp_path / "program.json").exists()
