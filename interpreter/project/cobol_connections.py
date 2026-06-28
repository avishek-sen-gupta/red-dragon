# pyright: standard
"""COBOL inter-program connection extraction.

ProgramRef      — identifies a program or copybook by name and optional file path.
Connection      — a directed COPY or CALL relationship between two ProgramRefs.
extract_cobol_connections() — compile a COBOL project and return all connections.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from interpreter.constants import Language
from interpreter.frontend import make_cobol_parser
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.imports import extract_imports
from interpreter.project.types import ImportKind, ImportRef


@dataclass(frozen=True)
class ProgramRef:
    """Identifies a COBOL program or copybook."""

    name: str
    file_path: Path | None


@dataclass(frozen=True)
class Connection:
    """A directed COPY or CALL relationship between two COBOL programs."""

    kind: str  # "COPY" or "CALL"
    source: ProgramRef
    target: ProgramRef

    def to_json(self) -> str:
        return json.dumps(
            {
                "kind": self.kind,
                "source_name": self.source.name,
                "source_file": (
                    str(self.source.file_path) if self.source.file_path else None
                ),
                "target_name": self.target.name,
                "target_file": (
                    str(self.target.file_path) if self.target.file_path else None
                ),
            }
        )


def extract_cobol_connections(
    source: bytes,
    *,
    copybook_dirs: list[Path] | None = None,
    program_source_dir: Path | None = None,
    extra_subprogram_sources: dict[str, bytes] | None = None,
    parser: Any = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    source_transform: Callable[[str], str] = lambda s: s,
) -> list[Connection]:
    """Compile a COBOL project and return all COPY and CALL connections.

    Calls compile_cobol() with the same arguments, then post-processes
    the finished LinkedProgram — no VM execution takes place.

    CALL target file paths are resolved from LinkedProgram.import_graph.
    COPY target file paths are always None (copybooks are inlined by ProLeap
    before red-dragon sees the ASG; the name is extracted from raw source).
    """
    main_path = Path("__main__.cbl")

    _parser = (
        parser if parser is not None else make_cobol_parser(copybook_dirs=copybook_dirs)
    )
    main_frontend, linked = compile_cobol(
        source,
        parser=_parser,
        copybook_dirs=copybook_dirs,
        extension_strategies=extension_strategies,
        cics_text_parser=cics_text_parser,
        observer=observer,
        program_source_dir=program_source_dir,
        extra_subprogram_sources=extra_subprogram_sources,
        source_transform=source_transform,
    )

    # The main module is always compiled as __main__.cbl; use the frontend's
    # program_id (the COBOL PROGRAM-ID paragraph) as the canonical name.
    main_program_id: str = main_frontend.program_id

    # Build {caller_path -> {called_name_upper -> resolved_path}} from import_graph.
    call_resolution: dict[Path, dict[str, Path]] = {}
    for caller_path, callee_paths in linked.import_graph.items():
        call_resolution[caller_path] = {p.stem.upper(): p for p in callee_paths}

    def _module_name(module_path: Path) -> str:
        """Return the PROGRAM-ID for the main module; stem for subprograms."""
        if module_path == main_path:
            return main_program_id
        return module_path.stem

    # When there are no subprograms, compile_cobol returns modules={}.
    # Reconstruct the main module's import list by re-running extract_imports
    # on the raw source (identical to what compile_cobol_module does internally).
    if linked.modules:
        modules_with_imports: dict[Path, tuple[ImportRef, ...]] = {
            path: module.imports for path, module in linked.modules.items()
        }
    else:
        main_imports = tuple(extract_imports(source, main_path, Language.COBOL))
        modules_with_imports = {main_path: main_imports}

    connections: list[Connection] = []
    for module_path, imports in modules_with_imports.items():
        source_ref = ProgramRef(name=_module_name(module_path), file_path=module_path)
        call_map = call_resolution.get(module_path, {})
        for ref in imports:
            if ref.kind == ImportKind.INCLUDE:
                connections.append(
                    Connection(
                        kind="COPY",
                        source=source_ref,
                        target=ProgramRef(name=ref.module_path, file_path=None),
                    )
                )
            elif ref.kind == ImportKind.REQUIRE:
                target_path = call_map.get(ref.module_path.upper())
                connections.append(
                    Connection(
                        kind="CALL",
                        source=source_ref,
                        target=ProgramRef(name=ref.module_path, file_path=target_path),
                    )
                )

    return connections
