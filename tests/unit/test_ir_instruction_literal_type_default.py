import inspect

from interpreter.ir import IRInstruction
from tests.covers import covers, NotLanguageFeature


class TestIRInstructionLiteralTypeDefault:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_literal_type_defaults_to_empty_string(self):
        sig = inspect.signature(IRInstruction)
        assert sig.parameters["literal_type"].default == ""
