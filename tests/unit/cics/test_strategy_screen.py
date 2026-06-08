"""Verify screen builtins are registered when the screen/input queues are provided."""

import queue

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.strategy import CicsLoweringStrategy
from interpreter.func_name import FuncName


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_strategy_registers_screen_builtins():
    from interpreter.vm.builtins import Builtins

    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()
    CicsLoweringStrategy(
        context_holder=[None],
        result_holder=[None],
        screen_queue=screen_q,
        input_queue=input_q,
    )
    assert FuncName("__cics_send_map") in Builtins.TABLE
    assert FuncName("__cics_receive_map") in Builtins.TABLE
    assert FuncName("__cics_send_text") in Builtins.TABLE


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_strategy_without_bms_still_constructs():
    # No bms_loader -> screen builtins simply not registered, no error.
    CicsLoweringStrategy(context_holder=[None], result_holder=[None])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_send_map_lowers_to_call_function():
    from interpreter.instructions import CallFunction
    from interpreter.cobol.cobol_statements import ExecCicsStatement
    from interpreter.cics.cics_parser import CicsOperand
    from interpreter.register import Register

    class _Ctx:
        def __init__(self):
            self.emitted = []
            self._n = 0

        def fresh_reg(self):
            self._n += 1
            return Register(f"%r{self._n}")

        def emit_inst(self, inst):
            self.emitted.append(inst)

    ctx = _Ctx()
    stmt = ExecCicsStatement(
        verb="SEND MAP",
        options={
            "MAP": CicsOperand("COSGN0A", True),
            "MAPSET": CicsOperand("COSGN00", True),
        },
    )
    strategy = CicsLoweringStrategy(context_holder=[None], result_holder=[None])
    strategy.lower(ctx, stmt, materialised=None)
    calls = [i for i in ctx.emitted if isinstance(i, CallFunction)]
    assert any(c.func_name == FuncName("__cics_send_map") for c in calls)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_send_map_lowering_passes_base_field_names():
    """SEND MAP resolves the FROM group's leaf fields, strips the O suffix,
    and passes the base names as a Const list arg (args[1])."""
    from interpreter.instructions import CallFunction, Const
    from interpreter.cobol.cobol_statements import ExecCicsStatement
    from interpreter.cics.cics_parser import CicsOperand
    from interpreter.cobol.data_layout import DataLayout, FieldLayout
    from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
    from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
    from interpreter.register import Register

    def _alpha(n):
        return CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC, total_digits=n
        )

    grp = DataLayout(
        fields={
            "USERIDO": FieldLayout(
                name="USERIDO", type_descriptor=_alpha(8), offset=12, byte_length=8
            ),
            "ERRMSGO": FieldLayout(
                name="ERRMSGO", type_descriptor=_alpha(78), offset=20, byte_length=78
            ),
        },
        offset=0,
        total_bytes=98,
    )
    ws = DataLayout(groups={"COSGN0AO": grp}, offset=0, total_bytes=98)
    empty = DataLayout()
    materialised = MaterialisedSectionedLayout(
        working_storage=(ws, Register("%ws")),
        linkage=(empty, Register("%lk")),
        local_storage=(empty, Register("%ls")),
    )

    class _Ctx:
        def __init__(self):
            self.emitted = []
            self._n = 0

        def fresh_reg(self):
            self._n += 1
            return Register(f"%r{self._n}")

        def emit_inst(self, inst):
            self.emitted.append(inst)
            return inst

        def group_leaf_names(self, group_name, mat):
            return mat.group_leaf_names(group_name)

    ctx = _Ctx()
    stmt = ExecCicsStatement(
        verb="SEND MAP",
        options={
            "MAP": CicsOperand("COSGN0A", True),
            "MAPSET": CicsOperand("COSGN00", True),
            "FROM": CicsOperand("COSGN0AO", False),
        },
    )
    strategy = CicsLoweringStrategy(context_holder=[None], result_holder=[None])
    strategy.lower(ctx, stmt, materialised=materialised)

    send_calls = [
        i
        for i in ctx.emitted
        if isinstance(i, CallFunction) and i.func_name == FuncName("__cics_send_map")
    ]
    assert len(send_calls) == 1
    call = send_calls[0]
    names_reg = call.args[1]
    consts = {i.result_reg: i.value for i in ctx.emitted if isinstance(i, Const)}
    assert consts[names_reg] == ["USERID", "ERRMSG"]
