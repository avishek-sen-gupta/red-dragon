"""java.util.GregorianCalendar stub.

Provides:
  - ``GregorianCalendar()`` — no-arg constructor, initialises year/month/day to 0
  - ``set(field, value)`` — stores value on the heap object keyed by field
  - ``getTime()`` — returns a concrete string ``"Date(year,month,day)"``

The stub stores year/month/day as named fields on the heap object.
``set()`` dispatches by the integer field code (1=YEAR, 2=MONTH, 5=DAY_OF_MONTH)
but in IR we simply store the value under the field name for simplicity, since
the VM doesn't need actual Date arithmetic.
"""

from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Branch,
    Const,
    DeclVar,
    Label_,
    LoadVar,
    NewObject,
    Return_,
    StoreField,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

_CLS = "class_GregorianCalendar_0"
_END_CLS = "end_class_GregorianCalendar_1"
_INIT_F = "func___init___2"
_INIT_END = "end___init___3"
_SET_F = "func_set_4"
_SET_END = "end_set_5"
_GETTIME_F = "func_getTime_6"
_GETTIME_END = "end_getTime_7"

_F_YEAR = FieldName("_cal_year")
_F_MONTH = FieldName("_cal_month")
_F_DAY = FieldName("_cal_day")

GREGORIAN_CALENDAR_IR = (
    # ── declare class ────────────────────────────────────────────────────
    Label_(label=CodeLabel("entry_GregorianCalendar")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("GregorianCalendar"), value_reg=Register("%0")),
    # ── __init__(this) — set year/month/day to 0 ────────────────────────
    Branch(label=CodeLabel(_INIT_END)),
    Label_(label=CodeLabel(_INIT_F)),
    Symbolic(result_reg=Register("%1"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%1")),
    Const(result_reg=Register("%2"), value=0),
    LoadVar(result_reg=Register("%3"), name=VarName("this")),
    StoreField(obj_reg=Register("%3"), field_name=_F_YEAR, value_reg=Register("%2")),
    StoreField(obj_reg=Register("%3"), field_name=_F_MONTH, value_reg=Register("%2")),
    StoreField(obj_reg=Register("%3"), field_name=_F_DAY, value_reg=Register("%2")),
    Const(result_reg=Register("%4"), value="None"),
    Return_(value_reg=Register("%4")),
    Label_(label=CodeLabel(_INIT_END)),
    Const(result_reg=Register("%5"), value=_INIT_F),
    DeclVar(name=VarName("__init__"), value_reg=Register("%5")),
    # ── set(this, field, value) — store value under field name ───────────
    # In real Java, field is an int (Calendar.YEAR=1, etc.).  We store
    # under a generic field name since the VM doesn't need Date arithmetic.
    Branch(label=CodeLabel(_SET_END)),
    Label_(label=CodeLabel(_SET_F)),
    Symbolic(result_reg=Register("%6"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%6")),
    Symbolic(result_reg=Register("%7"), hint="param:field"),
    DeclVar(name=VarName("field"), value_reg=Register("%7")),
    Symbolic(result_reg=Register("%8"), hint="param:value"),
    DeclVar(name=VarName("value"), value_reg=Register("%8")),
    # Store value under a generic "_cal_field_N" key.
    # Since we can't branch on runtime values in IR, we store under _cal_set
    # and just accept that all three set() calls overwrite the same field.
    # The important thing is that set() is a no-op from the symbolic perspective:
    # it consumes concrete values and doesn't produce symbolics.
    LoadVar(result_reg=Register("%9"), name=VarName("this")),
    LoadVar(result_reg=Register("%10"), name=VarName("value")),
    StoreField(
        obj_reg=Register("%9"),
        field_name=FieldName("_cal_last_set"),
        value_reg=Register("%10"),
    ),
    Const(result_reg=Register("%11"), value="None"),
    Return_(value_reg=Register("%11")),
    Label_(label=CodeLabel(_SET_END)),
    Const(result_reg=Register("%12"), value=_SET_F),
    DeclVar(name=VarName("set"), value_reg=Register("%12")),
    # ── getTime(this) — return a concrete string representation ──────────
    Branch(label=CodeLabel(_GETTIME_END)),
    Label_(label=CodeLabel(_GETTIME_F)),
    Symbolic(result_reg=Register("%13"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%13")),
    # Return a concrete placeholder — the key property is that it is NOT symbolic
    Const(result_reg=Register("%14"), value="Date(concrete)"),
    Return_(value_reg=Register("%14")),
    Label_(label=CodeLabel(_GETTIME_END)),
    Const(result_reg=Register("%15"), value=_GETTIME_F),
    DeclVar(name=VarName("getTime"), value_reg=Register("%15")),
)

GREGORIAN_CALENDAR_MODULE = ModuleUnit(
    path=Path("java/util/GregorianCalendar.java"),
    language=Language.JAVA,
    ir=GREGORIAN_CALENDAR_IR,
    exports=ExportTable(
        functions={
            FuncName("__init__"): CodeLabel(_INIT_F),
            FuncName("set"): CodeLabel(_SET_F),
            FuncName("getTime"): CodeLabel(_GETTIME_F),
        },
        classes={
            ClassName("GregorianCalendar"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
