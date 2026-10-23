# pyright: standard
"""The frontend defines each IR function its lowerings called exactly once, after the entry function, and lists it in the function symbol table; a program that calls none defines none; a function called only from another function's body is defined too."""

from pathlib import Path

from hlasm_asg.program.hlasm_program import HlasmProgram
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.hlasm_frontend import HlasmFrontend
from interpreter.hlasm.ir_function import IrFunction, define_called
from interpreter.instructions import Label_
from tests.covers import NotLanguageFeature, covers

FIXTURES = Path(__file__).parent / "fixtures"


def _defined(name: str) -> tuple[list[str], list[str]]:
    program = HlasmProgram.model_validate_json((FIXTURES / name).read_text())
    frontend = HlasmFrontend(program)
    labels = [
        str(i.label)
        for i in frontend.lower(b"")
        if isinstance(i, Label_) and str(i.label).startswith("func_")
    ]
    return labels, sorted(str(label) for label in frontend.func_symbol_table)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_called_functions_are_defined_once_and_others_never():
    assert {
        "dfp": _defined("dfp_program.json"),
        "none": _defined("seed_program.json"),
    } == {
        "dfp": (
            [
                "func_hello_0",
                "func___hlasm_dfp_decode_long_0",
                "func___hlasm_dfp_encode_long_0",
            ],
            [
                "func___hlasm_dfp_decode_long_0",
                "func___hlasm_dfp_encode_long_0",
                "func_hello_0",
            ],
        ),
        "none": (["func_hello_0"], ["func_hello_0"]),
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_function_called_from_another_function_body_is_defined_once():
    inner = IrFunction("inner", 1, lambda emitter, p: p[0])
    outer = IrFunction(
        "outer",
        1,
        lambda emitter, p: inner.call(emitter, (inner.call(emitter, (p[0],)),)),
    )
    emitter = HlasmEmitter()
    outer.call(emitter, (emitter.int_(1),))
    outer.call(emitter, (emitter.int_(2),))
    defined = define_called(emitter)
    labels = [str(i.label) for i in emitter.instructions() if isinstance(i, Label_)]

    assert ([f.name for f in defined], labels) == (
        ["outer", "inner"],
        ["func_outer_0", "end_outer_1", "func_inner_0", "end_inner_1"],
    )
