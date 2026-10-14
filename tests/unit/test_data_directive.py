"""A Data directive is stepped over by the VM and changes nothing."""

from interpreter.constants import FoundationTypeName
from interpreter.data_value import DataList, DataScalar
from interpreter.instructions import Data
from interpreter.ir import CodeLabel, Opcode
from interpreter.register import Register
from interpreter.run import execute_cfg, initial_vm_state
from interpreter.types.type_expr import scalar
from interpreter.types.typed_value import unwrap
from interpreter.var_name import VarName
from tests.covers import NotLanguageFeature, covers
from tests.unit.cfg_helpers import build_simple_cfg, make_instructions


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_data_directive_changes_nothing_when_the_program_runs():
    label, *rest = make_instructions(
        (Opcode.LABEL, {"label": CodeLabel("entry")}),
        (Opcode.CONST, {"result_reg": Register("%0"), "operands": [42]}),
        (Opcode.STORE_VAR, {"operands": ["x", "%0"]}),
        (Opcode.RETURN, {"operands": ["%0"]}),
    )
    directive = Data(
        name=VarName("PROG"),
        value=DataList((DataScalar(1, scalar(FoundationTypeName.INT)),)),
    )
    cfg, registry = build_simple_cfg([label, directive, *rest])
    vm, stats = execute_cfg(cfg, "entry", registry, vm=initial_vm_state())
    assert unwrap(vm.current_frame.local_vars[VarName("x")]) == 42
    assert stats.llm_calls == 0
