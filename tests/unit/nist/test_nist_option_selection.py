"""The NIST harness activates the optional-code variant a program's table entry selects."""

from __future__ import annotations

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.nist.conftest import (
    OPTION_SELECTIONS,
    programs_offering_variants,
    select_option,
)
from tests.nist.nist_option import OptionSelection

_INSTRUCTION = "*               WITH LETTERS T OR U ONLY ONE SHOULD BE SELECTED."
_T_CARD = "           15 FILLER              PIC X(24)."
_U_CARD = "        10 FILLER                 PIC X(24)."
_SELECT_T = OptionSelection(letter="T", cards=frozenset({"000300"}))


def _deck(*lines: tuple[str, str]) -> str:
    return "\n".join(f"{n}{text}".ljust(72) + "XX9994.2" for n, text in lines)


def _variant_deck(t_indicator: str) -> str:
    return _deck(
        ("000100", _INSTRUCTION),
        ("000200", "     10 XX-KEY."),
        ("000300", t_indicator + _T_CARD[1:]),
        ("000400", "*" + _U_CARD[1:]),
        ("000500", "*    MOVE 1 TO X."),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_selected_variant_cards_are_activated_and_nothing_else_changes() -> None:
    assert select_option(_variant_deck("*"), "XX999A", _SELECT_T) == _variant_deck(" ")


def _refusal(src: str) -> str:
    with pytest.raises(AssertionError) as refused:
        select_option(src, "XX999A", _SELECT_T)
    return str(refused.value).splitlines()[0]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_selection_the_source_does_not_bear_out_fails_loudly() -> None:
    no_instruction = _deck(("000300", "*" + _T_CARD[1:]))
    already_active = _variant_deck(" ")
    missing_card = _deck(("000100", _INSTRUCTION), ("000400", "*" + _U_CARD[1:]))

    messages = [_refusal(src) for src in (no_instruction, already_active, missing_card)]

    assert (
        messages
        == [
            "XX999A: not a program offering the T variant it is configured to select",
        ]
        * 3
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_corpus_program_offering_t_or_u_selects_a_variant() -> None:
    assert (programs_offering_variants(), tuple(OPTION_SELECTIONS)) == (
        ("IX107A", "IX207A", "IX208A"),
    ) * 2
