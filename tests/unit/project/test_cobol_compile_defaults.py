import inspect

from interpreter.project.cobol_compile import compile_cobol, compile_cobol_module
from interpreter.project.coprocessor_compile import compile_program
from interpreter.project.fresh_work_dir import FRESH_WORK_DIR
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_module_defaults_away_from_none():
    sig = inspect.signature(compile_cobol_module)
    assert sig.parameters["copybook_dirs"].default == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_defaults_away_from_none():
    sig = inspect.signature(compile_cobol)
    assert sig.parameters["copybook_dirs"].default == ()
    assert sig.parameters["programs"].default == ()
    assert "source_search_dirs" not in sig.parameters
    assert sig.parameters["work_dir"].default is FRESH_WORK_DIR
    assert (
        inspect.signature(compile_program).parameters["work_dir"].default
        is FRESH_WORK_DIR
    )
