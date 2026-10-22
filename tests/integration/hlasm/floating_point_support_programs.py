# pyright: standard
"""Floating-point-support programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests; FPRs and the FPC are read back through general registers."""

from collections.abc import Mapping

from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL

type Case = tuple[str, Mapping[int, int], int, str]

COMPLETED = "U0001"
SPECIFICATION = "S0C6"
DATA_EXCEPTION = "S0C7"
PRESET_CC = 2
PRESET = "         CLI   NEG,0\n"
SRC = 0x01234567_89ABCDEF
SRCP = 0xFEDCBA98_76543210
DNEG = 0x80000000_00000081
DPOS = 0x7FFFFFFF_FFFFFF7E
SIGN = 0x80000000_00000000
LOW_WORD = 0xFFFFFFFF


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<6} {operands}\n"


def _fpc(value: int) -> str:
    return _line("IILF", f"7,X'{value:08X}'") + _line("SFPC", "7")


def _stored_fpc(mnemonic: str, value: int) -> str:
    return (
        _line("IILF", f"7,X'{value:08X}'")
        + _line("ST", "7,OUT")
        + _line(mnemonic, "OUT")
    )


def _gr_fpc(mnemonic: str, value: int) -> str:
    return _line("IILF", f"7,X'{value:08X}'") + _line(mnemonic, "7")


def _low(value: int) -> int:
    return HIGH_FILL | value


def _kept(body: str, results: Mapping[int, int]) -> Case:
    return (PRESET + body, results, PRESET_CC, COMPLETED)


def _abends(body: str, abend: str) -> Case:
    return (PRESET + body + _line("LHI", "2,1"), {2: FILL}, PRESET_CC, abend)


MOVES: Mapping[str, Case] = {
    "LD LDY LDR": _kept(
        _line("LD", "1,SRC")
        + _line("LDY", "3,SRCP")
        + _line("LDR", "5,1")
        + _line("LGDR", "2,5")
        + _line("LGDR", "3,3"),
        {2: SRC, 3: SRCP},
    ),
    "LE LEY LER": _kept(
        _line("LD", "4,SRC")
        + _line("LE", "4,NEG")
        + _line("LD", "5,SRCP")
        + _line("LEY", "5,POS")
        + _line("LD", "6,DPOS")
        + _line("LER", "6,4")
        + _line("LGDR", "2,4")
        + _line("LGDR", "3,5")
        + _line("LGDR", "4,6"),
        {2: 0x80000001_89ABCDEF, 3: 0x7FFF7FFE_76543210, 4: 0x80000001_FFFFFF7E},
    ),
    "STE STEY STD STDY": _kept(
        _line("LD", "1,SRC")
        + _line("LD", "3,SRCP")
        + _line("STE", "1,OUT")
        + _line("STEY", "3,OUT+4")
        + _line("STD", "3,OUT+8")
        + _line("STDY", "1,OUT+16")
        + _line("LG", "2,OUT")
        + _line("LG", "3,OUT+8")
        + _line("LG", "4,OUT+16"),
        {2: 0x01234567_FEDCBA98, 3: SRCP, 4: SRC},
    ),
    "LDGR LGDR": _kept(
        _line("LG", "2,DNEG") + _line("LDGR", "7,2") + _line("LGDR", "3,7"),
        {2: DNEG, 3: DNEG},
    ),
    "LXR": _kept(
        _line("LD", "0,SRC")
        + _line("LD", "2,SRCP")
        + _line("LXR", "5,0")
        + _line("LGDR", "2,5")
        + _line("LGDR", "3,7"),
        {2: SRC, 3: SRCP},
    ),
    "LZER LZDR LZXR": _kept(
        _line("LD", "0,SRC")
        + _line("LD", "2,SRC")
        + _line("LD", "4,SRCP")
        + _line("LD", "6,SRC")
        + _line("LZER", "4")
        + _line("LZDR", "6")
        + _line("LZXR", "0")
        + _line("LGDR", "2,0")
        + _line("LGDR", "3,2")
        + _line("LGDR", "4,4")
        + _line("LGDR", "5,6"),
        {2: 0, 3: 0, 4: 0x76543210, 5: 0},
    ),
    "EX LER": _kept(
        _line("LD", "1,SRCP")
        + _line("LD", "2,SRC")
        + _line("LA", "7,X'12'")
        + _line("EX", "7,EXLER")
        + _line("LGDR", "2,1")
        + _line("J", "EXDONE")
        + "EXLER    LER   0,0\n"
        + "EXDONE   DS    0H\n",
        {2: 0x01234567_76543210},
    ),
    "LXR invalid pair": _abends(_line("LXR", "2,0"), SPECIFICATION),
    "LZXR invalid pair": _abends(_line("LZXR", "3"), SPECIFICATION),
}

SIGNS: Mapping[str, Case] = {
    "LCDFR LNDFR LPDFR": _kept(
        _line("LD", "1,DPOS")
        + _line("LD", "3,DNEG")
        + _line("LCDFR", "5,1")
        + _line("LNDFR", "6,1")
        + _line("LPDFR", "7,3")
        + _line("LCDFR", "8,3")
        + _line("LNDFR", "9,3")
        + _line("LPDFR", "10,1")
        + _line("LGDR", "2,5")
        + _line("LGDR", "3,6")
        + _line("LGDR", "4,7")
        + _line("LGDR", "5,8")
        + _line("LGDR", "6,9")
        + _line("LGDR", "7,10"),
        {
            2: SIGN | DPOS,
            3: SIGN | DPOS,
            4: DNEG ^ SIGN,
            5: DNEG ^ SIGN,
            6: DNEG,
            7: DPOS,
        },
    ),
    "CPSDR": _kept(
        _line("LD", "1,DPOS")
        + _line("LD", "3,DNEG")
        + _line("CPSDR", "5,3,1")
        + _line("CPSDR", "6,1,3")
        + _line("CPSDR", "7,1,1")
        + _line("LGDR", "2,5")
        + _line("LGDR", "3,6")
        + _line("LGDR", "4,7"),
        {2: SIGN | DPOS, 3: DNEG ^ SIGN, 4: DPOS},
    ),
    "sign forms on a GR image": _kept(
        _line("LDGR", "1,2")
        + _line("LCDFR", "3,1")
        + _line("LNDFR", "4,3")
        + _line("LPDFR", "5,1")
        + _line("CPSDR", "6,3,4")
        + _line("LGDR", "3,3")
        + _line("LGDR", "4,4")
        + _line("LGDR", "5,5")
        + _line("LGDR", "6,6"),
        {3: FILL ^ SIGN, 4: FILL, 5: FILL ^ SIGN, 6: FILL ^ SIGN},
    ),
    "LCDFR unnormalised": _kept(
        _line("LD", "1,SRC") + _line("LCDFR", "4,1") + _line("LGDR", "2,4"),
        {2: SIGN | SRC},
    ),
}

CONTROL: Mapping[str, Case] = {
    "EFPC initial": _kept(_line("EFPC", "2"), {2: _low(0)}),
    "SFPC EFPC": _kept(_fpc(0xFCFC1277) + _line("EFPC", "8"), {8: _low(0xFCFC1277)}),
    "LFPC STFPC": _kept(
        _stored_fpc("LFPC", 0x84001203)
        + _line("STFPC", "OUT+4")
        + _line("L", "8,OUT+4")
        + _line("EFPC", "9"),
        {8: _low(0x84001203), 9: _low(0x84001203)},
    ),
    "SRNM SRNMB SRNMT": _kept(
        _fpc(0x00000077)
        + _line("SRNM", "6")
        + _line("EFPC", "2")
        + _line("SRNMT", "2")
        + _line("EFPC", "3")
        + _line("SRNMB", "7")
        + _line("EFPC", "4")
        + _line("LA", "5,X'100'")
        + _line("SRNMB", "1(5)")
        + _line("EFPC", "6")
        + _line("SRNM", "7")
        + _line("EFPC", "8"),
        {
            2: _low(0x72),
            3: _low(0x22),
            4: _low(0x27),
            5: _low(0x100),
            6: _low(0x21),
            8: _low(0x23),
        },
    ),
    "SFASR no trap": _kept(
        _fpc(0x00F80000) + _gr_fpc("SFASR", 0x00040003) + _line("EFPC", "8"),
        {8: _low(0x00FC0003)},
    ),
    "LFAS no trap": _kept(
        _fpc(0x08F80000) + _stored_fpc("LFAS", 0x04041201) + _line("EFPC", "8"),
        {8: _low(0x04FC1201)},
    ),
}

CHECKED: Mapping[str, tuple[Case, int]] = {
    "SFPC bit 6": (_abends(_fpc(1) + _fpc(0x02000000), SPECIFICATION), 1),
    "SFPC bit 15": (_abends(_fpc(1) + _fpc(0x00010000), SPECIFICATION), 1),
    "SFPC bit 24": (_abends(_fpc(1) + _fpc(0x00000080), SPECIFICATION), 1),
    "SFPC bit 28": (_abends(_fpc(1) + _fpc(0x00000008), SPECIFICATION), 1),
    "SFPC mode 5": (_abends(_fpc(1) + _fpc(0x00000005), SPECIFICATION), 1),
    "LFPC mode 6": (
        _abends(_fpc(1) + _stored_fpc("LFPC", 0x00000006), SPECIFICATION),
        1,
    ),
    "SFASR mode 4": (
        _abends(_fpc(1) + _gr_fpc("SFASR", 0x00000004), SPECIFICATION),
        1,
    ),
    "LFAS bit 7": (
        _abends(_fpc(1) + _stored_fpc("LFAS", 0x01000000), SPECIFICATION),
        1,
    ),
    "SRNMB mode 5": (_abends(_fpc(1) + _line("SRNMB", "5"), SPECIFICATION), 1),
    "SRNMB bit 60": (_abends(_fpc(1) + _line("SRNMB", "8"), SPECIFICATION), 1),
    "SFASR invalid trap": (
        _abends(_fpc(0x00800000) + _gr_fpc("SFASR", 0x80000000), DATA_EXCEPTION),
        0x80808300,
    ),
    "SFASR division trap": (
        _abends(_fpc(0x00C00000) + _gr_fpc("SFASR", 0x40000000), DATA_EXCEPTION),
        0x40C04300,
    ),
    "SFASR overflow trap inexact": (
        _abends(_fpc(0x00280000) + _gr_fpc("SFASR", 0x20000000), DATA_EXCEPTION),
        0x20282B00,
    ),
    "SFASR underflow trap": (
        _abends(_fpc(0x00100000) + _gr_fpc("SFASR", 0x18000001), DATA_EXCEPTION),
        0x18101301,
    ),
    "SFASR overflow trap exact": (
        _abends(_fpc(0x00200000) + _gr_fpc("SFASR", 0x20000000), DATA_EXCEPTION),
        0x20202300,
    ),
    "LFAS underflow trap inexact": (
        _abends(_fpc(0x00180000) + _stored_fpc("LFAS", 0x10000000), DATA_EXCEPTION),
        0x10181B00,
    ),
    "SFASR priority": (
        _abends(_fpc(0x00880000) + _gr_fpc("SFASR", 0x88000000), DATA_EXCEPTION),
        0x88888300,
    ),
    "LFAS inexact trap": (
        _abends(_fpc(0x000C0000) + _stored_fpc("LFAS", 0x08004470), DATA_EXCEPTION),
        0x080C0B70,
    ),
    "LFAS quantum trap": (
        _abends(_fpc(0x00040000) + _stored_fpc("LFAS", 0x04000000), DATA_EXCEPTION),
        0x04040700,
    ),
}

CASES: Mapping[str, Case] = {
    **MOVES,
    **SIGNS,
    **CONTROL,
    **{name: case for name, (case, _) in CHECKED.items()},
}


def expected(case: str) -> HlasmMachine:
    _, registers, cc, abend = CASES[case]
    return HlasmMachine(HlasmRun(return_code=0, abend=abend, stdout=""), cc, registers)
