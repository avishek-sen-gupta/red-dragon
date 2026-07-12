import inspect

from interpreter.cobol.lower_arithmetic import _store_move_value
from interpreter.register import NO_REGISTER
from tests.covers import NotLanguageFeature, covers


class TestStoreMovValueDefault:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_zoned_display_reg_defaults_to_no_register(self):
        sig = inspect.signature(_store_move_value)
        assert sig.parameters["zoned_display_reg"].default is NO_REGISTER
