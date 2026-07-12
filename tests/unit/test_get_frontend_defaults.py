import inspect

from interpreter.frontend import get_frontend
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_get_frontend_defaults_away_from_none_except_deferred():
    sig = inspect.signature(get_frontend)
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["dialect_parsers"].default == ()
    assert sig.parameters["llm_client"].default is None
    assert "cobol_parser" not in sig.parameters
