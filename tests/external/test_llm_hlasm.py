"""External test: LLM frontend lowers HLASM to IR, VM executes it.

HLASM (IBM High Level Assembler) has no tree-sitter frontend. The LLM
frontend sends raw source to an LLM constrained by the IR schema, then
the deterministic VM executes the resulting IR.

Ported from scripts/demo_hlasm.py with sum=55 verification.

Run with: poetry run python -m pytest -m external tests/external/test_llm_hlasm.py -v
"""

import pytest

from interpreter.cfg import build_cfg
from interpreter.llm.llm_client import get_llm_client
from interpreter.llm.llm_frontend import LLMFrontend
from interpreter.registry import build_registry
from interpreter.run import execute_cfg
from interpreter.run_types import VMConfig
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import SymbolicValue

# Simple HLASM: compute sum = 1 + 2 + 3 + ... + 10
_HLASM_SUM = """\
SUMLOOP  CSECT
         SR    R3,R3          Clear accumulator (sum = 0)
         LA    R4,1           Load counter = 1
         LA    R5,10          Load limit = 10
LOOP     AR    R3,R4          sum = sum + counter
         LA    R4,1(R4)       counter = counter + 1
         CR    R4,R5          Compare counter to limit
         BNH   LOOP           Branch if counter <= limit
         ST    R3,SUM         Store result
         BR    R14            Return
SUM      DS    F              Result storage
         END   SUMLOOP
"""


def _get_locals(vm):
    frame = vm.call_stack[0]
    return {
        str(k): v.value if isinstance(v, TypedValue) else v
        for k, v in frame.local_vars.items()
    }


@pytest.mark.external
class TestHLASMLowering:
    def test_llm_produces_valid_ir(self):
        """LLM frontend can lower HLASM to valid IR instructions."""
        llm_client = get_llm_client(provider="claude")
        frontend = LLMFrontend(llm_client=llm_client, language="hlasm")
        instructions = frontend.lower(_HLASM_SUM.encode("utf-8"))
        assert len(instructions) > 0

    def test_hlasm_sum_produces_55(self):
        """HLASM sum of 1..10 executes to 55 in at least one variable."""
        llm_client = get_llm_client(provider="claude")
        frontend = LLMFrontend(llm_client=llm_client, language="hlasm")
        instructions = frontend.lower(_HLASM_SUM.encode("utf-8"))

        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)
        config = VMConfig(max_steps=500, source_language="hlasm")
        vm, stats = execute_cfg(cfg, cfg.entry, registry, config)

        locals_ = _get_locals(vm)
        # The expected value 55 should appear in at least one variable
        numeric_vals = [
            v
            for v in locals_.values()
            if isinstance(v, (int, float)) and not isinstance(v, SymbolicValue)
        ]
        assert (
            55 in numeric_vals or 55.0 in numeric_vals
        ), f"Expected 55 in some variable, got: {locals_}"
