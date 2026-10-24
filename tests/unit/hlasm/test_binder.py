# pyright: standard
"""The binder: sections at doubleword offsets in ESD order, commons merged at their largest length, names resolved locally, then across the image, then to a COBOL program's stub, then to zero (WXTRN) or a stub (EXTRN, warned once); duplicate names across both languages and records not bound yet are refused."""

import pytest

from interpreter.hlasm.binder import Binder
from interpreter.hlasm.cobol_owner import CobolOwner
from interpreter.hlasm.cobol_program import CobolProgram
from interpreter.hlasm.far_branch_entry import FarBranchEntry
from interpreter.hlasm.image_module import ImageModule
from interpreter.hlasm.module_layout import ModuleLayout
from interpreter.hlasm.module_owner import ModuleOwner
from interpreter.hlasm.placed_name import PlacedName
from interpreter.hlasm.stub_name import StubName
from interpreter.hlasm.unresolved_owner import UnresolvedOwner
from interpreter.hlasm.unsupported_binding import UnsupportedBinding
from interpreter.hlasm.weak_zero import WeakZero
from interpreter.project.argument_mode import ArgumentMode
from interpreter.project.common_section import CommonSection
from interpreter.project.control_section import ControlSection
from interpreter.project.default_end import DefaultEnd
from interpreter.project.diagnostic_place import DiagnosticPlace
from interpreter.project.diagnostic_severity import DiagnosticSeverity
from interpreter.project.duplicate_program_in_image import DuplicateProgramInImage
from interpreter.project.entry_label import EntryLabel
from interpreter.project.esd_record import EsdRecord
from interpreter.project.external_dummy_section import ExternalDummySection
from interpreter.project.external_reference import ExternalReference
from interpreter.project.object_module import ObjectModule
from interpreter.project.relocation_kind import RelocationKind
from interpreter.project.relocation_record import RelocationRecord
from interpreter.project.relocation_sign import RelocationSign
from interpreter.project.unit_diagnostic import UnitDiagnostic
from interpreter.project.unresolved_external import UnresolvedExternal
from interpreter.project.using_parameter import UsingParameter
from interpreter.project.weak_reference import WeakReference
from tests.covers import NotLanguageFeature, covers


def _module(
    name: str,
    esd: tuple[EsdRecord, ...],
    relocations: tuple[RelocationRecord, ...] = (),
) -> ImageModule:
    return ImageModule(
        name,
        f"{name}.asm",
        ObjectModule(esd, (), relocations, DefaultEnd(esd[0].name)),
    )


CALLER = _module(
    "A",
    (
        ControlSection("", 3),
        ControlSection("MAIN", 13),
        CommonSection("SHARED", 20),
        ExternalReference("SUB", 4),
        ExternalReference("GONE", 6),
        WeakReference("MAYBE"),
        WeakReference("HELPER"),
    ),
)
CALLEE = _module(
    "B",
    (
        ControlSection("SUB", 8),
        ControlSection("DATA", 4),
        EntryLabel("HELPER", "DATA", 2),
        CommonSection("SHARED", 32),
        ExternalReference("GONE", 9),
    ),
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_binder_lays_out_merges_and_resolves_names():
    binder = Binder((CALLER, CALLEE), ())

    assert binder.layouts == {
        "A": ModuleLayout({"": 0, "MAIN": 8}, 24),
        "B": ModuleLayout({"SUB": 0, "DATA": 8}, 16),
    }
    assert binder.commons == {"SHARED": 32}
    assert [
        binder.resolve(CALLER, name)
        for name in ("", "MAIN", "SHARED", "SUB", "HELPER", "MAYBE", "GONE")
    ] == [
        PlacedName("A", "", 0),
        PlacedName("A", "MAIN", 0),
        PlacedName("A", "SHARED", 0),
        PlacedName("B", "SUB", 0),
        PlacedName("B", "DATA", 2),
        WeakZero("MAYBE"),
        StubName("GONE", 0),
    ]
    assert binder.module_entries() == {
        "A": PlacedName("A", "", 0),
        "B": PlacedName("B", "SUB", 0),
    }
    assert binder.entry_points() == {
        "MAIN": PlacedName("A", "MAIN", 0),
        "SUB": PlacedName("B", "SUB", 0),
        "DATA": PlacedName("B", "DATA", 0),
        "HELPER": PlacedName("B", "DATA", 2),
    }
    assert binder.far_branch_table() == (
        FarBranchEntry(PlacedName("A", "", 0), 24, ModuleOwner("A")),
        FarBranchEntry(PlacedName("B", "SUB", 0), 16, ModuleOwner("B")),
        FarBranchEntry(StubName("GONE", 0), 8, UnresolvedOwner("GONE")),
    )
    assert binder.warnings() == (
        UnitDiagnostic(
            DiagnosticSeverity.WARNING,
            UnresolvedExternal("GONE"),
            DiagnosticPlace("A.asm", 6),
        ),
    )


COBSUB = CobolProgram(
    "COBSUB", "COBSUB.cbl", (UsingParameter(ArgumentMode.REFERENCE, 6),)
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_binder_gives_each_cobol_program_a_stub_its_names_bind_to():
    calls_cobol = _module(
        "A",
        (
            ControlSection("MAIN", 8),
            ExternalReference("COBSUB", 2),
            WeakReference("COBALT"),
            ExternalReference("GONE", 3),
        ),
    )
    cobalt = CobolProgram("COBALT", "COBALT.cbl", ())
    binder = Binder((calls_cobol,), (COBSUB, cobalt))

    assert [binder.resolve(calls_cobol, n) for n in ("COBSUB", "COBALT", "GONE")] == [
        StubName("COBSUB", 0),
        StubName("COBALT", 1),
        StubName("GONE", 2),
    ]
    assert binder.entry_points() == {"MAIN": PlacedName("A", "MAIN", 0)}
    assert binder.far_branch_table() == (
        FarBranchEntry(PlacedName("A", "MAIN", 0), 8, ModuleOwner("A")),
        FarBranchEntry(StubName("COBSUB", 0), 8, CobolOwner(COBSUB)),
        FarBranchEntry(StubName("COBALT", 1), 8, CobolOwner(cobalt)),
        FarBranchEntry(StubName("GONE", 2), 8, UnresolvedOwner("GONE")),
    )
    assert binder.warnings() == (
        UnitDiagnostic(
            DiagnosticSeverity.WARNING,
            UnresolvedExternal("GONE"),
            DiagnosticPlace("A.asm", 3),
        ),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_binder_refuses_a_program_id_defined_twice_in_either_language():
    with pytest.raises(DuplicateProgramInImage) as program_and_section:
        Binder((CALLEE,), (CobolProgram("DATA", "DATA.cbl", ()),))
    with pytest.raises(DuplicateProgramInImage) as program_and_entry:
        Binder((CALLEE,), (CobolProgram("HELPER", "HELPER.cbl", ()),))
    with pytest.raises(DuplicateProgramInImage) as two_programs:
        Binder((), (COBSUB, CobolProgram("COBSUB", "OTHER.cbl", ())))

    assert [
        str(program_and_section.value),
        str(program_and_entry.value),
        str(two_programs.value),
    ] == [
        "program DATA is in the image twice: B.asm and DATA.cbl",
        "program HELPER is in the image twice: B.asm and HELPER.cbl",
        "program COBSUB is in the image twice: COBSUB.cbl and OTHER.cbl",
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_binder_refuses_duplicates_and_records_it_does_not_bind():
    entry_twice = _module(
        "C", (ControlSection("OTHER", 4), EntryLabel("SUB", "OTHER", 0))
    )
    q_constant = _module(
        "D",
        (ControlSection("Q", 4),),
        (
            RelocationRecord(
                "Q", 0, 4, RelocationKind.PR_OFFSET, "PR", RelocationSign.PLUS, 0
            ),
        ),
    )
    dummy = _module("E", (ControlSection("X", 4), ExternalDummySection("PR", 8, 8)))

    with pytest.raises(DuplicateProgramInImage) as duplicate:
        Binder((CALLEE, entry_twice), ())

    with pytest.raises(UnsupportedBinding) as relocation:
        Binder((q_constant,), ())
    with pytest.raises(UnsupportedBinding) as external_dummy:
        Binder((dummy,), ())

    assert [
        str(duplicate.value),
        str(relocation.value),
        str(external_dummy.value),
    ] == [
        "program SUB is in the image twice: B.asm and C.asm",
        "PR_OFFSET relocation in module D is not bound yet (red-dragon-6uyp.96)",
        "XD PR in module E is not bound yet (red-dragon-6uyp.96)",
    ]
