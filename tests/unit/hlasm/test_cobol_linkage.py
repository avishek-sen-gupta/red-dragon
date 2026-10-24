# pyright: standard
"""The job-step module's COBOL linkage IR: each SD and LD name registers `__entry_<NAME>` from a function entering through one shared conversion, and the far branch calls a COBOL program by its entry variable."""

from interpreter.hlasm.binder import Binder
from interpreter.hlasm.cobol_program import CobolProgram
from interpreter.hlasm.image_module import ImageModule
from interpreter.hlasm.job_step import job_step_module
from interpreter.instructions import (
    CallFunction,
    CallWithMemory,
    Const,
    DeclVar,
    Symbolic,
)
from interpreter.project.argument_mode import ArgumentMode
from interpreter.project.control_section import ControlSection
from interpreter.project.default_end import DefaultEnd
from interpreter.project.entry_label import EntryLabel
from interpreter.project.external_reference import ExternalReference
from interpreter.project.object_module import ObjectModule
from interpreter.project.using_parameter import UsingParameter
from tests.covers import NotLanguageFeature, covers

ASM = ImageModule(
    "A",
    "A.asm",
    ObjectModule(
        (
            ControlSection("ASMSUB", 16),
            EntryLabel("ALT", "ASMSUB", 8),
            ExternalReference("COBSUB", 3),
        ),
        (),
        (),
        DefaultEnd("ASMSUB"),
    ),
)
COBSUB = CobolProgram(
    "COBSUB",
    "COBSUB.cbl",
    (
        UsingParameter(ArgumentMode.REFERENCE, 5),
        UsingParameter(ArgumentMode.VALUE, 8),
    ),
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_job_step_registers_cobol_entries_and_calls_cobol_programs():
    ir, functions = job_step_module(Binder((ASM,), (COBSUB,)))
    references = {str(i.result_reg): str(i.value) for i in ir if isinstance(i, Const)}
    declared = {
        str(i.name): references[str(i.value_reg)]
        for i in ir
        if isinstance(i, DeclVar) and str(i.value_reg) in references
    }

    assert (
        sorted(f.name for f in functions),
        {name: declared[name] for name in ("__entry_ASMSUB", "__entry_ALT")},
        [str(i.location) for i in ir if isinstance(i, CallWithMemory)],
        sorted(
            {
                str(i.func_name)
                for i in ir
                if isinstance(i, CallFunction) and "from_cobol" in str(i.func_name)
            }
        ),
        {i.hint.split(":")[0] for i in ir if isinstance(i, Symbolic)},
    ) == (
        ["__entry_ALT", "__entry_ASMSUB", "__hlasm_far_branch", "__hlasm_from_cobol"],
        {
            "__entry_ASMSUB": "func___entry_ASMSUB_0",
            "__entry_ALT": "func___entry_ALT_0",
        },
        ["__entry_COBSUB"],
        ["__hlasm_from_cobol"],
        {"param"},
    )
