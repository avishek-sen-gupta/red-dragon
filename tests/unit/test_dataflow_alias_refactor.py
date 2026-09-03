"""GEN/KILL expressed via the alias relation, on name-equality locations."""

from interpreter.dataflow import compute_gen_kill, collect_all_definitions
from interpreter.cfg import build_cfg
from interpreter.instructions import Const, StoreVar
from interpreter.register import Register
from interpreter.var_name import VarName
from tests.covers import NotLanguageFeature, covers


def _cfg(instructions):
    return build_cfg(instructions)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_gen_keeps_only_the_last_write_of_a_variable():
    insts = [
        Const.int_(Register("%0"), 1),
        StoreVar(name=VarName("x"), value_reg=Register("%0")),
        Const.int_(Register("%1"), 2),
        StoreVar(name=VarName("x"), value_reg=Register("%1")),
    ]
    cfg = _cfg(insts)
    block = next(iter(cfg.blocks.values()))
    all_defs = collect_all_definitions(cfg)
    defs_by_var = {}
    for d in all_defs:
        defs_by_var.setdefault(d.variable.alias_key(), set()).add(d)

    gen, _kill = compute_gen_kill(block, all_defs, defs_by_var)
    x_defs = [d for d in gen if d.variable == VarName("x")]
    assert len(x_defs) == 1, "only the last write of x belongs in GEN"
    assert x_defs[0].instruction_index == 3
