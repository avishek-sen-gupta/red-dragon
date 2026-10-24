# pyright: standard
"""An assembly's object module: ESD in section order with private code, common sections, ENTRY labels, external references by strength and external dummy sections; TXT from its constants; an ADDRESS RLD for each relocatable or external address constant, a PR_OFFSET, CLASS_LENGTH or PR_TOTAL RLD for each Q, J or CXD, a signed ADDRESS RLD per term of a complex-relocatable constant outside a DSECT; END at the named entry."""

from pathlib import Path

from hlasm_asg.program.hlasm_program import HlasmProgram
from interpreter.hlasm.hlasm_frontend import HlasmFrontend
from interpreter.project.common_section import CommonSection
from interpreter.project.control_section import ControlSection
from interpreter.project.entry_label import EntryLabel
from interpreter.project.external_dummy_section import ExternalDummySection
from interpreter.project.external_reference import ExternalReference
from interpreter.project.named_end import NamedEnd
from interpreter.project.no_relocation_target import NoRelocationTarget
from interpreter.project.object_module import ObjectModule
from interpreter.project.relocation_kind import RelocationKind
from interpreter.project.relocation_name import RelocationName
from interpreter.project.relocation_record import RelocationRecord
from interpreter.project.relocation_sign import RelocationSign
from interpreter.project.relocation_target import RelocationTarget
from interpreter.project.text_record import TextRecord
from interpreter.project.weak_reference import WeakReference
from tests.covers import NotLanguageFeature, covers

FIXTURES = Path(__file__).parent / "fixtures"


def _record(
    offset: int, length: int, kind: RelocationKind, target: RelocationTarget
) -> RelocationRecord:
    return RelocationRecord(
        "MAIN", offset, length, kind, target, RelocationSign.PLUS, 0
    )


def _address(offset: int, length: int, target: str, addend: int) -> RelocationRecord:
    return RelocationRecord(
        "MAIN",
        offset,
        length,
        RelocationKind.ADDRESS,
        RelocationName(target),
        RelocationSign.PLUS,
        addend,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_object_module_records_esd_txt_rld_and_end():
    program = HlasmProgram.model_validate_json(
        (FIXTURES / "linkage_program.json").read_text()
    )

    assert HlasmFrontend(program, "M").object_module == ObjectModule(
        esd=(
            ControlSection("", 2),
            ControlSection("MAIN", 23),
            CommonSection("SHARED", 20),
            ControlSection("DATA", 2),
            EntryLabel("HERE", "MAIN", 8),
            ExternalReference("STRONG", 4),
            WeakReference("WEAK"),
        ),
        text=(
            TextRecord("", 0, b"\x00\x01"),
            TextRecord("DATA", 0, b"\xc1\xc2"),
        ),
        relocations=(
            _address(8, 4, "DATA", 4),
            _address(12, 4, "STRONG", 0),
            _address(16, 4, "WEAK", 0),
            _address(20, 3, "MAIN", 8),
        ),
        end=NamedEnd("MAIN", "MAIN", 0),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_object_module_records_external_dummies_and_their_q_j_and_cxd_fields():
    program = HlasmProgram.model_validate_json(
        (FIXTURES / "pseudo_register_program.json").read_text()
    )

    assert HlasmFrontend(program, "M").object_module == ObjectModule(
        esd=(
            ControlSection("MAIN", 16),
            ExternalDummySection("PRA", 11, 4),
            ExternalDummySection("D", 20, 8),
        ),
        text=(),
        relocations=(
            _record(0, 4, RelocationKind.PR_OFFSET, RelocationName("PRA")),
            _record(4, 2, RelocationKind.PR_OFFSET, RelocationName("D")),
            _record(8, 4, RelocationKind.CLASS_LENGTH, RelocationName("PRA")),
            _record(12, 4, RelocationKind.PR_TOTAL, NoRelocationTarget()),
        ),
        end=NamedEnd("MAIN", "MAIN", 0),
    )


def _item(
    offset: int, length: int, target: str, sign: RelocationSign, addend: int
) -> RelocationRecord:
    return RelocationRecord(
        "B",
        offset,
        length,
        RelocationKind.ADDRESS,
        RelocationName(target),
        sign,
        addend,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_object_module_records_a_signed_rld_item_per_complex_relocatable_term():
    program = HlasmProgram.model_validate_json(
        (FIXTURES / "complex_relocatable_program.json").read_text()
    )
    plus, minus = RelocationSign.PLUS, RelocationSign.MINUS

    assert HlasmFrontend(program, "M").object_module == ObjectModule(
        esd=(
            ControlSection("MAIN", 8),
            ControlSection("B", 20),
            ExternalReference("E1", 10),
        ),
        text=(
            TextRecord("MAIN", 0, bytes(4)),
            TextRecord("MAIN", 4, bytes(4)),
            TextRecord("B", 0, bytes(2)),
            TextRecord("B", 16, b"\x00\x00\x00\x08"),
        ),
        relocations=(
            _item(4, 4, "B", minus, 4),
            _item(4, 4, "MAIN", plus, 0),
            _item(8, 2, "B", minus, 12),
            _item(8, 2, "MAIN", plus, 0),
            _item(8, 2, "MAIN", plus, 0),
            _item(12, 4, "E1", minus, 7),
            _item(12, 4, "MAIN", plus, 0),
        ),
        end=NamedEnd("MAIN", "MAIN", 0),
    )
