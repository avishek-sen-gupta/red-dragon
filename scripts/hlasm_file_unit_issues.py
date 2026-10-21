# pyright: standard
"""Files one beads issue per HLASM opcode unit, with dependencies and wave-2 supersedes."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import reduce
from pathlib import Path

from hlasm_asg.instruction_table.instruction_table import InstructionTable
from hlasm_asg.instruction_table.mnemonic_row import MnemonicRow
from hlasm_asg.opcode_unit import OpcodeUnit
from hlasm_asg.opcode_units import OpcodeUnits

logger = logging.getLogger(__name__)

EPIC = "red-dragon-6uyp"
SKELETON = "red-dragon-6uyp.7"
FP_LEAF = "red-dragon-6uyp.21"
UNITS_PATH = Path("hlasm_asg/opcode_units.json")
FLOATING_POINT_PREFIXES = ("fp-", "bfp-", "hfp-", "dfp-")
VECTOR_DECIMAL = "vector-decimal"
SEEDED = frozenset({"LA", "LR", "SR", "BCR", "BASR", "BALR", "BRAS"})
SUPERSEDES = {
    "vector": "red-dragon-6uyp.17",
    "nnpa": "red-dragon-6uyp.18",
    "crypto": "red-dragon-6uyp.19",
    "transactional": "red-dragon-6uyp.20",
}
Runner = Callable[[Sequence[str], str], str]


@dataclass(frozen=True)
class DryRunner:
    def __call__(self, argv: Sequence[str], stdin: str) -> str:
        logger.info("%s", " ".join(argv))
        return f"<new:{argv[2]}>"


@dataclass(frozen=True)
class BdRunner:
    def __call__(self, argv: Sequence[str], stdin: str) -> str:
        completed = subprocess.run(
            argv, input=stdin, capture_output=True, check=True, text=True
        )
        return completed.stdout.strip()


def is_floating_point(unit: OpcodeUnit) -> bool:
    return unit.name.startswith(FLOATING_POINT_PREFIXES)


def priority(unit: OpcodeUnit) -> int:
    if unit.wave == 2:
        return 3
    return 2 if is_floating_point(unit) else 1


def extended_by_base(table: InstructionTable) -> Mapping[str, tuple[str, ...]]:
    rows = [row for row in table.instructions if isinstance(row, MnemonicRow)]
    bases = {row.base for row in rows}
    return {
        base: tuple(sorted(row.mnemonic for row in rows if row.base == base))
        for base in bases
    }


def mnemonic_line(mnemonic: str, extended: Mapping[str, tuple[str, ...]]) -> str:
    seeded = " (seeded by the foundation)" if mnemonic in SEEDED else ""
    exts = extended.get(mnemonic, ())
    suffix = f": {', '.join(exts)}" if exts else ""
    return f"- {mnemonic}{seeded}{suffix}"


def floating_point_note(unit: OpcodeUnit) -> str:
    if not is_floating_point(unit):
        return ""
    return (
        f"\nFloating-point rule: arithmetic goes through the floating-point leaf "
        f"package ({FP_LEAF}) as builtins; byte encode/decode is IR.\n"
    )


def related_note(unit: OpcodeUnit, ids: Mapping[str, str]) -> str:
    if unit.name != "vector":
        return ""
    return f"\nVector-decimal instructions are filed separately as {ids['vector-decimal']}.\n"


def description(
    unit: OpcodeUnit,
    extended: Mapping[str, tuple[str, ...]],
    ids: Mapping[str, str],
) -> str:
    lines = "\n".join(mnemonic_line(m, extended) for m in unit.mnemonics)
    return (
        f"Wave {unit.wave} opcode unit '{unit.name}': {len(unit.mnemonics)} base "
        f"mnemonics, each followed by its extended mnemonics.\n\n{lines}\n"
        f"{floating_point_note(unit)}{related_note(unit, ids)}\n"
        f"Shared IR helpers expected: foundation helpers (red-dragon-6uyp.5, "
        f".7): fixed-width arithmetic and CC helpers in "
        f"interpreter/hlasm/fixed_width_ir.py, effective addresses, the branch "
        f"dispatch.\n\n"
        f"Acceptance: every mnemonic above lowered; unit tests (IR structure) and "
        f"integration tests (VM, concrete values); a z390 differential test per "
        f"mnemonic, or a Principles-of-Operation-derived expected value where "
        f"z390 lacks it, stated in the test.\n"
    )


def file_unit(
    run: Runner,
    extended: Mapping[str, tuple[str, ...]],
    ids: Mapping[str, str],
    unit: OpcodeUnit,
) -> Mapping[str, str]:
    created = run(
        [
            "bd",
            "create",
            f"HLASM opcodes: {unit.title}",
            f"--parent={EPIC}",
            "--type=feature",
            f"--priority={priority(unit)}",
            "--silent",
            "--stdin",
        ],
        description(unit, extended, ids),
    )
    logger.info("filed %s as %s", unit.name, created)
    dependencies = (SKELETON, FP_LEAF) if is_floating_point(unit) else (SKELETON,)
    tuple(run(["bd", "dep", "add", created, d], "") for d in dependencies)
    tuple(
        run(["bd", "supersede", SUPERSEDES[unit.name], f"--with={created}"], "")
        for _ in (unit,)
        if unit.name in SUPERSEDES
    )
    return {**ids, unit.name: created}


def load_extended() -> Mapping[str, tuple[str, ...]]:
    completed = subprocess.run(
        [os.environ["HLASM_AST_BRIDGE"], "--instruction-table"],
        capture_output=True,
        check=True,
        text=True,
    )
    return extended_by_base(InstructionTable.model_validate_json(completed.stdout))


def creation_order(units: Sequence[OpcodeUnit]) -> tuple[OpcodeUnit, ...]:
    return tuple(u for u in units if u.name == VECTOR_DECIMAL) + tuple(
        u for u in units if u.name != VECTOR_DECIMAL
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    dry_run = parser.parse_args().dry_run
    units = creation_order(
        OpcodeUnits.model_validate_json(UNITS_PATH.read_text()).units
    )
    extended = load_extended()
    run: Runner = DryRunner() if dry_run else BdRunner()
    ids = reduce(lambda acc, unit: file_unit(run, extended, acc, unit), units, {})
    logger.info("units filed: %d", len(ids))


if __name__ == "__main__":
    main()
