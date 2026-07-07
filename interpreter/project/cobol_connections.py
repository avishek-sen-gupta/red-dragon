# pyright: standard
"""COBOL inter-program connection extraction.

extract_cobol_connections() — compile a COBOL project and return its
CALL/COPY relationships as the shared knowledge-graph schema (GraphNode,
GraphEdge — see interpreter.project.graph_types).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

from interpreter.constants import Language
from interpreter.frontend_extension import (
    DialectParser,
    RedDragonExtensionLoweringStrategy,
)
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.graph_types import EdgeKind, GraphEdge, GraphNode, NodeKind
from interpreter.project.imports import extract_imports
from interpreter.project.types import ImportKind, ImportRef


def extract_cobol_connections(
    source: bytes,
    *,
    copybook_dirs: list[Path] = [],
    program_source_dirs: Sequence[Path] = (),
    extra_subprogram_sources: dict[str, bytes] = {},
    parser: Any,
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
    dialect_parsers: Sequence[DialectParser] = (),
    observer: FrontendObserver = NullFrontendObserver(),
    source_transform: Callable[[str], str] = lambda s: s,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Compile a COBOL project and return its CALL/COPY graph.

    Calls compile_cobol() with the same arguments, then post-processes the
    finished LinkedProgram — no VM execution takes place.

    CALL target file paths are resolved from LinkedProgram.import_graph.
    COPY target file paths are always None (copybooks are inlined by ProLeap
    before red-dragon sees the ASG; the name is extracted from raw source).
    Every node id is uppercased (the standard COBOL convention), so the same
    program/copybook referenced with different case always merges to one node.
    """
    main_path = Path("__main__.cbl")

    main_frontend, linked = compile_cobol(
        source,
        parser=parser,
        copybook_dirs=copybook_dirs,
        extension_strategies=extension_strategies,
        dialect_parsers=dialect_parsers,
        observer=observer,
        program_source_dirs=program_source_dirs,
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

    nodes: dict[tuple[NodeKind, str], GraphNode] = {}
    edges: list[GraphEdge] = []

    def _add_node(kind: NodeKind, name: str, file_path: Path | None) -> str:
        node_id = name.upper()
        key = (kind, node_id)
        existing = nodes.get(key)
        if existing is None:
            nodes[key] = GraphNode(
                id=node_id,
                kind=kind,
                file_path=str(file_path) if file_path is not None else None,
            )
        elif existing.file_path is None and file_path is not None:
            nodes[key] = GraphNode(
                id=node_id, kind=kind, file_path=str(file_path)
            )
        return node_id

    for module_path, imports in modules_with_imports.items():
        source_name = _module_name(module_path)
        # Only the main module's own compiled path is trustworthy as a node
        # file_path here. For every other module, import_graph is flat (main's
        # entry lists every subprogram module, whether or not main actually
        # calls it directly — see LinkedProgram.import_graph construction in
        # compile_cobol), so a subprogram's own module_path is not evidence
        # that anything in the graph actually resolves to it. Its file_path
        # is instead populated below, only when some other module's CALL
        # target resolves to it through call_resolution.
        source_file_path = module_path if module_path == main_path else None
        source_id = _add_node(NodeKind.PROGRAM, source_name, source_file_path)
        call_map = call_resolution.get(module_path, {})
        for ref in imports:
            if ref.kind == ImportKind.INCLUDE:
                target_id = _add_node(NodeKind.COPYBOOK, ref.module_path, None)
                edges.append(
                    GraphEdge(
                        source=source_id,
                        source_kind=NodeKind.PROGRAM,
                        target=target_id,
                        target_kind=NodeKind.COPYBOOK,
                        kind=EdgeKind.COPY,
                    )
                )
            elif ref.kind == ImportKind.REQUIRE:
                target_path = call_map.get(ref.module_path.upper())
                target_id = _add_node(NodeKind.PROGRAM, ref.module_path, target_path)
                edges.append(
                    GraphEdge(
                        source=source_id,
                        source_kind=NodeKind.PROGRAM,
                        target=target_id,
                        target_kind=NodeKind.PROGRAM,
                        kind=EdgeKind.CALL,
                    )
                )

    return list(nodes.values()), edges
