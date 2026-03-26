"""Tests for VMState — data_layout field and serialization."""

from interpreter.var_name import VarName
from interpreter.vm.vm_types import VMState


class TestVMStateDataLayout:
    def test_data_layout_default_empty(self):
        """VMState has empty data_layout by default."""
        vm = VMState()
        assert vm.data_layout == {}

    def test_data_layout_in_to_dict_when_populated(self):
        """to_dict() includes data_layout when it contains entries."""
        vm = VMState()
        vm.data_layout = {
            "WS-A": {
                "offset": 0,
                "length": 3,
                "category": "ZONED_DECIMAL",
                "total_digits": 3,
                "decimal_digits": 0,
                "signed": False,
            }
        }
        result = vm.to_dict()
        assert VarName("data_layout") in result
        assert result[VarName("data_layout")]["WS-A"]["offset"] == 0
        assert result[VarName("data_layout")]["WS-A"]["length"] == 3

    def test_data_layout_omitted_from_to_dict_when_empty(self):
        """to_dict() omits data_layout when empty (sparse serialization)."""
        vm = VMState()
        result = vm.to_dict()
        assert VarName("data_layout") not in result
