# pyright: standard
"""The names of an image: each module's layout, the common sections, what every name binds to, the stubs of COBOL programs and unresolved EXTRNs, the job-step entry points and the far-branch table."""

from collections.abc import Mapping, Sequence
from functools import cached_property
from itertools import accumulate
from pathlib import Path

from interpreter.hlasm.bound_name import BoundName
from interpreter.hlasm.cobol_owner import CobolOwner
from interpreter.hlasm.cobol_program import CobolProgram
from interpreter.hlasm.far_branch_entry import FarBranchEntry
from interpreter.hlasm.hlasm_constants import DOUBLEWORD_BYTES, STUB_BYTES
from interpreter.hlasm.image_module import ImageModule
from interpreter.hlasm.module_layout import ModuleLayout
from interpreter.hlasm.module_owner import ModuleOwner
from interpreter.hlasm.placed_name import PlacedName
from interpreter.hlasm.stub_name import StubName
from interpreter.hlasm.unknown_relocation_target import UnknownRelocationTarget
from interpreter.hlasm.unresolved_owner import UnresolvedOwner
from interpreter.hlasm.unsupported_binding import UnsupportedBinding
from interpreter.hlasm.weak_zero import WeakZero
from interpreter.project.common_section import CommonSection
from interpreter.project.control_section import ControlSection
from interpreter.project.default_end import DefaultEnd
from interpreter.project.diagnostic_place import DiagnosticPlace
from interpreter.project.diagnostic_severity import DiagnosticSeverity
from interpreter.project.duplicate_program_in_image import DuplicateProgramInImage
from interpreter.project.entry_label import EntryLabel
from interpreter.project.external_dummy_section import ExternalDummySection
from interpreter.project.external_reference import ExternalReference
from interpreter.project.named_end import NamedEnd
from interpreter.project.relocation_kind import RelocationKind
from interpreter.project.unit_diagnostic import UnitDiagnostic
from interpreter.project.unresolved_external import UnresolvedExternal
from interpreter.project.weak_reference import WeakReference

PRIVATE_CODE = ""


def aligned(length: int, boundary: int) -> int:
    return -(-length // boundary) * boundary


def _layout(module: ImageModule) -> ModuleLayout:
    sections = [r for r in module.object_module.esd if isinstance(r, ControlSection)]
    starts = tuple(
        accumulate((aligned(s.length, DOUBLEWORD_BYTES) for s in sections), initial=0)
    )
    return ModuleLayout(
        {s.name: start for s, start in zip(sections, starts, strict=False)},
        starts[-1],
    )


def _exported(module: ImageModule) -> Mapping[str, PlacedName]:
    return {
        **{
            r.name: PlacedName(module.name, r.name, 0)
            for r in module.object_module.esd
            if isinstance(r, ControlSection) and r.name != PRIVATE_CODE
        },
        **{
            r.name: PlacedName(module.name, r.section, r.offset)
            for r in module.object_module.esd
            if isinstance(r, EntryLabel)
        },
    }


def _ended(module: ImageModule) -> PlacedName:
    match module.object_module.end:
        case NamedEnd(section=section, offset=offset):
            return PlacedName(module.name, section, offset)
        case DefaultEnd(section=default):
            return PlacedName(module.name, default, 0)


def _refuse_unsupported(module: ImageModule) -> None:
    unsupported = [
        *(
            f"XD {r.name}"
            for r in module.object_module.esd
            if isinstance(r, ExternalDummySection)
        ),
        *(
            f"{r.kind.value} relocation"
            for r in module.object_module.relocations
            if r.kind != RelocationKind.ADDRESS
        ),
    ]
    if unsupported:
        raise UnsupportedBinding(unsupported[0], module.name)


def _named_files(
    modules: Sequence[ImageModule], programs: Sequence[CobolProgram]
) -> tuple[tuple[str, str], ...]:
    return (
        *((name, module.file) for module in modules for name in _exported(module)),
        *((program.name, program.file) for program in programs),
    )


def _refuse_duplicates(
    modules: Sequence[ImageModule], programs: Sequence[CobolProgram]
) -> None:
    named = _named_files(modules, programs)
    clash = next(
        (
            (named[later][0], named[earlier][1], named[later][1])
            for later in range(len(named))
            for earlier in range(later)
            if named[earlier][0] == named[later][0]
        ),
        (),
    )
    match clash:
        case (str(name), str(first), str(second)):
            raise DuplicateProgramInImage(name, Path(first), Path(second))
        case _:
            return


class Binder:
    """Raises on a name defined twice and on a record it does not bind yet."""

    def __init__(
        self,
        modules: Sequence[ImageModule],
        programs: Sequence[CobolProgram] = (),
    ) -> None:
        _refuse_duplicates(modules, programs)
        _ = [_refuse_unsupported(module) for module in modules]
        self.modules = tuple(modules)
        self.programs = {program.name: program for program in programs}

    @cached_property
    def layouts(self) -> Mapping[str, ModuleLayout]:
        return {module.name: _layout(module) for module in self.modules}

    @cached_property
    def commons(self) -> Mapping[str, int]:
        sections = [
            r
            for module in self.modules
            for r in module.object_module.esd
            if isinstance(r, CommonSection)
        ]
        return {
            name: max(s.length for s in sections if s.name == name)
            for name in dict.fromkeys(s.name for s in sections)
        }

    @cached_property
    def _definitions(self) -> Mapping[str, PlacedName]:
        return {
            name: placed
            for module in self.modules
            for name, placed in _exported(module).items()
        }

    @cached_property
    def _unresolved_names(self) -> tuple[str, ...]:
        named = [
            r.name
            for module in self.modules
            for r in module.object_module.esd
            if isinstance(r, ExternalReference)
            and r.name not in self._definitions
            and r.name not in self.programs
        ]
        return tuple(n for at, n in enumerate(named) if n not in named[:at])

    @cached_property
    def stubs(self) -> Mapping[str, StubName]:
        names = (*self.programs, *self._unresolved_names)
        return {name: StubName(name, index) for index, name in enumerate(names)}

    def resolve(self, module: ImageModule, target: str) -> BoundName:
        esd = module.object_module.esd
        if any(
            isinstance(r, ControlSection | CommonSection) and r.name == target
            for r in esd
        ):
            return PlacedName(module.name, target, 0)
        if target in self._bound_names:
            return self._bound_names[target]
        return self._unresolved(module, target)

    @cached_property
    def _bound_names(self) -> Mapping[str, BoundName]:
        return {
            **{name: self.stubs[name] for name in self.programs},
            **self._definitions,
        }

    def _unresolved(self, module: ImageModule, target: str) -> BoundName:
        esd = module.object_module.esd
        if any(isinstance(r, WeakReference) and r.name == target for r in esd):
            return WeakZero(target)
        if target in self.stubs:
            return self.stubs[target]
        raise UnknownRelocationTarget(target, module.name)

    def entry_points(self) -> Mapping[str, PlacedName]:
        return self._definitions

    def module_entries(self) -> Mapping[str, PlacedName]:
        return {module.name: _ended(module) for module in self.modules}

    def far_branch_table(self) -> tuple[FarBranchEntry, ...]:
        modules = tuple(
            FarBranchEntry(
                PlacedName(module.name, next(iter(layout.offsets)), 0),
                layout.length,
                ModuleOwner(module.name),
            )
            for module in self.modules
            for layout in (self.layouts[module.name],)
            if layout.offsets
        )
        stubs = tuple(
            FarBranchEntry(stub, STUB_BYTES, self._stub_owner(stub.name))
            for stub in self.stubs.values()
        )
        return (*modules, *stubs)

    def _stub_owner(self, name: str) -> CobolOwner | UnresolvedOwner:
        if name in self.programs:
            return CobolOwner(self.programs[name])
        return UnresolvedOwner(name)

    def warnings(self) -> tuple[UnitDiagnostic, ...]:
        declared = {
            r.name: DiagnosticPlace(module.file, r.line)
            for module in reversed(self.modules)
            for r in module.object_module.esd
            if isinstance(r, ExternalReference)
        }
        return tuple(
            UnitDiagnostic(
                DiagnosticSeverity.WARNING,
                UnresolvedExternal(name),
                declared[name],
            )
            for name in self._unresolved_names
        )
