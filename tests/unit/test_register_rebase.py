"""Tests for Register.rebase() — offset numeric suffix in register names."""

from interpreter.register import Register, NO_REGISTER


class TestRegisterRebase:
    def test_simple_rebase(self):
        reg = Register("%r0")
        assert reg.rebase(100) == Register("%r100")

    def test_rebase_nonzero(self):
        reg = Register("%r5")
        assert reg.rebase(10) == Register("%r15")

    def test_rebase_zero_offset(self):
        reg = Register("%r42")
        assert reg.rebase(0) == Register("%r42")

    def test_rebase_non_numeric_suffix(self):
        """Non-numeric register names are returned unchanged."""
        reg = Register("%tmp")
        assert reg.rebase(100) == Register("%tmp")

    def test_rebase_no_prefix(self):
        """Register names without % prefix still rebase."""
        reg = Register("r5")
        assert reg.rebase(10) == Register("r15")

    def test_no_register_rebase(self):
        """NO_REGISTER.rebase() returns NO_REGISTER."""
        assert NO_REGISTER.rebase(100) is NO_REGISTER
