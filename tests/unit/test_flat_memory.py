"""Regions are segments of one flat address space: allocated contiguously from
4096, resolved by address, and a read or write past a segment's end carries on
into the following segments."""

from __future__ import annotations

import logging

import pytest

from interpreter.address import Address
from interpreter.func_name import FuncName
from interpreter.vm.segment import Segment
from interpreter.vm.vm import apply_update
from interpreter.vm.vm_types import RegionWrite, StackFrame, StateUpdate, VMState
from tests.covers import NotLanguageFeature, covers


def _vm(*regions: tuple[str, bytes]) -> VMState:
    vm = VMState(call_stack=[StackFrame(function_name=FuncName("f"))])
    for name, data in regions:
        vm.region_set(Address(name), bytearray(data))
    return vm


def _write(vm: VMState, name: str, offset: int, data: bytes) -> None:
    apply_update(
        vm,
        StateUpdate(
            region_writes=[
                RegionWrite(
                    address=vm.segment_of(Address(name)).base + offset, data=list(data)
                )
            ]
        ),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_regions_are_segments_allocated_contiguously_from_4096() -> None:
    vm = _vm(("rgn_named", b"abc"), ("rgn_other", b"defgh"))
    apply_update(vm, StateUpdate(new_regions={"rgn_9": 2}))

    assert (
        vm.segment_of(Address("rgn_named")),
        vm.segment_of(Address("rgn_other")),
        vm.segment_of(Address("rgn_9")),
        vm.read_at(4098, 3),
    ) == (
        Segment(base=4096, size=3),
        Segment(base=4099, size=5),
        Segment(base=4104, size=2),
        b"cde",
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_write_past_a_segment_end_carries_into_the_next_and_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    vm = _vm(("rgn_a", b"\x00\x00"), ("rgn_b", b"\x00\x00\x00"))

    with caplog.at_level(logging.WARNING):
        _write(vm, "rgn_a", 1, b"\x01\x02\x03")

    assert (
        bytes(vm.region_get(Address("rgn_a")) or b""),
        bytes(vm.region_get(Address("rgn_b")) or b""),
        caplog.messages,
    ) == (
        b"\x00\x01",
        b"\x02\x03\x00",
        ["write of 3 bytes at address 4097 crosses a segment end"],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_write_past_the_last_segment_drops_the_overrun_and_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    vm = _vm(("rgn_a", b"\x00\x00"))

    with caplog.at_level(logging.WARNING):
        _write(vm, "rgn_a", 1, b"\x07\x08\x09")

    assert (bytes(vm.region_get(Address("rgn_a")) or b""), caplog.messages) == (
        b"\x00\x07",
        [
            "write of 3 bytes at address 4097 crosses a segment end",
            "write of 3 bytes at address 4097 runs 2 bytes past the last segment",
        ],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_read_past_a_segment_end_returns_the_following_bytes_and_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    vm = _vm(("rgn_a", b"\x01\x02"), ("rgn_b", b"\x03\x04"))

    with caplog.at_level(logging.WARNING):
        read = vm.read_at(4097, 5)

    assert (read, caplog.messages) == (
        b"\x02\x03\x04",
        [
            "read of 5 bytes at address 4097 crosses a segment end",
            "read of 5 bytes at address 4097 runs 2 bytes past the last segment",
        ],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_region_set_on_an_existing_region_writes_in_place_and_keeps_its_size() -> None:
    vm = _vm(("rgn_a", b"ab"))
    live = vm.region_get(Address("rgn_a"))

    vm.region_set(Address("rgn_a"), bytearray(b"xy"))

    with pytest.raises(ValueError, match="rgn_a is 2 bytes; cannot set 3"):
        vm.region_set(Address("rgn_a"), bytearray(b"xyz"))
    assert (bytes(live or b""), vm.segment_of(Address("rgn_a"))) == (
        b"xy",
        Segment(base=4096, size=2),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_access_across_an_empty_regions_address_stays_aligned() -> None:
    vm = _vm(("rgn_empty", b""), ("rgn_b", b"\x01\x02\x03"))

    read = vm.read_at(4096, 3)
    vm.write_at(4096, b"\x09\x08")

    assert (read, bytes(vm.region_get(Address("rgn_b")) or b"")) == (
        b"\x00\x01\x02",
        b"\x08\x02\x03",
    )
