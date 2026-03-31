from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.field_name import FieldKind, FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    CallFunction,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadVar,
    NewObject,
    Return_,
    StoreField,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.types.type_expr import scalar
from interpreter.var_name import VarName

_VALUE = FieldName("value")
# FieldName("length", FieldKind.SPECIAL) is checked by the _builtin_len
# dispatcher, so s.length() resolves to this field without entering our IR stub.
_LEN_SPECIAL = FieldName("length", FieldKind.SPECIAL)

_CLS = "class_String_0"
_END_CLS = "end_class_String_1"
_INIT_F = "func___init___2"
_INIT_END = "end___init___3"
_UPPER_F = "func_toUpperCase_4"
_UPPER_END = "end_toUpperCase_5"
_LOWER_F = "func_toLowerCase_6"
_LOWER_END = "end_toLowerCase_7"
_LEN_F = "func_length_8"
_LEN_END = "end_length_9"
_TRIM_F = "func_trim_10"
_TRIM_END = "end_trim_11"
_CONTAINS_F = "func_contains_12"
_CONTAINS_END = "end_contains_13"

STRING_IR = (
    # ── declare String class ─────────────────────────────────────────────────
    Label_(label=CodeLabel("entry_String")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("String"), value_reg=Register("%0")),
    # ── __init__(this, value) — store value + pre-compute length ──────────────
    # Pre-storing FieldName("length", FieldKind.SPECIAL) lets the VM's
    # built-in _builtin_len dispatcher return the correct integer instead of
    # len(fields) when user code calls  s.length().
    Branch(label=CodeLabel(_INIT_END)),
    Label_(label=CodeLabel(_INIT_F)),
    Symbolic(result_reg=Register("%1"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%1")),
    Symbolic(result_reg=Register("%2"), hint="param:value"),
    DeclVar(name=VarName("value"), value_reg=Register("%2")),
    LoadVar(result_reg=Register("%3"), name=VarName("this")),
    LoadVar(result_reg=Register("%4"), name=VarName("value")),
    StoreField(obj_reg=Register("%3"), field_name=_VALUE, value_reg=Register("%4")),
    CallFunction(
        result_reg=Register("%5"),
        func_name=FuncName("len"),
        args=(Register("%4"),),
    ),
    StoreField(
        obj_reg=Register("%3"), field_name=_LEN_SPECIAL, value_reg=Register("%5")
    ),
    Const(result_reg=Register("%6"), value="None"),
    Return_(value_reg=Register("%6")),
    Label_(label=CodeLabel(_INIT_END)),
    Const(result_reg=Register("%7"), value=_INIT_F),
    DeclVar(name=VarName("__init__"), value_reg=Register("%7")),
    # ── toUpperCase() → new String(str_upper(this.value)) ────────────────────
    Branch(label=CodeLabel(_UPPER_END)),
    Label_(label=CodeLabel(_UPPER_F)),
    Symbolic(result_reg=Register("%8"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%8")),
    LoadVar(result_reg=Register("%9"), name=VarName("this")),
    LoadField(result_reg=Register("%10"), obj_reg=Register("%9"), field_name=_VALUE),
    CallFunction(
        result_reg=Register("%11"),
        func_name=FuncName("str_upper"),
        args=(Register("%10"),),
    ),
    NewObject(result_reg=Register("%12"), type_hint=scalar("String")),
    StoreField(obj_reg=Register("%12"), field_name=_VALUE, value_reg=Register("%11")),
    CallFunction(
        result_reg=Register("%13"),
        func_name=FuncName("len"),
        args=(Register("%11"),),
    ),
    StoreField(
        obj_reg=Register("%12"), field_name=_LEN_SPECIAL, value_reg=Register("%13")
    ),
    Return_(value_reg=Register("%12")),
    Label_(label=CodeLabel(_UPPER_END)),
    Const(result_reg=Register("%14"), value=_UPPER_F),
    DeclVar(name=VarName("toUpperCase"), value_reg=Register("%14")),
    # ── toLowerCase() → new String(str_lower(this.value)) ────────────────────
    Branch(label=CodeLabel(_LOWER_END)),
    Label_(label=CodeLabel(_LOWER_F)),
    Symbolic(result_reg=Register("%15"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%15")),
    LoadVar(result_reg=Register("%16"), name=VarName("this")),
    LoadField(result_reg=Register("%17"), obj_reg=Register("%16"), field_name=_VALUE),
    CallFunction(
        result_reg=Register("%18"),
        func_name=FuncName("str_lower"),
        args=(Register("%17"),),
    ),
    NewObject(result_reg=Register("%19"), type_hint=scalar("String")),
    StoreField(obj_reg=Register("%19"), field_name=_VALUE, value_reg=Register("%18")),
    CallFunction(
        result_reg=Register("%20"),
        func_name=FuncName("len"),
        args=(Register("%18"),),
    ),
    StoreField(
        obj_reg=Register("%19"), field_name=_LEN_SPECIAL, value_reg=Register("%20")
    ),
    Return_(value_reg=Register("%19")),
    Label_(label=CodeLabel(_LOWER_END)),
    Const(result_reg=Register("%21"), value=_LOWER_F),
    DeclVar(name=VarName("toLowerCase"), value_reg=Register("%21")),
    # ── length() — note: s.length() is intercepted by the _method_length
    #   builtin which reads _LEN_SPECIAL from the heap object stored in __init__.
    #   This IR stub is kept for export completeness but is not executed via
    #   the normal method-call path.
    Branch(label=CodeLabel(_LEN_END)),
    Label_(label=CodeLabel(_LEN_F)),
    Symbolic(result_reg=Register("%22"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%22")),
    LoadVar(result_reg=Register("%23"), name=VarName("this")),
    LoadField(
        result_reg=Register("%24"), obj_reg=Register("%23"), field_name=_LEN_SPECIAL
    ),
    Return_(value_reg=Register("%24")),
    Label_(label=CodeLabel(_LEN_END)),
    Const(result_reg=Register("%25"), value=_LEN_F),
    DeclVar(name=VarName("length"), value_reg=Register("%25")),
    # ── trim() → new String(str_strip(this.value)) ───────────────────────────
    Branch(label=CodeLabel(_TRIM_END)),
    Label_(label=CodeLabel(_TRIM_F)),
    Symbolic(result_reg=Register("%26"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%26")),
    LoadVar(result_reg=Register("%27"), name=VarName("this")),
    LoadField(result_reg=Register("%28"), obj_reg=Register("%27"), field_name=_VALUE),
    CallFunction(
        result_reg=Register("%29"),
        func_name=FuncName("str_strip"),
        args=(Register("%28"),),
    ),
    NewObject(result_reg=Register("%30"), type_hint=scalar("String")),
    StoreField(obj_reg=Register("%30"), field_name=_VALUE, value_reg=Register("%29")),
    CallFunction(
        result_reg=Register("%31"),
        func_name=FuncName("len"),
        args=(Register("%29"),),
    ),
    StoreField(
        obj_reg=Register("%30"), field_name=_LEN_SPECIAL, value_reg=Register("%31")
    ),
    Return_(value_reg=Register("%30")),
    Label_(label=CodeLabel(_TRIM_END)),
    Const(result_reg=Register("%32"), value=_TRIM_F),
    DeclVar(name=VarName("trim"), value_reg=Register("%32")),
    # ── contains(s) → s.value in this.value via BinopKind.IN ─────────────────
    Branch(label=CodeLabel(_CONTAINS_END)),
    Label_(label=CodeLabel(_CONTAINS_F)),
    Symbolic(result_reg=Register("%33"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%33")),
    Symbolic(result_reg=Register("%34"), hint="param:s"),
    DeclVar(name=VarName("s"), value_reg=Register("%34")),
    LoadVar(result_reg=Register("%35"), name=VarName("this")),
    LoadField(result_reg=Register("%36"), obj_reg=Register("%35"), field_name=_VALUE),
    LoadVar(result_reg=Register("%37"), name=VarName("s")),
    LoadField(result_reg=Register("%38"), obj_reg=Register("%37"), field_name=_VALUE),
    Binop(
        result_reg=Register("%39"),
        operator=BinopKind.IN,
        left=Register("%38"),
        right=Register("%36"),
    ),
    Return_(value_reg=Register("%39")),
    Label_(label=CodeLabel(_CONTAINS_END)),
    Const(result_reg=Register("%40"), value=_CONTAINS_F),
    DeclVar(name=VarName("contains"), value_reg=Register("%40")),
)

STRING_MODULE = ModuleUnit(
    path=Path("java/lang/String.java"),
    language=Language.JAVA,
    ir=STRING_IR,
    exports=ExportTable(
        functions={
            FuncName("__init__"): CodeLabel(_INIT_F),
            FuncName("toUpperCase"): CodeLabel(_UPPER_F),
            FuncName("toLowerCase"): CodeLabel(_LOWER_F),
            FuncName("length"): CodeLabel(_LEN_F),
            FuncName("trim"): CodeLabel(_TRIM_F),
            FuncName("contains"): CodeLabel(_CONTAINS_F),
        },
        classes={
            ClassName("String"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
