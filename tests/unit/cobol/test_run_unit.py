"""The COBOL run unit's region and EXTERNAL directories: the region's layout, and the
start-up code the COBOL frontend supplies to set them up."""

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.external_area import ExternalKind, external_directory
from interpreter.cobol.run_unit import (
    RANDOM_STATE,
    RUN_UNIT_LAYOUT,
    RUN_UNIT_RETURN_CODE,
    RUN_UNIT_VAR,
    run_unit_allocation,
)
from interpreter.instructions import AllocRegion, Const, DeclVar, NewObject
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_cobol_frontend_starts_a_link_by_allocating_the_run_unit_region():
    size, region, records, files = (Register(f"%{n}") for n in range(4))
    expected = (
        Const.int_(size, 6),
        AllocRegion(result_reg=region, size_reg=size),
        DeclVar(name=RUN_UNIT_VAR, value_reg=region),
        NewObject(result_reg=records),
        DeclVar(name=external_directory(ExternalKind.RECORD), value_reg=records),
        NewObject(result_reg=files),
        DeclVar(name=external_directory(ExternalKind.FILE), value_reg=files),
    )
    assert (
        run_unit_allocation(),
        CobolFrontend(make_cobol_parser()).start_up_ir(),
    ) == (expected, expected)
    rc = RUN_UNIT_LAYOUT.lookup_or_raise(RUN_UNIT_RETURN_CODE)
    state = RUN_UNIT_LAYOUT.lookup_or_raise(RANDOM_STATE)
    assert (rc.offset, rc.byte_length, state.offset, state.byte_length) == (0, 2, 2, 4)
