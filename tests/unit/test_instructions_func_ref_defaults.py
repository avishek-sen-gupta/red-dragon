import inspect

from interpreter.instructions import Const
from tests.covers import NotLanguageFeature, covers


class TestConstFuncRefDefaults:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_func_ref_params_defaults_to_empty_list(self):
        sig = inspect.signature(Const.func_ref)
        assert sig.parameters["params"].default == []
