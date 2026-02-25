"""LLM Interpreter Backend."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from .ir import IRInstruction
from .vm import VMState, StateUpdate, _resolve_reg, _serialize_value


SYSTEM_PROMPT = """\
You are a symbolic interpreter executing IR instructions one at a time.

You receive:
1. The IR instruction to execute
2. The resolved operand values (register names replaced with actual values)
3. The current VM state (heap, variables, path conditions)

You must return a JSON object with the effects of executing this instruction.
IMPORTANT: You MUST populate the correct fields — especially register_writes and var_writes.
If the instruction has a result_reg, you MUST include it in register_writes.

## JSON response schema

{
  "register_writes": {"<reg>": <value>},     // REQUIRED if instruction has result_reg
  "var_writes": {"<name>": <value>},          // for STORE_VAR
  "heap_writes": [{"obj_addr": "...", "field": "...", "value": ...}],
  "new_objects": [{"addr": "...", "type_hint": "..."}],
  "next_label": "<label>" or null,            // for BRANCH_IF — which target to take
  "call_push": {"function_name": "...", "return_label": "..."} or null,
  "call_pop": false,
  "return_value": null,
  "path_condition": "<condition>" or null,     // for BRANCH_IF decisions
  "reasoning": "short explanation"
}

Symbolic values: {"__symbolic__": true, "name": "sym_N", "type_hint": "...", "constraints": [...]}

## Rules by opcode

BINOP/UNOP with symbolic operands:
- If one operand is symbolic, produce a symbolic result describing the expression
- Example: sym_0 + 1 → {"__symbolic__": true, "name": "sym_1", "type_hint": "int", "constraints": ["sym_0 + 1"]}

CALL_FUNCTION / CALL_METHOD / CALL_UNKNOWN:
- For known builtins (len, print, range, int, str, type, isinstance, etc.), compute the result
- For user-defined functions visible in the program, return a symbolic value representing the call result
- ALWAYS write the result to the result register via register_writes
- Example: call_function print with args [5] → register_writes: {"%3": null} (print returns None)
- Example: call_function len with args [[1,2,3]] → register_writes: {"%3": 3}
- Example: call_function factorial with args [5] → register_writes: {"%3": {"__symbolic__": true, "name": "sym_0", "type_hint": "int", "constraints": ["factorial(5)"]}}

BRANCH_IF with symbolic condition:
- Choose the most likely/interesting path and set next_label to that target label
- Set path_condition to describe the assumption you made
- The label field contains "true_label,false_label"

## Examples

Instruction: %5 = binop * sym_0 4
Resolved operands: sym_0 (symbolic int), 4
→ {"register_writes": {"%5": {"__symbolic__": true, "name": "sym_1", "type_hint": "int", "constraints": ["sym_0 * 4"]}}, "reasoning": "symbolic multiply"}

Instruction: %9 = call_function factorial 5
→ {"register_writes": {"%9": {"__symbolic__": true, "name": "sym_2", "type_hint": "int", "constraints": ["factorial(5)"]}}, "reasoning": "recursive call to user function factorial"}

Instruction: %3 = call_function len [1, 2, 3]
→ {"register_writes": {"%3": 3}, "reasoning": "len of 3-element list"}

Instruction: branch_if sym_0 if_true_2,if_false_3  (where sym_0 has constraint "n <= 1")
→ {"next_label": "if_false_3", "path_condition": "assuming n > 1 (sym_0 is false)", "reasoning": "choosing false branch for more interesting path"}

Respond with ONLY valid JSON. No markdown fences. No text outside the JSON object.
"""


class LLMBackend(ABC):
    @abstractmethod
    def interpret_instruction(self, instruction: IRInstruction,
                              state: VMState) -> StateUpdate:
        ...

    def _build_prompt(self, instruction: IRInstruction,
                      state: VMState) -> str:
        """Build a user prompt with resolved operand values."""
        frame = state.current_frame

        # Resolve operand values for the LLM
        resolved = {}
        for i, op in enumerate(instruction.operands):
            raw = op
            val = _resolve_reg(state, op)
            if val is not raw:  # was a register reference
                resolved[str(op)] = _serialize_value(val)

        # Build a compact state snapshot (only what's relevant)
        compact_state = {
            "local_vars": {k: _serialize_value(v)
                           for k, v in frame.local_vars.items()},
        }
        if state.heap:
            compact_state["heap"] = {k: v.to_dict()
                                     for k, v in state.heap.items()}
        if state.path_conditions:
            compact_state["path_conditions"] = state.path_conditions

        msg = {
            "instruction": str(instruction),
            "result_reg": instruction.result_reg,
            "opcode": instruction.opcode.value,
            "operands": instruction.operands,
        }
        if resolved:
            msg["resolved_operand_values"] = resolved
        msg["state"] = compact_state

        return json.dumps(msg, indent=2, default=str)

    @staticmethod
    def _parse_response(text: str) -> StateUpdate:
        """Parse LLM response text into a StateUpdate."""
        text = text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
        text = text.strip()
        data = json.loads(text)
        return StateUpdate(**data)


class ClaudeBackend(LLMBackend):
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        import anthropic
        self._client = anthropic.Anthropic()
        self._model = model

    def interpret_instruction(self, instruction: IRInstruction,
                              state: VMState) -> StateUpdate:
        user_msg = self._build_prompt(instruction, state)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return self._parse_response(response.content[0].text)


class OpenAIBackend(LLMBackend):
    def __init__(self, model: str = "gpt-4o"):
        import openai
        self._client = openai.OpenAI()
        self._model = model

    def interpret_instruction(self, instruction: IRInstruction,
                              state: VMState) -> StateUpdate:
        user_msg = self._build_prompt(instruction, state)
        response = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=1024,
        )
        return self._parse_response(response.choices[0].message.content)


def get_backend(name: str) -> LLMBackend:
    if name == "claude":
        return ClaudeBackend()
    if name == "openai":
        return OpenAIBackend()
    raise ValueError(f"Unknown backend: {name}")
