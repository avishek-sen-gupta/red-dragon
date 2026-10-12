"""The COBOL run unit's region: its layout, and the start-up code the COBOL frontend supplies to allocate it."""

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.run_unit import (
    RANDOM_STATE,
    RUN_UNIT_LAYOUT,
    RUN_UNIT_RETURN_CODE,
    RUN_UNIT_VAR,
    run_unit_allocation,
)
from interpreter.instructions import AllocRegion, Const, DeclVar
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_cobol_frontend_starts_a_link_by_allocating_the_run_unit_region():
    size, alloc, decl = run_unit_allocation()
    assert isinstance(size, Const) and size.value == 6
    assert isinstance(alloc, AllocRegion) and alloc.size_reg == size.result_reg
    assert isinstance(decl, DeclVar) and decl.name == RUN_UNIT_VAR
    assert decl.value_reg == alloc.result_reg
    assert CobolFrontend(make_cobol_parser()).start_up_ir() == (size, alloc, decl)
    rc = RUN_UNIT_LAYOUT.lookup_or_raise(RUN_UNIT_RETURN_CODE)
    state = RUN_UNIT_LAYOUT.lookup_or_raise(RANDOM_STATE)
    assert (rc.offset, rc.byte_length, state.offset, state.byte_length) == (0, 2, 2, 4)
