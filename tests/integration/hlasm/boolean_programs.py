# pyright: standard
"""Boolean programs, one per mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

CC_ZERO = 0
CC_NONZERO = 1
ONES_64 = 0xFFFFFFFF_FFFFFFFF

ANDS: Mapping[str, Case] = {
    "N": ("         L     2,NEG\n" "         N     2,POS\n", {2: HIGH_FILL}, CC_ZERO),
    "NY": (
        "         L     3,NEG\n" "         NY    3,NEG\n",
        {3: HIGH_FILL | 0x80000001},
        CC_NONZERO,
    ),
    "NR": (
        "         LHI   4,-1\n" "         L     5,POS\n" "         NR    4,5\n",
        {4: HIGH_FILL | 0x7FFF7FFE},
        CC_NONZERO,
    ),
    "NRK": (
        "         L     3,NEG\n" "         L     4,POS\n" "         NRK   5,3,4\n",
        {3: HIGH_FILL | 0x80000001, 4: HIGH_FILL | 0x7FFF7FFE, 5: HIGH_FILL},
        CC_ZERO,
    ),
    "NG": ("         LG    2,SRC\n" "         NG    2,SRCP\n", {2: 0}, CC_ZERO),
    "NGR": (
        "         LG    3,DNEG\n" "         LG    4,SRC\n" "         NGR   3,4\n",
        {3: 0x00000000_00000081},
        CC_NONZERO,
    ),
    "NGRK": (
        "         LG    3,SRC\n" "         LGHI  4,-256\n" "         NGRK  5,3,4\n",
        {5: 0x01234567_89ABCD00},
        CC_NONZERO,
    ),
}

ORS: Mapping[str, Case] = {
    "O": ("         LHI   2,0\n" "         O     2,ZERO\n", {2: HIGH_FILL}, CC_ZERO),
    "OY": (
        "         L     3,NEG\n" "         OY    3,POS\n",
        {3: HIGH_FILL | 0xFFFF7FFF},
        CC_NONZERO,
    ),
    "OR": (
        "         L     4,NEG\n" "         LHI   5,2\n" "         OR    4,5\n",
        {4: HIGH_FILL | 0x80000003},
        CC_NONZERO,
    ),
    "ORK": (
        "         LHI   3,0\n" "         LHI   4,0\n" "         ORK   5,3,4\n",
        {5: HIGH_FILL},
        CC_ZERO,
    ),
    "OG": (
        "         LG    2,SRC\n" "         OG    2,SRCP\n",
        {2: ONES_64},
        CC_NONZERO,
    ),
    "OGR": (
        "         LGHI  3,0\n" "         LGHI  4,0\n" "         OGR   3,4\n",
        {3: 0},
        CC_ZERO,
    ),
    "OGRK": (
        "         LG    3,DNEG\n" "         LGHI  4,2\n" "         OGRK  5,3,4\n",
        {5: 0x80000000_00000083},
        CC_NONZERO,
    ),
}

EXCLUSIVE_ORS: Mapping[str, Case] = {
    "X": ("         L     2,NEG\n" "         X     2,NEG\n", {2: HIGH_FILL}, CC_ZERO),
    "XY": (
        "         L     3,NEG\n" "         XY    3,POS\n",
        {3: HIGH_FILL | 0xFFFF7FFF},
        CC_NONZERO,
    ),
    "XR": (
        "         LHI   4,-1\n" "         L     5,NEG\n" "         XR    4,5\n",
        {4: HIGH_FILL | 0x7FFFFFFE},
        CC_NONZERO,
    ),
    "XRK": (
        "         L     3,POS\n" "         L     4,POS\n" "         XRK   5,3,4\n",
        {5: HIGH_FILL},
        CC_ZERO,
    ),
    "XG": (
        "         LG    2,SRC\n" "         XG    2,SRCP\n",
        {2: ONES_64},
        CC_NONZERO,
    ),
    "XGR": ("         LG    3,DPOS\n" "         XGR   3,3\n", {3: 0}, CC_ZERO),
    "XGRK": (
        "         LG    3,DNEG\n" "         LG    4,DPOS\n" "         XGRK  5,3,4\n",
        {5: ONES_64},
        CC_NONZERO,
    ),
}

DISTINCT_CONNECTIVES: Mapping[str, Case] = {
    "NCRK": (
        "         LHI   3,-1\n" "         L     4,POS\n" "         NCRK  5,3,4\n",
        {5: HIGH_FILL | 0x80008001},
        CC_NONZERO,
    ),
    "NCGRK": (
        "         LG    3,DNEG\n" "         LGHI  4,-1\n" "         NCGRK 5,3,4\n",
        {5: 0},
        CC_ZERO,
    ),
    "OCRK": (
        "         LHI   3,0\n" "         LHI   4,-1\n" "         OCRK  5,3,4\n",
        {5: HIGH_FILL},
        CC_ZERO,
    ),
    "OCGRK": (
        "         LGHI  3,0\n" "         LG    4,DPOS\n" "         OCGRK 5,3,4\n",
        {5: 0x80000000_00000081},
        CC_NONZERO,
    ),
    "NNRK": (
        "         L     3,NEG\n" "         L     4,POS\n" "         NNRK  5,3,4\n",
        {5: HIGH_FILL | 0xFFFFFFFF},
        CC_NONZERO,
    ),
    "NNGRK": (
        "         LGHI  3,-1\n" "         LGHI  4,-1\n" "         NNGRK 5,3,4\n",
        {5: 0},
        CC_ZERO,
    ),
    "NORK": (
        "         LHI   3,-1\n" "         L     4,POS\n" "         NORK  5,3,4\n",
        {5: HIGH_FILL},
        CC_ZERO,
    ),
    "NOGRK": (
        "         LGHI  3,0\n" "         LG    4,SRC\n" "         NOGRK 5,3,4\n",
        {5: 0xFEDCBA98_76543210},
        CC_NONZERO,
    ),
    "NOTR": (
        "         L     3,POS\n" "         NOTR  5,3\n",
        {3: HIGH_FILL | 0x7FFF7FFE, 5: HIGH_FILL | 0x80008001},
        CC_NONZERO,
    ),
    "NOTGR": ("         LGHI  3,-1\n" "         NOTGR 5,3\n", {5: 0}, CC_ZERO),
    "NXRK": (
        "         L     3,NEG\n" "         L     4,NEG\n" "         NXRK  5,3,4\n",
        {5: HIGH_FILL | 0xFFFFFFFF},
        CC_NONZERO,
    ),
    "NXGRK": (
        "         LG    3,SRC\n" "         LG    4,SRCP\n" "         NXGRK 5,3,4\n",
        {5: 0},
        CC_ZERO,
    ),
}

STORAGE_IMMEDIATES: Mapping[str, Case] = {
    "NI": (
        "         NI    OUT,X'0F'\n" "         LLC   7,OUT\n",
        {7: HIGH_FILL | 0x0F},
        CC_NONZERO,
    ),
    "NIY": (
        "         NIY   OUT+1,X'00'\n" "         LLC   7,OUT+1\n",
        {7: HIGH_FILL},
        CC_ZERO,
    ),
    "OI": (
        "         LHI   2,0\n"
        "         STC   2,OUT\n"
        "         OI    OUT,X'80'\n"
        "         LLC   7,OUT\n",
        {7: HIGH_FILL | 0x80},
        CC_NONZERO,
    ),
    "OIY": (
        "         LHI   2,0\n"
        "         STC   2,OUT\n"
        "         OIY   OUT,X'00'\n"
        "         LLC   7,OUT\n",
        {7: HIGH_FILL},
        CC_ZERO,
    ),
    "XI": (
        "         XI    OUT,X'FF'\n" "         LLC   7,OUT\n",
        {7: HIGH_FILL},
        CC_ZERO,
    ),
    "XIY": (
        "         XIY   OUT,X'0F'\n" "         LLC   7,OUT\n",
        {7: HIGH_FILL | 0xF0},
        CC_NONZERO,
    ),
}

FIELD_IMMEDIATES: Mapping[str, Case] = {
    "NIHF": (
        "         LG    2,SRC\n" "         NIHF  2,X'F0F0F0F0'\n",
        {2: 0x00204060_89ABCDEF},
        CC_NONZERO,
    ),
    "NIHH": (
        "         LG    2,SRC\n" "         NIHH  2,X'FEDC'\n",
        {2: 0x00004567_89ABCDEF},
        CC_ZERO,
    ),
    "NIHL": (
        "         LG    2,SRC\n" "         NIHL  2,X'00FF'\n",
        {2: 0x01230067_89ABCDEF},
        CC_NONZERO,
    ),
    "NILF": (
        "         LG    2,SRC\n"
        "         CHI   2,0\n"
        "         NILF  2,X'76543210'\n",
        {2: 0x01234567_00000000},
        CC_ZERO,
    ),
    "NILH": (
        "         LG    2,SRC\n" "         NILH  2,X'0F0F'\n",
        {2: 0x01234567_090BCDEF},
        CC_NONZERO,
    ),
    "NILL": (
        "         LG    2,SRC\n" "         NILL  2,X'3210'\n",
        {2: 0x01234567_89AB0000},
        CC_ZERO,
    ),
    "OIHF": (
        "         LGHI  2,0\n" "         OIHF  2,X'80000000'\n",
        {2: 0x80000000_00000000},
        CC_NONZERO,
    ),
    "OIHH": ("         LGHI  2,1\n" "         OIHH  2,0\n", {2: 1}, CC_ZERO),
    "OIHL": (
        "         LG    2,SRC\n" "         OIHL  2,X'8000'\n",
        {2: 0x0123C567_89ABCDEF},
        CC_NONZERO,
    ),
    "OILF": (
        "         LG    2,SRC\n" "         OILF  2,1\n",
        {2: 0x01234567_89ABCDEF},
        CC_NONZERO,
    ),
    "OILH": (
        "         LG    2,DNEG\n" "         OILH  2,0\n",
        {2: 0x80000000_00000081},
        CC_ZERO,
    ),
    "OILL": (
        "         LGHI  2,0\n" "         OILL  2,X'FFFF'\n",
        {2: 0x00000000_0000FFFF},
        CC_NONZERO,
    ),
    "XIHF": (
        "         LG    2,SRC\n"
        "         CHI   2,0\n"
        "         XIHF  2,X'01234567'\n",
        {2: 0x00000000_89ABCDEF},
        CC_ZERO,
    ),
    "XILF": (
        "         LG    2,SRC\n" "         XILF  2,X'FFFFFFFF'\n",
        {2: 0x01234567_76543210},
        CC_NONZERO,
    ),
}

STORAGE_TO_STORAGE: Mapping[str, Case] = {
    "NC": (
        "         NC    OUT(12),SRCP\n"
        "         LG    7,OUT\n"
        "         L     8,OUT+8\n",
        {7: 0xFEDCBA98_76543210, 8: HIGH_FILL},
        CC_NONZERO,
    ),
    "XC": (
        "         XC    OUT(8),OUT\n"
        "         LG    7,OUT\n"
        "         LG    8,OUT+8\n",
        {7: 0, 8: ONES_64},
        CC_ZERO,
    ),
    "OC": (
        "         XC    OUT(8),OUT\n"
        "         OI    OUT,X'5A'\n"
        "         OC    OUT+1(7),OUT\n"
        "         LG    7,OUT\n",
        {7: 0x5A5A5A5A_5A5A5A5A},
        CC_NONZERO,
    ),
}

STORAGE_TO_STORAGE_LENGTHS: Mapping[str, Case] = {
    "XC implicit length": (
        "         XC    SRC,SRC\n" "         LG    7,SRC\n" "         LG    8,SRCP\n",
        {7: 0, 8: 0xFEDCBA98_76543210},
        CC_ZERO,
    ),
    "XC after a nonzero NC": (
        "         NC    OUT(8),SRCP\n"
        "         XC    OUT(8),OUT\n"
        "         LG    7,OUT\n",
        {7: 0},
        CC_ZERO,
    ),
    "XC length 0": (
        "         XC    OUT(0),OUT\n" "         LG    7,OUT\n",
        {7: 0x00FFFFFF_FFFFFFFF},
        CC_ZERO,
    ),
}

CASES: Mapping[str, Case] = {
    **ANDS,
    **ORS,
    **EXCLUSIVE_ORS,
    **DISTINCT_CONNECTIVES,
    **STORAGE_IMMEDIATES,
    **FIELD_IMMEDIATES,
    **STORAGE_TO_STORAGE,
    **STORAGE_TO_STORAGE_LENGTHS,
}
