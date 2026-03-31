from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.field_name import FieldKind, FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Branch,
    CallFunction,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    LoadVar,
    NewObject,
    Return_,
    StoreField,
    StoreIndex,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.register import Register
from interpreter.var_name import VarName

_ENTRIES = FieldName("entries")
_LEN_SPECIAL = FieldName("length", FieldKind.SPECIAL)

_CLS = "class_HashMap_0"
_END_CLS = "end_class_HashMap_1"
_INIT_F = "func___init___2"
_INIT_END = "end___init___3"
_PUT_F = "func_put_4"
_PUT_END = "end_put_5"
_GET_F = "func_get_6"
_GET_END = "end_get_7"
_CONTAINS_F = "func_containsKey_8"
_CONTAINS_END = "end_containsKey_9"
_SIZE_F = "func_size_10"
_SIZE_END = "end_size_11"

HASH_MAP_IR = (
    # ── declare HashMap class ─────────────────────────────────────────────────
    Label_(label=CodeLabel("entry_HashMap")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("HashMap"), value_reg=Register("%0")),
    # ── __init__(this) — initialise self.entries = {} and this.length = 0 ─────
    Branch(label=CodeLabel(_INIT_END)),
    Label_(label=CodeLabel(_INIT_F)),
    Symbolic(result_reg=Register("%1"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%1")),
    NewObject(result_reg=Register("%2"), type_hint="dict"),
    LoadVar(result_reg=Register("%3"), name=VarName("this")),
    StoreField(obj_reg=Register("%3"), field_name=_ENTRIES, value_reg=Register("%2")),
    Const(result_reg=Register("%4"), value="0"),
    StoreField(
        obj_reg=Register("%3"), field_name=_LEN_SPECIAL, value_reg=Register("%4")
    ),
    Const(result_reg=Register("%5"), value="None"),
    Return_(value_reg=Register("%5")),
    Label_(label=CodeLabel(_INIT_END)),
    Const(result_reg=Register("%6"), value=_INIT_F),
    DeclVar(name=VarName("__init__"), value_reg=Register("%6")),
    # ── put(this, key, value) → entries[key] = value; update this.length ──────
    Branch(label=CodeLabel(_PUT_END)),
    Label_(label=CodeLabel(_PUT_F)),
    Symbolic(result_reg=Register("%7"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%7")),
    Symbolic(result_reg=Register("%8"), hint="param:key"),
    DeclVar(name=VarName("key"), value_reg=Register("%8")),
    Symbolic(result_reg=Register("%9"), hint="param:value"),
    DeclVar(name=VarName("value"), value_reg=Register("%9")),
    LoadVar(result_reg=Register("%10"), name=VarName("this")),
    LoadField(result_reg=Register("%11"), obj_reg=Register("%10"), field_name=_ENTRIES),
    LoadVar(result_reg=Register("%12"), name=VarName("key")),
    LoadVar(result_reg=Register("%13"), name=VarName("value")),
    StoreIndex(
        arr_reg=Register("%11"), index_reg=Register("%12"), value_reg=Register("%13")
    ),
    # Update this.length = len(entries) so _method_length returns correct count.
    CallFunction(
        result_reg=Register("%14"),
        func_name=FuncName("len"),
        args=(Register("%11"),),
    ),
    LoadVar(result_reg=Register("%15"), name=VarName("this")),
    StoreField(
        obj_reg=Register("%15"), field_name=_LEN_SPECIAL, value_reg=Register("%14")
    ),
    Const(result_reg=Register("%16"), value="None"),
    Return_(value_reg=Register("%16")),
    Label_(label=CodeLabel(_PUT_END)),
    Const(result_reg=Register("%17"), value=_PUT_F),
    DeclVar(name=VarName("put"), value_reg=Register("%17")),
    # ── get(this, key) → entries[key] ─────────────────────────────────────────
    Branch(label=CodeLabel(_GET_END)),
    Label_(label=CodeLabel(_GET_F)),
    Symbolic(result_reg=Register("%18"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%18")),
    Symbolic(result_reg=Register("%19"), hint="param:key"),
    DeclVar(name=VarName("key"), value_reg=Register("%19")),
    LoadVar(result_reg=Register("%20"), name=VarName("this")),
    LoadField(result_reg=Register("%21"), obj_reg=Register("%20"), field_name=_ENTRIES),
    LoadVar(result_reg=Register("%22"), name=VarName("key")),
    LoadIndex(
        result_reg=Register("%23"), arr_reg=Register("%21"), index_reg=Register("%22")
    ),
    Return_(value_reg=Register("%23")),
    Label_(label=CodeLabel(_GET_END)),
    Const(result_reg=Register("%24"), value=_GET_F),
    DeclVar(name=VarName("get"), value_reg=Register("%24")),
    # ── containsKey(this, key) → dict_contains_key(entries, key) ─────────────
    # BinopKind.IN on a heap dict returns UNCOMPUTABLE (Pointer has no __contains__).
    # Use the dict_contains_key builtin instead.
    Branch(label=CodeLabel(_CONTAINS_END)),
    Label_(label=CodeLabel(_CONTAINS_F)),
    Symbolic(result_reg=Register("%25"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%25")),
    Symbolic(result_reg=Register("%26"), hint="param:key"),
    DeclVar(name=VarName("key"), value_reg=Register("%26")),
    LoadVar(result_reg=Register("%27"), name=VarName("this")),
    LoadField(result_reg=Register("%28"), obj_reg=Register("%27"), field_name=_ENTRIES),
    LoadVar(result_reg=Register("%29"), name=VarName("key")),
    CallFunction(
        result_reg=Register("%30"),
        func_name=FuncName("dict_contains_key"),
        args=(Register("%28"), Register("%29")),
    ),
    Return_(value_reg=Register("%30")),
    Label_(label=CodeLabel(_CONTAINS_END)),
    Const(result_reg=Register("%31"), value=_CONTAINS_F),
    DeclVar(name=VarName("containsKey"), value_reg=Register("%31")),
    # ── size(this) → DEAD CODE at runtime (intercepted by METHOD_TABLE) ───────
    Branch(label=CodeLabel(_SIZE_END)),
    Label_(label=CodeLabel(_SIZE_F)),
    Symbolic(result_reg=Register("%32"), hint="param:this"),
    DeclVar(name=VarName("this"), value_reg=Register("%32")),
    LoadVar(result_reg=Register("%33"), name=VarName("this")),
    LoadField(
        result_reg=Register("%34"),
        obj_reg=Register("%33"),
        field_name=_LEN_SPECIAL,
    ),
    Return_(value_reg=Register("%34")),
    Label_(label=CodeLabel(_SIZE_END)),
    Const(result_reg=Register("%35"), value=_SIZE_F),
    DeclVar(name=VarName("size"), value_reg=Register("%35")),
)

HASH_MAP_MODULE = ModuleUnit(
    path=Path("java/util/HashMap.java"),
    language=Language.JAVA,
    ir=HASH_MAP_IR,
    exports=ExportTable(
        functions={
            FuncName("__init__"): CodeLabel(_INIT_F),
            FuncName("put"): CodeLabel(_PUT_F),
            FuncName("get"): CodeLabel(_GET_F),
            FuncName("containsKey"): CodeLabel(_CONTAINS_F),
            FuncName("size"): CodeLabel(_SIZE_F),
        },
        classes={
            ClassName("HashMap"): CodeLabel(_CLS),
        },
    ),
    imports=(),
)
