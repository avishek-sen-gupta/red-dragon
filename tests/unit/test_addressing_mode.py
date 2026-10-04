"""Each LP setting resolves to the signed binary pointer type of its width."""

from cobol_asg.lp import LP
from cobol_asg.resolve_addressing_mode import addressing_mode
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_lp_setting_gives_a_signed_binary_pointer_of_its_width() -> None:
    assert tuple(
        (
            addressing_mode(lp).pointer_type.byte_length,
            addressing_mode(lp).pointer_type.signed,
        )
        for lp in (LP.LP32, LP.LP64)
    ) == ((4, True), (8, True))
