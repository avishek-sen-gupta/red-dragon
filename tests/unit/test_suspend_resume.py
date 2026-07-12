"""Cooperative suspend/resume primitive (run_resumable / resume / Suspend).

Exercises the core continuation mechanism exhaustively:
  * basic suspend → resume with an injected value, working storage persists;
  * resume FROM SCRATCH — serialize the continuation, throw away and rebuild the
    whole pipeline (fresh CFG + registry), resume against it;
  * multi-suspend (a program that suspends more than once in one execution);
  * multi-shot — fork a suspended continuation and resume it twice independently
    (a property a thread/greenlet fundamentally cannot provide).
Nested-CALL suspension lives in test_suspend_resume_calls.py.
"""

from __future__ import annotations

import copy
import pickle

from interpreter.ir import CodeLabel, Opcode
from interpreter.register import Register
from interpreter.run import (
    Completed,
    Suspended,
    initial_vm_state,
    resume,
    run_resumable,
)
from interpreter.types.typed_value import unwrap
from interpreter.var_name import VarName
from tests.unit.cfg_helpers import build_simple_cfg, make_instructions


def _local(vm, name: str):
    return unwrap(vm.current_frame.local_vars[VarName(name)])


# A program that stores working state, yields 42, then on resume adds the
# injected value to the stored state and returns it:
#   saved = 10 ; yield 42 ; result = injected + saved ; return result
def _save_yield_add_program():
    return make_instructions(
        (Opcode.LABEL, {"label": CodeLabel("entry")}),
        (Opcode.CONST, {"result_reg": Register("%0"), "operands": [10]}),
        (Opcode.STORE_VAR, {"operands": ["saved", "%0"]}),
        (Opcode.CONST, {"result_reg": Register("%1"), "operands": [42]}),
        (Opcode.SUSPEND, {"result_reg": Register("%2"), "operands": ["%1"]}),
        (Opcode.LOAD_VAR, {"result_reg": Register("%3"), "operands": ["saved"]}),
        (Opcode.BINOP, {"result_reg": Register("%4"), "operands": ["+", "%2", "%3"]}),
        (Opcode.STORE_VAR, {"operands": ["result", "%4"]}),
        (Opcode.RETURN, {"operands": ["%4"]}),
    )


def test_basic_suspend_then_resume():
    cfg, registry = build_simple_cfg(_save_yield_add_program())

    out = run_resumable(
        cfg,
        "entry",
        registry,
        vm=initial_vm_state(),
    )
    assert isinstance(out, Suspended)
    assert out.value == 42  # the yielded payload

    done = resume(cfg, registry, out.state, 99)  # inject 99
    assert isinstance(done, Completed)
    assert _local(done.vm, "result") == 109  # 99 (injected) + 10 (persisted)


def test_resume_from_scratch_rebuilds_entire_pipeline():
    # Run to the suspend on one pipeline...
    cfg1, registry1 = build_simple_cfg(_save_yield_add_program())
    out = run_resumable(
        cfg1,
        "entry",
        registry1,
        vm=initial_vm_state(),
    )
    assert isinstance(out, Suspended)

    # ...serialize the continuation, then discard EVERYTHING (cfg1/registry1) and
    # rebuild a fresh pipeline from source, and resume against it.
    # (pickle here round-trips our OWN ExecutionState produced moments earlier —
    # trusted, self-generated data, not an external payload.)
    blob = pickle.dumps(out.state)
    del cfg1, registry1, out

    cfg2, registry2 = build_simple_cfg(_save_yield_add_program())  # fresh program
    state2 = pickle.loads(blob)
    done = resume(cfg2, registry2, state2, 99)
    assert isinstance(done, Completed)
    assert _local(done.vm, "result") == 109


def test_multiple_suspends_in_one_execution():
    # yield 1 ; yield (injected) ; result = (second injected) ; return
    cfg, registry = build_simple_cfg(
        make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.CONST, {"result_reg": Register("%0"), "operands": [1]}),
            (Opcode.SUSPEND, {"result_reg": Register("%1"), "operands": ["%0"]}),
            (Opcode.SUSPEND, {"result_reg": Register("%2"), "operands": ["%1"]}),
            (Opcode.STORE_VAR, {"operands": ["result", "%2"]}),
            (Opcode.RETURN, {"operands": ["%2"]}),
        )
    )

    a = run_resumable(
        cfg,
        "entry",
        registry,
        vm=initial_vm_state(),
    )
    assert isinstance(a, Suspended) and a.value == 1

    b = resume(cfg, registry, a.state, 10)  # inject 10 -> %1; second SUSPEND yields it
    assert isinstance(b, Suspended) and b.value == 10

    c = resume(cfg, registry, b.state, 20)  # inject 20 -> %2
    assert isinstance(c, Completed)
    assert _local(c.vm, "result") == 20


def test_multi_shot_fork_resume_twice_independently():
    cfg, registry = build_simple_cfg(_save_yield_add_program())
    out = run_resumable(
        cfg,
        "entry",
        registry,
        vm=initial_vm_state(),
    )
    assert isinstance(out, Suspended)

    # Fork the continuation: two independent deep copies resumed with different
    # injected values yield independent results. (One-shot greenlets/threads
    # cannot do this — the continuation here is pure, copyable data.)
    fork_a = copy.deepcopy(out.state)
    fork_b = copy.deepcopy(out.state)

    done_a = resume(cfg, registry, fork_a, 99)
    done_b = resume(cfg, registry, fork_b, 1000)
    assert isinstance(done_a, Completed) and isinstance(done_b, Completed)
    assert _local(done_a.vm, "result") == 109
    assert _local(done_b.vm, "result") == 1010
