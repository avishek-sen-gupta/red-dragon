import inspect

from interpreter.frontend import get_frontend
from interpreter.frontends import get_cobol_frontend
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_get_frontend_defaults_away_from_none_except_deferred():
    sig = inspect.signature(get_frontend)
    cobol_sig = inspect.signature(get_cobol_frontend)
    assert cobol_sig.parameters["copybook_dirs"].default == ()
    assert cobol_sig.parameters["dialect_parsers"].default == ()
    assert sig.parameters["llm_client"].default is None
    assert "cobol_parser" not in sig.parameters
    assert "copybook_dirs" not in sig.parameters
