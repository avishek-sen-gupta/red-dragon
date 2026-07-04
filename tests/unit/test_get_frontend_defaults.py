import inspect

from interpreter.frontend import get_frontend, _NO_CICS_TEXT_PARSER
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_get_frontend_defaults_away_from_none_except_deferred():
    sig = inspect.signature(get_frontend)
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["cics_text_parser"].default is _NO_CICS_TEXT_PARSER
    # Deferred to red-dragon-79iv — untouched in this plan
    assert sig.parameters["cobol_parser"].default is None
    assert sig.parameters["llm_client"].default is None
