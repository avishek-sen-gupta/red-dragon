# pyright: standard
"""HLASM compiled through AST, unit and linked files, each reused when already on disk; the unit's diagnostics are logged each time it is used."""

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
from interpreter.frontends import get_hlasm_frontend
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.project.compiler import build_export_table
from interpreter.project.fresh_work_dir import FRESH_WORK_DIR, FreshWorkDir
from interpreter.project.hlasm_compile_options import HlasmCompileOptions
from interpreter.project.hlasm_lowering_settings import HlasmLoweringSettings
from interpreter.project.ir_codec import IrCodec
from interpreter.project.linked_codec import LinkedCodec
from interpreter.project.linker import link_every_module, module_prefix
from interpreter.project.source_file import SourceFile
from interpreter.project.start_up import START_UP_PATH, with_start_up
from interpreter.project.types import LinkedProgram, ModuleUnit
from interpreter.project.unit_codec import UnitCodec
from interpreter.project.unit_diagnostic import UnitDiagnostic
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder

HLASM_FRONTEND_LOGGER = "interpreter.hlasm"
logger = logging.getLogger(HLASM_FRONTEND_LOGGER)

_MAIN_PATH = Path("__main__.asm")
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

    def linked(self) -> LinkedProgram:
        unit = self._artifact("unit")
        digest = hashlib.sha256(unit.name.encode("utf-8")).hexdigest()
        target = self.work_dir / f"image-{digest}.linked.json"
        codec = LinkedCodec(IrCodec())
        if not target.exists():
            codec.write(self._link(self._unit_module()), target)
        linked = codec.read(target)
        _report(linked.modules[self.program.path].diagnostics)
        return linked

    def _unit_module(self) -> ModuleUnit:
        target = self._artifact("unit")
        codec = UnitCodec(IrCodec())
        if target.exists():
            return codec.read(target)
        module = self._module()
        codec.write(module, target)
        return module

    def _module(self) -> ModuleUnit:
        frontend = get_hlasm_frontend(self.parser.read(self.ast()))
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
        )

    def _link(self, unit: ModuleUnit) -> LinkedProgram:
        start_up = get_hlasm_frontend(self.parser.read(self.ast())).start_up_ir()
        modules, graph = with_start_up(
            start_up, Language.HLASM, {unit.path: unit}, {unit.path: ()}
        )
        linked = link_every_module(
            modules=modules,
            import_graph=graph,
            project_root=_PROJECT_ROOT,
            topo_order=(START_UP_PATH, unit.path),
            language=Language.HLASM,
            type_env_builder=TypeEnvironmentBuilder(),
            symbol_table=SymbolTable.empty(),
        )
        entry = unit.entry_label.namespace(module_prefix(unit.path, _PROJECT_ROOT))
        return dataclasses.replace(
            linked, programs={unit.program: entry}, entry_func_label=entry
        )


def _report(diagnostics: Sequence[UnitDiagnostic]) -> None:
    _ = [logger.log(d.severity.value, d.text) for d in diagnostics]


def _work_dir(given: Path | FreshWorkDir) -> Path:
    match given:
        case Path():
            given.mkdir(parents=True, exist_ok=True)
            return given
        case FreshWorkDir():
            return Path(tempfile.mkdtemp())


def lower_hlasm_program(
    source: bytes,
    *,
    parser: HlasmAstParser,
    work_dir: Path,
    options: HlasmCompileOptions = _NO_INPUTS,
) -> tuple[Path, ...]:
    return (
        _Assembly(
            SourceFile(_MAIN_PATH, source), parser, options, _work_dir(work_dir)
        ).unit(),
    )


def compile_hlasm(
    source: bytes,
    *,
    parser: HlasmAstParser,
    options: HlasmCompileOptions = _NO_INPUTS,
    work_dir: Path | FreshWorkDir = FRESH_WORK_DIR,
) -> LinkedProgram:
    return _Assembly(
        SourceFile(_MAIN_PATH, source), parser, options, _work_dir(work_dir)
    ).linked()
