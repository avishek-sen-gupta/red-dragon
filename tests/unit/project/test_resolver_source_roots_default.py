import inspect

from interpreter.project.resolver import JavaImportResolver
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_source_roots_defaults_to_empty_list():
    sig = inspect.signature(JavaImportResolver.__init__)
    assert sig.parameters["source_roots"].default == []
