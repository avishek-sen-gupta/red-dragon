import inspect

from interpreter.project.compiler import compile_module
from tests.covers import covers, NotLanguageFeature


class TestCompileCopybookDirsDefault:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_copybook_dirs_defaults_to_empty_list(self):
        sig = inspect.signature(compile_module)
        assert sig.parameters["copybook_dirs"].default == []
        # source stays untouched — deferred, its None means "derive from file_path"
        assert sig.parameters["source"].default is None
