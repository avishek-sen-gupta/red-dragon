import inspect

from interpreter.cobol.real_file_provider import RealFileIOProvider
from tests.covers import NotLanguageFeature, covers


class TestRealFileIOProviderDefaults:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_file_control_and_path_overrides_default_to_empty(self):
        sig = inspect.signature(RealFileIOProvider.__init__)
        assert sig.parameters["file_control"].default == []
        assert sig.parameters["path_overrides"].default == {}
