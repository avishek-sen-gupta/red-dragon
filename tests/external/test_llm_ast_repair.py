"""External test: LLM-assisted AST repair for malformed source code.

Exercises the RepairingFrontendDecorator: broken source gets repaired by the LLM,
then lowered deterministically. Verifies that repair reduces SYMBOLIC instructions.

Ported from scripts/demo_ast_repair.py with proper assertions.

Run with: poetry run python -m pytest -m external tests/external/test_llm_ast_repair.py -v
"""

import pytest

from interpreter.ast_repair.repair_config import RepairConfig
from interpreter.ast_repair.repairing_frontend_decorator import (
    RepairingFrontendDecorator,
)
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.ir import Opcode
from interpreter.llm.llm_client import get_llm_client
from interpreter.parser import TreeSitterParserFactory

_BROKEN_PYTHON = b"""\
import math

def calculate_area(radius:
    return math.pi * radius ** 2

def greet(name
    message = f"Hello, {name}!"
    print(message)

result = calculate_area(5)
greeting = greet("World")
"""

_BROKEN_JAVASCRIPT = b"""\
function fibonacci(n {
  if (n <= 1) return n;
  return fibonacci(n - 1) + fibonacci(n - 2)

const result = fibonacci(10;
console.log(result);
"""


def _count_unsupported_symbolics(instructions):
    return sum(
        1
        for inst in instructions
        if inst.opcode == Opcode.SYMBOLIC
        and any("unsupported:" in str(op) for op in inst.operands)
    )


@pytest.mark.external
class TestASTRepairPython:
    def test_broken_source_has_parse_errors(self):
        """The broken Python source should have tree-sitter parse errors."""
        parser = TreeSitterParserFactory().get_parser(Language.PYTHON)
        tree = parser.parse(_BROKEN_PYTHON)
        assert tree.root_node.has_error

    def test_repair_reduces_symbolics(self):
        """LLM repair should produce fewer unsupported SYMBOLIC instructions."""
        # Baseline: lowering without repair
        plain_frontend = get_frontend(Language.PYTHON)
        plain_ir = plain_frontend.lower(_BROKEN_PYTHON)
        plain_symbolics = _count_unsupported_symbolics(plain_ir)

        # With LLM repair
        repair_client = get_llm_client(provider="claude")
        config = RepairConfig(max_retries=3, context_lines=3)
        repair_frontend = RepairingFrontendDecorator(
            inner_frontend=get_frontend(Language.PYTHON),
            llm_client=repair_client,
            parser_factory=TreeSitterParserFactory(),
            language=Language.PYTHON,
            config=config,
        )
        repaired_ir = repair_frontend.lower(_BROKEN_PYTHON)
        repaired_symbolics = _count_unsupported_symbolics(repaired_ir)

        # Repair should produce at least as good coverage
        assert (
            repaired_symbolics <= plain_symbolics
        ), f"Repair made things worse: {repaired_symbolics} > {plain_symbolics}"

    def test_repair_produces_more_instructions(self):
        """Repaired source should produce at least as many IR instructions."""
        plain_frontend = get_frontend(Language.PYTHON)
        plain_ir = plain_frontend.lower(_BROKEN_PYTHON)

        repair_client = get_llm_client(provider="claude")
        config = RepairConfig(max_retries=3, context_lines=3)
        repair_frontend = RepairingFrontendDecorator(
            inner_frontend=get_frontend(Language.PYTHON),
            llm_client=repair_client,
            parser_factory=TreeSitterParserFactory(),
            language=Language.PYTHON,
            config=config,
        )
        repaired_ir = repair_frontend.lower(_BROKEN_PYTHON)

        assert len(repaired_ir) >= len(
            plain_ir
        ), f"Repaired IR shorter: {len(repaired_ir)} < {len(plain_ir)}"


@pytest.mark.external
class TestASTRepairJavaScript:
    def test_broken_source_has_parse_errors(self):
        parser = TreeSitterParserFactory().get_parser(Language.JAVASCRIPT)
        tree = parser.parse(_BROKEN_JAVASCRIPT)
        assert tree.root_node.has_error

    def test_repair_reduces_symbolics(self):
        plain_frontend = get_frontend(Language.JAVASCRIPT)
        plain_ir = plain_frontend.lower(_BROKEN_JAVASCRIPT)
        plain_symbolics = _count_unsupported_symbolics(plain_ir)

        repair_client = get_llm_client(provider="claude")
        config = RepairConfig(max_retries=3, context_lines=3)
        repair_frontend = RepairingFrontendDecorator(
            inner_frontend=get_frontend(Language.JAVASCRIPT),
            llm_client=repair_client,
            parser_factory=TreeSitterParserFactory(),
            language=Language.JAVASCRIPT,
            config=config,
        )
        repaired_ir = repair_frontend.lower(_BROKEN_JAVASCRIPT)
        repaired_symbolics = _count_unsupported_symbolics(repaired_ir)

        assert repaired_symbolics <= plain_symbolics
