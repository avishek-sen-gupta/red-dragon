#!/usr/bin/env python3
"""Demo: COBOL feature showcase — full pipeline from .cbl source to final variable states.

Exercises the complete COBOL pipeline:
  1. COBOL source (fixed-format) is fed to the ProLeap Java bridge
  2. Bridge parses and serializes ASG to JSON
  3. Python frontend lowers statements to TAC IR
  4. CFG is built and VM executes deterministically
  5. Final memory regions are decoded and displayed

Each demo program focuses on a different cluster of COBOL features.
All programs run through the real ProLeap parser — no mocked ASGs.

Usage:
    poetry run python scripts/demo_cobol_features.py
    poetry run python scripts/demo_cobol_features.py --verbose
    poetry run python scripts/demo_cobol_features.py --program arithmetic
    poetry run python scripts/demo_cobol_features.py --list

Requires:
    PROLEAP_BRIDGE_JAR env var (or default path at
    ~/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpreter.run import run

logger = logging.getLogger(__name__)

# ── COBOL formatting helpers ────────────────────────────────────

AREA_A = "       "  # cols 1-6 seq + col 7 indicator (space)
COMMENT = "      *"  # col 7 = * for comment line


def _fixed(lines: list[str]) -> str:
    """Convert short-form COBOL lines to FIXED format.

    Lines starting with '*' become comment lines (indicator in col 7).
    All other lines get the standard 7-space Area A prefix.
    """
    formatted = [
        COMMENT + line[1:] if line.startswith("*") else AREA_A + line for line in lines
    ]
    return "\n".join(formatted) + "\n"


def _run_cobol(lines: list[str], max_steps: int = 10000):
    """Run COBOL source through the full pipeline, return VMState."""
    source = _fixed(lines)
    return run(source=source, language="cobol", max_steps=max_steps)


# ── Memory decoding ─────────────────────────────────────────────


def _decode_zoned(region: list[int], offset: int, length: int) -> int:
    """Decode unsigned zoned decimal (EBCDIC) from a memory region."""
    digits = [region[offset + i] & 0x0F for i in range(length)]
    return sum(d * (10 ** (length - 1 - i)) for i, d in enumerate(digits))


def _decode_alpha(region: list[int], offset: int, length: int) -> str:
    """Decode EBCDIC alphanumeric bytes to ASCII string."""
    ebcdic_to_ascii = {
        0x40: " ",
        0xC1: "A",
        0xC2: "B",
        0xC3: "C",
        0xC4: "D",
        0xC5: "E",
        0xC6: "F",
        0xC7: "G",
        0xC8: "H",
        0xC9: "I",
        0xD1: "J",
        0xD2: "K",
        0xD3: "L",
        0xD4: "M",
        0xD5: "N",
        0xD6: "O",
        0xD7: "P",
        0xD8: "Q",
        0xD9: "R",
        0xE2: "S",
        0xE3: "T",
        0xE4: "U",
        0xE5: "V",
        0xE6: "W",
        0xE7: "X",
        0xE8: "Y",
        0xE9: "Z",
        0xF0: "0",
        0xF1: "1",
        0xF2: "2",
        0xF3: "3",
        0xF4: "4",
        0xF5: "5",
        0xF6: "6",
        0xF7: "7",
        0xF8: "8",
        0xF9: "9",
    }
    return "".join(ebcdic_to_ascii.get(region[offset + i], "?") for i in range(length))


# ── Field descriptor ─────────────────────────────────────────────


@dataclass(frozen=True)
class Field:
    name: str
    offset: int
    length: int
    kind: str  # "numeric" or "alpha"
    description: str


def _show_results(title: str, vm, fields: list[Field]) -> None:
    """Display decoded field values from the first memory region."""
    region = list(vm.region_get(list(vm.region_keys())[0]))

    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)
    hdr_name = "Field"
    hdr_val = "Value"
    print(f"  {hdr_name:<14} {hdr_val:>10}   Description")
    print("-" * 72)
    for f in fields:
        if f.kind == "numeric":
            val = str(_decode_zoned(region, f.offset, f.length))
        else:
            val = repr(_decode_alpha(region, f.offset, f.length))
        print(f"  {f.name:<14} {val:>10}   {f.description}")
    print("=" * 72)


# ── Demo programs ────────────────────────────────────────────────


def demo_arithmetic() -> None:
    """All arithmetic forms: in-place, GIVING, COMPUTE, literals."""
    vm = _run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. DEMO-ARITH.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "77 WS-A     PIC 9(4) VALUE 10.",
            "77 WS-B     PIC 9(4) VALUE 25.",
            "77 WS-C     PIC 9(4) VALUE 3.",
            "77 WS-SUM   PIC 9(4) VALUE 0.",
            "77 WS-PROD  PIC 9(4) VALUE 0.",
            "77 WS-QUOT  PIC 9(4) VALUE 0.",
            "77 WS-ADDG  PIC 9(4) VALUE 0.",
            "77 WS-SUBG  PIC 9(4) VALUE 0.",
            "77 WS-COMP  PIC 9(4) VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "* In-place ADD and SUBTRACT",
            "    ADD WS-A TO WS-SUM.",
            "    ADD WS-B TO WS-SUM.",
            "    SUBTRACT WS-C FROM WS-SUM.",
            "* ADD / SUBTRACT GIVING",
            "    ADD WS-A TO WS-B GIVING WS-ADDG.",
            "    SUBTRACT WS-C FROM WS-B GIVING WS-SUBG.",
            "* MULTIPLY / DIVIDE GIVING",
            "    MULTIPLY WS-A BY WS-C GIVING WS-PROD.",
            "    DIVIDE WS-B BY WS-A GIVING WS-QUOT.",
            "* COMPUTE with expression",
            "    COMPUTE WS-COMP = WS-A + WS-B * WS-C.",
            "    STOP RUN.",
        ]
    )

    _show_results(
        "ARITHMETIC: in-place, GIVING, COMPUTE",
        vm,
        [
            Field("WS-A", 0, 4, "numeric", "input = 10"),
            Field("WS-B", 4, 4, "numeric", "input = 25"),
            Field("WS-C", 8, 4, "numeric", "input = 3"),
            Field("WS-SUM", 12, 4, "numeric", "10 + 25 - 3 = 32"),
            Field("WS-PROD", 16, 4, "numeric", "MULTIPLY 10 BY 3 GIVING = 30"),
            Field("WS-QUOT", 20, 4, "numeric", "DIVIDE 25 BY 10 GIVING = 2"),
            Field("WS-ADDG", 24, 4, "numeric", "ADD 10 TO 25 GIVING = 35"),
            Field("WS-SUBG", 28, 4, "numeric", "SUBTRACT 3 FROM 25 GIVING = 22"),
            Field("WS-COMP", 32, 4, "numeric", "COMPUTE 10 + 25*3 = 85"),
        ],
    )


def demo_control_flow() -> None:
    """IF/ELSE, EVALUATE/WHEN, PERFORM TIMES/UNTIL/VARYING."""
    vm = _run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. DEMO-CTLFLOW.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "77 WS-X     PIC 9(4) VALUE 15.",
            "77 WS-IF-R  PIC 9(4) VALUE 0.",
            "77 WS-CODE  PIC 9(4) VALUE 2.",
            "77 WS-EV-R  PIC 9(4) VALUE 0.",
            "77 WS-CTR   PIC 9(4) VALUE 0.",
            "77 WS-SUM   PIC 9(4) VALUE 0.",
            "77 WS-I     PIC 9(4) VALUE 0.",
            "77 WS-ACC   PIC 9(4) VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "* IF / ELSE",
            "    IF WS-X > 10",
            "        MOVE 1 TO WS-IF-R",
            "    ELSE",
            "        MOVE 2 TO WS-IF-R",
            "    END-IF.",
            "* EVALUATE / WHEN",
            "    EVALUATE WS-CODE",
            "        WHEN 1",
            "            MOVE 10 TO WS-EV-R",
            "        WHEN 2",
            "            MOVE 20 TO WS-EV-R",
            "        WHEN OTHER",
            "            MOVE 99 TO WS-EV-R",
            "    END-EVALUATE.",
            "* PERFORM TIMES",
            "    PERFORM 3 TIMES",
            "        ADD 1 TO WS-CTR",
            "    END-PERFORM.",
            "* PERFORM UNTIL",
            "    PERFORM UNTIL WS-SUM > 20",
            "        ADD 7 TO WS-SUM",
            "    END-PERFORM.",
            "* PERFORM VARYING",
            "    PERFORM VARYING WS-I FROM 1 BY 1",
            "        UNTIL WS-I > 5",
            "        ADD WS-I TO WS-ACC",
            "    END-PERFORM.",
            "    STOP RUN.",
        ],
        max_steps=20000,
    )

    _show_results(
        "CONTROL FLOW: IF, EVALUATE, PERFORM (3 forms)",
        vm,
        [
            Field("WS-X", 0, 4, "numeric", "input = 15"),
            Field("WS-IF-R", 4, 4, "numeric", "IF 15 > 10 -> true -> 1"),
            Field("WS-CODE", 8, 4, "numeric", "input = 2"),
            Field("WS-EV-R", 12, 4, "numeric", "EVALUATE 2 -> WHEN 2 -> 20"),
            Field("WS-CTR", 16, 4, "numeric", "PERFORM 3 TIMES -> 3"),
            Field("WS-SUM", 20, 4, "numeric", "PERFORM UNTIL > 20: 7+7+7=21"),
            Field("WS-I", 24, 4, "numeric", "VARYING counter final = 6"),
            Field("WS-ACC", 28, 4, "numeric", "VARYING 1+2+3+4+5 = 15"),
        ],
    )


def demo_string_ops() -> None:
    """MOVE, STRING, UNSTRING, INSPECT TALLYING, INSPECT REPLACING."""
    vm = _run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. DEMO-STRING.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            '77 WS-FIRST PIC X(5) VALUE "HELLO".',
            '77 WS-LAST  PIC X(5) VALUE "WORLD".',
            "77 WS-JOINED PIC X(10) VALUE SPACES.",
            '77 WS-FULL  PIC X(11) VALUE "ALPHA BRAVO".',
            "77 WS-PART1 PIC X(5) VALUE SPACES.",
            "77 WS-PART2 PIC X(5) VALUE SPACES.",
            '77 WS-DATA  PIC X(10) VALUE "ABCABCABCA".',
            "77 WS-COUNT PIC 9(4) VALUE 0.",
            '77 WS-REPL  PIC X(5) VALUE "AABAA".',
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "* STRING concatenation",
            "    STRING WS-FIRST DELIMITED BY SIZE",
            "           WS-LAST  DELIMITED BY SIZE",
            "           INTO WS-JOINED.",
            "* UNSTRING splitting",
            "    UNSTRING WS-FULL DELIMITED BY SPACES",
            "        INTO WS-PART1 WS-PART2.",
            '* INSPECT TALLYING: count "A" in WS-DATA',
            "    INSPECT WS-DATA TALLYING WS-COUNT",
            '        FOR ALL "A".',
            '* INSPECT REPLACING: replace "A" with "Z" in WS-REPL',
            '    INSPECT WS-REPL REPLACING ALL "A" BY "Z".',
            "    STOP RUN.",
        ]
    )

    _show_results(
        "STRING OPS: STRING, UNSTRING, INSPECT",
        vm,
        [
            Field("WS-FIRST", 0, 5, "alpha", 'input = "HELLO"'),
            Field("WS-LAST", 5, 5, "alpha", 'input = "WORLD"'),
            Field("WS-JOINED", 10, 10, "alpha", 'STRING -> "HELLOWORLD"'),
            Field("WS-FULL", 20, 11, "alpha", 'input = "ALPHA BRAVO"'),
            Field("WS-PART1", 31, 5, "alpha", 'UNSTRING -> "ALPHA"'),
            Field("WS-PART2", 36, 5, "alpha", 'UNSTRING -> "BRAVO"'),
            Field("WS-DATA", 41, 10, "alpha", 'input = "ABCABCABCA"'),
            Field("WS-COUNT", 51, 4, "numeric", 'TALLYING ALL "A" -> 4'),
            Field("WS-REPL", 55, 5, "alpha", 'REPLACING ALL A BY Z -> "ZZBZZ"'),
        ],
    )


def demo_level88() -> None:
    """Level-88 condition names: single value, multi-value, THRU range."""
    vm = _run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. DEMO-LVL88.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            '05 WS-STATUS PIC X(1) VALUE "A".',
            '   88 STATUS-ACTIVE VALUE "A".',
            '   88 STATUS-INACTIVE VALUE "I".',
            "05 WS-SCORE  PIC 9(4) VALUE 35.",
            "   88 IN-RANGE VALUE 10 THRU 50.",
            '05 WS-LETTER PIC X(1) VALUE "B".',
            '   88 IS-VOWEL VALUE "A" "E" "I" "O" "U".',
            "77 WS-R1 PIC 9(4) VALUE 0.",
            "77 WS-R2 PIC 9(4) VALUE 0.",
            "77 WS-R3 PIC 9(4) VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "* Test single-value condition name",
            "    IF STATUS-ACTIVE",
            "        MOVE 1 TO WS-R1",
            "    ELSE",
            "        MOVE 2 TO WS-R1",
            "    END-IF.",
            "* Test THRU range condition",
            "    IF IN-RANGE",
            "        MOVE 1 TO WS-R2",
            "    ELSE",
            "        MOVE 2 TO WS-R2",
            "    END-IF.",
            '* Test multi-value condition ("B" is not a vowel)',
            "    IF IS-VOWEL",
            "        MOVE 1 TO WS-R3",
            "    ELSE",
            "        MOVE 2 TO WS-R3",
            "    END-IF.",
            "    STOP RUN.",
        ]
    )

    _show_results(
        "LEVEL-88 CONDITION NAMES: single, THRU, multi-value",
        vm,
        [
            Field("WS-STATUS", 0, 1, "alpha", 'input = "A"'),
            Field("WS-SCORE", 1, 4, "numeric", "input = 35"),
            Field("WS-LETTER", 5, 1, "alpha", '"B"'),
            Field("WS-R1", 6, 4, "numeric", "STATUS-ACTIVE? A=A -> true -> 1"),
            Field("WS-R2", 10, 4, "numeric", "IN-RANGE 10..50? 35 in -> true -> 1"),
            Field("WS-R3", 14, 4, "numeric", "IS-VOWEL? B not in AEIOU -> false -> 2"),
        ],
    )


def demo_perform_and_paragraphs() -> None:
    """PERFORM paragraph calls, PERFORM THRU, nested PERFORMs."""
    vm = _run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. DEMO-PERF.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "77 WS-A   PIC 9(4) VALUE 0.",
            "77 WS-B   PIC 9(4) VALUE 0.",
            "77 WS-C   PIC 9(4) VALUE 0.",
            "77 WS-I   PIC 9(4) VALUE 0.",
            "77 WS-ACC PIC 9(4) VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    PERFORM INIT-PARA.",
            "    PERFORM CALC-PARA.",
            "    PERFORM LOOP-PARA.",
            "    STOP RUN.",
            "",
            "INIT-PARA.",
            "    MOVE 10 TO WS-A.",
            "    MOVE 20 TO WS-B.",
            "",
            "CALC-PARA.",
            "    ADD WS-A TO WS-B GIVING WS-C.",
            "",
            "LOOP-PARA.",
            "    PERFORM VARYING WS-I FROM 1 BY 1",
            "        UNTIL WS-I > WS-A",
            "        ADD 1 TO WS-ACC",
            "    END-PERFORM.",
        ],
        max_steps=50000,
    )

    _show_results(
        "PERFORM: paragraph calls, VARYING with field limit",
        vm,
        [
            Field("WS-A", 0, 4, "numeric", "INIT-PARA: MOVE 10"),
            Field("WS-B", 4, 4, "numeric", "INIT-PARA: MOVE 20"),
            Field("WS-C", 8, 4, "numeric", "CALC-PARA: ADD 10 TO 20 GIVING = 30"),
            Field("WS-I", 12, 4, "numeric", "loop counter final = 11"),
            Field("WS-ACC", 16, 4, "numeric", "VARYING 1..10, ADD 1 each = 10"),
        ],
    )


def demo_occurs_and_subscripts() -> None:
    """OCCURS tables with literal and field-based subscripts."""
    vm = _run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. DEMO-OCCURS.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "77 WS-TBL PIC 9(4) OCCURS 5.",
            "77 WS-IDX PIC 9(4) VALUE 3.",
            "77 WS-SUM PIC 9(4) VALUE 0.",
            "77 WS-I   PIC 9(4) VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "* Fill table with PERFORM VARYING",
            "    PERFORM VARYING WS-I FROM 1 BY 1",
            "        UNTIL WS-I > 5",
            "        MULTIPLY WS-I BY 10 GIVING WS-TBL(WS-I)",
            "    END-PERFORM.",
            "* Read back using literal and field subscript",
            "    ADD WS-TBL(1) TO WS-SUM.",
            "    ADD WS-TBL(WS-IDX) TO WS-SUM.",
            "    ADD WS-TBL(5) TO WS-SUM.",
            "    STOP RUN.",
        ],
        max_steps=20000,
    )

    _show_results(
        "OCCURS: table fill, literal + field subscripts",
        vm,
        [
            Field("WS-TBL(1)", 0, 4, "numeric", "1 * 10 = 10"),
            Field("WS-TBL(2)", 4, 4, "numeric", "2 * 10 = 20"),
            Field("WS-TBL(3)", 8, 4, "numeric", "3 * 10 = 30"),
            Field("WS-TBL(4)", 12, 4, "numeric", "4 * 10 = 40"),
            Field("WS-TBL(5)", 16, 4, "numeric", "5 * 10 = 50"),
            Field("WS-IDX", 20, 4, "numeric", "subscript = 3"),
            Field("WS-SUM", 24, 4, "numeric", "TBL(1)+TBL(3)+TBL(5) = 10+30+50 = 90"),
            Field("WS-I", 28, 4, "numeric", "loop counter final = 6"),
        ],
    )


def demo_blank_when_zero() -> None:
    """BLANK WHEN ZERO: zero values become EBCDIC spaces."""
    vm = _run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. DEMO-BWZ.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "77 WS-AMT1 PIC 9(4) BLANK WHEN ZERO VALUE 0.",
            "77 WS-AMT2 PIC 9(4) BLANK WHEN ZERO VALUE 42.",
            "77 WS-AMT3 PIC 9(4) BLANK WHEN ZERO VALUE 99.",
            "77 WS-NORM PIC 9(4) VALUE 0.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            "    MOVE 0 TO WS-AMT3.",
            "    STOP RUN.",
        ]
    )

    region = list(vm.region_get(list(vm.region_keys())[0]))

    print()
    print("=" * 72)
    print("  BLANK WHEN ZERO: zero -> spaces, non-zero -> normal digits")
    print("=" * 72)
    hdr_name = "Field"
    hdr_val = "Value"
    hdr_raw = "Raw bytes"
    print(f"  {hdr_name:<14} {hdr_val:>10}   {hdr_raw:<20}  Description")
    print("-" * 72)

    bwz_fields = [
        ("WS-AMT1", 0, 4, "BWZ + VALUE 0 -> spaces"),
        ("WS-AMT2", 4, 4, "BWZ + VALUE 42 -> normal"),
        ("WS-AMT3", 8, 4, "BWZ + MOVE 0 -> spaces"),
        ("WS-NORM", 12, 4, "no BWZ + VALUE 0 -> zoned 0"),
    ]

    for name, off, ln, desc in bwz_fields:
        raw = [region[off + i] for i in range(ln)]
        raw_hex = " ".join(f"{b:02X}" for b in raw)
        all_spaces = all(b == 0x40 for b in raw)
        if all_spaces:
            display = repr("    ")
        else:
            val = _decode_zoned(region, off, ln)
            display = str(val)
        print(f"  {name:<14} {display:>10}   [{raw_hex}]  {desc}")

    print("=" * 72)


# ── Registry ─────────────────────────────────────────────────────

DEMOS = {
    "arithmetic": ("Arithmetic: in-place, GIVING, COMPUTE", demo_arithmetic),
    "control_flow": ("Control flow: IF, EVALUATE, PERFORM", demo_control_flow),
    "string_ops": ("String ops: STRING, UNSTRING, INSPECT", demo_string_ops),
    "level88": ("Level-88 condition names", demo_level88),
    "perform": ("PERFORM paragraphs and VARYING", demo_perform_and_paragraphs),
    "occurs": ("OCCURS tables and subscripts", demo_occurs_and_subscripts),
    "blank_when_zero": ("BLANK WHEN ZERO clause", demo_blank_when_zero),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="COBOL feature showcase — full pipeline demos"
    )
    parser.add_argument(
        "--program",
        "-p",
        choices=list(DEMOS.keys()),
        help="Run a specific demo program (default: all)",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available demo programs and exit",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.list:
        print("Available COBOL demo programs:")
        for key, (desc, _) in DEMOS.items():
            print(f"  {key:<18} {desc}")
        return

    jar_path = os.environ.get(
        "PROLEAP_BRIDGE_JAR",
        os.path.expanduser(
            "~/code/red-dragon/proleap-bridge/target/" "proleap-bridge-0.1.0-shaded.jar"
        ),
    )
    if not os.path.isfile(jar_path):
        print(f"ERROR: ProLeap bridge JAR not found at {jar_path}")
        print("Set PROLEAP_BRIDGE_JAR or build with: cd proleap-bridge && mvn package")
        sys.exit(1)
    os.environ["PROLEAP_BRIDGE_JAR"] = jar_path

    programs_to_run = [args.program] if args.program else list(DEMOS.keys())

    total = len(programs_to_run)
    for i, key in enumerate(programs_to_run, 1):
        desc, fn = DEMOS[key]
        print(f"\n>>> [{i}/{total}] {desc}")
        fn()

    print(f"\nAll {total} demo(s) completed successfully.")


if __name__ == "__main__":
    main()
