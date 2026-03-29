"""Data types for multi-file project support.

Defines ImportRef, ExportTable, ModuleUnit, LinkedProgram — the core
data model for the multi-file pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence

from interpreter.cfg_types import CFG
from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.register import Register
from interpreter.var_name import VarName
from interpreter.instructions import InstructionBase
from interpreter.registry import FunctionRegistry

# ── Errors ───────────────────────────────────────────────────────


class CyclicImportError(Exception):
    """Raised when a cyclic import dependency is detected."""

    def __init__(self, cycle: list[Path]):
        self.cycle = cycle
        path_str = " → ".join(str(p) for p in cycle)
        super().__init__(f"Cyclic import detected: {path_str}")


# ── Import kind ──────────────────────────────────────────────────


class ImportKind(Enum):
    """The mechanism used by an import statement."""

    IMPORT = "import"
    INCLUDE = "include"
    USE = "use"
    REQUIRE = "require"
    MOD = "mod"
    USING = "using"


# ── ImportRef ────────────────────────────────────────────────────


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


# ── ExportTable ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ExportTable:
    """A module's exported symbols.

    Maps exported names to their internal IR labels. Built during compilation
    by scanning the registry and top-level DECL_VAR instructions.
    """

    functions: dict[FuncName, CodeLabel] = field(default_factory=dict)
    classes: dict[ClassName, CodeLabel] = field(default_factory=dict)
    variables: dict[VarName, Register] = field(default_factory=dict)

    def lookup(self, name: str) -> CodeLabel | Register | None:
        """Look up an exported name across all symbol categories.

        Priority: functions > classes > variables.
        Accepts plain str and converts to typed keys for lookups.
        """
        func_hit = self.functions.get(FuncName(name))
        if func_hit is not None:
            return func_hit
        class_hit = self.classes.get(ClassName(name))
        if class_hit is not None:
            return class_hit
        return self.variables.get(VarName(name))

    def all_names(self) -> set[str]:
        """All exported names (deduplicated, as plain strings)."""
        return (
            {str(k) for k in self.functions}
            | {str(k) for k in self.classes}
            | {str(k) for k in self.variables}
        )


# ── ModuleUnit ───────────────────────────────────────────────────


@dataclass(frozen=True)
class ModuleUnit:
    """A single compiled file — the atomic unit of multi-file compilation.

    Contains the raw (un-namespaced) IR and metadata. The linker operates
    on ModuleUnits to produce a LinkedProgram.
    """

    path: Path
    language: Language
    ir: tuple[...]
    exports: ExportTable
    imports: tuple[ImportRef, ...]


# ── LinkedProgram ────────────────────────────────────────────────


@dataclass
class LinkedProgram:
    """Merged multi-file program ready for execution or analysis.

    After linking, all labels are namespaced and cross-module references
    are resolved. The merged_ir/merged_cfg/merged_registry feed directly
    into execute_cfg() and analyze_interprocedural() with zero changes.
    """

    modules: dict[Path, ModuleUnit]
    merged_ir: list[InstructionBase]
    merged_cfg: CFG
    merged_registry: FunctionRegistry
    entry_module: Path
    import_graph: dict[Path, list[Path]]
    unresolved_imports: list[ImportRef] = field(default_factory=list)
    func_symbol_table: dict[CodeLabel, FuncRef] = field(default_factory=dict)
    class_symbol_table: dict[CodeLabel, ClassRef] = field(default_factory=dict)
