# pyright: standard
"""The Language enum — the bounded set of supported source languages.

A leaf-vocabulary module (stdlib-only) so static-analysis consumers that need
only the language tag never import the heavier interpreter.constants (which
pulls in interpreter.type_name for the IR type ontology). interpreter.constants
re-exports Language for backward compatibility.
"""

from __future__ import annotations

from enum import StrEnum


class Language(StrEnum):
    """Bounded set of supported source languages.

    Each member's value is the tree-sitter language name string, so
    ``Language.PYTHON == "python"`` is ``True`` and members pass through
    directly to ``tree_sitter_language_pack.get_parser()``.
    """

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    RUBY = "ruby"
    GO = "go"
    PHP = "php"
    CSHARP = "csharp"
    C = "c"
    CPP = "cpp"
    RUST = "rust"
    KOTLIN = "kotlin"
    SCALA = "scala"
    LUA = "lua"
    PASCAL = "pascal"
    COBOL = "cobol"
