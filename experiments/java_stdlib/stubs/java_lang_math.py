from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
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
from interpreter.operator_kind import BinopKind
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

# ── Labels ───────────────────────────────────────────────────────────────────
_CLS = "class_Math_0"
_END_CLS = "end_class_Math_1"
_SQRT_F = "func_sqrt_2"
_SQRT_END = "end_sqrt_3"
_ABS_F = "func_abs_4"
_ABS_END = "end_abs_5"
_POW_F = "func_pow_6"
_POW_END = "end_pow_7"
_MIN_F = "func_min_8"
_MIN_END = "end_min_9"
_MAX_F = "func_max_10"
_MAX_END = "end_max_11"

# ── IR ───────────────────────────────────────────────────────────────────────
# Register numbers are global across the whole module — never restart at %0.
MATH_IR = (
    # ── top-level: declare Math class ────────────────────────────────────────
    Label_(label=CodeLabel("entry_Math")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("Math"), value_reg=Register("%0")),
    # ── sqrt(x) → x ** 0.5 ──────────────────────────────────────────────────
    Branch(label=CodeLabel(_SQRT_END)),
    Label_(label=CodeLabel(_SQRT_F)),
    Symbolic(result_reg=Register("%1"), hint="param:x"),
    DeclVar(name=VarName("x"), value_reg=Register("%1")),
    LoadVar(result_reg=Register("%2"), name=VarName("x")),
    Const(result_reg=Register("%3"), value="0.5"),
    Binop(
        result_reg=Register("%4"),
        operator=BinopKind.POWER,
        left=Register("%2"),
        right=Register("%3"),
    ),
    Return_(value_reg=Register("%4")),
    Label_(label=CodeLabel(_SQRT_END)),
    Const(result_reg=Register("%5"), value=_SQRT_F),
    DeclVar(name=VarName("sqrt"), value_reg=Register("%5")),
    # ── abs(x) → VM builtin "abs" ────────────────────────────────────────────
    Branch(label=CodeLabel(_ABS_END)),
    Label_(label=CodeLabel(_ABS_F)),
    Symbolic(result_reg=Register("%6"), hint="param:x"),
    DeclVar(name=VarName("x"), value_reg=Register("%6")),
    LoadVar(result_reg=Register("%7"), name=VarName("x")),
    CallFunction(
        result_reg=Register("%8"),
        func_name=FuncName("abs"),
        args=(Register("%7"),),
    ),
    Return_(value_reg=Register("%8")),
    Label_(label=CodeLabel(_ABS_END)),
    Const(result_reg=Register("%9"), value=_ABS_F),
    DeclVar(name=VarName("abs"), value_reg=Register("%9")),
    # ── pow(x, y) → x ** y ───────────────────────────────────────────────────
    Branch(label=CodeLabel(_POW_END)),
    Label_(label=CodeLabel(_POW_F)),
    Symbolic(result_reg=Register("%10"), hint="param:x"),
    DeclVar(name=VarName("x"), value_reg=Register("%10")),
    Symbolic(result_reg=Register("%11"), hint="param:y"),
    DeclVar(name=VarName("y"), value_reg=Register("%11")),
    LoadVar(result_reg=Register("%12"), name=VarName("x")),
    LoadVar(result_reg=Register("%13"), name=VarName("y")),
    Binop(
        result_reg=Register("%14"),
        operator=BinopKind.POWER,
        left=Register("%12"),
        right=Register("%13"),
    ),
    Return_(value_reg=Register("%14")),
    Label_(label=CodeLabel(_POW_END)),
    Const(result_reg=Register("%15"), value=_POW_F),
    DeclVar(name=VarName("pow"), value_reg=Register("%15")),
    # ── min(x, y) → VM builtin "min" ─────────────────────────────────────────
    Branch(label=CodeLabel(_MIN_END)),
    Label_(label=CodeLabel(_MIN_F)),
    Symbolic(result_reg=Register("%16"), hint="param:x"),
    DeclVar(name=VarName("x"), value_reg=Register("%16")),
    Symbolic(result_reg=Register("%17"), hint="param:y"),
    DeclVar(name=VarName("y"), value_reg=Register("%17")),
    LoadVar(result_reg=Register("%18"), name=VarName("x")),
    LoadVar(result_reg=Register("%19"), name=VarName("y")),
    CallFunction(
        result_reg=Register("%20"),
        func_name=FuncName("min"),
        args=(Register("%18"), Register("%19")),
    ),
    Return_(value_reg=Register("%20")),
    Label_(label=CodeLabel(_MIN_END)),
    Const(result_reg=Register("%21"), value=_MIN_F),
    DeclVar(name=VarName("min"), value_reg=Register("%21")),
    # ── max(x, y) → VM builtin "max" ─────────────────────────────────────────
    Branch(label=CodeLabel(_MAX_END)),
    Label_(label=CodeLabel(_MAX_F)),
    Symbolic(result_reg=Register("%22"), hint="param:x"),
    DeclVar(name=VarName("x"), value_reg=Register("%22")),
    Symbolic(result_reg=Register("%23"), hint="param:y"),
    DeclVar(name=VarName("y"), value_reg=Register("%23")),
    LoadVar(result_reg=Register("%24"), name=VarName("x")),
    LoadVar(result_reg=Register("%25"), name=VarName("y")),
    CallFunction(
        result_reg=Register("%26"),
        func_name=FuncName("max"),
        args=(Register("%24"), Register("%25")),
    ),
    Return_(value_reg=Register("%26")),
    Label_(label=CodeLabel(_MAX_END)),
    Const(result_reg=Register("%27"), value=_MAX_F),
    DeclVar(name=VarName("max"), value_reg=Register("%27")),
)

MATH_MODULE = ModuleUnit(
    path=Path("java/lang/Math.java"),
    language=Language.JAVA,
    ir=MATH_IR,
    exports=ExportTable(
        functions={
            FuncName("sqrt"): CodeLabel(_SQRT_F),
            FuncName("abs"): CodeLabel(_ABS_F),
            FuncName("pow"): CodeLabel(_POW_F),
            FuncName("min"): CodeLabel(_MIN_F),
            FuncName("max"): CodeLabel(_MAX_F),
        },
        classes={
            ClassName("Math"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
