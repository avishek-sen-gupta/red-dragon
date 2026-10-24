# pyright: standard
"""Binds the HLASM units of an image into its start-up module and job-step module, and names each entry's job-step function."""

from collections.abc import Sequence
from pathlib import Path

from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.hlasm.binder import Binder
from interpreter.hlasm.binder_start_up import bound_start_up
from interpreter.hlasm.image_module import ImageModule
from interpreter.hlasm.job_step import (
    end_step,
    job_step_label,
    job_step_module,
    named_step,
)
from interpreter.project.bound_image import BoundImage
from interpreter.project.linker import module_prefix
from interpreter.project.start_up import START_UP_PATH
from interpreter.project.types import ExportTable, ModuleUnit

JOB_STEP_PATH = Path("__hlasm_job__")
_PROJECT_ROOT = Path("/")


def image_module(unit: ModuleUnit) -> ImageModule:
    return ImageModule(
        module_prefix(unit.path, _PROJECT_ROOT), unit.path.name, unit.object_module
    )


def bind_image(units: Sequence[ModuleUnit]) -> BoundImage:
    binder = Binder(tuple(map(image_module, units)))
    ir, stub_call = job_step_module(binder)
    labels = {name: job_step_label(named_step(name)) for name in binder.entry_points()}
    ends = {
        unit.path: job_step_label(end_step(image_module(unit).name)) for unit in units
    }
    prefix = module_prefix(JOB_STEP_PATH, _PROJECT_ROOT)
    return BoundImage(
        start_up=ModuleUnit(
            path=START_UP_PATH,
            language=Language.HLASM,
            ir=bound_start_up(binder),
            exports=ExportTable(),
            imports=(),
        ),
        job_step=ModuleUnit(
            path=JOB_STEP_PATH,
            language=Language.HLASM,
            ir=ir,
            exports=ExportTable(
                functions={
                    **{
                        FuncName(str(label)): label
                        for label in (*labels.values(), *ends.values())
                    },
                    FuncName(stub_call.name): stub_call.label,
                }
            ),
            imports=(),
            diagnostics=binder.warnings(),
        ),
        programs={name: label.namespace(prefix) for name, label in labels.items()},
        module_entries={path: label.namespace(prefix) for path, label in ends.items()},
    )
