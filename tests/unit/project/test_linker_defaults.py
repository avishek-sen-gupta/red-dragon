import inspect

from interpreter.project.linker import link_modules
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_data_layout_and_type_env_builder_default_away_from_none():
    sig = inspect.signature(link_modules)
    assert sig.parameters["data_layout"].default == {}
    assert sig.parameters["type_env_builder"].default is not None
    # symbol_table stays untouched — deferred, mutated in place downstream
    assert sig.parameters["symbol_table"].default is None
