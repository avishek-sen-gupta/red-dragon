# pyright: standard
"""Load address and immediate programs shared by the VM tests and the z390 differential tests."""

from tests.integration.hlasm.load_store_programs import HIGH_FILL

CC_TWO = 2
SET_CC_TWO = "         LA    9,1\n" "         SR    9,10\n"

ADDRESSES = (
    f"{SET_CC_TWO}"
    "         LG    3,DNEG\n"
    "         LG    5,DPOS\n"
    "         LA    4,2(3,5)\n"
    "         LAY   6,-3(3)\n"
    "         LAE   7,5(3)\n"
    "         LAEY  8,-128(3)\n"
    "         LA    9,X'FFF'\n"
    "         LARL  10,POS\n"
    "         L     11,0(10)\n"
)
ADDRESSES_RESULTS = {
    4: HIGH_FILL | 0x00000001,
    6: HIGH_FILL | 0x0000007E,
    7: HIGH_FILL | 0x00000086,
    8: HIGH_FILL | 0x00000001,
    9: HIGH_FILL | 0x00000FFF,
    11: HIGH_FILL | 0x7FFF7FFE,
}

BEYOND_STORAGE = (
    "         LG    3,DNEG\n"
    "         LG    5,DPOS\n"
    "         LAE   7,0(5)\n"
    "         LAEY  8,-130(3)\n"
)
BEYOND_STORAGE_RESULTS = {7: HIGH_FILL | 0x7FFFFF7E, 8: HIGH_FILL | 0x7FFFFFFF}

SAME_ADDRESS = "         LARL  10,POS\n" "         LA    11,POS\n"

OTHER_SECTION = "         LARL  2,POS\n" "         L     3,0(2)\n"
OTHER_SECTION_RESULTS = {3: 0x7FFF7FFE}

INDEXED = (
    f"{SET_CC_TWO}"
    "         LG    3,DNEG\n"
    "         LG    4,SRC\n"
    "         LXAB  2,1(3,4)\n"
    "         LXAH  6,1(3,4)\n"
    "         LXAF  7,-130(3,4)\n"
    "         LXAG  8,0(3)\n"
    "         LXAQ  9,2(3,4)\n"
)
INDEXED_RESULTS = {
    2: HIGH_FILL | 0x09ABCE71,
    6: HIGH_FILL | 0x09ABCEF3,
    7: HIGH_FILL | 0x09ABCDEB,
    8: HIGH_FILL | 0x00000408,
    9: HIGH_FILL | 0x09ABD61F,
}

LOGICAL_INDEXED = (
    f"{SET_CC_TWO}"
    "         LG    3,DNEG\n"
    "         LG    4,SRC\n"
    "         LLXAB 2,1(3,4)\n"
    "         LLXAH 6,1(3,4)\n"
    "         LLXAF 7,-130(3,4)\n"
    "         LLXAG 8,5(,4)\n"
    "         LLXAQ 9,2(3,4)\n"
)
LOGICAL_INDEXED_RESULTS = {
    2: HIGH_FILL | 0x09ABCE71,
    6: HIGH_FILL | 0x09ABCEF3,
    7: HIGH_FILL | 0x09ABCDEB,
    8: HIGH_FILL | 0x09ABCE17,
    9: HIGH_FILL | 0x09ABD61F,
}

LOADED_IMMEDIATES = (
    f"{SET_CC_TWO}"
    "         LHI   2,-2\n"
    "         LHI   3,X'7FFF'\n"
    "         LGHI  4,-32768\n"
    "         LGFI  5,-2147483647\n"
    "         LGFI  6,X'12345678'\n"
    "         LLIHF 7,X'89ABCDEF'\n"
    "         LLIHH 8,X'8001'\n"
    "         LLIHL 9,X'8002'\n"
    "         LLILF 10,X'FFFFFFFE'\n"
    "         LLILH 11,X'8003'\n"
)
LOADED_IMMEDIATES_RESULTS = {
    2: HIGH_FILL | 0xFFFFFFFE,
    3: HIGH_FILL | 0x00007FFF,
    4: 0xFFFFFFFF_FFFF8000,
    5: 0xFFFFFFFF_80000001,
    6: 0x00000000_12345678,
    7: 0x89ABCDEF_00000000,
    8: 0x80010000_00000000,
    9: 0x00008002_00000000,
    10: 0x00000000_FFFFFFFE,
    11: 0x00000000_80030000,
}

INSERTED_IMMEDIATES = (
    f"{SET_CC_TWO}"
    "         LLILL 2,X'8004'\n"
    "         LLGFI 3,X'80000005'\n"
    "         LLGHI 4,X'FFFF'\n"
    "         LFI   5,-6\n"
    "         IIHF  6,X'01234567'\n"
    "         IIHH  7,X'8001'\n"
    "         IIHL  8,X'8002'\n"
    "         IILF  9,X'FEDCBA98'\n"
    "         IILH  10,X'8003'\n"
    "         IILL  11,X'8004'\n"
)
INSERTED_IMMEDIATES_RESULTS = {
    2: 0x00000000_00008004,
    3: 0x00000000_80000005,
    4: 0x00000000_0000FFFF,
    5: HIGH_FILL | 0xFFFFFFFA,
    6: 0x01234567_A5A5A5A5,
    7: 0x8001A5A5_A5A5A5A5,
    8: 0xA5A58002_A5A5A5A5,
    9: HIGH_FILL | 0xFEDCBA98,
    10: 0xA5A5A5A5_8003A5A5,
    11: 0xA5A5A5A5_A5A58004,
}
