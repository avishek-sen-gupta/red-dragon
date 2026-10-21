"""Deterministic tree-sitter frontends for all supported languages."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.cobol_parser import ProLeapCobolParser
from cobol_asg.copybook_search import CopybookSearch
from cobol_asg.frontend_extension import DialectParser
from cobol_asg.lp32 import LP32_MODE
from cobol_asg.subprocess_runner import RealSubprocessRunner
from hlasm_asg.hlasm_bridge_parser import HlasmBridgeParser, make_hlasm_parser
from hlasm_asg.program.hlasm_program import HlasmProgram
from interpreter.cobol.cobol_frontend import CobolFrontend, CompileOptions
from interpreter.constants import Language
from interpreter.frontend_extension_lowering import RedDragonExtensionLoweringStrategy
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.frontends._base import BaseFrontend
from interpreter.hlasm.hlasm_frontend import HlasmFrontend
from interpreter.parser import TreeSitterParserFactory

PROLEAP_BRIDGE_JAR = "proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
HLASM_MACLIB = Path(__file__).resolve().parents[2] / "hlasm-bridge" / "maclib"
_NULL_OBSERVER = NullFrontendObserver()

# Lazy imports to avoid loading all frontends at startup
_FRONTEND_CLASSES: dict[Language, str] = {
    Language.PYTHON: "python.PythonFrontend",
    Language.JAVASCRIPT: "javascript.JavaScriptFrontend",
    Language.TYPESCRIPT: "typescript.TypeScriptFrontend",
    Language.JAVA: "java.JavaFrontend",
    Language.RUBY: "ruby.RubyFrontend",
    Language.GO: "go.GoFrontend",
    Language.PHP: "php.PhpFrontend",
    Language.CSHARP: "csharp.CSharpFrontend",
    Language.C: "c.CFrontend",
    Language.CPP: "cpp.CppFrontend",
    Language.RUST: "rust.RustFrontend",
    Language.KOTLIN: "kotlin.KotlinFrontend",
    Language.SCALA: "scala.ScalaFrontend",
    Language.LUA: "lua.LuaFrontend",
    Language.PASCAL: "pascal.PascalFrontend",
}


def get_deterministic_frontend(
    language: Language,
    observer: FrontendObserver = _NULL_OBSERVER,
) -> BaseFrontend:
    """Instantiate the deterministic frontend for *language*.

    Raises ``ValueError`` if *language* has no registered frontend.
    """
    if language not in _FRONTEND_CLASSES:
        raise ValueError(f"Unsupported language for deterministic frontend: {language}")
    module_name, class_name = _FRONTEND_CLASSES[language].split(".")
    import importlib

    mod = importlib.import_module(f".{module_name}", package=__package__)
    cls = getattr(mod, class_name)
    return cls(TreeSitterParserFactory(), language, observer)


def get_cobol_frontend(
    observer: FrontendObserver = _NULL_OBSERVER,
    copybook_dirs: Sequence[Path] = (),
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
    dialect_parsers: Sequence[DialectParser] = (),
    tolerant: bool = False,
    addressing_mode: AddressingMode = LP32_MODE,
) -> CobolFrontend:
    parser = ProLeapCobolParser(
        RealSubprocessRunner(),
        os.environ.get("PROLEAP_BRIDGE_JAR", PROLEAP_BRIDGE_JAR),
        CopybookSearch(dirs=tuple(copybook_dirs)),
        addressing_mode=addressing_mode,
    )
    return CobolFrontend(
        parser,
        observer=observer,
        extension_strategies=extension_strategies,
        dialect_parsers=dialect_parsers,
        options=CompileOptions(tolerant=tolerant, addressing_mode=addressing_mode),
    )


def get_hlasm_parser(syslib: Sequence[Path] = ()) -> HlasmBridgeParser:
    return make_hlasm_parser((HLASM_MACLIB, *syslib))


def get_hlasm_frontend(program: HlasmProgram) -> HlasmFrontend:
    return HlasmFrontend(program)


SUPPORTED_DETERMINISTIC_LANGUAGES: tuple[str, ...] = tuple(_FRONTEND_CLASSES.keys())

__all__ = [
    "SUPPORTED_DETERMINISTIC_LANGUAGES",
    "BaseFrontend",
    "Language",
    "get_cobol_frontend",
    "get_deterministic_frontend",
    "get_hlasm_frontend",
    "get_hlasm_parser",
]
