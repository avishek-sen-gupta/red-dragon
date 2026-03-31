from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Branch,
    CallFunction,
    Const,
    DeclVar,
    Label_,
    LoadVar,
    Return_,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

_CLS = "class_PrintStream_0"
_END_CLS = "end_class_PrintStream_1"
_PRINTLN_F = "func_println_2"
_PRINTLN_END = "end_println_3"
_PRINT_F = "func_print_4"
_PRINT_END = "end_print_5"

PRINT_STREAM_IR = (
    # ── declare PrintStream class ─────────────────────────────────────────────
    Label_(label=CodeLabel("entry_PrintStream")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("PrintStream"), value_reg=Register("%0")),
    # ── println(this, msg) → println(msg) ────────────────────────────────────
    Branch(label=CodeLabel(_PRINTLN_END)),
    Label_(label=CodeLabel(_PRINTLN_F)),
    Symbolic(result_reg=Register("%1"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%1")),
    Symbolic(result_reg=Register("%2"), hint="param:msg"),
    DeclVar(name=VarName("msg"), value_reg=Register("%2")),
    LoadVar(result_reg=Register("%3"), name=VarName("msg")),
    CallFunction(
        result_reg=Register("%4"),
        func_name=FuncName("println"),
        args=(Register("%3"),),
    ),
    Const(result_reg=Register("%5"), value="None"),
    Return_(value_reg=Register("%5")),
    Label_(label=CodeLabel(_PRINTLN_END)),
    Const(result_reg=Register("%6"), value=_PRINTLN_F),
    DeclVar(name=VarName("println"), value_reg=Register("%6")),
    # ── print(this, msg) → print(msg) ─────────────────────────────────────────
    Branch(label=CodeLabel(_PRINT_END)),
    Label_(label=CodeLabel(_PRINT_F)),
    Symbolic(result_reg=Register("%7"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%7")),
    Symbolic(result_reg=Register("%8"), hint="param:msg"),
    DeclVar(name=VarName("msg"), value_reg=Register("%8")),
    LoadVar(result_reg=Register("%9"), name=VarName("msg")),
    CallFunction(
        result_reg=Register("%10"),
        func_name=FuncName("print"),
        args=(Register("%9"),),
    ),
    Const(result_reg=Register("%11"), value="None"),
    Return_(value_reg=Register("%11")),
    Label_(label=CodeLabel(_PRINT_END)),
    Const(result_reg=Register("%12"), value=_PRINT_F),
    DeclVar(name=VarName("print"), value_reg=Register("%12")),
)

PRINT_STREAM_MODULE = ModuleUnit(
    path=Path("java/io/PrintStream.java"),
    language=Language.JAVA,
    ir=PRINT_STREAM_IR,
    exports=ExportTable(
        functions={
            FuncName("println"): CodeLabel(_PRINTLN_F),
            FuncName("print"): CodeLabel(_PRINT_F),
        },
        classes={
            ClassName("PrintStream"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
