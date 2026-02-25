"""Tests for ChunkExtractor, IRRenumberer, and ChunkedLLMFrontend."""

from __future__ import annotations

import json
from collections import deque

import pytest

from interpreter import constants
from interpreter.chunked_llm_frontend import (
    ChunkedLLMFrontend,
    ChunkExtractor,
    IRRenumberer,
    SourceChunk,
)
from interpreter.frontend import get_frontend
from interpreter.ir import IRInstruction, Opcode
from interpreter.llm_client import LLMClient
from interpreter.llm_frontend import LLMFrontend
from interpreter.parser import Parser, ParserFactory, TreeSitterParserFactory


class FakeSequentialLLMClient(LLMClient):
    """Returns canned responses from a queue, one per call."""

    def __init__(self, responses: list[str]):
        self._responses: deque[str] = deque(responses)

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        if not self._responses:
            raise RuntimeError("FakeSequentialLLMClient: no more canned responses")
        return self._responses.popleft()


def _make_ir_json(instructions: list[dict]) -> str:
    return json.dumps(instructions)


def _entry_label_dict() -> dict:
    return {"opcode": "LABEL", "result_reg": None, "operands": [], "label": "entry"}


def _parse_tree(source: str, language: str = "python"):
    """Parse source with real tree-sitter and return the tree."""
    parser = Parser(TreeSitterParserFactory())
    return parser.parse(source, language)


# ─── TestChunkExtractor ───────────────────────────────────────────────


class TestChunkExtractor:
    def setup_method(self):
        self.extractor = ChunkExtractor()

    def test_single_function(self):
        source = "def foo():\n    return 1\n"
        tree = _parse_tree(source)
        chunks = self.extractor.extract_chunks(tree, source.encode(), "python")
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "function"
        assert chunks[0].name == "foo"
        assert "def foo" in chunks[0].source_text

    def test_function_and_top_level(self):
        source = "def foo():\n    return 1\n\nx = foo()\n"
        tree = _parse_tree(source)
        chunks = self.extractor.extract_chunks(tree, source.encode(), "python")
        assert len(chunks) == 2
        assert chunks[0].chunk_type == "function"
        assert chunks[0].name == "foo"
        assert chunks[1].chunk_type == "top_level"
        assert "x = foo()" in chunks[1].source_text

    def test_class(self):
        source = "class MyClass:\n    def __init__(self):\n        self.x = 1\n"
        tree = _parse_tree(source)
        chunks = self.extractor.extract_chunks(tree, source.encode(), "python")
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "class"
        assert chunks[0].name == "MyClass"

    def test_multiple_functions(self):
        source = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        tree = _parse_tree(source)
        chunks = self.extractor.extract_chunks(tree, source.encode(), "python")
        assert len(chunks) == 2
        assert all(c.chunk_type == "function" for c in chunks)
        assert chunks[0].name == "foo"
        assert chunks[1].name == "bar"

    def test_contiguous_top_level_grouped(self):
        source = "x = 1\ny = 2\nz = 3\n"
        tree = _parse_tree(source)
        chunks = self.extractor.extract_chunks(tree, source.encode(), "python")
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "top_level"
        assert "x = 1" in chunks[0].source_text
        assert "z = 3" in chunks[0].source_text

    def test_interleaved_functions_and_top_level(self):
        source = "x = 1\ndef foo():\n    pass\ny = 2\ndef bar():\n    pass\nz = 3\n"
        tree = _parse_tree(source)
        chunks = self.extractor.extract_chunks(tree, source.encode(), "python")
        # Functions/classes come first, then top-level groups
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        top_chunks = [c for c in chunks if c.chunk_type == "top_level"]
        assert len(func_chunks) == 2
        assert len(top_chunks) == 3
        # Functions should be before top-level in output
        first_func_idx = next(
            i for i, c in enumerate(chunks) if c.chunk_type == "function"
        )
        last_top_idx = max(
            i for i, c in enumerate(chunks) if c.chunk_type == "top_level"
        )
        assert first_func_idx < last_top_idx

    def test_empty_source(self):
        source = ""
        tree = _parse_tree(source)
        chunks = self.extractor.extract_chunks(tree, source.encode(), "python")
        assert chunks == []


# ─── TestIRRenumberer ─────────────────────────────────────────────────


class TestIRRenumberer:
    def setup_method(self):
        self.renumberer = IRRenumberer()

    def test_register_offset(self):
        instructions = [
            IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["42"]),
            IRInstruction(
                opcode=Opcode.BINOP, result_reg="%1", operands=["+", "%0", "%0"]
            ),
        ]
        result, next_offset = self.renumberer.renumber(instructions, 10, "_s")
        assert result[0].result_reg == "%10"
        assert result[1].result_reg == "%11"
        assert result[1].operands == ["+", "%10", "%10"]
        assert next_offset == 12

    def test_label_suffix(self):
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="func_foo_0"),
            IRInstruction(opcode=Opcode.BRANCH, label="end_foo_1"),
        ]
        result, _ = self.renumberer.renumber(instructions, 0, "_chunk0")
        assert result[0].label == "func_foo_0_chunk0"
        assert result[1].label == "end_foo_1_chunk0"

    def test_branch_if_comma_separated_labels(self):
        instructions = [
            IRInstruction(
                opcode=Opcode.BRANCH_IF,
                operands=["%0"],
                label="if_true_0,if_false_1",
            ),
        ]
        result, _ = self.renumberer.renumber(instructions, 0, "_chunk1")
        assert result[0].label == "if_true_0_chunk1,if_false_1_chunk1"

    def test_function_ref_label_renaming(self):
        instructions = [
            IRInstruction(
                opcode=Opcode.CONST,
                result_reg="%0",
                operands=["<function:foo@func_foo_0>"],
            ),
            IRInstruction(
                opcode=Opcode.CONST,
                result_reg="%1",
                operands=["<class:Bar@class_Bar_0>"],
            ),
        ]
        result, _ = self.renumberer.renumber(instructions, 5, "_chunk2")
        assert result[0].operands == ["<function:foo@func_foo_0_chunk2>"]
        assert result[1].operands == ["<class:Bar@class_Bar_0_chunk2>"]

    def test_non_register_operands_untouched(self):
        instructions = [
            IRInstruction(opcode=Opcode.STORE_VAR, operands=["my_var", "%0"]),
            IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%1", operands=["my_var"]),
        ]
        result, _ = self.renumberer.renumber(instructions, 3, "_s")
        assert result[0].operands == ["my_var", "%3"]
        assert result[1].operands == ["my_var"]


# ─── TestChunkedLLMFrontend ──────────────────────────────────────────


def _single_func_ir() -> str:
    """Canned LLM response for a single function."""
    return _make_ir_json(
        [
            _entry_label_dict(),
            {
                "opcode": "BRANCH",
                "result_reg": None,
                "operands": [],
                "label": "end_foo_1",
            },
            {
                "opcode": "LABEL",
                "result_reg": None,
                "operands": [],
                "label": "func_foo_0",
            },
            {
                "opcode": "CONST",
                "result_reg": "%0",
                "operands": ["1"],
                "label": None,
            },
            {
                "opcode": "RETURN",
                "result_reg": None,
                "operands": ["%0"],
                "label": None,
            },
            {
                "opcode": "LABEL",
                "result_reg": None,
                "operands": [],
                "label": "end_foo_1",
            },
            {
                "opcode": "CONST",
                "result_reg": "%1",
                "operands": ["<function:foo@func_foo_0>"],
                "label": None,
            },
            {
                "opcode": "STORE_VAR",
                "result_reg": None,
                "operands": ["foo", "%1"],
                "label": None,
            },
        ]
    )


def _second_func_ir() -> str:
    """Canned LLM response for a second function."""
    return _make_ir_json(
        [
            _entry_label_dict(),
            {
                "opcode": "BRANCH",
                "result_reg": None,
                "operands": [],
                "label": "end_bar_1",
            },
            {
                "opcode": "LABEL",
                "result_reg": None,
                "operands": [],
                "label": "func_bar_0",
            },
            {
                "opcode": "CONST",
                "result_reg": "%0",
                "operands": ["2"],
                "label": None,
            },
            {
                "opcode": "RETURN",
                "result_reg": None,
                "operands": ["%0"],
                "label": None,
            },
            {
                "opcode": "LABEL",
                "result_reg": None,
                "operands": [],
                "label": "end_bar_1",
            },
            {
                "opcode": "CONST",
                "result_reg": "%1",
                "operands": ["<function:bar@func_bar_0>"],
                "label": None,
            },
            {
                "opcode": "STORE_VAR",
                "result_reg": None,
                "operands": ["bar", "%1"],
                "label": None,
            },
        ]
    )


def _top_level_ir() -> str:
    """Canned LLM response for top-level code."""
    return _make_ir_json(
        [
            _entry_label_dict(),
            {
                "opcode": "CONST",
                "result_reg": "%0",
                "operands": ["42"],
                "label": None,
            },
            {
                "opcode": "STORE_VAR",
                "result_reg": None,
                "operands": ["x", "%0"],
                "label": None,
            },
        ]
    )


class TestChunkedLLMFrontend:
    def _make_frontend(
        self, responses: list[str], language: str = "python"
    ) -> ChunkedLLMFrontend:
        client = FakeSequentialLLMClient(responses)
        inner = LLMFrontend(client, language=language)
        return ChunkedLLMFrontend(inner, TreeSitterParserFactory(), language)

    def test_single_function_file(self):
        source = "def foo():\n    return 1\n"
        frontend = self._make_frontend([_single_func_ir()])
        result = frontend.lower(None, source.encode())
        assert result[0].opcode == Opcode.LABEL
        assert result[0].label == "entry"
        # Should contain the function body instructions (renumbered)
        opcodes = [inst.opcode for inst in result]
        assert Opcode.BRANCH in opcodes
        assert Opcode.RETURN in opcodes

    def test_two_functions_non_colliding_registers(self):
        source = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
        frontend = self._make_frontend([_single_func_ir(), _second_func_ir()])
        result = frontend.lower(None, source.encode())
        # Collect all result_reg values
        regs = [inst.result_reg for inst in result if inst.result_reg is not None]
        # All registers should be unique
        assert len(regs) == len(set(regs)), f"Duplicate registers found: {regs}"

    def test_two_functions_non_colliding_labels(self):
        source = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
        frontend = self._make_frontend([_single_func_ir(), _second_func_ir()])
        result = frontend.lower(None, source.encode())
        # Collect all LABEL labels
        labels = [
            inst.label for inst in result if inst.opcode == Opcode.LABEL and inst.label
        ]
        # All labels should be unique
        assert len(labels) == len(set(labels)), f"Duplicate labels found: {labels}"

    def test_single_entry_label(self):
        source = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
        frontend = self._make_frontend([_single_func_ir(), _second_func_ir()])
        result = frontend.lower(None, source.encode())
        entry_labels = [
            inst
            for inst in result
            if inst.opcode == Opcode.LABEL and inst.label == "entry"
        ]
        assert len(entry_labels) == 1

    def test_chunk_failure_produces_symbolic_placeholder(self):
        source = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
        # First chunk succeeds, second returns invalid JSON
        frontend = self._make_frontend([_single_func_ir(), "NOT VALID JSON AT ALL"])
        result = frontend.lower(None, source.encode())
        symbolic_instructions = [
            inst
            for inst in result
            if inst.opcode == Opcode.SYMBOLIC
            and any("chunk_error:" in str(op) for op in inst.operands)
        ]
        assert len(symbolic_instructions) == 1
        assert "chunk_error:bar" in str(symbolic_instructions[0].operands)

    def test_tree_none_triggers_internal_parse(self):
        source = "def foo():\n    return 1\n"
        frontend = self._make_frontend([_single_func_ir()])
        # Pass tree=None — should parse internally
        result = frontend.lower(None, source.encode())
        assert len(result) > 1
        assert result[0].opcode == Opcode.LABEL
        assert result[0].label == "entry"


# ─── TestFrontendFactory (chunked_llm) ───────────────────────────────


class TestChunkedLLMFrontendFactory:
    def test_get_frontend_returns_chunked_llm_frontend(self):
        fake = FakeSequentialLLMClient(["[]"])
        frontend = get_frontend(
            "python",
            frontend_type=constants.FRONTEND_CHUNKED_LLM,
            llm_client=fake,
        )
        assert isinstance(frontend, ChunkedLLMFrontend)
