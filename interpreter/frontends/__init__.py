"""Deterministic tree-sitter frontends for all supported languages."""

from __future__ import annotations

from typing import Callable

from interpreter.frontends._base import BaseFrontend
from interpreter.constants import Language
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.parser import TreeSitterParserFactory

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
    observer: FrontendObserver = NullFrontendObserver(),
) -> BaseFrontend:
    """Instantiate the deterministic frontend for *language*.

    Raises ``ValueError`` if *language* has no registered frontend.
    """
    spec = _FRONTEND_CLASSES.get(language)
    if spec is None:
        raise ValueError(f"Unsupported language for deterministic frontend: {language}")
    module_name, class_name = spec.split(".")
    import importlib

    mod = importlib.import_module(f".{module_name}", package=__package__)
    cls = getattr(mod, class_name)
    return cls(TreeSitterParserFactory(), language, observer)


SUPPORTED_DETERMINISTIC_LANGUAGES: tuple[str, ...] = tuple(_FRONTEND_CLASSES.keys())

__all__ = [
    "BaseFrontend",
    "Language",
    "get_deterministic_frontend",
    "SUPPORTED_DETERMINISTIC_LANGUAGES",
]
