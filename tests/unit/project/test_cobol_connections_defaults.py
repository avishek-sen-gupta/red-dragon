import inspect

from interpreter.project.cobol_connections import extract_cobol_connections
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_extract_cobol_connections_defaults_away_from_none():
    sig = inspect.signature(extract_cobol_connections)
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["program_source_dirs"].default == ()
    assert sig.parameters["extra_subprogram_sources"].default == {}
    assert sig.parameters["dialect_parsers"].default == ()
