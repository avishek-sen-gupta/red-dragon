"""Tests for interpreter.llm_frontend."""

from __future__ import annotations

import json

import pytest

from interpreter.ir import IRInstruction, Opcode
from interpreter.llm_client import LLMClient
from interpreter.llm_frontend import (
    IRParsingError,
    LLMFrontend,
    LLMFrontendPrompts,
    _parse_ir_response,
    _parse_single_instruction,
    _strip_markdown_fences,
    _validate_ir,
)


class FakeLLMClient(LLMClient):
    """Fake LLM client that returns a canned response."""

    def __init__(self, response: str = "[]"):
        self.response = response
        self.calls: list[dict] = []

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_message": user_message,
                "max_tokens": max_tokens,
            }
        )
        return self.response


SIMPLE_IR_JSON = json.dumps(
    [
        {
            "opcode": "LABEL",
            "result_reg": None,
            "operands": [],
            "label": "entry",
            "source_location": None,
        },
        {
            "opcode": "CONST",
            "result_reg": "%0",
            "operands": ["42"],
            "label": None,
            "source_location": "1:0",
        },
        {
            "opcode": "STORE_VAR",
            "result_reg": None,
            "operands": ["x", "%0"],
            "label": None,
            "source_location": "1:0",
        },
    ]
)


class TestStripMarkdownFences:
    def test_no_fences(self):
        assert _strip_markdown_fences("[1, 2, 3]") == "[1, 2, 3]"

    def test_json_fences(self):
        text = "```json\n[1, 2, 3]\n```"
        assert _strip_markdown_fences(text) == "[1, 2, 3]"

    def test_plain_fences(self):
        text = "```\n[1, 2, 3]\n```"
        assert _strip_markdown_fences(text) == "[1, 2, 3]"

    def test_whitespace_around_fences(self):
        text = "  ```json\n{}\n```  "
        assert _strip_markdown_fences(text) == "{}"


class TestParseSingleInstruction:
    def test_const_instruction(self):
        raw = {
            "opcode": "CONST",
            "result_reg": "%0",
            "operands": ["42"],
            "label": None,
        }
        inst = _parse_single_instruction(raw)
        assert inst.opcode == Opcode.CONST
        assert inst.result_reg == "%0"
        assert inst.operands == ["42"]
        assert inst.label is None

    def test_label_instruction(self):
        raw = {"opcode": "LABEL", "result_reg": None, "operands": [], "label": "entry"}
        inst = _parse_single_instruction(raw)
        assert inst.opcode == Opcode.LABEL
        assert inst.label == "entry"

    def test_unknown_opcode_raises(self):
        raw = {"opcode": "INVALID_OP"}
        with pytest.raises(IRParsingError, match="Unknown opcode"):
            _parse_single_instruction(raw)

    def test_missing_opcode_raises(self):
        with pytest.raises(IRParsingError, match="Unknown opcode"):
            _parse_single_instruction({})

    def test_all_opcodes_parseable(self):
        for opcode in Opcode:
            raw = {"opcode": opcode.value, "operands": []}
            inst = _parse_single_instruction(raw)
            assert inst.opcode == opcode


class TestParseIRResponse:
    def test_valid_json_array(self):
        instructions = _parse_ir_response(SIMPLE_IR_JSON)
        assert len(instructions) == 3
        assert instructions[0].opcode == Opcode.LABEL
        assert instructions[1].opcode == Opcode.CONST
        assert instructions[2].opcode == Opcode.STORE_VAR

    def test_with_markdown_fences(self):
        wrapped = f"```json\n{SIMPLE_IR_JSON}\n```"
        instructions = _parse_ir_response(wrapped)
        assert len(instructions) == 3

    def test_invalid_json_raises(self):
        with pytest.raises(IRParsingError, match="Failed to parse"):
            _parse_ir_response("not json at all")

    def test_non_array_raises(self):
        with pytest.raises(IRParsingError, match="Expected JSON array"):
            _parse_ir_response('{"opcode": "CONST"}')

    def test_empty_array(self):
        result = _parse_ir_response("[]")
        assert result == []


class TestValidateIR:
    def test_valid_with_entry_label(self):
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["1"]),
        ]
        result = _validate_ir(instructions)
        assert len(result) == 2
        assert result[0].label == "entry"

    def test_auto_prepends_entry_label(self):
        instructions = [
            IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["1"]),
        ]
        result = _validate_ir(instructions)
        assert len(result) == 2
        assert result[0].opcode == Opcode.LABEL
        assert result[0].label == "entry"
        assert result[1].opcode == Opcode.CONST

    def test_empty_raises(self):
        with pytest.raises(IRParsingError, match="empty instruction list"):
            _validate_ir([])

    def test_wrong_first_label_prepends_entry(self):
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="not_entry"),
            IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["1"]),
        ]
        result = _validate_ir(instructions)
        assert len(result) == 3
        assert result[0].label == "entry"


class TestLLMFrontend:
    def test_lower_sends_correct_prompt(self):
        fake = FakeLLMClient(response=SIMPLE_IR_JSON)
        frontend = LLMFrontend(fake, language="python")
        result = frontend.lower(None, b"x = 42")

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["system_prompt"] == LLMFrontendPrompts.SYSTEM_PROMPT
        assert "python" in call["user_message"]
        assert "x = 42" in call["user_message"]
        assert len(result) == 3

    def test_lower_with_different_language(self):
        fake = FakeLLMClient(response=SIMPLE_IR_JSON)
        frontend = LLMFrontend(fake, language="javascript")
        frontend.lower(None, b"let x = 42;")

        assert "javascript" in fake.calls[0]["user_message"]
        assert "let x = 42;" in fake.calls[0]["user_message"]

    def test_lower_auto_prepends_entry_when_missing(self):
        no_entry_json = json.dumps(
            [
                {
                    "opcode": "CONST",
                    "result_reg": "%0",
                    "operands": ["1"],
                    "label": None,
                }
            ]
        )
        fake = FakeLLMClient(response=no_entry_json)
        frontend = LLMFrontend(fake, language="python")
        result = frontend.lower(None, b"x = 1")

        assert result[0].opcode == Opcode.LABEL
        assert result[0].label == "entry"
        assert result[1].opcode == Opcode.CONST

    def test_lower_handles_string_source(self):
        fake = FakeLLMClient(response=SIMPLE_IR_JSON)
        frontend = LLMFrontend(fake, language="python")
        # Pass string instead of bytes
        result = frontend.lower(None, "x = 42")
        assert len(result) == 3

    def test_lower_raises_on_bad_response(self):
        fake = FakeLLMClient(response="not valid json")
        frontend = LLMFrontend(fake, language="python")
        with pytest.raises(IRParsingError):
            frontend.lower(None, b"x = 42")

    def test_tree_parameter_ignored(self):
        """LLM frontend ignores the tree parameter."""
        fake = FakeLLMClient(response=SIMPLE_IR_JSON)
        frontend = LLMFrontend(fake, language="python")
        sentinel = object()
        result = frontend.lower(sentinel, b"x = 42")
        assert len(result) == 3
