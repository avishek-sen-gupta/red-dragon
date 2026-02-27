"""Composable API functions for the LLM Symbolic Interpreter pipelines.

Each function corresponds to a CLI workflow (--ir-only, --cfg-only, --mermaid)
but is callable programmatically without argparse.
"""

from __future__ import annotations

import logging
from typing import Optional

from tree_sitter import Node

from .cfg import CFG, build_cfg, cfg_to_mermaid, extract_function_instructions
from .frontend import get_frontend
from .ir import IRInstruction
from .ir_stats import count_opcodes
from .parser import Parser, TreeSitterParserFactory
from .registry import build_registry
from .run import execute_cfg_traced
from .run_types import VMConfig
from .trace_types import ExecutionTrace
from . import constants

logger = logging.getLogger(__name__)

_FUNCTION_NODE_TYPES: frozenset[str] = frozenset(
    {
        "function_definition",
        "function_declaration",
        "method_declaration",
        "function_item",
        "function_expression",
        "arrow_function",
    }
)


def lower_source(
    source: str,
    language: str = "python",
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    backend: str = "claude",
) -> list[IRInstruction]:
    """Parse and lower source code to IR instructions.

    Args:
        source: The source code text.
        language: Source language name (e.g. "python", "javascript").
        frontend_type: "deterministic", "llm", or "chunked_llm".
        backend: LLM provider name when using an LLM frontend.

    Returns:
        A list of IR instructions.
    """
    logger.info("Lowering source (%s, frontend=%s)", language, frontend_type)
    if frontend_type in (constants.FRONTEND_LLM, constants.FRONTEND_CHUNKED_LLM):
        frontend = get_frontend(
            language,
            frontend_type=frontend_type,
            llm_provider=backend,
        )
        return frontend.lower(None, source.encode("utf-8"))

    tree = Parser(TreeSitterParserFactory()).parse(source, language)
    frontend = get_frontend(language)
    return frontend.lower(tree, source.encode("utf-8"))


def dump_ir(
    source: str,
    language: str = "python",
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    backend: str = "claude",
) -> str:
    """Lower source to IR and return a human-readable text dump.

    Args:
        source: The source code text.
        language: Source language name.
        frontend_type: Frontend type.
        backend: LLM provider name.

    Returns:
        A multi-line string with one IR instruction per line.
    """
    instructions = lower_source(source, language, frontend_type, backend)
    return "\n".join(f"  {inst}" for inst in instructions)


def build_cfg_from_source(
    source: str,
    language: str = "python",
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    backend: str = "claude",
    function_name: str = "",
) -> CFG:
    """Parse, lower, optionally slice to a function, and build a CFG.

    Args:
        source: The source code text.
        language: Source language name.
        frontend_type: Frontend type.
        backend: LLM provider name.
        function_name: If non-empty, extract only this function's instructions
            before building the CFG.

    Returns:
        A CFG object.
    """
    instructions = lower_source(source, language, frontend_type, backend)
    if function_name:
        logger.info("Extracting function '%s' from IR", function_name)
        instructions = extract_function_instructions(instructions, function_name)
    return build_cfg(instructions)


def dump_cfg(
    source: str,
    language: str = "python",
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    backend: str = "claude",
    function_name: str = "",
) -> str:
    """Build a CFG from source and return its text representation.

    Args:
        source: The source code text.
        language: Source language name.
        frontend_type: Frontend type.
        backend: LLM provider name.
        function_name: If non-empty, scope to this function.

    Returns:
        The CFG's string representation.
    """
    cfg = build_cfg_from_source(source, language, frontend_type, backend, function_name)
    return str(cfg)


def dump_mermaid(
    source: str,
    language: str = "python",
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    backend: str = "claude",
    function_name: str = "",
) -> str:
    """Build a CFG from source and return a Mermaid flowchart diagram.

    Args:
        source: The source code text.
        language: Source language name.
        frontend_type: Frontend type.
        backend: LLM provider name.
        function_name: If non-empty, scope to this function.

    Returns:
        A Mermaid flowchart string.
    """
    cfg = build_cfg_from_source(source, language, frontend_type, backend, function_name)
    return cfg_to_mermaid(cfg)


def ir_stats(
    source: str,
    language: str = "python",
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    backend: str = "claude",
) -> dict[str, int]:
    """Lower source to IR and return opcode frequency counts.

    Args:
        source: The source code text.
        language: Source language name.
        frontend_type: Frontend type.
        backend: LLM provider name.

    Returns:
        A dict mapping opcode name strings to their occurrence counts.
    """
    instructions = lower_source(source, language, frontend_type, backend)
    return count_opcodes(instructions)


def execute_traced(
    source: str,
    language: str = "python",
    function_name: str = "",
    entry_point: str = "",
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    backend: str = "claude",
    max_steps: int = 100,
) -> ExecutionTrace:
    """Parse, lower, build CFG, and execute with full trace recording.

    Composes: lower_source → build_cfg_from_source → build_registry →
    execute_cfg_traced.  Returns an ExecutionTrace containing per-step
    VMState snapshots suitable for replay in a TUI.

    Args:
        source: The source code text.
        language: Source language name (e.g. "python", "javascript").
        function_name: If non-empty, scope CFG to this function.
        entry_point: Entry point label or function name.
        frontend_type: Frontend type.
        backend: LLM provider name.
        max_steps: Maximum interpretation steps.

    Returns:
        An ExecutionTrace with initial_state, steps, and stats.
    """
    logger.info(
        "execute_traced: language=%s, function=%s, max_steps=%d",
        language,
        function_name,
        max_steps,
    )
    instructions = lower_source(source, language, frontend_type, backend)
    cfg = build_cfg_from_source(
        source, language, frontend_type, backend, function_name=function_name
    )
    registry = build_registry(instructions, cfg)
    config = VMConfig(backend=backend, max_steps=max_steps)
    _vm, trace = execute_cfg_traced(cfg, entry_point, registry, config)
    return trace


def _find_function_node(node: Node, name: str) -> Optional[Node]:
    """Recursively walk the AST to find a function/method node matching *name*."""
    if node.type in _FUNCTION_NODE_TYPES:
        name_node = node.child_by_field_name("name")
        if name_node is not None and name_node.text.decode("utf-8") == name:
            return node

    return next(
        (
            found
            for child in node.children
            if (found := _find_function_node(child, name)) is not None
        ),
        None,
    )


def extract_function_source(
    source: str,
    function_name: str,
    language: str = "python",
) -> str:
    """Extract the raw source text of a named function from source code.

    Parses *source* with tree-sitter, then recursively walks the AST to find
    a function or method node whose name matches *function_name*.

    Args:
        source: The source code text.
        function_name: The name of the function/method to extract.
        language: Source language name (e.g. "python", "javascript").

    Returns:
        The source text of the matched function.

    Raises:
        ValueError: If no function with the given name is found.
    """
    logger.info("Extracting function source for '%s' (%s)", function_name, language)
    tree = Parser(TreeSitterParserFactory()).parse(source, language)
    source_bytes = source.encode("utf-8")
    match = _find_function_node(tree.root_node, function_name)
    if match is None:
        raise ValueError(f"Function '{function_name}' not found in source")
    return source_bytes[match.start_byte : match.end_byte].decode("utf-8")
