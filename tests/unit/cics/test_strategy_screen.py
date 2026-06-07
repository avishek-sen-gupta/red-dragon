"""Verify screen builtins are registered when BmsLoader + queues are provided."""

import queue

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.strategy import CicsLoweringStrategy
from interpreter.cics.bms.loader import BmsLoader
from interpreter.func_name import FuncName


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_strategy_registers_screen_builtins():
    from interpreter.vm.builtins import Builtins

    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()
    loader = BmsLoader(maps_dir=None)
    CicsLoweringStrategy(
        context_holder=[None],
        result_holder=[None],
        bms_loader=loader,
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
        verb="SEND MAP", options={"MAP": "COSGN0A", "MAPSET": "COSGN00"}
    )
    strategy = CicsLoweringStrategy(context_holder=[None], result_holder=[None])
    strategy.lower(ctx, stmt, materialised=None)
    calls = [i for i in ctx.emitted if isinstance(i, CallFunction)]
    assert any(c.func_name == FuncName("__cics_send_map") for c in calls)
