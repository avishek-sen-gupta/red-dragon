"""Tests for refactored backend that delegates to LLMClient."""

from __future__ import annotations

import json

import pytest

from interpreter.backend import ClaudeBackend, OpenAIBackend, get_backend
from interpreter.ir import IRInstruction, Opcode
from interpreter.vm import VMState, StackFrame


class FakeAnthropicResponse:
    def __init__(self, text: str):
        self.content = [type("Block", (), {"text": text})()]


class FakeAnthropicClient:
    def __init__(self):
        self.messages = self
        self.last_call = {}

    def create(self, **kwargs):
        self.last_call = kwargs
        return FakeAnthropicResponse(
            json.dumps(
                {
                    "register_writes": {"%0": 42},
                    "var_writes": {},
                    "reasoning": "test",
                }
            )
        )


class FakeOpenAIResponse:
    def __init__(self, text: str):
        self.choices = [
            type("Choice", (), {"message": type("Msg", (), {"content": text})()})()
        ]


class FakeOpenAIClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": self})()
        self.last_call = {}

    def create(self, **kwargs):
        self.last_call = kwargs
        return FakeOpenAIResponse(
            json.dumps(
                {
                    "register_writes": {"%0": 42},
                    "var_writes": {},
                    "reasoning": "test",
                }
            )
        )


def _make_vm_with_frame() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    return vm


class TestClaudeBackendRefactored:
    def test_interpret_instruction(self):
        fake = FakeAnthropicClient()
        backend = ClaudeBackend(client=fake)
        inst = IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["42"])
        vm = _make_vm_with_frame()
        update = backend.interpret_instruction(inst, vm)

        assert update.register_writes == {"%0": 42}
        assert update.reasoning == "test"


class TestOpenAIBackendRefactored:
    def test_interpret_instruction(self):
        fake = FakeOpenAIClient()
        backend = OpenAIBackend(client=fake)
        inst = IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["42"])
        vm = _make_vm_with_frame()
        update = backend.interpret_instruction(inst, vm)

        assert update.register_writes == {"%0": 42}
        assert update.reasoning == "test"


class TestGetBackendFactory:
    def test_claude_with_client(self):
        fake = FakeAnthropicClient()
        backend = get_backend("claude", client=fake)
        assert isinstance(backend, ClaudeBackend)

    def test_openai_with_client(self):
        fake = FakeOpenAIClient()
        backend = get_backend("openai", client=fake)
        assert isinstance(backend, OpenAIBackend)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown backend"):
            get_backend("gemini")
