"""Shared helpers for the Rosetta cross-language test suite."""

import logging
import statistics

import tree_sitter_language_pack

from interpreter.cfg import build_cfg
from interpreter.frontends import (
    get_deterministic_frontend,
    SUPPORTED_DETERMINISTIC_LANGUAGES,
)
from interpreter.ir import IRInstruction, Opcode
from interpreter.registry import build_registry
from interpreter.run import execute_cfg
from interpreter.run_types import ExecutionStats, VMConfig
from interpreter.vm_types import VMState

logger = logging.getLogger(__name__)


def parse_for_language(language: str, source: str) -> list[IRInstruction]:
    """Parse *source* with tree-sitter and lower via the deterministic frontend."""
    parser = tree_sitter_language_pack.get_parser(language)
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    frontend = get_deterministic_frontend(language)
    return frontend.lower(tree, source_bytes)


def opcodes(instructions: list[IRInstruction]) -> set[Opcode]:
    """Return the set of opcodes present in *instructions*."""
    return {inst.opcode for inst in instructions}


def find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    """Return all instructions matching *opcode*."""
    return [inst for inst in instructions if inst.opcode == opcode]


def count_symbolic_unsupported(instructions: list[IRInstruction]) -> int:
    """Count SYMBOLIC instructions whose operands contain 'unsupported:'."""
    return len(
        [
            inst
            for inst in instructions
            if inst.opcode == Opcode.SYMBOLIC
            and any("unsupported:" in str(op) for op in inst.operands)
        ]
    )


def assert_clean_lowering(
    ir: list[IRInstruction],
    *,
    min_instructions: int,
    required_opcodes: set[Opcode],
    language: str,
) -> None:
    """Run the standard 4-tier assertion battery on a single language lowering."""
    # Tier 1: entry label
    assert ir[0].opcode == Opcode.LABEL, f"[{language}] first instruction must be LABEL"
    assert ir[0].label == "entry", f"[{language}] first label must be 'entry'"

    # Tier 2: minimum instruction count
    assert (
        len(ir) >= min_instructions
    ), f"[{language}] expected >= {min_instructions} instructions, got {len(ir)}"

    # Tier 3: zero unsupported symbolics
    unsupported = count_symbolic_unsupported(ir)
    assert (
        unsupported == 0
    ), f"[{language}] found {unsupported} unsupported SYMBOLIC instructions"

    # Tier 4: required opcodes present
    present = opcodes(ir)
    missing = required_opcodes - present
    assert not missing, f"[{language}] missing required opcodes: {missing}"


def assert_cross_language_consistency(
    results: dict[str, list[IRInstruction]],
    *,
    required_opcodes: set[Opcode],
) -> None:
    """Run cross-language aggregate assertions."""
    # All 15 languages covered
    assert set(results.keys()) == set(
        SUPPORTED_DETERMINISTIC_LANGUAGES
    ), f"Missing languages: {set(SUPPORTED_DETERMINISTIC_LANGUAGES) - set(results.keys())}"

    # Opcode intersection contains required opcodes
    opcode_sets = [opcodes(ir) for ir in results.values()]
    intersection = set.intersection(*opcode_sets)
    missing = required_opcodes - intersection
    assert not missing, f"Required opcodes not universal: {missing}"

    # Instruction count variance <= 5x median
    counts = [len(ir) for ir in results.values()]
    median_count = statistics.median(counts)
    for lang, ir in results.items():
        ratio = len(ir) / median_count if median_count > 0 else 0
        assert ratio <= 5.0, (
            f"[{lang}] instruction count {len(ir)} is {ratio:.1f}x median "
            f"({median_count:.0f}) — possible degenerate lowering"
        )


# ---------------------------------------------------------------------------
# VM execution helpers
# ---------------------------------------------------------------------------

# Languages excluded from all execution tests (structural barriers):
EXCLUDED_EXECUTION_LANGUAGES: frozenset[str] = frozenset()

STANDARD_EXECUTABLE_LANGUAGES: frozenset[str] = frozenset(
    {
        "python",
        "javascript",
        "typescript",
        "ruby",
        "php",
        "c",
        "cpp",
        "rust",
        "kotlin",
        "lua",
        "java",
        "csharp",
        "scala",
        "pascal",
        "go",
    }
)


def execute_for_language(
    language: str, source: str, max_steps: int = 2000
) -> tuple[VMState, ExecutionStats]:
    """Parse, lower, build CFG/registry, and execute IR through the VM.

    Returns the final (VMState, ExecutionStats) pair.
    """
    logger.info("Executing %s program through VM (max_steps=%d)", language, max_steps)
    instructions = parse_for_language(language, source)
    cfg = build_cfg(instructions)
    registry = build_registry(instructions, cfg)
    config = VMConfig(max_steps=max_steps)
    vm, stats = execute_cfg(cfg, "entry", registry, config)
    logger.info(
        "Execution complete for %s: %d steps, %d LLM calls",
        language,
        stats.steps,
        stats.llm_calls,
    )
    return vm, stats


def _var_name_for_language(var_name: str, language: str) -> str:
    """Return the variable name as stored by the VM for a given language.

    PHP variables are stored with their ``$`` prefix.
    """
    return f"${var_name}" if language == "php" else var_name


def extract_answer(vm: VMState, language: str) -> object:
    """Extract the ``answer`` variable from frame 0 locals."""
    name = _var_name_for_language("answer", language)
    frame = vm.call_stack[0]
    assert name in frame.local_vars, (
        f"[{language}] expected '{name}' in frame 0 locals, "
        f"got: {sorted(frame.local_vars.keys())}"
    )
    return frame.local_vars[name]


def extract_array(
    vm: VMState, var_name: str, length: int, language: str
) -> list[object]:
    """Extract a heap-allocated array from frame 0 locals.

    Returns a Python list of the first *length* indexed fields.
    """
    name = _var_name_for_language(var_name, language)
    frame = vm.call_stack[0]
    assert name in frame.local_vars, (
        f"[{language}] expected '{name}' in frame 0 locals, "
        f"got: {sorted(frame.local_vars.keys())}"
    )
    heap_addr = frame.local_vars[name]
    assert heap_addr in vm.heap, (
        f"[{language}] expected heap address '{heap_addr}' in heap, "
        f"got: {sorted(vm.heap.keys())}"
    )
    obj = vm.heap[heap_addr]
    # Lua uses 1-based indexing; detect by checking for key "0"
    start_index = 0 if "0" in obj.fields else 1
    return [obj.fields[str(start_index + i)] for i in range(length)]
