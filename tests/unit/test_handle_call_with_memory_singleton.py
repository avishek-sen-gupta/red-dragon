"""Unit test: _handle_call_with_memory dispatches via singleton __init_params__."""

from interpreter.address import Address
from interpreter.cobol.features import CobolFeature
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import CallWithMemory
from interpreter.ir import CodeLabel
from interpreter.refs.func_ref import BoundFuncRef, FuncRef
from interpreter.register import Register
from interpreter.types.typed_value import typed
from interpreter.var_name import VarName
from interpreter.vm.vm_types import HeapObject, VMState
from tests.covers import covers


def _make_vm_with_singleton(program_id: str) -> VMState:
    """Build a minimal VMState with a singleton HeapObject in scope."""
    from interpreter.vm.vm_types import StackFrame

    pid_lower = program_id.lower()
    pid_upper = program_id.upper()

    proc_label = CodeLabel(f"func_{pid_lower}_0")
    init_params_label = CodeLabel(f"func_init_params_{pid_lower}_0")

    init_params_ref = BoundFuncRef(
        func_ref=FuncRef(name=FuncName(str(init_params_label)), label=init_params_label)
    )

    singleton = HeapObject(
        fields={
            FieldName("__init_params__"): typed(init_params_ref),
            FieldName("ws_handle"): typed(Address("obj_0")),
            FieldName("run"): typed(
                BoundFuncRef(
                    func_ref=FuncRef(name=FuncName(str(proc_label)), label=proc_label)
                )
            ),
        }
    )

    singleton_addr = Address("obj_1")
    singleton_var = VarName(f"__prog_{pid_upper}")

    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=FuncName("<main>")))
    vm._heap[singleton_addr] = singleton
    vm.call_stack[0].local_vars[singleton_var] = typed(singleton_addr)

    params_addr = Address("obj_2")
    vm.call_stack[0].local_vars[VarName("__ws_region")] = typed(params_addr)

    return vm


@covers(CobolFeature.CALL_USING)
def test_call_with_memory_dispatches_to_init_params():
    """Handler must dispatch to func_init_params_<pid>_0, not func_<pid>_0 directly."""
    from dataclasses import replace

    from interpreter.cfg import CFG, BasicBlock
    from interpreter.handlers.calls import _handle_call_with_memory
    from interpreter.instructions import Return_
    from interpreter.vm.executor import _default_handler_context

    pid = "SUBPROG"
    pid_lower = pid.lower()
    init_params_label = CodeLabel(f"func_init_params_{pid_lower}_0")
    proc_label = CodeLabel(f"func_{pid_lower}_0")

    cfg = CFG(
        blocks={
            init_params_label: BasicBlock(
                label=init_params_label, instructions=[Return_()]
            ),
            proc_label: BasicBlock(label=proc_label, instructions=[Return_()]),
        }
    )

    vm = _make_vm_with_singleton(pid)
    params_reg = Register("%r0")
    results_reg = Register("%r1")
    ws_addr = Address("obj_10")
    vm.current_frame.registers[params_reg] = typed(ws_addr)
    vm.current_frame.registers[results_reg] = typed(ws_addr)

    inst = CallWithMemory(
        func_name=FuncName(pid),
        params_reg=params_reg,
        results_reg=results_reg,
    )

    ctx = replace(_default_handler_context(), cfg=cfg, current_label=CodeLabel("entry"))
    result = _handle_call_with_memory(inst, vm, ctx)

    assert result.handled
    assert result.update.next_label == init_params_label
