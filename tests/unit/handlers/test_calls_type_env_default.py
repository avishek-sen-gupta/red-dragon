import inspect

from interpreter.handlers.calls import _try_class_constructor_call
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_type_env_defaults_away_from_none():
    sig = inspect.signature(_try_class_constructor_call)
    assert sig.parameters["type_env"].default is not None
