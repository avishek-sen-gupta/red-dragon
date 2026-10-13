import inspect

from interpreter.project.compiler import compile_module
from tests.covers import NotLanguageFeature, covers


class TestCompileCopybookDirsDefault:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_compile_module_takes_no_copybook_dirs(self):
        sig = inspect.signature(compile_module)
        assert "copybook_dirs" not in sig.parameters
        # source stays untouched — deferred, its None means "derive from file_path"
        assert sig.parameters["source"].default is None
