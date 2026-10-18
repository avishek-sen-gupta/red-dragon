"""An access below 4096 goes to the VM's null-access strategy: warned and
ignored by default, or halting the run."""

import logging

import pytest

from interpreter.address import Address
from interpreter.vm.halt_on_null import HaltOnNull
from interpreter.vm.null_address_access import NullAddressAccess
from interpreter.vm.vm_types import SymbolicRegionWrite, SymbolicValue, VMState
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_default_strategy_reads_zeroes_drops_writes_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    vm = VMState()
    vm.region_set(Address("rgn_a"), bytearray(b"ab"))

    with caplog.at_level(logging.WARNING):
        read = vm.read_at(8, 3)
        vm.write_at(0, b"\x01\x02")
        vm.write_symbolic(
            SymbolicRegionWrite(address=4, width=2, value=SymbolicValue(name="s"))
        )
        loaded = vm.load(4, 2)

    assert (
        read,
        loaded,
        bytes(vm.region_get(Address("rgn_a")) or b""),
        caplog.messages,
    ) == (
        b"\x00\x00\x00",
        [0, 0],
        b"ab",
        [
            "read of 3 bytes at NULL-page address 8",
            "write of 2 bytes at NULL-page address 0 dropped",
            "write of 2 bytes at NULL-page address 4 dropped",
            "read of 2 bytes at NULL-page address 4",
        ],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_halting_strategy_stops_on_a_null_page_access() -> None:
    vm = VMState(null_access=HaltOnNull())

    with pytest.raises(NullAddressAccess, match="4 bytes at NULL-page address 16"):
        vm.read_at(16, 4)
