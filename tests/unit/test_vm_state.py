"""Tests for VMState — declarations field and serialization."""

import copy

from interpreter.constants import FoundationTypeName
from interpreter.data_value import DataField, DataList, DataRecord, DataScalar
from interpreter.field_name import FieldName
from interpreter.instructions import Data
from interpreter.types.type_expr import scalar
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

    def test_deepcopy_shares_declarations_by_identity(self):
        amount = DataScalar(value=7, type_expr=scalar(FoundationTypeName.INT))
        field = DataField(name=FieldName("amount"), value=amount)
        record = DataRecord(fields=(field,))
        items = DataList(items=(record, amount))
        vm = VMState()
        vm.declarations = (Data(name=VarName("__layout"), value=items),)

        copied = copy.deepcopy(vm)

        assert (copied is vm, copied.declarations is vm.declarations) == (False, True)
        assert [copy.deepcopy(v) is v for v in (amount, field, record, items)] == [
            True,
            True,
            True,
            True,
        ]
