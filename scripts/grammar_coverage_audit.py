"""Deterministic grammar coverage audit across all 15 language frontends.

Enumerates every named node type from each tree-sitter grammar and diffs
it against the union of types handled by the corresponding frontend's
dispatch tables, noise types, comment types, and block_node_types.

Sub-structural false positives are eliminated using tree-sitter's
lookahead_iterator: only node types that can appear at block/statement
scope are classified as true gaps. Sub-structural nodes (e.g. catch_clause,
class_body) consumed inline by parent handlers are not counted as gaps.

Usage:
    poetry run python scripts/grammar_coverage_audit.py
    poetry run python scripts/grammar_coverage_audit.py --output results.json

With no --output flag: JSON to stdout, summary to stderr.
With --output FILE: JSON to file, summary to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import tree_sitter
import tree_sitter_language_pack

from interpreter.constants import Language
from interpreter.frontends import get_deterministic_frontend
from interpreter.frontends.go.verified_features import GO_VERIFIED_FEATURES
from interpreter.frontends.kotlin.verified_features import KOTLIN_VERIFIED_FEATURES
from interpreter.frontends.rust.verified_features import RUST_VERIFIED_FEATURES

# Map from language to its verified-features labels (implemented via internal
# dispatch rather than top-level dispatch tables).
_VERIFIED_FEATURE_LABELS: dict[Language, frozenset[str]] = {
    Language.GO: frozenset(f.label for f in GO_VERIFIED_FEATURES),
    Language.KOTLIN: frozenset(f.label for f in KOTLIN_VERIFIED_FEATURES),
    Language.RUST: frozenset(f.label for f in RUST_VERIFIED_FEATURES),
}

# Languages with deterministic frontends (COBOL excluded — no deterministic frontend).
AUDIT_LANGUAGES: tuple[Language, ...] = (
    Language.PYTHON,
    Language.JAVA,
    Language.JAVASCRIPT,
    Language.TYPESCRIPT,
    Language.CSHARP,
    Language.KOTLIN,
    Language.SCALA,
    Language.GO,
    Language.RUST,
    Language.C,
    Language.CPP,
    Language.RUBY,
    Language.PHP,
    Language.LUA,
    Language.PASCAL,
)


@dataclass(frozen=True)
class BlockConfig:
    """Config for extracting block-level dispatchable types via lookahead_iterator."""

    snippet: bytes  # Minimal parseable source containing a block with statements
    block_node_type: str  # tree-sitter node type name of the block container
    stmt_child_index: int = 0  # named_children index of the first real statement


# Per-language block configs.  stmt_child_index=1 for Pascal because kBegin is
# named_children[0] and the first real statement is at index 1.
_BLOCK_CONFIGS: dict[Language, BlockConfig] = {
    Language.PYTHON: BlockConfig(
        snippet=b"def f():\n    x = 1\n    return x",
        block_node_type="block",
    ),
    Language.JAVA: BlockConfig(
        snippet=b"class X { void f() { int x = 1; return; } }",
        block_node_type="block",
    ),
    Language.JAVASCRIPT: BlockConfig(
        snippet=b"function f() { let x = 1; return x; }",
        block_node_type="statement_block",
    ),
    Language.TYPESCRIPT: BlockConfig(
        snippet=b"function f() { let x = 1; return x; }",
        block_node_type="statement_block",
    ),
    Language.CSHARP: BlockConfig(
        snippet=b"class X { void F() { int x = 1; return; } }",
        block_node_type="block",
    ),
    Language.KOTLIN: BlockConfig(
        snippet=b"fun f() { val x = 1\n return x }",
        block_node_type="statements",
    ),
    Language.SCALA: BlockConfig(
        snippet=b"object X { def f() = { val x = 1 } }",
        block_node_type="block",
    ),
    Language.GO: BlockConfig(
        snippet=b"package main; func f() { x := 1; _ = x }",
        block_node_type="block",
    ),
    Language.RUST: BlockConfig(
        snippet=b"fn f() { let x = 1; }",
        block_node_type="block",
    ),
    Language.C: BlockConfig(
        snippet=b"void f() { int x = 1; }",
        block_node_type="compound_statement",
    ),
    Language.CPP: BlockConfig(
        snippet=b"void f() { int x = 1; }",
        block_node_type="compound_statement",
    ),
    Language.RUBY: BlockConfig(
        snippet=b"def f\n  x = 1\n  return x\nend",
        block_node_type="body_statement",
    ),
    Language.PHP: BlockConfig(
        snippet=b"<?php function f() { $x = 1; }",
        block_node_type="compound_statement",
    ),
    Language.LUA: BlockConfig(
        snippet=b"function f() local x = 1 end",
        block_node_type="block",
    ),
    Language.PASCAL: BlockConfig(
        snippet=b"program X; begin x := 1; y := 2; end.",
        block_node_type="block",
        stmt_child_index=1,  # named_children[0] is kBegin keyword; skip it
    ),
}


@dataclass(frozen=True)
class _DispatchableInfo:
    """Result of the block-level lookahead query."""

    has_data: bool
    types: frozenset[str]


@dataclass(frozen=True)
class LanguageResult:
    language: str
    total_grammar_nodes: int
    handled_count: int
    dispatchable_count: int
    true_gap_count: int
    sub_structural_count: int
    verified_count: int
    covered: list[str]
    true_gaps: list[str]
    sub_structural: list[str]
    verified: list[str]


def _find_node(node: tree_sitter.Node, node_type: str) -> tuple[tree_sitter.Node, ...]:
    """Depth-first search — returns a 1-tuple if found, empty tuple if not."""
    if node.type == node_type and node.named_child_count > 0:
        return (node,)
    return next(
        (r for child in node.children for r in (_find_node(child, node_type),) if r),
        (),
    )


def enumerate_grammar_nodes(ts_language_name: str) -> frozenset[str]:
    """Return all named node type strings defined in the grammar."""
    lang = tree_sitter_language_pack.get_language(ts_language_name)
    return frozenset(
        lang.node_kind_for_id(i)
        for i in range(lang.node_kind_count)
        if lang.node_kind_is_named(i)
    )


def get_block_dispatchable_types(
    language: Language, grammar_nodes: frozenset[str]
) -> _DispatchableInfo:
    """Return named node types valid at block/statement scope via lookahead_iterator.

    Uses tree-sitter's LR parser state machine: parse a minimal snippet,
    find the block node, read the parse_state of the first real statement
    child, then ask lookahead_iterator what symbols are valid at that state.

    Returns _DispatchableInfo(has_data=False) if no config or block not found.
    """
    if language not in _BLOCK_CONFIGS:
        return _DispatchableInfo(has_data=False, types=frozenset())

    config = _BLOCK_CONFIGS[language]
    ts_lang = tree_sitter_language_pack.get_language(str(language))
    parser = tree_sitter.Parser(ts_lang)
    tree = parser.parse(config.snippet)

    match _find_node(tree.root_node, config.block_node_type):
        case ():
            return _DispatchableInfo(has_data=False, types=frozenset())
        case (block,):
            named = block.named_children
            if len(named) <= config.stmt_child_index:
                return _DispatchableInfo(has_data=False, types=frozenset())
            stmt_state = named[config.stmt_child_index].parse_state
            it = ts_lang.lookahead_iterator(stmt_state)
            return _DispatchableInfo(
                has_data=True,
                types=frozenset(it.names()) & grammar_nodes,
            )
        case _:
            return _DispatchableInfo(has_data=False, types=frozenset())


def _frontend_constants_types(frontend: object) -> frozenset[str]:
    """Return the union of noise, comment, block, and benign node types."""
    if not hasattr(frontend, "_build_constants"):
        return frozenset()
    constants = frontend._build_constants()  # type: ignore[union-attr]
    return (
        constants.noise_types
        | constants.comment_types
        | constants.block_node_types
        | constants.known_benign_types
    )


def extract_handled_types(language: Language) -> frozenset[str]:
    """Return the union of all node type strings a frontend explicitly handles.

    Covers context-mode frontends (_build_expr_dispatch / _build_stmt_dispatch)
    and legacy frontends (_EXPR_DISPATCH / _STMT_DISPATCH), plus noise types,
    comment types, and block_node_types from GrammarConstants.
    """
    frontend = get_deterministic_frontend(language)

    expr_keys = (
        frozenset(frontend._build_expr_dispatch().keys())
        if hasattr(frontend, "_build_expr_dispatch")
        else frozenset()
    )
    stmt_keys = (
        frozenset(frontend._build_stmt_dispatch().keys())
        if hasattr(frontend, "_build_stmt_dispatch")
        else frozenset()
    )
    expr_legacy = (
        frozenset(frontend._EXPR_DISPATCH.keys())
        if hasattr(frontend, "_EXPR_DISPATCH")
        else frozenset()
    )
    stmt_legacy = (
        frozenset(frontend._STMT_DISPATCH.keys())
        if hasattr(frontend, "_STMT_DISPATCH")
        else frozenset()
    )

    return (
        expr_keys
        | stmt_keys
        | expr_legacy
        | stmt_legacy
        | _frontend_constants_types(frontend)
    )


def _compute_gap_partition(
    unhandled: frozenset[str],
    info: _DispatchableInfo,
) -> tuple[list[str], list[str]]:
    """Partition unhandled nodes into true gaps and sub-structural nodes."""
    if info.has_data:
        return sorted(unhandled & info.types), sorted(unhandled - info.types)
    # No dispatchable info: treat all unhandled as true gaps
    return sorted(unhandled), []


def audit_language(language: Language) -> LanguageResult:
    """Run the grammar coverage audit for a single language."""
    grammar_nodes = enumerate_grammar_nodes(str(language))
    handled = extract_handled_types(language)
    info = get_block_dispatchable_types(language, grammar_nodes)
    verified_labels = _VERIFIED_FEATURE_LABELS.get(language, frozenset())

    covered = sorted(grammar_nodes & handled)
    unhandled = grammar_nodes - handled - verified_labels
    true_gaps, sub_structural = _compute_gap_partition(unhandled, info)
    verified = sorted(grammar_nodes & verified_labels)

    return LanguageResult(
        language=str(language),
        total_grammar_nodes=len(grammar_nodes),
        handled_count=len(covered),
        dispatchable_count=len(info.types) if info.has_data else 0,
        true_gap_count=len(true_gaps),
        sub_structural_count=len(sub_structural),
        verified_count=len(verified),
        covered=covered,
        true_gaps=true_gaps,
        sub_structural=sub_structural,
        verified=verified,
    )


def build_json(results: Sequence[LanguageResult]) -> dict[str, object]:
    """Build the full JSON output structure."""
    languages_json = {
        r.language: {
            "total_grammar_nodes": r.total_grammar_nodes,
            "handled_count": r.handled_count,
            "dispatchable_count": r.dispatchable_count,
            "true_gap_count": r.true_gap_count,
            "sub_structural_count": r.sub_structural_count,
            "verified_count": r.verified_count,
            "covered": r.covered,
            "true_gaps": r.true_gaps,
            "sub_structural": r.sub_structural,
            "verified": r.verified,
        }
        for r in results
    }
    total_true_gaps = sum(r.true_gap_count for r in results)
    languages_with_gaps = [r.language for r in results if r.true_gap_count > 0]
    return {
        "generated": str(date.today()),
        "languages": languages_json,
        "summary": {
            "total_true_gap_count": total_true_gaps,
            "languages_with_gaps": languages_with_gaps,
        },
    }


def print_summary(results: Sequence[LanguageResult], output_stream) -> None:
    """Print a human-readable summary table."""
    col_width = max(len(r.language) for r in results) + 2
    for r in results:
        label = f"{r.language:<{col_width}}"
        print(
            f"  {label}: {r.handled_count:4d} / {r.total_grammar_nodes:4d} handled"
            f"  ({r.true_gap_count} true gaps,"
            f" {r.sub_structural_count} sub-structural,"
            f" {r.verified_count} verified)",
            file=output_stream,
        )

    total_true_gaps = sum(r.true_gap_count for r in results)
    print("  " + "─" * 60, file=output_stream)
    print(
        f"  TOTAL: {total_true_gaps} true gaps across {len(results)} languages",
        file=output_stream,
    )


def _audit_with_progress(language: Language) -> LanguageResult:
    """Audit a language and log progress to stderr."""
    sys.stderr.write(f"Auditing {language}...\n")
    return audit_language(language)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic grammar coverage audit for all RedDragon frontends."
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write JSON to FILE instead of stdout (summary then goes to stdout).",
    )
    args = parser.parse_args()

    results = [_audit_with_progress(language) for language in AUDIT_LANGUAGES]

    payload = build_json(results)
    json_text = json.dumps(payload, indent=2)

    summary_stream = sys.stdout if args.output else sys.stderr
    if args.output:
        with open(args.output, "w") as f:
            f.write(json_text + "\n")
    else:
        sys.stdout.write(json_text + "\n")

    print_summary(results, summary_stream)


if __name__ == "__main__":
    main()
