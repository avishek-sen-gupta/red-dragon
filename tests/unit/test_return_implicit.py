"""Return_.implicit distinguishes synthetic fall-through returns from real ones."""

from interpreter.instructions import Return_
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers


class TestReturnImplicitFlag:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_defaults_to_explicit(self):
        assert Return_(value_reg=Register("%0")).implicit is False

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_can_mark_implicit(self):
        assert Return_(value_reg=Register("%0"), implicit=True).implicit is True

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_implicit_survives_map_registers(self):
        inst = Return_(value_reg=Register("%0"), implicit=True)
        mapped = inst.map_registers(lambda r: r.rebase(100))
        assert mapped.implicit is True
        assert mapped.value_reg == Register("%100")
