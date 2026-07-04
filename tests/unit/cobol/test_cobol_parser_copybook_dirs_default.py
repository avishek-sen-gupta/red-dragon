import inspect

from interpreter.cobol.cobol_parser import ProLeapCobolParser, make_cobol_parser
from tests.covers import NotLanguageFeature, covers


class TestCopybookDirsDefaults:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_proleap_cobol_parser_copybook_dirs_defaults_to_empty_list(self):
        sig = inspect.signature(ProLeapCobolParser.__init__)
        assert sig.parameters["copybook_dirs"].default == []

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_make_cobol_parser_copybook_dirs_defaults_to_empty_list(self):
        sig = inspect.signature(make_cobol_parser)
        assert sig.parameters["copybook_dirs"].default == []
