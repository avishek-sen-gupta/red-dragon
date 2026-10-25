# pyright: standard
"""OPEN's file declaration answers the provider's outcome, and an uncomputable value when the run has no provider."""

from interpreter.hlasm_run_inputs.declare_file_builtins import declare_file_builtins
from interpreter.hlasm_run_inputs.run_input_names import DECLARE_FILE_BUILTIN
from interpreter.record_io.access_result import AccessCondition
from interpreter.record_io.real_file_provider import RealFileProvider
from interpreter.run import initial_vm_state
from interpreter.types.typed_value import typed
from interpreter.vm.uncomputable import UNCOMPUTABLE
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_declaration_answers_the_providers_outcome_or_uncomputable_without_one():
    declare = declare_file_builtins()[DECLARE_FILE_BUILTIN]
    args = [typed("INDD"), typed(False), typed(80)]

    assert (
        declare(args, initial_vm_state(io_provider=RealFileProvider())).value,
        declare(args, initial_vm_state()).value,
    ) == (AccessCondition.OK.position(), UNCOMPUTABLE)
