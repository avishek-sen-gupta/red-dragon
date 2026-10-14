"""IrCodec round-trips every instruction, type expression and table exactly."""

import json
import typing
from decimal import Decimal
from pathlib import Path

import pytest

from interpreter.class_name import NO_CLASS_NAME, ClassName
from interpreter.constants import FoundationTypeName
from interpreter.continuation_name import ContinuationName
from interpreter.data_value import DataField, DataList, DataRecord, DataScalar
from interpreter.field_name import NO_FIELD_NAME, FieldKind, FieldName
from interpreter.frontends.symbol_table import (
    ClassInfo,
    FieldInfo,
    FunctionInfo,
    SymbolTable,
)
from interpreter.func_name import NO_FUNC_NAME, FuncName
from interpreter.instructions import (
    AddressOf,
    AllocRegion,
    Binop,
    Branch,
    BranchIf,
    CallCtorFunction,
    CallFunction,
    CallMethod,
    CallUnknown,
    CallWithMemory,
    Const,
    Data,
    DeclVar,
    Halt_,
    ImportModule,
    Instruction,
    Label_,
    LoadField,
    LoadFieldIndirect,
    LoadIndex,
    LoadIndirect,
    LoadRegion,
    LoadVar,
    NewArray,
    NewObject,
    ResumeContinuation,
    Return_,
    SetContinuation,
    StoreField,
    StoreIndex,
    StoreIndirect,
    StoreVar,
    Suspend,
    Symbolic,
    Throw_,
    TryPop,
    TryPush,
    Unop,
    WriteRegion,
)
from interpreter.ir import (
    NO_LABEL,
    CodeLabel,
    NoCodeLabel,
    SourceLocation,
    SpreadArguments,
)
from interpreter.operator_kind import BinopKind, UnopKind
from interpreter.path_name import PathName
from interpreter.project.ir_codec import IrCodec
from interpreter.project.types import ExportTable, ImportKind, ImportRef
from interpreter.project.unit_format_error import UnitFormatError
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.register import NO_REGISTER, NoRegister, Register
from interpreter.type_name import TypeName
from interpreter.types import type_expr as te
from interpreter.types.type_expr import scalar
from interpreter.var_name import NO_VAR_NAME, VarName
from tests.covers import NotLanguageFeature, covers

_R = Register
_L = CodeLabel
_LOC = SourceLocation(start_line=3, start_col=1, end_line=3, end_col=9)
_INT = te.scalar(TypeName("Int"))

_SAMPLES = (
    Const(
        result_reg=_R("%1"),
        value=Decimal("12.50"),
        type_expr=_INT,
        source_location=_LOC,
    ),
    LoadVar(result_reg=_R("%2"), name=VarName("x")),
    DeclVar(name=VarName("x"), value_reg=_R("%1")),
    StoreVar(name=VarName("x"), value_reg=_R("%1")),
    Symbolic(result_reg=_R("%3"), hint="param:args"),
    Binop(
        result_reg=_R("%4"), operator=BinopKind.NOT_IN, left=_R("%1"), right=_R("%2")
    ),
    Unop(result_reg=_R("%5"), operator=UnopKind.NOT, operand=_R("%4")),
    CallFunction(
        result_reg=_R("%6"),
        func_name=FuncName("f"),
        args=(_R("%1"), SpreadArguments(register=_R("%2"))),
    ),
    CallMethod(
        result_reg=_R("%7"),
        obj_reg=_R("%1"),
        method_name=FuncName("m"),
        args=(_R("%2"),),
    ),
    CallUnknown(result_reg=_R("%8"), target_reg=_R("%1"), args=()),
    CallCtorFunction(
        result_reg=_R("%9"), func_name=FuncName("C"), type_hint=_INT, args=(_R("%1"),)
    ),
    CallWithMemory(
        result_reg=_R("%10"), location=VarName("__entry_X"), memory=_R("%1")
    ),
    CallWithMemory(result_reg=_R("%11"), location=_R("%7"), memory=_R("%1")),
    LoadField(
        result_reg=_R("%12"),
        obj_reg=_R("%1"),
        field_name=FieldName("f", FieldKind.INDEX),
    ),
    StoreField(obj_reg=_R("%1"), field_name=FieldName("f"), value_reg=_R("%2")),
    LoadFieldIndirect(result_reg=_R("%13"), obj_reg=_R("%1"), name_reg=_R("%2")),
    LoadIndex(result_reg=_R("%14"), arr_reg=_R("%1"), index_reg=_R("%2")),
    StoreIndex(
        arr_reg=_R("%1"),
        index_reg=_R("%2"),
        value_reg=SpreadArguments(register=_R("%3")),
    ),
    LoadIndirect(result_reg=_R("%15"), ptr_reg=_R("%1")),
    StoreIndirect(ptr_reg=_R("%1"), value_reg=_R("%2")),
    ImportModule(module_path="a.b", resolved_path=PathName("a/b.py")),
    AddressOf(result_reg=_R("%16"), var_name=VarName("x")),
    NewObject(result_reg=_R("%17"), type_hint=te.ParameterizedType("Array", (_INT,))),
    NewArray(result_reg=_R("%18"), type_hint=_INT, size_reg=_R("%1")),
    Label_(label=_L("func_x_0")),
    Branch(label=_L("after_0")),
    BranchIf(cond_reg=_R("%1"), branch_targets=(_L("t"), _L("f"))),
    Return_(value_reg=_R("%1"), implicit=True),
    Return_(value_reg=None),
    Halt_(),
    Throw_(value_reg=_R("%1")),
    TryPush(catch_labels=(_L("c"),), finally_label=_L("fin"), end_label=NO_LABEL),
    TryPop(),
    AllocRegion(result_reg=_R("%19"), size_reg=_R("%1")),
    LoadRegion(
        result_reg=_R("%20"), region_reg=_R("%1"), offset_reg=_R("%2"), length=4
    ),
    WriteRegion(region_reg=_R("%1"), offset_reg=_R("%2"), length=4, value_reg=_R("%3")),
    SetContinuation(name=ContinuationName("k"), target_label=_L("ret")),
    ResumeContinuation(name=ContinuationName("k")),
    Suspend(operand_reg=_R("%1")),
    Data(
        name=VarName("PROG"),
        value=DataRecord(
            (
                DataField(
                    FieldName("files"),
                    DataList(
                        (
                            DataRecord(
                                (
                                    DataField(
                                        FieldName("assign_to"),
                                        DataScalar(
                                            "IN1", scalar(FoundationTypeName.STRING)
                                        ),
                                    ),
                                    DataField(
                                        FieldName("depending"),
                                        DataScalar(
                                            False, scalar(FoundationTypeName.BOOL)
                                        ),
                                    ),
                                    DataField(
                                        FieldName("record_lengths"),
                                        DataList(
                                            (
                                                DataScalar(
                                                    80, scalar(FoundationTypeName.INT)
                                                ),
                                            )
                                        ),
                                    ),
                                )
                            ),
                        )
                    ),
                ),
            )
        ),
    ),
)

_TYPES = (
    te.UNKNOWN,
    _INT,
    te.EnumType("Colour"),
    te.AnnotationType("Final"),
    te.StructPatternType("Point"),
    te.ParameterizedType("Map", (_INT, te.UNKNOWN)),
    te.FunctionType((_INT,), te.UNKNOWN),
    te.UnionType(frozenset({_INT, te.EnumType("E")})),
    te.TypeVar("T", bound=_INT),
)


def _round_trip[T](value: T) -> T:
    codec = IrCodec()
    decoded = codec.decode(json.loads(json.dumps(codec.encode(value))))
    assert isinstance(decoded, type(value))
    return decoded


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_samples_cover_every_instruction_class():
    assert {type(s) for s in _SAMPLES} == set(typing.get_args(Instruction))


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("instruction", _SAMPLES, ids=lambda i: type(i).__name__)
def test_every_instruction_round_trips_with_its_field_types(instruction):
    decoded = _round_trip(instruction)
    assert (decoded, {f: type(getattr(decoded, f)) for f in vars(decoded)}) == (
        instruction,
        {f: type(getattr(instruction, f)) for f in vars(instruction)},
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("type_expr", _TYPES, ids=lambda t: type(t).__name__)
def test_every_type_expression_round_trips(type_expr):
    decoded = _round_trip(type_expr)
    assert (decoded, type(decoded)) == (type_expr, type(type_expr))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_null_objects_decode_to_their_singletons():
    decoded = _round_trip(LoadField())
    assert (
        type(decoded.result_reg),
        decoded.field_name is NO_FIELD_NAME,
        type(decoded.label),
        _round_trip(NO_VAR_NAME) is NO_VAR_NAME,
        _round_trip(NO_FUNC_NAME) is NO_FUNC_NAME,
        _round_trip(NO_CLASS_NAME) is NO_CLASS_NAME,
        _round_trip(NO_REGISTER) is NO_REGISTER,
    ) == (NoRegister, True, NoCodeLabel, True, True, True, True)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize(
    "value",
    [
        Decimal("0.10"),
        Decimal("0E-7"),
        Decimal("-1.5E+3"),
        [1, 2, 255],
        b"\x00\xc1",
        None,
        True,
        7,
        7.5,
        "PIC X",
        ["MAP1", "MAP2"],
    ],
    ids=repr,
)
def test_const_values_keep_their_python_type(value):
    decoded = _round_trip(Const(result_reg=_R("%1"), value=value, type_expr=te.UNKNOWN))
    assert (decoded.value, type(decoded.value)) == (value, type(value))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_tables_round_trip():
    tables = (
        ExportTable(
            functions={FuncName("f"): _L("func_f_0")},
            classes={ClassName("C"): _L("class_C_0")},
            variables={VarName("v"): _R("%1")},
        ),
        ImportRef(
            source_file=Path("a.py"),
            module_path="b",
            names=("x",),
            kind=ImportKind.USING,
            alias="y",
            line=4,
        ),
        FuncRef(name=FuncName("f"), label=_L("func_f_0")),
        ClassRef(name=ClassName("C"), label=_L("class_C_0"), parents=(ClassName("B"),)),
        SymbolTable(
            classes={
                ClassName("C"): ClassInfo(
                    name=ClassName("C"),
                    fields={
                        FieldName("a"): FieldInfo(
                            name=FieldName("a"),
                            type_hint="Int",
                            has_initializer=True,
                            children=(
                                FieldInfo(
                                    name=FieldName("b"),
                                    type_hint="",
                                    has_initializer=False,
                                ),
                            ),
                        )
                    },
                    methods={
                        FuncName("m"): FunctionInfo(
                            name=FuncName("m"), params=("self",), return_type=""
                        )
                    },
                    constants={"K": "1"},
                    parents=(),
                )
            },
            functions={},
            constants={"Z": "2"},
        ),
        {
            "WS-A": {
                "offset": 0,
                "length": 5,
                "category": "ALPHANUMERIC",
                "signed": False,
            }
        },
    )
    assert [_round_trip(t) for t in tables] == list(tables)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_unknown_class_or_value_is_a_format_error():
    with pytest.raises(UnitFormatError, match="NoSuchInstruction"):
        IrCodec().decode({"$": "dc", "v": {"c": "NoSuchInstruction", "v": {}}})
    with pytest.raises(UnitFormatError, match="complex"):
        IrCodec().encode(1j)
