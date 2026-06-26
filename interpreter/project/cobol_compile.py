# pyright: standard
"""Shared single-module COBOL compile core.

compile_cobol_module(): bytes → (CobolFrontend, ModuleUnit)

This is the canonical entry point for compiling a single COBOL source unit.
It knows about COBOL-specific injection points (parser, extension_strategies,
cics_text_parser) abstractly — no CICS/SQL specifics live here.
All frontend construction is routed through get_frontend (the factory).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.project.compiler import build_export_table
from interpreter.project.imports import extract_imports
from interpreter.project.types import ModuleUnit
from interpreter import constants


def compile_cobol_module(
    source: bytes,
    *,
    parser: Any = None,
    copybook_dirs: list[Path] | None = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = Path("__main__.cbl"),
) -> tuple[Any, ModuleUnit]:
    """Lower one COBOL source into a (frontend, ModuleUnit). The shared core."""
    frontend = get_frontend(
        Language.COBOL,
        frontend_type=constants.FRONTEND_COBOL,
        observer=observer,
        copybook_dirs=copybook_dirs,
        cobol_parser=parser,
        extension_strategies=extension_strategies,
        cics_text_parser=cics_text_parser,
    )
    ir = frontend.lower(source)
    exports = build_export_table(
        ir, frontend.func_symbol_table, frontend.class_symbol_table
    )
    imports = tuple(extract_imports(source, path, Language.COBOL))
    module = ModuleUnit(
        path=path,
        language=Language.COBOL,
        ir=tuple(ir),
        exports=exports,
        imports=imports,
        symbol_table=frontend.symbol_table,
    )
    return frontend, module
