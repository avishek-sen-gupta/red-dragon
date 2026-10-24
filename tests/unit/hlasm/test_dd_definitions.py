# pyright: standard
"""The DD run input: a supplied DDNAME answers 1 and its RECFM byte, LRECL and BLKSIZE (0 where not given), any other answers zeros, and each DDNAME's path overrides the file provider's."""

from pathlib import Path

from interpreter.hlasm_run_inputs.dd_definition import DdDefinition
from interpreter.hlasm_run_inputs.dd_run_inputs import dd_run_inputs
from interpreter.hlasm_run_inputs.record_format import RecordFormat
from interpreter.hlasm_run_inputs.run_input_names import DD_BUILTIN
from interpreter.run import initial_vm_state
from interpreter.types.type_expr import UNKNOWN
from interpreter.types.typed_value import typed
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_dd_answers_its_supplied_fields_and_an_unknown_name_zeros():
    builtins, provider_inputs = dd_run_inputs(
        {
            "INDD": DdDefinition(Path("in.dat"), RecordFormat.VB, 104, 1000),
            "OUTDD": DdDefinition(Path("out.dat")),
        }
    )

    answers = [
        builtins[DD_BUILTIN]([typed(name, UNKNOWN)], initial_vm_state()).value
        for name in ("INDD", "OUTDD", "SYSIN")
    ]

    assert (answers, dict(provider_inputs.path_overrides)) == (
        [[1, 0x50, 104, 1000], [1, 0, 0, 0], [0, 0, 0, 0]],
        {"INDD": Path("in.dat"), "OUTDD": Path("out.dat")},
    )
