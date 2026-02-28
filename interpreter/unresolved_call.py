"""Unresolved call resolvers — pluggable strategies for unknown function/method calls."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from interpreter.ir import IRInstruction
from interpreter.llm_client import LLMClient
from interpreter.vm_types import (
    ExecutionResult,
    HeapWrite,
    StateUpdate,
    SymbolicValue,
    VMState,
    _serialize_value,
)

logger = logging.getLogger(__name__)


def _symbolic_name(val: Any) -> str:
    """Get a human-readable name for a value, suitable for symbolic hints."""
    if isinstance(val, SymbolicValue):
        return val.name
    if isinstance(val, dict) and val.get("__symbolic__"):
        return val.get("name", "?")
    return repr(val)


class UnresolvedCallResolver(ABC):
    """Strategy for resolving calls to unknown functions/methods."""

    @abstractmethod
    def resolve_call(
        self,
        func_name: str,
        args: list[Any],
        inst: IRInstruction,
        vm: VMState,
    ) -> ExecutionResult:
        """Resolve an unknown function call and return an ExecutionResult."""
        ...

    @abstractmethod
    def resolve_method(
        self,
        obj_desc: str,
        method_name: str,
        args: list[Any],
        inst: IRInstruction,
        vm: VMState,
    ) -> ExecutionResult:
        """Resolve an unknown method call and return an ExecutionResult."""
        ...


class SymbolicResolver(UnresolvedCallResolver):
    """Default resolver — creates symbolic values for unknown calls."""

    def resolve_call(
        self,
        func_name: str,
        args: list[Any],
        inst: IRInstruction,
        vm: VMState,
    ) -> ExecutionResult:
        args_desc = ", ".join(_symbolic_name(a) for a in args)
        sym = vm.fresh_symbolic(hint=f"{func_name}({args_desc})")
        sym.constraints = [f"{func_name}({args_desc})"]
        logger.debug("Unknown function %s — creating symbolic %s", func_name, sym.name)
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"unknown function {func_name}({args_desc}) → symbolic {sym.name}",
            )
        )

    def resolve_method(
        self,
        obj_desc: str,
        method_name: str,
        args: list[Any],
        inst: IRInstruction,
        vm: VMState,
    ) -> ExecutionResult:
        args_desc = ", ".join(_symbolic_name(a) for a in args)
        call_desc = f"{obj_desc}.{method_name}({args_desc})"
        sym = vm.fresh_symbolic(hint=call_desc)
        sym.constraints = [call_desc]
        logger.debug(
            "Unknown method %s.%s — creating symbolic %s",
            obj_desc,
            method_name,
            sym.name,
        )
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym.to_dict()},
                reasoning=f"unknown method {call_desc} → symbolic {sym.name}",
            )
        )


PLAUSIBLE_VALUE_SYSTEM_PROMPT = """\
You evaluate function/method calls and return plausible concrete results.
Given a function name, its arguments, and relevant heap state, return:
1. The most likely return value
2. Any side effects as direct heap/variable mutations

Return JSON:
{
  "value": <concrete_value_or_null>,
  "heap_writes": [{"obj_addr": "...", "field": "...", "value": ...}],
  "var_writes": {"<name>": <value>},
  "reasoning": "short explanation"
}

For standard library functions (math.sqrt, string.upper, list.append, etc.), compute the exact result.
For functions with side effects, include the mutations in heap_writes/var_writes.
For unknown functions, return your best estimate based on the name and arguments.

Respond with ONLY valid JSON. No markdown fences. No text outside the JSON object.
"""


class LLMPlausibleResolver(UnresolvedCallResolver):
    """Resolver that uses a lightweight LLM call to get plausible concrete values."""

    def __init__(self, llm_client: LLMClient, source_language: str = ""):
        self._llm_client = llm_client
        self._source_language = source_language
        self._fallback = SymbolicResolver()

    def _build_prompt(
        self,
        call_desc: str,
        args: list[Any],
        inst: IRInstruction,
        vm: VMState,
    ) -> str:
        frame = vm.current_frame
        compact_state: dict[str, Any] = {
            "local_vars": {k: _serialize_value(v) for k, v in frame.local_vars.items()},
        }
        if vm.heap:
            compact_state["heap"] = {k: v.to_dict() for k, v in vm.heap.items()}

        msg: dict[str, Any] = {
            "call": call_desc,
            "args": [_serialize_value(a) for a in args],
            "result_reg": inst.result_reg,
            "state": compact_state,
        }
        if self._source_language:
            msg["language"] = self._source_language

        return json.dumps(msg, indent=2, default=str)

    def _parse_llm_response(self, text: str, inst: IRInstruction) -> ExecutionResult:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
        text = text.strip()

        data = json.loads(text)
        value = data.get("value")
        reasoning = data.get("reasoning", "LLM plausible value")

        register_writes: dict[str, Any] = {}
        if inst.result_reg:
            register_writes[inst.result_reg] = value

        heap_writes = [
            HeapWrite(
                obj_addr=hw["obj_addr"],
                field=hw["field"],
                value=hw["value"],
            )
            for hw in data.get("heap_writes", [])
        ]

        var_writes: dict[str, Any] = data.get("var_writes", {})

        return ExecutionResult.success(
            StateUpdate(
                register_writes=register_writes,
                heap_writes=heap_writes,
                var_writes=var_writes,
                reasoning=f"LLM plausible: {reasoning}",
            )
        )

    def resolve_call(
        self,
        func_name: str,
        args: list[Any],
        inst: IRInstruction,
        vm: VMState,
    ) -> ExecutionResult:
        args_desc = ", ".join(_symbolic_name(a) for a in args)
        call_desc = f"{func_name}({args_desc})"
        try:
            prompt = self._build_prompt(call_desc, args, inst, vm)
            logger.info("LLM plausible-value call for %s", call_desc)
            raw = self._llm_client.complete(
                system_prompt=PLAUSIBLE_VALUE_SYSTEM_PROMPT,
                user_message=prompt,
                max_tokens=512,
            )
            return self._parse_llm_response(raw, inst)
        except Exception:
            logger.warning(
                "LLM plausible-value call failed for %s, falling back to symbolic",
                call_desc,
                exc_info=True,
            )
            return self._fallback.resolve_call(func_name, args, inst, vm)

    def resolve_method(
        self,
        obj_desc: str,
        method_name: str,
        args: list[Any],
        inst: IRInstruction,
        vm: VMState,
    ) -> ExecutionResult:
        args_desc = ", ".join(_symbolic_name(a) for a in args)
        call_desc = f"{obj_desc}.{method_name}({args_desc})"
        try:
            prompt = self._build_prompt(call_desc, args, inst, vm)
            logger.info("LLM plausible-value call for %s", call_desc)
            raw = self._llm_client.complete(
                system_prompt=PLAUSIBLE_VALUE_SYSTEM_PROMPT,
                user_message=prompt,
                max_tokens=512,
            )
            return self._parse_llm_response(raw, inst)
        except Exception:
            logger.warning(
                "LLM plausible-value call failed for %s, falling back to symbolic",
                call_desc,
                exc_info=True,
            )
            return self._fallback.resolve_method(obj_desc, method_name, args, inst, vm)
