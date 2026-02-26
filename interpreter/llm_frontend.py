"""LLM-based frontend — sends raw source to an LLM to produce IR instructions."""

from __future__ import annotations

import json
import logging
from typing import Any

from .frontend import Frontend
from .ir import NO_SOURCE_LOCATION, IRInstruction, Opcode
from .llm_client import LLMClient
from . import constants

logger = logging.getLogger(__name__)


class IRParsingError(Exception):
    """Raised when the LLM response cannot be parsed into valid IR."""

    pass


class LLMFrontendPrompts:
    """Prompt templates for LLM-based IR lowering."""

    SYSTEM_PROMPT = """\
You are a compiler frontend. Lower source code into flattened three-address code (TAC) IR.

## Instruction format

Each instruction is a JSON object:
{"opcode": "OPCODE", "result_reg": "%N" or null, "operands": [...], "label": "..." or null, "source_location": null}

Registers are sequential: %0, %1, %2, ...
Labels use underscores: entry, func_fib_0, if_true_1, end_fib_2, etc.

## Opcodes

Value producers (result_reg is set):
- CONST: operands=[value_string]. Strings must include quotes: ["\\\"Alice\\\""]
- LOAD_VAR: operands=[var_name]
- LOAD_FIELD: operands=[obj_reg, field_name]
- LOAD_INDEX: operands=[obj_reg, index_reg]
- NEW_OBJECT: operands=[type_name]
- NEW_ARRAY: operands=[type_name, size_reg]
- BINOP: operands=[op, lhs_reg, rhs_reg]
- UNOP: operands=[op, operand_reg]
- CALL_FUNCTION: operands=[func_name, arg1, arg2, ...]. Use for ALL calls: named functions AND constructors
- CALL_METHOD: operands=[obj_reg, method_name, arg1, ...]
- CALL_UNKNOWN: operands=[target_reg, arg1, ...]

Consumers / control flow (result_reg is null):
- STORE_VAR: operands=[var_name, value_reg]
- STORE_FIELD: operands=[obj_reg, field_name, value_reg]
- STORE_INDEX: operands=[obj_reg, index_reg, value_reg]
- BRANCH_IF: operands=[cond_reg], label="true_label,false_label"
- BRANCH: label=target_label
- RETURN: operands=[value_reg]
- THROW: operands=[value_reg]

Special:
- SYMBOLIC: operands=["param:name"]. Declares a function parameter
- LABEL: label=label_name. Marks a branch target

## CRITICAL patterns — follow exactly

### Function definition pattern

For `def foo(a, b): ...body... return expr`:

1. BRANCH to end_foo_N (skip over body in linear flow)
2. LABEL func_foo_M (function entry point)
3. For EACH parameter: SYMBOLIC "param:name" → STORE_VAR name %reg
4. ...body instructions...
5. CONST "None" → RETURN %reg (implicit return at end of function)
6. LABEL end_foo_N
7. CONST "<function:foo@func_foo_M>" → STORE_VAR foo %reg

The STORE_VAR after the end label registers the function by name. The value MUST be \
"<function:NAME@FUNC_LABEL>" where NAME is the function name and FUNC_LABEL is the \
label from step 2.

### Class definition pattern

For `class Cls: def __init__(self, x): ...`:

1. BRANCH to end_class_Cls_N (skip over class body)
2. LABEL class_Cls_M (class entry point)
3. ...nested function definitions for methods (each using the function pattern above)...
4. LABEL end_class_Cls_N
5. CONST "<class:Cls@class_Cls_M>" → STORE_VAR Cls %reg

Methods inside a class use the EXACT same function definition pattern. The __init__ \
method must be named exactly __init__.

### Constructor calls

To call a constructor like `obj = Cls(arg1, arg2)`, use CALL_FUNCTION:
  CALL_FUNCTION Cls %arg1 %arg2 → STORE_VAR obj %result

Do NOT use NEW_OBJECT + CALL_METHOD for constructors. Use CALL_FUNCTION with the class name.

### Method calls

To call a method like `obj.method(arg)`:
  LOAD_VAR obj → %obj_reg
  CALL_METHOD %obj_reg method %arg_reg → %result_reg

### If/elif/else

  ...compute condition...
  BRANCH_IF %cond if_true_N,if_false_N (or if_true_N,if_end_N when no else)
  LABEL if_true_N
  ...true body...
  BRANCH if_end_N
  LABEL if_false_N
  ...false body (or elif chain)...
  BRANCH if_end_N
  LABEL if_end_N

## Full example: function with if/else

Source:
```
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
result = fib(6)
```

IR:
[
  {"opcode":"LABEL","result_reg":null,"operands":[],"label":"entry","source_location":null},
  {"opcode":"BRANCH","result_reg":null,"operands":[],"label":"end_fib_1","source_location":null},
  {"opcode":"LABEL","result_reg":null,"operands":[],"label":"func_fib_0","source_location":null},
  {"opcode":"SYMBOLIC","result_reg":"%0","operands":["param:n"],"label":null,"source_location":null},
  {"opcode":"STORE_VAR","result_reg":null,"operands":["n","%0"],"label":null,"source_location":null},
  {"opcode":"LOAD_VAR","result_reg":"%1","operands":["n"],"label":null,"source_location":null},
  {"opcode":"CONST","result_reg":"%2","operands":["1"],"label":null,"source_location":null},
  {"opcode":"BINOP","result_reg":"%3","operands":["<=","%1","%2"],"label":null,"source_location":null},
  {"opcode":"BRANCH_IF","result_reg":null,"operands":["%3"],"label":"if_true_2,if_end_3","source_location":null},
  {"opcode":"LABEL","result_reg":null,"operands":[],"label":"if_true_2","source_location":null},
  {"opcode":"LOAD_VAR","result_reg":"%4","operands":["n"],"label":null,"source_location":null},
  {"opcode":"RETURN","result_reg":null,"operands":["%4"],"label":null,"source_location":null},
  {"opcode":"BRANCH","result_reg":null,"operands":[],"label":"if_end_3","source_location":null},
  {"opcode":"LABEL","result_reg":null,"operands":[],"label":"if_end_3","source_location":null},
  {"opcode":"LOAD_VAR","result_reg":"%5","operands":["n"],"label":null,"source_location":null},
  {"opcode":"CONST","result_reg":"%6","operands":["1"],"label":null,"source_location":null},
  {"opcode":"BINOP","result_reg":"%7","operands":["-","%5","%6"],"label":null,"source_location":null},
  {"opcode":"CALL_FUNCTION","result_reg":"%8","operands":["fib","%7"],"label":null,"source_location":null},
  {"opcode":"LOAD_VAR","result_reg":"%9","operands":["n"],"label":null,"source_location":null},
  {"opcode":"CONST","result_reg":"%10","operands":["2"],"label":null,"source_location":null},
  {"opcode":"BINOP","result_reg":"%11","operands":["-","%9","%10"],"label":null,"source_location":null},
  {"opcode":"CALL_FUNCTION","result_reg":"%12","operands":["fib","%11"],"label":null,"source_location":null},
  {"opcode":"BINOP","result_reg":"%13","operands":["+","%8","%12"],"label":null,"source_location":null},
  {"opcode":"RETURN","result_reg":null,"operands":["%13"],"label":null,"source_location":null},
  {"opcode":"CONST","result_reg":"%14","operands":["None"],"label":null,"source_location":null},
  {"opcode":"RETURN","result_reg":null,"operands":["%14"],"label":null,"source_location":null},
  {"opcode":"LABEL","result_reg":null,"operands":[],"label":"end_fib_1","source_location":null},
  {"opcode":"CONST","result_reg":"%15","operands":["<function:fib@func_fib_0>"],"label":null,"source_location":null},
  {"opcode":"STORE_VAR","result_reg":null,"operands":["fib","%15"],"label":null,"source_location":null},
  {"opcode":"CONST","result_reg":"%16","operands":["6"],"label":null,"source_location":null},
  {"opcode":"CALL_FUNCTION","result_reg":"%17","operands":["fib","%16"],"label":null,"source_location":null},
  {"opcode":"STORE_VAR","result_reg":null,"operands":["result","%17"],"label":null,"source_location":null}
]

## Rules

- The first instruction is always LABEL "entry"
- Every expression is flattened into registers. No nested expressions
- Every function parameter needs SYMBOLIC + STORE_VAR (both instructions)
- Functions end with an implicit CONST "None" + RETURN
- String literals include quotes in the operand: ["\\\"hello\\\""]
- Numeric literals are strings: ["42"], ["3.14"]
- Boolean literals: ["True"], ["False"]. None: ["None"]
- Do NOT add comments in the JSON
- Return ONLY the JSON array. No markdown fences. No text outside the array
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
        source_location=NO_SOURCE_LOCATION,
    )


def _parse_ir_response(raw_text: str) -> list[IRInstruction]:
    """Parse the LLM's raw text response into a list of IRInstructions."""
    cleaned = _strip_markdown_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed. Raw response:\n%s", raw_text[:2000])
        raise IRParsingError(f"Failed to parse LLM response as JSON: {exc}") from exc

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

    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_MAX_RETRIES = 3

    def __init__(
        self,
        llm_client: LLMClient,
        language: str = "python",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self._llm_client = llm_client
        self._language = language
        self._max_tokens = max_tokens
        self._max_retries = max_retries

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

        last_error: IRParsingError | None = None
        for attempt in range(1, self._max_retries + 1):
            raw_response = self._llm_client.complete(
                system_prompt=LLMFrontendPrompts.SYSTEM_PROMPT,
                user_message=user_message,
                max_tokens=self._max_tokens,
            )

            logger.debug("LLM raw response length: %d chars", len(raw_response))

            try:
                instructions = _parse_ir_response(raw_response)
            except IRParsingError as exc:
                last_error = exc
                logger.warning(
                    "LLMFrontend: parse attempt %d/%d failed: %s",
                    attempt,
                    self._max_retries,
                    exc,
                )
                continue

            instructions = _validate_ir(instructions)
            logger.info("LLMFrontend: produced %d IR instructions", len(instructions))
            return instructions

        raise last_error  # type: ignore[misc]
