"""Deterministic tree-sitter frontends for all supported languages."""

from __future__ import annotations

from typing import Callable

from ._base import BaseFrontend
from .python import PythonFrontend

# Lazy imports to avoid loading all frontends at startup
_FRONTEND_CLASSES: dict[str, str] = {
    "python": "python.PythonFrontend",
    "javascript": "javascript.JavaScriptFrontend",
    "typescript": "typescript.TypeScriptFrontend",
    "java": "java.JavaFrontend",
    "ruby": "ruby.RubyFrontend",
    "go": "go.GoFrontend",
    "php": "php.PhpFrontend",
    "csharp": "csharp.CSharpFrontend",
    "c": "c.CFrontend",
    "cpp": "cpp.CppFrontend",
    "rust": "rust.RustFrontend",
    "kotlin": "kotlin.KotlinFrontend",
    "scala": "scala.ScalaFrontend",
    "lua": "lua.LuaFrontend",
    "pascal": "pascal.PascalFrontend",
}


def get_deterministic_frontend(language: str) -> BaseFrontend:
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
    return cls()


SUPPORTED_DETERMINISTIC_LANGUAGES: tuple[str, ...] = tuple(_FRONTEND_CLASSES.keys())

__all__ = [
    "BaseFrontend",
    "PythonFrontend",
    "get_deterministic_frontend",
    "SUPPORTED_DETERMINISTIC_LANGUAGES",
]
