# pyright: standard
"""Branch on condition programs: R2 records the path taken, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import DATA, HIGH_FILL

type Case = tuple[int, str, bool]

TAKEN = HIGH_FILL | 1
FELL_THROUGH = HIGH_FILL | 2
PATH_REGISTER = 2

SET_CC = {
    0: "         CLI   ZERO,0\n",
    1: "         CLI   ZERO,1\n",
    2: "         CLI   NEG,0\n",
    3: "         L     3,NEG\n" "         A     3,NEG\n",
}

TARGETS = (
    "         DS    0D\n"
    "TGT      DC    A(0),A(TAKEN)\n"
    "HIGHTGT  DC    X'FFFFFFFF',A(X'80000000'+TAKEN)\n"
    "DATATGT  DC    A(0),A(FILL)\n"
)


def _register(mask: str) -> str:
    return f"         LA    4,TAKEN\n         {mask:<5} 4\n"


def _line(mnemonic: str, operands: str) -> str:
    return f"         {mnemonic:<5} {operands}\n"


def path_program(cc: int, branch: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        f"{SET_CC[cc]}{branch}"
        "         LHI   2,2\n"
        "         ABEND 1\n"
        "TAKEN    LHI   2,1\n"
        "         ABEND 1\n"
        f"{TARGETS}{DATA}"
        "         END\n"
    )


def cross_section_program() -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        "         CLI   ZERO,1\n"
        "         JL    THERE\n"
        "         LHI   2,2\n"
        "         ABEND 1\n"
        f"{DATA}"
        "D        CSECT\n"
        "THERE    LHI   2,1\n"
        "         ABEND 1\n"
        "         END   T\n"
    )


BRANCH_ON_CONDITION: Mapping[str, Case] = {
    "BC": (0, _line("BC", "8,TAKEN"), True),
    "BC not selected": (0, _line("BC", "6,TAKEN"), False),
    "BC 12 at CC 1": (1, _line("BC", "12,TAKEN"), True),
    "BC 12 at CC 2": (2, _line("BC", "12,TAKEN"), False),
    "BC indexed": (1, "         LA    5,4\n" + _line("BC", "4,TAKEN-4(5)"), True),
    "B": (3, _line("B", "TAKEN"), True),
    "BE": (0, _line("BE", "TAKEN"), True),
    "BNE": (0, _line("BNE", "TAKEN"), False),
    "BH": (2, _line("BH", "TAKEN"), True),
    "BL": (1, _line("BL", "TAKEN"), True),
    "BNH": (2, _line("BNH", "TAKEN"), False),
    "BNL": (2, _line("BNL", "TAKEN"), True),
    "BO": (3, _line("BO", "TAKEN"), True),
    "BNO": (3, _line("BNO", "TAKEN"), False),
    "BZ": (1, _line("BZ", "TAKEN"), False),
    "BNZ": (1, _line("BNZ", "TAKEN"), True),
    "BM": (1, _line("BM", "TAKEN"), True),
    "BNM": (0, _line("BNM", "TAKEN"), True),
    "BP": (2, _line("BP", "TAKEN"), True),
    "BNP": (2, _line("BNP", "TAKEN"), False),
    "NOP": (0, _line("NOP", "TAKEN"), False),
}

BRANCH_ON_CONDITION_REGISTER: Mapping[str, Case] = {
    "BCR": (1, "         LA    4,TAKEN\n" + _line("BCR", "4,4"), True),
    "BR": (3, _register("BR"), True),
    "BER": (0, _register("BER"), True),
    "BNER": (0, _register("BNER"), False),
    "BHR": (2, _register("BHR"), True),
    "BLR": (2, _register("BLR"), False),
    "BOR": (3, _register("BOR"), True),
    "BNZR": (1, _register("BNZR"), True),
    "NOPR": (0, _register("NOPR"), False),
    "BCR 15,0": (0, _line("BCR", "15,0"), False),
    "BCR 14,0": (1, _line("BCR", "14,0"), False),
}

BRANCH_INDIRECT_ON_CONDITION: Mapping[str, Case] = {
    "BIC": (1, _line("BIC", "4,TGT"), True),
    "BI": (3, _line("BI", "TGT"), True),
    "BIE": (1, _line("BIE", "TGT"), False),
    "BINE": (1, _line("BINE", "TGT"), True),
    "BIO": (3, _line("BIO", "TGT"), True),
    "BIH": (2, _line("BIH", "TGT"), True),
    "BINL": (1, _line("BINL", "TGT"), False),
    "BI high word and bit 32": (0, _line("BI", "HIGHTGT"), True),
}

BRANCH_RELATIVE_ON_CONDITION: Mapping[str, Case] = {
    "BRC": (2, _line("BRC", "2,TAKEN"), True),
    "BRC 5 at CC 3": (3, _line("BRC", "5,TAKEN"), True),
    "BRC 5 at CC 2": (2, _line("BRC", "5,TAKEN"), False),
    "BRC 10 at CC 0": (0, _line("BRC", "10,TAKEN"), True),
    "BRC 10 at CC 1": (1, _line("BRC", "10,TAKEN"), False),
    "J": (3, _line("J", "TAKEN"), True),
    "JE": (0, _line("JE", "TAKEN"), True),
    "JNE": (0, _line("JNE", "TAKEN"), False),
    "JH": (2, _line("JH", "TAKEN"), True),
    "JL": (1, _line("JL", "TAKEN"), True),
    "JO": (3, _line("JO", "TAKEN"), True),
    "JNO": (3, _line("JNO", "TAKEN"), False),
    "JNOP": (0, _line("JNOP", "TAKEN"), False),
    "JC": (3, _line("JC", "3,TAKEN"), True),
    "BRE": (1, _line("BRE", "TAKEN"), False),
    "BRU": (1, _line("BRU", "TAKEN"), True),
    "BRNZ": (2, _line("BRNZ", "TAKEN"), True),
}

BRANCH_RELATIVE_ON_CONDITION_LONG: Mapping[str, Case] = {
    "BRCL": (1, _line("BRCL", "4,TAKEN"), True),
    "BRCL 9 at CC 0": (0, _line("BRCL", "9,TAKEN"), True),
    "BRCL 9 at CC 2": (2, _line("BRCL", "9,TAKEN"), False),
    "JLU": (0, _line("JLU", "TAKEN"), True),
    "JLE": (0, _line("JLE", "TAKEN"), True),
    "JLNE": (0, _line("JLNE", "TAKEN"), False),
    "JLH": (1, _line("JLH", "TAKEN"), False),
    "JLNOP": (0, _line("JLNOP", "TAKEN"), False),
    "JLC": (3, _line("JLC", "1,TAKEN"), True),
    "BRUL": (2, _line("BRUL", "TAKEN"), True),
    "BRNEL": (3, _line("BRNEL", "TAKEN"), True),
    "BRZL": (2, _line("BRZL", "TAKEN"), False),
}

BRANCH_PREDICTION: Mapping[str, Case] = {
    "BPP": (0, _line("BPP", "8,NEXT,TAKEN") + "NEXT     DS    0H\n", False),
    "BPRP": (2, _line("BPRP", "8,NEXT,TAKEN") + "NEXT     DS    0H\n", False),
}

CASES: Mapping[str, Case] = {
    **BRANCH_ON_CONDITION,
    **BRANCH_ON_CONDITION_REGISTER,
    **BRANCH_INDIRECT_ON_CONDITION,
    **BRANCH_RELATIVE_ON_CONDITION,
    **BRANCH_RELATIVE_ON_CONDITION_LONG,
    **BRANCH_PREDICTION,
}

DIRECT_INTO_DATA = (
    _line("J", "FILL"),
    _line("BC", "15,FILL"),
    _line("BRCL", "15,FILL"),
)
INTO_DATA = (*DIRECT_INTO_DATA, _line("BI", "DATATGT"))

CNOP_PADDING = (10, 16)
NO_OP_HALFWORD = b"\x07\x00"


def cnop_target_program(before_target: str, target: str) -> str:
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         XGR   2,2\n"
        "         B     X\n"
        f"{before_target}"
        f"{target}"
        "         LA    2,7\n"
        "         ABEND 1\n"
        "         END\n"
    )


PADDED_CNOP_TARGET = cnop_target_program("", "X        DS    0H\n         CNOP  0,8\n")
ALIGNED_CNOP_TARGET = cnop_target_program(
    "         DC    3H'0'\n", "X        CNOP  0,8\n"
)
