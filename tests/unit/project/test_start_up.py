"""The start-up module: a link carries one when its frontend supplies start-up code, as every module's dependency."""

from pathlib import Path

from interpreter.constants import Language
from interpreter.instructions import Const
from interpreter.project.start_up import START_UP_PATH, with_start_up
from interpreter.project.types import NO_MODULE_UNIT
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_start_up_code_becomes_a_module_every_module_depends_on():
    a, b = Path("A.cbl"), Path("B.cbl")
    start_up = (Const.int_(Register("%0"), 6),)
    modules, graph = with_start_up(
        start_up,
        Language.COBOL,
        {a: NO_MODULE_UNIT, b: NO_MODULE_UNIT},
        {a: [b], b: []},
    )
    assert set(modules) == {START_UP_PATH, a, b}
    assert modules[START_UP_PATH].ir == start_up
    assert modules[START_UP_PATH].language == Language.COBOL
    assert graph == {START_UP_PATH: [], a: [b, START_UP_PATH], b: [START_UP_PATH]}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_no_start_up_code_leaves_the_link_unchanged():
    a = Path("a.py")
    modules, graph = with_start_up((), Language.PYTHON, {a: NO_MODULE_UNIT}, {a: []})
    assert (modules, graph) == ({a: NO_MODULE_UNIT}, {a: []})
