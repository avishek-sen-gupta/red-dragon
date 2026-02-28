"""Tests for UnresolvedCallResolver — SymbolicResolver and LLMPlausibleResolver."""

import json

import pytest

from interpreter.ir import IRInstruction, Opcode
from interpreter.llm_client import LLMClient
from interpreter.unresolved_call import (
    LLMPlausibleResolver,
    SymbolicResolver,
    UnresolvedCallResolver,
)
from interpreter.vm_types import (
    ExecutionResult,
    StackFrame,
    HeapObject,
    VMState,
)


def _make_vm() -> VMState:
    """Create a minimal VMState with one stack frame."""
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="test"))
    return vm


def _make_call_inst(
    result_reg: str = "%0", func_name: str = "unknown_func"
) -> IRInstruction:
    """Create a CALL_FUNCTION instruction."""
    return IRInstruction(
        opcode=Opcode.CALL_FUNCTION,
        result_reg=result_reg,
        operands=[func_name],
    )


def _make_method_inst(result_reg: str = "%0") -> IRInstruction:
    """Create a CALL_METHOD instruction."""
    return IRInstruction(
        opcode=Opcode.CALL_METHOD,
        result_reg=result_reg,
        operands=["obj", "method"],
    )


class FakeLLMClient(LLMClient):
    """Fake LLM client that returns a preconfigured response."""

    def __init__(self, response: str):
        self._response = response

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        return self._response


class FailingLLMClient(LLMClient):
    """LLM client that always raises an exception."""

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        raise ConnectionError("LLM service unavailable")


class TestSymbolicResolver:
    def test_resolve_call_produces_symbolic_value(self):
        resolver = SymbolicResolver()
        vm = _make_vm()
        inst = _make_call_inst()

        result = resolver.resolve_call("math.sqrt", [16], inst, vm)

        assert result.handled
        reg_val = result.update.register_writes["%0"]
        assert reg_val["__symbolic__"] is True
        assert "math.sqrt(16)" in reg_val.get("type_hint", "")

    def test_resolve_call_includes_constraint(self):
        resolver = SymbolicResolver()
        vm = _make_vm()
        inst = _make_call_inst()

        result = resolver.resolve_call("foo", [1, 2], inst, vm)

        reg_val = result.update.register_writes["%0"]
        assert "foo(1, 2)" in reg_val["constraints"]

    def test_resolve_method_produces_symbolic_value(self):
        resolver = SymbolicResolver()
        vm = _make_vm()
        inst = _make_method_inst()

        result = resolver.resolve_method("myobj", "do_thing", [42], inst, vm)

        assert result.handled
        reg_val = result.update.register_writes["%0"]
        assert reg_val["__symbolic__"] is True
        assert "myobj.do_thing(42)" in reg_val.get("type_hint", "")

    def test_resolve_method_includes_constraint(self):
        resolver = SymbolicResolver()
        vm = _make_vm()
        inst = _make_method_inst()

        result = resolver.resolve_method("obj", "method", [], inst, vm)

        reg_val = result.update.register_writes["%0"]
        assert "obj.method()" in reg_val["constraints"]

    def test_increments_symbolic_counter(self):
        resolver = SymbolicResolver()
        vm = _make_vm()
        inst = _make_call_inst()

        resolver.resolve_call("f", [], inst, vm)
        assert vm.symbolic_counter == 1

        resolver.resolve_call("g", [], inst, vm)
        assert vm.symbolic_counter == 2

    def test_is_instance_of_abc(self):
        assert isinstance(SymbolicResolver(), UnresolvedCallResolver)


class TestLLMPlausibleResolver:
    def test_resolve_call_returns_concrete_value(self):
        response = json.dumps({"value": 4.0, "reasoning": "sqrt(16) = 4"})
        resolver = LLMPlausibleResolver(llm_client=FakeLLMClient(response))
        vm = _make_vm()
        inst = _make_call_inst()

        result = resolver.resolve_call("math.sqrt", [16], inst, vm)

        assert result.handled
        assert result.update.register_writes["%0"] == 4.0
        assert "LLM plausible" in result.update.reasoning

    def test_resolve_call_with_side_effects(self):
        response = json.dumps(
            {
                "value": None,
                "heap_writes": [
                    {"obj_addr": "arr_5", "field": "3", "value": "new_element"},
                    {"obj_addr": "arr_5", "field": "length", "value": 4},
                ],
                "reasoning": "append adds element at end",
            }
        )
        resolver = LLMPlausibleResolver(llm_client=FakeLLMClient(response))
        vm = _make_vm()
        inst = _make_call_inst()

        result = resolver.resolve_call("list.append", ["x"], inst, vm)

        assert result.handled
        assert len(result.update.heap_writes) == 2
        assert result.update.heap_writes[0].obj_addr == "arr_5"
        assert result.update.heap_writes[0].field == "3"
        assert result.update.heap_writes[0].value == "new_element"
        assert result.update.heap_writes[1].field == "length"
        assert result.update.heap_writes[1].value == 4

    def test_resolve_call_with_var_writes(self):
        response = json.dumps(
            {
                "value": "ok",
                "var_writes": {"status": "done"},
                "reasoning": "side effect on var",
            }
        )
        resolver = LLMPlausibleResolver(llm_client=FakeLLMClient(response))
        vm = _make_vm()
        inst = _make_call_inst()

        result = resolver.resolve_call("set_status", [], inst, vm)

        assert result.update.var_writes == {"status": "done"}
        assert result.update.register_writes["%0"] == "ok"

    def test_resolve_method_returns_concrete_value(self):
        response = json.dumps({"value": "HELLO", "reasoning": "upper()"})
        resolver = LLMPlausibleResolver(llm_client=FakeLLMClient(response))
        vm = _make_vm()
        inst = _make_method_inst()

        result = resolver.resolve_method("s", "upper", [], inst, vm)

        assert result.handled
        assert result.update.register_writes["%0"] == "HELLO"

    def test_fallback_to_symbolic_on_llm_failure(self):
        resolver = LLMPlausibleResolver(llm_client=FailingLLMClient())
        vm = _make_vm()
        inst = _make_call_inst()

        result = resolver.resolve_call("broken_func", [1], inst, vm)

        assert result.handled
        reg_val = result.update.register_writes["%0"]
        assert reg_val["__symbolic__"] is True
        assert "broken_func(1)" in reg_val.get("type_hint", "")

    def test_fallback_to_symbolic_on_invalid_json(self):
        resolver = LLMPlausibleResolver(
            llm_client=FakeLLMClient("not valid json at all")
        )
        vm = _make_vm()
        inst = _make_call_inst()

        result = resolver.resolve_call("bad_json_func", [], inst, vm)

        assert result.handled
        reg_val = result.update.register_writes["%0"]
        assert reg_val["__symbolic__"] is True

    def test_method_fallback_to_symbolic_on_failure(self):
        resolver = LLMPlausibleResolver(llm_client=FailingLLMClient())
        vm = _make_vm()
        inst = _make_method_inst()

        result = resolver.resolve_method("obj", "broken", [], inst, vm)

        assert result.handled
        reg_val = result.update.register_writes["%0"]
        assert reg_val["__symbolic__"] is True

    def test_source_language_included_in_prompt(self):
        calls: list[str] = []

        class CapturingClient(LLMClient):
            def complete(
                self, system_prompt: str, user_message: str, max_tokens: int = 4096
            ) -> str:
                calls.append(user_message)
                return json.dumps({"value": 42, "reasoning": "captured"})

        resolver = LLMPlausibleResolver(
            llm_client=CapturingClient(), source_language="python"
        )
        vm = _make_vm()
        inst = _make_call_inst()

        resolver.resolve_call("func", [], inst, vm)

        assert len(calls) == 1
        prompt_data = json.loads(calls[0])
        assert prompt_data["language"] == "python"

    def test_strips_markdown_fences_from_response(self):
        response = '```json\n{"value": 99, "reasoning": "fenced"}\n```'
        resolver = LLMPlausibleResolver(llm_client=FakeLLMClient(response))
        vm = _make_vm()
        inst = _make_call_inst()

        result = resolver.resolve_call("fenced_func", [], inst, vm)

        assert result.update.register_writes["%0"] == 99

    def test_is_instance_of_abc(self):
        response = json.dumps({"value": 1, "reasoning": "test"})
        resolver = LLMPlausibleResolver(llm_client=FakeLLMClient(response))
        assert isinstance(resolver, UnresolvedCallResolver)

    def test_heap_state_included_in_prompt(self):
        calls: list[str] = []

        class CapturingClient(LLMClient):
            def complete(
                self, system_prompt: str, user_message: str, max_tokens: int = 4096
            ) -> str:
                calls.append(user_message)
                return json.dumps({"value": None, "reasoning": "captured"})

        resolver = LLMPlausibleResolver(llm_client=CapturingClient())
        vm = _make_vm()
        vm.heap["obj_1"] = HeapObject(type_hint="MyClass")
        vm.heap["obj_1"].fields["x"] = 10
        inst = _make_call_inst()

        resolver.resolve_call("func", [], inst, vm)

        prompt_data = json.loads(calls[0])
        assert "heap" in prompt_data["state"]
        assert "obj_1" in prompt_data["state"]["heap"]
