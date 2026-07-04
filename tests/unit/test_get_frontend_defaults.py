import inspect

from interpreter.frontend import get_frontend
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_get_frontend_defaults_away_from_none_except_deferred():
    sig = inspect.signature(get_frontend)
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["dialect_parsers"].default == ()
    # Deferred to red-dragon-79iv — untouched in this plan
    assert sig.parameters["cobol_parser"].default is None
    assert sig.parameters["llm_client"].default is None
