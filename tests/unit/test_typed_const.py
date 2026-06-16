# pyright: standard
"""Tests for typed Const factory classmethods (Task 2: required TypeExpr on Const)."""

import pytest

from tests.covers import NotLanguageFeature, covers
from interpreter.instructions import Const
from interpreter.types.type_expr import scalar, NULL
from interpreter.constants import FoundationTypeName
from interpreter.cfg import build_cfg
from interpreter.registry import build_registry
from interpreter.run import execute_cfg
from interpreter.run_types import VMConfig
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.types.typed_value import unwrap
from interpreter.instructions import Label_, Return_


def _run(const_inst: Const) -> object:
    instrs = [
        Label_(label=CodeLabel("entry")),
        const_inst,
        Return_(value_reg=const_inst.result_reg),
    ]
    cfg = build_cfg(instrs)
    vm, _ = execute_cfg(
        cfg, "entry", build_registry(instrs, cfg), VMConfig(max_steps=10)
    )
    return unwrap(vm.current_frame.registers.get(const_inst.result_reg))


class TestTypedConst:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_string_const_stays_string(self) -> None:
        c = Const.string(Register("%r"), "10")
        assert _run(c) == "10" and c.type_expr == scalar(FoundationTypeName.STRING)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_int_const_is_int(self) -> None:
        c = Const.int_(Register("%r"), 10)
        assert _run(c) == 10 and c.type_expr == scalar(FoundationTypeName.INT)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_null_const_has_null_type(self) -> None:
        c = Const.null_(Register("%r"))
        assert _run(c) is None and c.type_expr == NULL

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_raw_const_requires_type_expr(self) -> None:
        with pytest.raises(TypeError):
            Const(result_reg=Register("%r"), value="x")
