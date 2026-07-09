# pyright: standard
"""ImportRef / ImportKind — the import-statement vocabulary.

A leaf module (stdlib-only) so import-extraction code (interpreter.project.
cobol_imports and the tree-sitter extractors) and static-analysis consumers can
depend on this without pulling in the IR/CFG-heavy interpreter.project.types
(ExportTable / ModuleUnit / LinkedProgram). types re-exports both names.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ImportKind(Enum):
    """The mechanism used by an import statement."""

    IMPORT = "import"
    INCLUDE = "include"
    USE = "use"
    REQUIRE = "require"
    MOD = "mod"
    USING = "using"


@dataclass(frozen=True)
class ImportRef:
    """A single import statement's information.

    Represents what the source code *says*, not where the target *is*.
    Resolution (ImportRef → file path) is handled separately by ImportResolver.

    Fields:
        source_file:    Path of the file containing this import statement.
        module_path:    The module/package path as written in source.
                        Examples: "os.path", "./utils", "com.example.Utils",
                        "crate::utils", "stdio.h", "fmt".
        names:          Specific names imported. Empty tuple = import the module
                        itself. ("*",) = wildcard import.
        is_relative:    Whether this is a relative import.
        relative_level: Number of parent levels for relative imports
                        (Python's ``from ..`` is 2, ``from .`` is 1, absolute is 0).
        is_system:      Whether this is a standard library / system import.
        kind:           Import mechanism.
                        "import" | "include" | "use" | "require" | "mod" | "using"
        alias:          Optional alias name (``import X as Y``).
    """

    source_file: Path
    module_path: str
    names: tuple[str, ...] = ()
    is_relative: bool = False
    relative_level: int = 0
    is_system: bool = False
    kind: ImportKind = ImportKind.IMPORT
    alias: str | None = None
