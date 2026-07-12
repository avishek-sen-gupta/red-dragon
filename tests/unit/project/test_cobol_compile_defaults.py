import inspect

from interpreter.project.cobol_compile import compile_cobol, compile_cobol_module
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_module_defaults_away_from_none():
    sig = inspect.signature(compile_cobol_module)
    assert sig.parameters["copybook_dirs"].default == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_defaults_away_from_none():
    sig = inspect.signature(compile_cobol)
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["extra_subprogram_sources"].default == {}
    assert sig.parameters["program_source_dirs"].default == ()
    # ast_cache_dir stays untouched — deferred, ephemeral-vs-owned lifecycle sentinel
    assert sig.parameters["ast_cache_dir"].default is None
