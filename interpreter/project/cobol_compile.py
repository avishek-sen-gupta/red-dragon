# pyright: standard
"""COBOL compilation in three stages chained only through files.

parse_stage():  sources → <stem>-<digest>.ast.json
_Lowering.lower(): an AST file → <stem>-<digest>.unit.json
lower_cobol_program(): one program, parsed and lowered → its unit file
link_units():   unit files → image-<digest>.linked.json, read back; no unit is main
compile_cobol(): parses, lowers and links its programs into
                 <main stem>-<digest>.linked.json, whose entry is its main program.

The digest covers the source bytes and the lowering settings; a stage skips a
program whose output file already exists. It knows about COBOL-specific
injection points (parser, extension_strategies, dialect_parsers) abstractly — no
CICS/SQL specifics live here. It compiles the programs it is given and searches
no directory.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import tempfile
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tqdm import tqdm

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.ast_store import AsgJsonParser, AstParseError
from cobol_asg.cobol_parser import ProLeapCobolParser
from cobol_asg.frontend_extension import DialectParser
from cobol_asg.lp import LP
from cobol_asg.lp32 import LP32_MODE
from cobol_asg.resolve_addressing_mode import addressing_mode
from interpreter.constants import Language
from interpreter.frontend_extension_lowering import RedDragonExtensionLoweringStrategy
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.frontends import get_cobol_frontend
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.ir import CodeLabel
from interpreter.project.compiler import build_export_table
from interpreter.project.duplicate_program_in_image import DuplicateProgramInImage
from interpreter.project.fresh_work_dir import FRESH_WORK_DIR, FreshWorkDir
from interpreter.project.imports import extract_imports
from interpreter.project.ir_codec import IrCodec
from interpreter.project.linked_codec import LinkedCodec
from interpreter.project.linker import link_every_module, module_prefix
from interpreter.project.lowering_settings import LoweringSettings
from interpreter.project.source_file import SourceFile
from interpreter.project.start_up import START_UP_PATH, with_start_up
from interpreter.project.types import LinkedProgram, ModuleUnit
from interpreter.project.unit_codec import UnitCodec
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder

logger = logging.getLogger(__name__)

_MAIN_PATH = Path("__main__.cbl")
_PROGRAM_PATH = Path("__lowered__.cbl")
PROJECT_ROOT = Path("/")


def compile_cobol_module(
    source: bytes,
    *,
    parser: Any,
    copybook_dirs: list[Path] = [],
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
    dialect_parsers: Sequence[DialectParser] = (),
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = _MAIN_PATH,
    ast_path: Path,
    tolerant: bool = False,
    addressing_mode: AddressingMode = LP32_MODE,
) -> ModuleUnit:
    """Lower one COBOL program's AST file into a ModuleUnit. The shared core."""
    frontend = get_cobol_frontend(
        observer=observer,
        copybook_dirs=copybook_dirs,
        extension_strategies=extension_strategies,
        dialect_parsers=dialect_parsers,
        tolerant=tolerant,
        addressing_mode=addressing_mode,
    )
    ir = frontend.lower_from_ast_dict(json.loads(ast_path.read_text("utf-8")))
    return ModuleUnit(
        path=path,
        language=Language.COBOL,
        ir=tuple(ir),
        exports=build_export_table(
            ir, frontend.func_symbol_table, frontend.class_symbol_table
        ),
        imports=tuple(extract_imports(source, path, Language.COBOL)),
        symbol_table=frontend.symbol_table,
        entry_label=CodeLabel(f"func_{frontend.program_id.lower()}_0"),
        program=frontend.program_id,
    )


def _cache_dir(given: Path | FreshWorkDir) -> Path:
    match given:
        case Path():
            return given
        case FreshWorkDir():
            return Path(tempfile.mkdtemp())


def _parse_one(program: SourceFile, parser: AsgJsonParser, target: Path) -> Path:
    """One program's bridge output, written to its AST file. Runs on a worker thread."""
    try:
        parser.parse_to_file(program.source, target)
    except Exception as exc:  # noqa: BLE001
        raise AstParseError(
            f"{program.path.name}: {type(exc).__name__}: {exc}"
        ) from exc
    return target


def parse_stage(
    programs: Sequence[SourceFile],
    parser: AsgJsonParser,
    settings: LoweringSettings,
    work_dir: Path,
) -> Mapping[Path, Path]:
    """Each program's AST file, parsing (in parallel) only those not yet on disk."""
    work_dir.mkdir(parents=True, exist_ok=True)
    targets = {p.path: settings.artifact(p, work_dir, "ast") for p in programs}
    missing = [p for p in programs if not targets[p.path].exists()]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_parse_one, p, parser, targets[p.path]) for p in missing
        ]
        tuple(
            future.result()
            for future in tqdm(
                futures, total=len(futures), desc="parse COBOL", unit="program"
            )
        )
    return targets


@dataclass(frozen=True)
class _Lowering:
    """The arguments every program of one run unit is lowered with."""

    parser: Any
    copybook_dirs: Sequence[Path]
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy]
    dialect_parsers: Sequence[DialectParser]
    observer: FrontendObserver
    tolerant: bool
    addressing_mode: AddressingMode
    settings: LoweringSettings
    units: UnitCodec

    def lower(self, program: SourceFile, ast_file: Path, work_dir: Path) -> Path:
        """The program's unit file, lowering it only if it is not yet on disk."""
        target = self.settings.artifact(program, work_dir, "unit")
        if not target.exists():
            self.units.write(self._module(program, ast_file), target)
        return target

    def lower_as_program(
        self, program: SourceFile, ast_file: Path, work_dir: Path
    ) -> Path:
        target = self.settings.artifact(program, work_dir, "unit")
        if not target.exists():
            module = self._module(program, ast_file)
            self.units.write(
                dataclasses.replace(module, path=Path(f"{module.program}.cbl")),
                target,
            )
        return target

    def lower_or_skip(
        self, program: SourceFile, ast_file: Path, work_dir: Path
    ) -> tuple[Path, ...]:
        try:
            return (self.lower(program, ast_file, work_dir),)
        except Exception:  # noqa: BLE001
            logger.warning(
                "compile_cobol: %s failed to lower — skipping",
                program.path.stem,
                exc_info=True,
            )
            return ()

    def _module(self, program: SourceFile, ast_file: Path) -> ModuleUnit:
        return compile_cobol_module(
            program.source,
            parser=self.parser,
            copybook_dirs=list(self.copybook_dirs),
            extension_strategies=self.extension_strategies,
            dialect_parsers=self.dialect_parsers,
            observer=self.observer,
            path=program.path,
            ast_path=ast_file,
            tolerant=self.tolerant,
            addressing_mode=self.addressing_mode,
        )


def lower_cobol_program(
    source: bytes,
    *,
    parser: ProLeapCobolParser,
    copybook_dirs: Sequence[Path],
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy],
    dialect_parsers: Sequence[DialectParser],
    work_dir: Path,
    tolerant: bool,
) -> Path:
    mode = addressing_mode(LP.LP32)
    mode_parser = parser.with_addressing_mode(mode)
    settings = LoweringSettings(
        LP.LP32,
        tuple(strategy.name for strategy in extension_strategies),
        tolerant,
        tuple(copybook_dirs),
    )
    program = SourceFile(_PROGRAM_PATH, source)
    asts = parse_stage((program,), mode_parser, settings, work_dir)
    lowering = _Lowering(
        parser=mode_parser,
        copybook_dirs=copybook_dirs,
        extension_strategies=extension_strategies,
        dialect_parsers=dialect_parsers,
        observer=NullFrontendObserver(),
        tolerant=tolerant,
        addressing_mode=mode,
        settings=settings,
        units=UnitCodec(IrCodec()),
    )
    return lowering.lower_as_program(program, asts[program.path], work_dir)


def link_units(units: Sequence[Path], work_dir: Path) -> LinkedProgram:
    return _linked_file(units, _linked_target(work_dir, "image", units), _no_main)


def _no_main(image: LinkedProgram) -> LinkedProgram:
    return image


def _linked_target(work_dir: Path, stem: str, units: Sequence[Path]) -> Path:
    digest = hashlib.sha256("\0".join(p.name for p in units).encode("utf-8"))
    return work_dir / f"{stem}-{digest.hexdigest()}.linked.json"


def _linked_file(
    units: Sequence[Path],
    target: Path,
    entered: Callable[[LinkedProgram], LinkedProgram],
) -> LinkedProgram:
    codec = LinkedCodec(IrCodec())
    if not target.exists():
        codec.write(entered(_link(units)), target)
    return codec.read(target)


def _refuse_duplicates(units: Sequence[Path], read: Sequence[ModuleUnit]) -> None:
    clash = next(
        (
            (read[later].program, units[earlier], units[later])
            for later in range(len(read))
            for earlier in range(later)
            if read[earlier].program == read[later].program
        ),
        (),
    )
    match clash:
        case (str(program), Path() as first, Path() as second):
            raise DuplicateProgramInImage(program, first, second)
        case _:
            return


def _link(units: Sequence[Path]) -> LinkedProgram:
    codec = UnitCodec(IrCodec())
    read = tuple(codec.read(f) for f in units)
    _refuse_duplicates(units, read)
    modules, graph = with_start_up(
        get_cobol_frontend().start_up_ir(),
        Language.COBOL,
        {unit.path: unit for unit in read},
        {unit.path: () for unit in read},
    )
    linked = link_every_module(
        modules=modules,
        import_graph=graph,
        project_root=PROJECT_ROOT,
        topo_order=(START_UP_PATH, *(unit.path for unit in read)),
        language=Language.COBOL,
        type_env_builder=TypeEnvironmentBuilder(),
        symbol_table=SymbolTable.empty(),
    )
    return dataclasses.replace(
        linked,
        programs={
            unit.program: unit.entry_label.namespace(
                module_prefix(unit.path, PROJECT_ROOT)
            )
            for unit in read
        },
    )


def compile_cobol(
    source: bytes,
    *,
    parser: Any,
    programs: Sequence[SourceFile] = (),
    copybook_dirs: Sequence[Path] = (),
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
    dialect_parsers: Sequence[DialectParser] = (),
    observer: FrontendObserver = NullFrontendObserver(),
    work_dir: Path | FreshWorkDir = FRESH_WORK_DIR,
    tolerant: bool = False,
    lp: LP = LP.LP32,
) -> LinkedProgram:
    mode = addressing_mode(lp)
    mode_parser = parser.with_addressing_mode(mode)
    settings = LoweringSettings(
        lp,
        tuple(strategy.name for strategy in extension_strategies),
        tolerant,
        tuple(copybook_dirs),
    )
    workspace = _cache_dir(work_dir)
    main = SourceFile(_MAIN_PATH, source)
    by_path = {program.path: program for program in (main, *programs)}
    asts = parse_stage(tuple(by_path.values()), mode_parser, settings, workspace)
    lowering = _Lowering(
        parser=mode_parser,
        copybook_dirs=copybook_dirs,
        extension_strategies=extension_strategies,
        dialect_parsers=dialect_parsers,
        observer=observer,
        tolerant=tolerant,
        addressing_mode=mode,
        settings=settings,
        units=UnitCodec(IrCodec()),
    )
    main_unit = lowering.lower(main, asts[main.path], workspace)
    callee_units = tuple(
        unit
        for path, program in by_path.items()
        if path != main.path
        for unit in lowering.lower_or_skip(program, asts[path], workspace)
    )
    return _link_entered_at_main(main_unit, callee_units, workspace)


def _link_entered_at_main(
    main_unit: Path, callee_units: Sequence[Path], work_dir: Path
) -> LinkedProgram:
    main_program = UnitCodec(IrCodec()).read(main_unit).program
    units = (*callee_units, main_unit)
    return _linked_file(
        units,
        _linked_target(work_dir, main_unit.name.rpartition("-")[0], units),
        lambda image: dataclasses.replace(
            image, entry_func_label=image.programs[main_program]
        ),
    )
