"""Tests for refactored backend that delegates to LLMClient."""

from __future__ import annotations

import json

import pytest

from interpreter.llm.backend import LLMInterpreterBackend, get_backend
from interpreter.llm.llm_client import LLMClient
from interpreter.register import Register
from interpreter.ir import IRInstruction, Opcode
from interpreter.vm.vm import VMState, StackFrame


class FakeLLMClient(LLMClient):
    """Fake LLMClient for testing backend logic."""

    def __init__(self, response_json: dict):
        self._response_json = response_json
        self.last_call: dict = {}

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        self.last_call = {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "max_tokens": max_tokens,
        }
        return json.dumps(self._response_json)


def _make_vm_with_frame() -> VMState:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    return vm


class TestLLMInterpreterBackend:
    def test_interpret_instruction(self):
        fake_client = FakeLLMClient(
            {
                "register_writes": {"%0": 42},
                "var_writes": {},
                "reasoning": "test",
            }
        )
        backend = LLMInterpreterBackend(llm_client=fake_client)
        inst = IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["42"])
        vm = _make_vm_with_frame()
        update = backend.interpret_instruction(inst, vm)

        assert update.register_writes == {Register("%0"): 42}
        assert update.reasoning == "test"

    def test_passes_system_prompt(self):
        fake_client = FakeLLMClient(
            {
                "register_writes": {"%0": 1},
                "reasoning": "ok",
            }
        )
        backend = LLMInterpreterBackend(llm_client=fake_client)
        inst = IRInstruction(opcode=Opcode.CONST, result_reg="%0", operands=["1"])
        vm = _make_vm_with_frame()
        backend.interpret_instruction(inst, vm)

        assert "symbolic interpreter" in fake_client.last_call["system_prompt"]
        assert fake_client.last_call["max_tokens"] == 1024


class TestGetBackendFactory:
    def test_returns_llm_interpreter_backend(self):
        from types import SimpleNamespace

        def fake_completion_fn(**kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {"register_writes": {}, "reasoning": "ok"}
                            )
                        )
                    )
                ]
            )

        backend = get_backend("claude", client=fake_completion_fn)
        assert isinstance(backend, LLMInterpreterBackend)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_backend("gemini")
