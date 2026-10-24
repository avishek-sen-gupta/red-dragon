# pyright: standard
"""HLASM compiled through AST, unit and linked files, each reused when already on disk; the unit's diagnostics are logged each time it is used. Link also takes COBOL unit files, binding them into one mixed image."""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hlasm_asg.assembly_inputs import AssemblyInputs
from hlasm_asg.hlasm_ast_parser import HlasmAstParser
from interpreter.constants import Language
from interpreter.frontends import bind_image, get_cobol_frontend, get_hlasm_frontend
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.ir import CodeLabel
from interpreter.project.coded_diagnostic import CodedDiagnostic
from interpreter.project.comment_mnote import CommentMnote
from interpreter.project.compiler import build_export_table
from interpreter.project.constant_diagnostic import ConstantDiagnostic
from interpreter.project.constant_source import ConstantSource
from interpreter.project.diagnostic_place import DiagnosticPlace
from interpreter.project.fresh_work_dir import FRESH_WORK_DIR, FreshWorkDir
from interpreter.project.hlasm_compile_options import HlasmCompileOptions
from interpreter.project.hlasm_lowering_settings import HlasmLoweringSettings
from interpreter.project.in_macro import InMacro
from interpreter.project.in_open_code import InOpenCode
from interpreter.project.ir_codec import IrCodec
from interpreter.project.linked_codec import LinkedCodec
from interpreter.project.linker import link_every_module, module_prefix
from interpreter.project.severity_mnote import SeverityMnote
from interpreter.project.source_file import SourceFile
from interpreter.project.start_up import START_UP_PATH
from interpreter.project.types import ExportTable, LinkedProgram, ModuleUnit
from interpreter.project.unit_codec import UnitCodec
from interpreter.project.unit_diagnostic import UnitDiagnostic
from interpreter.project.unresolved_external import UnresolvedExternal
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder

HLASM_FRONTEND_LOGGER = "interpreter.hlasm"
logger = logging.getLogger(HLASM_FRONTEND_LOGGER)

_MAIN_PATH = Path("__main__.asm")
COBOL_START_UP_PATH = Path("__cobol_start_up__")
_PROJECT_ROOT = Path("/")
_NO_INPUTS = HlasmCompileOptions()


@dataclass(frozen=True)
class _Assembly:
    """One source and the work directory its artifacts live in."""

    program: SourceFile
    parser: HlasmAstParser
    options: HlasmCompileOptions
    work_dir: Path

    def _artifact(self, kind: str) -> Path:
        settings = HlasmLoweringSettings(
            self.parser.syslib, self.parser.identity, self.options.names
        )
        return settings.artifact(self.program, self.work_dir, kind)

    def ast(self) -> Path:
        target = self._artifact("ast")
        if not target.exists():
            self.parser.parse_to_file(
                self.program.source,
                str(self.program.path),
                target,
                AssemblyInputs(self.options.names, self.options.clock.now()),
            )
        return target

    def unit(self) -> Path:
        _report(self._unit_module().diagnostics)
        return self._artifact("unit")

    def unit_file(self) -> Path:
        target = self._artifact("unit")
        if not target.exists():
            UnitCodec(IrCodec()).write(self._module(), target)
        return target

    def _unit_module(self) -> ModuleUnit:
        target = self._artifact("unit")
        codec = UnitCodec(IrCodec())
        if target.exists():
            return codec.read(target)
        module = self._module()
        codec.write(module, target)
        return module

    def _name(self) -> str:
        return module_prefix(self.program.path, _PROJECT_ROOT)

    def _module(self) -> ModuleUnit:
        frontend = get_hlasm_frontend(self.parser.read(self.ast()), self._name())
        ir = frontend.lower(self.program.source)
        return ModuleUnit(
            path=self.program.path,
            language=Language.HLASM,
            ir=tuple(ir),
            exports=build_export_table(
                ir, frontend.func_symbol_table, frontend.class_symbol_table
            ),
            imports=(),
            entry_label=frontend.entry_label,
            program=frontend.entry_name,
            diagnostics=frontend.diagnostics,
            object_module=frontend.object_module,
        )


def _cobol_start_up(read: Sequence[ModuleUnit]) -> dict[Path, ModuleUnit]:
    if all(unit.language != Language.COBOL for unit in read):
        return {}
    return {
        COBOL_START_UP_PATH: ModuleUnit(
            path=COBOL_START_UP_PATH,
            language=Language.COBOL,
            ir=get_cobol_frontend().start_up_ir(),
            exports=ExportTable(),
            imports=(),
        )
    }


def _cobol_programs(read: Sequence[ModuleUnit]) -> dict[str, CodeLabel]:
    return {
        unit.program: unit.entry_label.namespace(
            module_prefix(unit.path, _PROJECT_ROOT)
        )
        for unit in read
        if unit.language == Language.COBOL
    }


def _link(units: Sequence[Path]) -> LinkedProgram:
    codec = UnitCodec(IrCodec())
    read = tuple(codec.read(path) for path in units)
    bound = bind_image(read)
    modules = {
        **_cobol_start_up(read),
        START_UP_PATH: bound.start_up,
        **{unit.path: unit for unit in read},
        bound.job_step.path: bound.job_step,
    }
    linked = link_every_module(
        modules=modules,
        import_graph={path: () for path in modules},
        project_root=_PROJECT_ROOT,
        topo_order=tuple(modules),
        language=Language.HLASM,
        type_env_builder=TypeEnvironmentBuilder(),
        symbol_table=SymbolTable.empty(),
    )
    first = next(unit for unit in read if unit.language == Language.HLASM)
    return dataclasses.replace(
        linked,
        programs={**_cobol_programs(read), **bound.programs},
        entry_func_label=bound.module_entries[first.path],
    )


def _linked(units: Sequence[Path], work_dir: Path) -> LinkedProgram:
    names = "\0".join(path.name for path in units)
    digest = hashlib.sha256(names.encode("utf-8")).hexdigest()
    target = work_dir / f"image-{digest}.linked.json"
    codec = LinkedCodec(IrCodec())
    if not target.exists():
        codec.write(_link(units), target)
    linked = codec.read(target)
    _report(tuple(d for unit in linked.modules.values() for d in unit.diagnostics))
    return linked


def _mnote(kind: SeverityMnote | CommentMnote) -> str:
    match kind:
        case SeverityMnote(level=level, text=noted):
            return f"MNOTE {level},{noted}"
        case CommentMnote(text=commented):
            return f"MNOTE *,{commented}"


def _written_in(source: ConstantSource) -> str:
    match source:
        case InMacro(name=name):
            return f" in macro {name}"
        case InOpenCode():
            return ""


def _headed(diagnostic: UnitDiagnostic) -> str:
    kind = diagnostic.kind
    match kind:
        case UnresolvedExternal(name=name):
            return f"EXTRN {name} is not in the image; calls reach it by name"
        case _:
            return _assembled(kind)


def _assembled(
    kind: CodedDiagnostic | ConstantDiagnostic | SeverityMnote | CommentMnote,
) -> str:
    match kind:
        case CodedDiagnostic(code=code, text=text):
            return f"{code} {text}"
        case ConstantDiagnostic(constant=constant, warning=warning, source=source):
            return f"{constant} {warning.value}{_written_in(source)}"
        case mnote:
            return _mnote(mnote)


def _at(place: DiagnosticPlace) -> str:
    return f"{place.file}:{place.line}"


def _rendered(diagnostic: UnitDiagnostic) -> str:
    called = ", ".join(map(_at, diagnostic.stack))
    suffix = f" (called from {called})" if diagnostic.stack else ""
    return f"{_at(diagnostic.place)}: {_headed(diagnostic)}{suffix}"


def _report(diagnostics: Sequence[UnitDiagnostic]) -> None:
    _ = [logger.log(d.severity.value, _rendered(d)) for d in diagnostics]


def _work_dir(given: Path | FreshWorkDir) -> Path:
    match given:
        case Path():
            given.mkdir(parents=True, exist_ok=True)
            return given
        case FreshWorkDir():
            return Path(tempfile.mkdtemp())


def lower_hlasm_program(
    program: SourceFile,
    *,
    parser: HlasmAstParser,
    work_dir: Path,
    options: HlasmCompileOptions = _NO_INPUTS,
) -> tuple[Path, ...]:
    return (_Assembly(program, parser, options, _work_dir(work_dir)).unit(),)


def link_hlasm_units(units: Sequence[Path], work_dir: Path) -> LinkedProgram:
    return _linked(units, _work_dir(work_dir))


def compile_hlasm(
    source: bytes,
    *,
    parser: HlasmAstParser,
    options: HlasmCompileOptions = _NO_INPUTS,
    work_dir: Path | FreshWorkDir = FRESH_WORK_DIR,
    programs: Sequence[SourceFile] = (),
) -> LinkedProgram:
    work = _work_dir(work_dir)
    main, *companions = (
        _Assembly(program, parser, options, work)
        for program in (SourceFile(_MAIN_PATH, source), *programs)
    )
    units = (main.unit_file(), *(c.unit_file() for c in companions))
    return _linked(units, work)
