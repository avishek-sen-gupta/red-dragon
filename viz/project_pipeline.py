"""Project pipeline — compile a directory into a ProjectPipelineResult for TUI display."""

from __future__ import annotations
import bisect
import dataclasses
import logging
from dataclasses import dataclass, field
from pathlib import Path

from interpreter.constants import Language
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.interprocedural.types import InterproceduralResult
from interpreter.parser import TreeSitterParserFactory
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.project.linker import module_prefix
from interpreter.project.resolver import topological_sort
from interpreter.project.types import LinkedProgram
from interpreter.run import run_linked_traced
from interpreter.trace_types import ExecutionTrace
from viz.pipeline import ASTNode, _ast_from_ts_node

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectPipelineResult:
    """All stage outputs from a multi-file project pipeline run."""

    linked: LinkedProgram
    module_sources: dict[Path, str]
    module_asts: dict[Path, ASTNode]
    topo_order: list[Path]
    module_ir_ranges: list[tuple[int, int, Path]]
    instruction_to_index: dict[int, int]
    trace: ExecutionTrace | None = None
    interprocedural: InterproceduralResult | None = None


def run_project_pipeline(directory: str | Path, language: str) -> ProjectPipelineResult:
    """Compile a directory into a ProjectPipelineResult. Execution deferred."""
    directory = Path(directory).resolve()
    lang = Language(language)
    linked = compile_directory(directory, lang)
    topo_order = topological_sort(linked.import_graph)

    parser_factory = TreeSitterParserFactory()
    ts_parser = parser_factory.get_parser(language)
    module_sources: dict[Path, str] = {}
    module_asts: dict[Path, ASTNode] = {}
    for path in topo_order:
        text = path.read_text()
        module_sources[path] = text
        source_bytes = text.encode("utf-8")
        tree = ts_parser.parse(source_bytes)
        module_asts[path] = _ast_from_ts_node(tree.root_node, source_bytes)

    module_ir_ranges = _build_module_ir_ranges(linked, topo_order, directory)
    instruction_to_index = {id(inst): i for i, inst in enumerate(linked.merged_ir)}

    return ProjectPipelineResult(
        linked=linked,
        module_sources=module_sources,
        module_asts=module_asts,
        topo_order=topo_order,
        module_ir_ranges=module_ir_ranges,
        instruction_to_index=instruction_to_index,
    )


def execute_project(
    result: ProjectPipelineResult, entry_point: EntryPoint | None, max_steps: int
) -> ProjectPipelineResult:
    """Execute the linked program and populate the trace."""
    if entry_point is None:
        entry_point = EntryPoint.top_level()
    _vm, trace = run_linked_traced(result.linked, entry_point, max_steps=max_steps)
    try:
        interprocedural = analyze_interprocedural(
            result.linked.merged_cfg, result.linked.merged_registry
        )
    except Exception:
        logger.warning("Interprocedural analysis failed", exc_info=True)
        interprocedural = None
    return dataclasses.replace(result, trace=trace, interprocedural=interprocedural)


def lookup_module_for_index(
    ranges: list[tuple[int, int, Path]], index: int
) -> Path | None:
    """Binary search module_ir_ranges to find owning module for an instruction index."""
    starts = [r[0] for r in ranges]
    pos = bisect.bisect_right(starts, index) - 1
    if pos < 0:
        return None
    start, end, path = ranges[pos]
    if start <= index < end:
        return path
    return None


def _build_module_ir_ranges(
    linked: LinkedProgram, topo_order: list[Path], project_root: Path
) -> list[tuple[int, int, Path]]:
    """Build (start, end, path) ranges mapping merged_ir indices to source modules."""
    if not topo_order:
        return []
    prefixes = {module_prefix(path, project_root): path for path in topo_order}
    merged_ir = linked.merged_ir
    ranges: list[tuple[int, int, Path]] = []
    current_path = topo_order[0]
    current_start = 0

    for i, inst in enumerate(merged_ir):
        if inst.opcode.name == "LABEL" and hasattr(inst, "label"):
            label_str = str(inst.label)
            for prefix, path in prefixes.items():
                if label_str.startswith(prefix + ".") or label_str == prefix:
                    if path != current_path:
                        if i > current_start:
                            ranges.append((current_start, i, current_path))
                        current_path = path
                        current_start = i
                    break

    if len(merged_ir) > current_start:
        ranges.append((current_start, len(merged_ir), current_path))
    return ranges
