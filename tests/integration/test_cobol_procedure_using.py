"""A called program's parameters bind in its PROCEDURE DIVISION USING order.

The LINKAGE items below are declared LK-B first, but USING lists LK-A first, so
the caller's first argument belongs in LK-A. Binding by declaration order puts it
in LK-B instead, and the callee's writes come back swapped.
"""

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import CallUsingParam
from interpreter.address import Address
from interpreter.cobol.features import CobolFeature
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.run import initial_vm_state, run_linked
from interpreter.var_name import VarName
from interpreter.vm.vm_types import Pointer
from tests.covers import covers
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode_zoned_unsigned,
)

SUB_SRC = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. SUB.\n"
    "       DATA DIVISION.\n"
    "       LINKAGE SECTION.\n"
    "       01 LK-B PIC 9(4).\n"
    "       01 LK-A PIC 9(4).\n"
    "       PROCEDURE DIVISION USING LK-A BY VALUE LK-B.\n"
    "           MOVE 11 TO LK-A.\n"
    "           MOVE 22 TO LK-B.\n"
    "           GOBACK.\n"
)

MAIN_SRC = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. MAIN.\n"
    "       DATA DIVISION.\n"
    "       WORKING-STORAGE SECTION.\n"
    "       01 WS-ONE PIC 9(4) VALUE 0.\n"
    "       01 WS-TWO PIC 9(4) VALUE 0.\n"
    "       PROCEDURE DIVISION.\n"
    "           CALL 'SUB' USING WS-ONE WS-TWO.\n"
    "           STOP RUN.\n"
)


@covers(CobolFeature.PROCEDURE_DIVISION_USING)
def test_the_bridge_records_the_using_list_in_order() -> None:
    asg = make_cobol_parser().parse(SUB_SRC.encode())

    assert asg.procedure_using == [
        CallUsingParam(name="LK-A", param_type="REFERENCE"),
        CallUsingParam(name="LK-B", param_type="VALUE"),
    ]


@covers(CobolFeature.PROCEDURE_DIVISION_USING, CobolFeature.CALL_USING)
def test_each_argument_lands_in_the_parameter_using_lists_at_its_position(
    tmp_path,
) -> None:
    (tmp_path / "SUB.cbl").write_text(SUB_SRC.replace("BY VALUE ", ""))
    (tmp_path / "MAIN.cbl").write_text(MAIN_SRC)
    vm = run_linked(
        compile_directory(tmp_path, Language.COBOL),
        entry_point=EntryPoint.function(
            lambda ref: str(ref.label).endswith("func_main_0")
            and "init_params" not in str(ref.label)
        ),
        max_steps=3000,
        initial_vm=initial_vm_state(),
    )

    ws = _main_working_storage(vm)
    assert (_decode_zoned_unsigned(ws, 0, 4), _decode_zoned_unsigned(ws, 4, 4)) == (
        11,
        22,
    )


def _main_working_storage(vm):
    pointer = next(
        frame.local_vars[VarName("__prog_MAIN")].value
        for frame in reversed(vm.call_stack)
        if VarName("__prog_MAIN") in frame.local_vars
    )
    assert isinstance(pointer, Pointer)
    region = vm.region_get(
        Address(vm.heap_get(pointer.base).fields[FieldName("ws_handle")].value)
    )
    assert isinstance(region, bytearray)
    return region
