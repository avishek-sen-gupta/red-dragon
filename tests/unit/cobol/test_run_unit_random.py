"""FUNCTION RANDOM's generator, per Enterprise COBOL 6.5 Language Reference ch. 83:
seed 0 when the first reference has no argument, the same sequence for the same
seed, and values strictly between zero and one."""

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.run_unit import advanced, restarted, value_of
from tests.covers import covers

_M = 2**31 - 1


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_the_sequence_starts_at_seed_zero_and_repeats_for_the_same_seed():
    unseeded = advanced(0)
    seeded_zero = restarted(0)
    assert unseeded == seeded_zero == 16807
    assert advanced(unseeded) == advanced(seeded_zero) == 16807 * 16807 % _M
    assert restarted(42) == 43 * 16807 % _M
    assert restarted(2_147_483_646) == restarted(0)
    assert restarted(-5) == restarted(0)
    assert value_of(16807) == 16807 / _M
    assert 0 < value_of(1) < value_of(_M - 1) < 1
