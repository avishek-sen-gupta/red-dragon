"""Tests for VMState — declarations field and serialization."""

from interpreter.data_value import DataList
from interpreter.instructions import Data
from interpreter.var_name import VarName
from interpreter.vm.vm_types import VMState


class TestVMStateDeclarations:
    def test_declarations_default_empty(self):
        vm = VMState()
        assert vm.declarations == ()

    def test_declarations_in_to_dict_when_populated(self):
        vm = VMState()
        vm.declarations = (
            Data(name=VarName("__first"), value=DataList(())),
            Data(name=VarName("__second"), value=DataList(())),
        )
        assert vm.to_dict()["declarations"] == ["data __first", "data __second"]

    def test_declarations_omitted_from_to_dict_when_empty(self):
        vm = VMState()
        result = vm.to_dict()
        assert "declarations" not in result
