"""LLM-based frontend — sends raw source to an LLM to produce IR instructions."""

from __future__ import annotations

import json
import logging
from typing import Any

from .frontend import Frontend
from .ir import IRInstruction, Opcode
from .llm_client import LLMClient
from . import constants

logger = logging.getLogger(__name__)


class IRParsingError(Exception):
    """Raised when the LLM response cannot be parsed into valid IR."""

    pass


class LLMFrontendPrompts:
    """Prompt templates for LLM-based IR lowering."""

    SYSTEM_PROMPT = """\
You are a compiler frontend. Your job is to lower source code into a flattened \
three-address code (TAC) intermediate representation (IR).

## IR Specification

Each instruction is a JSON object with these fields:
- "opcode": one of the opcodes listed below (string, UPPER_CASE)
- "result_reg": the register that receives the result (string like "%0", "%1", ...), or null
- "operands": list of operands (strings, numbers, register references like "%0")
- "label": for LABEL instructions: the label name; for BRANCH/BRANCH_IF: the target label(s); otherwise null
- "source_location": optional "line:col" string, or null

## Opcodes (19 total)

### Value producers (have result_reg)
- CONST: Load a constant. operands=[value]. Example: {"%0 = CONST 42"} → {"opcode":"CONST","result_reg":"%0","operands":["42"],"label":null}
- LOAD_VAR: Load a variable by name. operands=[var_name]. Example: %1 = LOAD_VAR x
- LOAD_FIELD: Load a field from an object. operands=[obj_reg, field_name]. Example: %2 = LOAD_FIELD %0 "name"
- LOAD_INDEX: Load by index. operands=[obj_reg, index_reg]. Example: %3 = LOAD_INDEX %0 %1
- NEW_OBJECT: Allocate an object. operands=[type_name]. Example: %4 = NEW_OBJECT dict
- NEW_ARRAY: Allocate an array. operands=[type_name, size_reg]. Example: %5 = NEW_ARRAY list %3
- BINOP: Binary operation. operands=[operator, lhs_reg, rhs_reg]. Example: %6 = BINOP + %0 %1
- UNOP: Unary operation. operands=[operator, operand_reg]. Example: %7 = UNOP - %0
- CALL_FUNCTION: Call a named function. operands=[func_name, arg_reg1, arg_reg2, ...]. Example: %8 = CALL_FUNCTION factorial %0
- CALL_METHOD: Call a method. operands=[obj_reg, method_name, arg_reg1, ...]. Example: %9 = CALL_METHOD %0 append %1
- CALL_UNKNOWN: Call a dynamic target. operands=[target_reg, arg_reg1, ...]. Example: %10 = CALL_UNKNOWN %0 %1

### Value consumers / control flow (no result_reg)
- STORE_VAR: Store to a variable. operands=[var_name, value_reg]. Example: STORE_VAR x %0
- STORE_FIELD: Store to a field. operands=[obj_reg, field_name, value_reg]. Example: STORE_FIELD %0 name %1
- STORE_INDEX: Store by index. operands=[obj_reg, index_reg, value_reg]. Example: STORE_INDEX %0 %1 %2
- BRANCH_IF: Conditional branch. operands=[condition_reg]. label="true_label,false_label". Example: BRANCH_IF %0 → label:"if_true_0,if_false_1"
- BRANCH: Unconditional branch. label=target_label. Example: BRANCH → label:"end_0"
- RETURN: Return from function. operands=[value_reg]. Example: RETURN %0
- THROW: Throw/raise. operands=[value_reg]. Example: THROW %0

### Special
- SYMBOLIC: Declare an unknown/symbolic value. operands=[hint_string]. Example: %11 = SYMBOLIC "param:n"
- LABEL: Pseudo-instruction marking a label. label=label_name. Example: LABEL → label:"entry"

## Conventions

1. **Entry label**: The first instruction MUST be a LABEL with label="entry".
2. **Registers**: Use sequential numbering: %0, %1, %2, ...
3. **Labels**: Use descriptive names with underscores: entry, func_factorial_0, if_true_1, while_cond_2, etc.
4. **Function definitions**: Emit BRANCH to skip over the body, then LABEL for the function, \
SYMBOLIC instructions for parameters (with "param:name" hints), the body, an implicit RETURN None, \
then the end LABEL. After the end label, STORE_VAR the function reference as "<function:name@label>".
5. **Class definitions**: Similar skip pattern. Store as "<class:name@label>".
6. **For loops**: Lower to index-based iteration: init index=0, compute len, loop condition (index < len), \
LOAD_INDEX for element, body, increment index, BRANCH back.
7. **While loops**: LABEL for condition, compute condition, BRANCH_IF to body/end, body, BRANCH back.
8. **If/elif/else**: Compute condition, BRANCH_IF to true/false labels, bodies with BRANCH to end.

## Output format

Return a JSON array of instruction objects. Example:
```json
[
  {"opcode": "LABEL", "result_reg": null, "operands": [], "label": "entry", "source_location": null},
  {"opcode": "CONST", "result_reg": "%0", "operands": ["5"], "label": null, "source_location": "1:0"},
  {"opcode": "STORE_VAR", "result_reg": null, "operands": ["x", "%0"], "label": null, "source_location": "1:0"}
]
```

Return ONLY the JSON array. No markdown fences. No explanation text outside the array.
"""

    USER_PROMPT_TEMPLATE = (
        "Lower the following {language} source code into IR instructions:\n\n{source}"
    )


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM response text."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1 :] if first_newline != -1 else text[3:]
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return text.strip()


def _parse_single_instruction(raw: dict[str, Any]) -> IRInstruction:
    """Map a raw dict from the LLM response to an IRInstruction."""
    opcode_str = raw.get("opcode", "")
    try:
        opcode = Opcode(opcode_str)
    except ValueError as exc:
        raise IRParsingError(f"Unknown opcode: {opcode_str!r}") from exc

    return IRInstruction(
        opcode=opcode,
        result_reg=raw.get("result_reg"),
        operands=raw.get("operands", []),
        label=raw.get("label"),
        source_location=raw.get("source_location"),
    )


def _repair_json(text: str) -> str:
    """Attempt to repair common JSON issues from smaller LLMs.

    Fixes: JS-style // comments, trailing commas before ] or },
    and truncated responses (truncates to last complete JSON object).
    """
    import re

    # Strip // line comments (common with smaller models)
    text = re.sub(r"//[^\n]*", "", text)

    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # If response was truncated (no closing ]), find last complete object
    stripped = text.strip()
    if not stripped.endswith("]"):
        logger.warning("JSON appears truncated, finding last complete element")
        last_brace = stripped.rfind("}")
        if last_brace > 0:
            text = stripped[: last_brace + 1] + "\n]"

    # Try to find the outermost JSON array even if there's trailing garbage
    bracket_depth = 0
    last_valid_end = -1
    for i, ch in enumerate(text):
        if ch == "[":
            bracket_depth += 1
        elif ch == "]":
            bracket_depth -= 1
            if bracket_depth == 0:
                last_valid_end = i + 1
                break

    if last_valid_end > 0:
        text = text[:last_valid_end]

    return text


def _parse_ir_response(raw_text: str) -> list[IRInstruction]:
    """Parse the LLM's raw text response into a list of IRInstructions."""
    cleaned = _strip_markdown_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Initial JSON parse failed, attempting repair")
        repaired = _repair_json(cleaned)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            logger.error("JSON repair also failed. Raw response:\n%s", raw_text[:2000])
            raise IRParsingError(
                f"Failed to parse LLM response as JSON: {exc}"
            ) from exc

    if not isinstance(data, list):
        raise IRParsingError(f"Expected JSON array, got {type(data).__name__}")

    return [_parse_single_instruction(item) for item in data]


def _validate_ir(instructions: list[IRInstruction]) -> list[IRInstruction]:
    """Validate and fix up the IR instruction list.

    - Ensures the list is non-empty
    - Ensures the first instruction is a LABEL with label="entry"
    """
    if not instructions:
        raise IRParsingError("LLM returned an empty instruction list")

    first = instructions[0]
    has_entry_label = (
        first.opcode == Opcode.LABEL and first.label == constants.CFG_ENTRY_LABEL
    )

    if not has_entry_label:
        logger.warning("LLM response missing entry label — auto-prepending")
        entry_label = IRInstruction(
            opcode=Opcode.LABEL,
            label=constants.CFG_ENTRY_LABEL,
        )
        instructions = [entry_label] + instructions

    return instructions


class LLMFrontend(Frontend):
    """Frontend that uses an LLM to lower source code directly to IR.

    Ignores the tree-sitter AST (tree param) — works from raw source only.
    """

    def __init__(self, llm_client: LLMClient, language: str = "python"):
        self._llm_client = llm_client
        self._language = language

    def lower(self, tree: Any, source: bytes) -> list[IRInstruction]:
        """Lower source code to IR via LLM.

        Args:
            tree: Ignored (kept for Frontend ABC compatibility).
            source: Raw source code bytes.

        Returns:
            List of IR instructions.
        """
        source_text = source.decode("utf-8") if isinstance(source, bytes) else source
        logger.info(
            "LLMFrontend: lowering %d chars of %s source",
            len(source_text),
            self._language,
        )

        user_message = LLMFrontendPrompts.USER_PROMPT_TEMPLATE.format(
            language=self._language,
            source=source_text,
        )

        raw_response = self._llm_client.complete(
            system_prompt=LLMFrontendPrompts.SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=4096,
        )

        logger.debug("LLM raw response length: %d chars", len(raw_response))

        instructions = _parse_ir_response(raw_response)
        instructions = _validate_ir(instructions)

        logger.info("LLMFrontend: produced %d IR instructions", len(instructions))
        return instructions
