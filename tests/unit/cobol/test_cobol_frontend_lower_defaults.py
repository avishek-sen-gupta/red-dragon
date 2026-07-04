import inspect

from interpreter.cobol.cobol_frontend import CobolFrontend
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_resolved_imports_defaults_to_empty_dict():
    """Test that resolved_imports parameter defaults to {} instead of None."""
    sig = inspect.signature(CobolFrontend.lower)
    assert sig.parameters["resolved_imports"].default == {}
