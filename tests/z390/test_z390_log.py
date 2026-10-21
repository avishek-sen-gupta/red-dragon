# pyright: standard
"""An abending z390 LOG yields the run, the PSW condition code (short or AMODE 64 PSW) and the dumped registers."""

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import hlasm_machine_of_log

AMODE_64_PSW = (
    "EZ390E error  11 ABEND PSW=0785360180000000 00000000000FFEEC 0A0D"
    "         SVC   ABEND U0042"
)

ABENDED_LOG = (
    "16:57:43 PROG      EZ390 START USING z390 V1.8.05 ON J2SE 21.0.12 10/21/26",
    "EZ390I options = ",
    "EZ390I Trace Table Entry      800FFFE0 0DC0         BASR ",
    "EZ390E error  11 ABEND PSW=07852600 800FFFF0 0A0D         SVC   ABEND U0042",
    " R0-R3 F4F4F4F4800FFFE0 F4F4F4F40000002A F4F4F4F400000005 8000000000000001",
    " R4-R7 F4F4F4F4F4F4F4F4 F4F4F4F4F4F4F4F4 F4F4F4F4F4F4F4F4 F4F4F4F4F4F4F4F4",
    " R8-RB F4F4F4F4F4F4F4F4 F4F4F4F4F4F4F4F4 F4F4F4F4F4F4F4F4 F4F4F4F4F4F4F4F4",
    " RC-RF F4F4F4F4800FFFE2 F4F4F4F400002100 F4F4F4F400002018 F4F4F4F4800FFFE0",
    "EZ390E error  12 program aborting due to abend U0042",
    "EZ390I instructions/sec     = 100",
    "16:57:43 PROG      EZ390 ENDED   RC=16 SEC= 0 MEM(MB)=  7 IO=34 INS=5",
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_abend_dump_gives_cc_and_registers():
    machine = hlasm_machine_of_log(ABENDED_LOG)

    assert machine.restricted_to((2, 3, 12, 15)) == HlasmMachine(
        run=HlasmRun(return_code=0, abend="U0042", stdout=""),
        cc=2,
        gprs={
            2: 0xF4F4F4F400000005,
            3: 0x8000000000000001,
            12: 0xF4F4F4F4800FFFE2,
            15: 0xF4F4F4F4800FFFE0,
        },
    )
    assert sorted(machine.gprs) == list(range(16))
    assert (
        hlasm_machine_of_log(
            tuple(AMODE_64_PSW if "ABEND PSW" in line else line for line in ABENDED_LOG)
        ).cc
        == 3
    )
