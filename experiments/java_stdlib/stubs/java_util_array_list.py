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
    LoadIndex,
    LoadVar,
    NewArray,
    Return_,
    StoreField,
    Symbolic,
)
from interpreter.instructions import NO_REGISTER
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

_ELEMENTS = FieldName("elements")
_LEN_SPECIAL = FieldName("length", FieldKind.SPECIAL)

_CLS = "class_ArrayList_0"
_END_CLS = "end_class_ArrayList_1"
_INIT_F = "func___init___2"
_INIT_END = "end___init___3"
_ADD_F = "func_add_4"
_ADD_END = "end_add_5"
_GET_F = "func_get_6"
_GET_END = "end_get_7"
_SIZE_F = "func_size_8"
_SIZE_END = "end_size_9"
_EMPTY_F = "func_isEmpty_10"
_EMPTY_END = "end_isEmpty_11"

ARRAY_LIST_IR = (
    # ── declare ArrayList class ───────────────────────────────────────────────
    Label_(label=CodeLabel("entry_ArrayList")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("ArrayList"), value_reg=Register("%0")),
    # ── __init__(this) — initialise self.elements as a heap array ─────────────
    # Also store length=0 on this so _method_length returns 0 before any add().
    Branch(label=CodeLabel(_INIT_END)),
    Label_(label=CodeLabel(_INIT_F)),
    Symbolic(result_reg=Register("%1"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%1")),
    NewArray(result_reg=Register("%2"), type_hint="list", size_reg=NO_REGISTER),
    LoadVar(result_reg=Register("%3"), name=VarName("this")),
    StoreField(obj_reg=Register("%3"), field_name=_ELEMENTS, value_reg=Register("%2")),
    Const(result_reg=Register("%4"), value="0"),
    StoreField(
        obj_reg=Register("%3"), field_name=_LEN_SPECIAL, value_reg=Register("%4")
    ),
    Const(result_reg=Register("%5"), value="None"),
    Return_(value_reg=Register("%5")),
    Label_(label=CodeLabel(_INIT_END)),
    Const(result_reg=Register("%6"), value=_INIT_F),
    DeclVar(name=VarName("__init__"), value_reg=Register("%6")),
    # ── add(this, element) → list_append to elements, update this.length ──────
    Branch(label=CodeLabel(_ADD_END)),
    Label_(label=CodeLabel(_ADD_F)),
    Symbolic(result_reg=Register("%7"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%7")),
    Symbolic(result_reg=Register("%8"), hint="param:element"),
    DeclVar(name=VarName("element"), value_reg=Register("%8")),
    LoadVar(result_reg=Register("%9"), name=VarName("this")),
    LoadField(result_reg=Register("%10"), obj_reg=Register("%9"), field_name=_ELEMENTS),
    LoadVar(result_reg=Register("%11"), name=VarName("element")),
    CallFunction(
        result_reg=Register("%12"),
        func_name=FuncName("list_append"),
        args=(Register("%10"), Register("%11")),
    ),
    # Update this.length with len(elements) so _method_length returns correct value.
    CallFunction(
        result_reg=Register("%13"),
        func_name=FuncName("len"),
        args=(Register("%10"),),
    ),
    LoadVar(result_reg=Register("%14"), name=VarName("this")),
    StoreField(
        obj_reg=Register("%14"), field_name=_LEN_SPECIAL, value_reg=Register("%13")
    ),
    Const(result_reg=Register("%15"), value="True"),
    Return_(value_reg=Register("%15")),
    Label_(label=CodeLabel(_ADD_END)),
    Const(result_reg=Register("%16"), value=_ADD_F),
    DeclVar(name=VarName("add"), value_reg=Register("%16")),
    # ── get(this, index) → elements[index] ────────────────────────────────────
    Branch(label=CodeLabel(_GET_END)),
    Label_(label=CodeLabel(_GET_F)),
    Symbolic(result_reg=Register("%17"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%17")),
    Symbolic(result_reg=Register("%18"), hint="param:index"),
    DeclVar(name=VarName("index"), value_reg=Register("%18")),
    LoadVar(result_reg=Register("%19"), name=VarName("this")),
    LoadField(
        result_reg=Register("%20"), obj_reg=Register("%19"), field_name=_ELEMENTS
    ),
    LoadVar(result_reg=Register("%21"), name=VarName("index")),
    LoadIndex(
        result_reg=Register("%22"), arr_reg=Register("%20"), index_reg=Register("%21")
    ),
    Return_(value_reg=Register("%22")),
    Label_(label=CodeLabel(_GET_END)),
    Const(result_reg=Register("%23"), value=_GET_F),
    DeclVar(name=VarName("get"), value_reg=Register("%23")),
    # ── size(this) → len(elements) via this.length (set by add) ──────────────
    # This stub is DEAD CODE at runtime — `_method_length` in Builtins.METHOD_TABLE
    # intercepts all `size` method calls before the IR stub is reached.
    # Kept for export completeness only.
    Branch(label=CodeLabel(_SIZE_END)),
    Label_(label=CodeLabel(_SIZE_F)),
    Symbolic(result_reg=Register("%24"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%24")),
    LoadVar(result_reg=Register("%25"), name=VarName("this")),
    LoadField(
        result_reg=Register("%26"), obj_reg=Register("%25"), field_name=_LEN_SPECIAL
    ),
    Return_(value_reg=Register("%26")),
    Label_(label=CodeLabel(_SIZE_END)),
    Const(result_reg=Register("%27"), value=_SIZE_F),
    DeclVar(name=VarName("size"), value_reg=Register("%27")),
    # ── isEmpty(this) → this.length == 0 ──────────────────────────────────────
    Branch(label=CodeLabel(_EMPTY_END)),
    Label_(label=CodeLabel(_EMPTY_F)),
    Symbolic(result_reg=Register("%28"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%28")),
    LoadVar(result_reg=Register("%29"), name=VarName("this")),
    LoadField(
        result_reg=Register("%30"), obj_reg=Register("%29"), field_name=_LEN_SPECIAL
    ),
    Const(result_reg=Register("%31"), value="0"),
    Binop(
        result_reg=Register("%32"),
        operator=BinopKind.EQ,
        left=Register("%30"),
        right=Register("%31"),
    ),
    Return_(value_reg=Register("%32")),
    Label_(label=CodeLabel(_EMPTY_END)),
    Const(result_reg=Register("%33"), value=_EMPTY_F),
    DeclVar(name=VarName("isEmpty"), value_reg=Register("%33")),
)

ARRAY_LIST_MODULE = ModuleUnit(
    path=Path("java/util/ArrayList.java"),
    language=Language.JAVA,
    ir=ARRAY_LIST_IR,
    exports=ExportTable(
        functions={
            FuncName("__init__"): CodeLabel(_INIT_F),
            FuncName("add"): CodeLabel(_ADD_F),
            FuncName("get"): CodeLabel(_GET_F),
            FuncName("size"): CodeLabel(_SIZE_F),
            FuncName("isEmpty"): CodeLabel(_EMPTY_F),
        },
        classes={
            ClassName("ArrayList"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
