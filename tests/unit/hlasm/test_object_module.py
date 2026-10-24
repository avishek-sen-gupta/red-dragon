# pyright: standard
"""An assembly's object module: ESD in section order with private code, common sections, ENTRY labels and external references by strength; TXT from its constants; an ADDRESS RLD for each relocatable or external address constant; END at the named entry."""

from pathlib import Path

from hlasm_asg.program.hlasm_program import HlasmProgram
from interpreter.hlasm.hlasm_frontend import HlasmFrontend
from interpreter.project.common_section import CommonSection
from interpreter.project.control_section import ControlSection
from interpreter.project.entry_label import EntryLabel
from interpreter.project.external_reference import ExternalReference
from interpreter.project.named_end import NamedEnd
from interpreter.project.object_module import ObjectModule
from interpreter.project.relocation_kind import RelocationKind
from interpreter.project.relocation_record import RelocationRecord
from interpreter.project.relocation_sign import RelocationSign
from interpreter.project.text_record import TextRecord
from interpreter.project.weak_reference import WeakReference
from tests.covers import NotLanguageFeature, covers

FIXTURES = Path(__file__).parent / "fixtures"


def _address(offset: int, length: int, target: str, addend: int) -> RelocationRecord:
    return RelocationRecord(
        "MAIN",
        offset,
        length,
        RelocationKind.ADDRESS,
        target,
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
