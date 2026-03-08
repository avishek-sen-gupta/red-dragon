"""
04_symbolic_audit.py
---------------------
Audits every SYMBOLIC instruction across the entire Rosetta corpus.
Classifies each into:
  - param:       function parameter declaration (always resolves at call time)
  - caught_exception:  exception object binding (always resolves in catch handler)
  - unsupported: unhandled AST node type (genuine incompleteness)
  - other:       any other SYMBOLIC hint

Run from the red-dragon repo root:
    poetry run python3 scripts/04_symbolic_audit.py [--verbose]

Options:
    --verbose   Print every individual SYMBOLIC instruction with context

Output: summary counts per category, per algorithm, per language.
        In verbose mode: full instruction list with surrounding IR context.
"""

import sys
import os
import importlib
import glob
import argparse

sys.path.insert(0, "tests/unit/rosetta")

from interpreter.cfg import build_cfg
from interpreter.frontends import (
    get_deterministic_frontend,
    SUPPORTED_DETERMINISTIC_LANGUAGES,
)
from interpreter.ir import Opcode

LANGS = sorted(SUPPORTED_DETERMINISTIC_LANGUAGES)


def classify(sym_instruction):
    """Classify a SYMBOLIC instruction by its operand hint."""
    operands = sym_instruction.operands
    if not operands:
        return "no_hint"
    hint = str(operands[0])
    if hint.startswith("param:"):
        return "param"
    if hint.startswith("caught_exception:"):
        return "caught_exception"
    if hint.startswith("unsupported:"):
        return "unsupported"
    return "other"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verbose", action="store_true", help="Print every SYMBOLIC with context"
    )
    args = parser.parse_args()

    totals = {
        "param": 0,
        "caught_exception": 0,
        "unsupported": 0,
        "other": 0,
        "no_hint": 0,
    }
    unresolved = []  # (algo, lang, instruction, context)

    for path in sorted(glob.glob("tests/unit/rosetta/test_rosetta_*.py")):
        modname = os.path.basename(path)[:-3]
        algo = modname.replace("test_rosetta_", "")
        try:
            mod = importlib.import_module(modname)
            programs = getattr(mod, "PROGRAMS", None)
            if not programs:
                continue

            for lang in LANGS:
                if lang not in programs:
                    continue
                try:
                    fe = get_deterministic_frontend(lang)
                    ir = fe.lower(programs[lang].encode())
                    for idx, inst in enumerate(ir):
                        if inst.opcode != Opcode.SYMBOLIC:
                            continue
                        category = classify(inst)
                        totals[category] += 1

                        if args.verbose or category in (
                            "unsupported",
                            "other",
                            "no_hint",
                        ):
                            before = str(ir[idx - 1]) if idx > 0 else "(start)"
                            after = str(ir[idx + 1]) if idx < len(ir) - 1 else "(end)"
                            entry = {
                                "algo": algo,
                                "lang": lang,
                                "category": category,
                                "inst": str(inst),
                                "before": before,
                                "after": after,
                            }
                            if category in ("unsupported", "other", "no_hint"):
                                unresolved.append(entry)
                            if args.verbose:
                                print(f"  [{algo}/{lang}] {category}: {inst}")
                                print(f"    before: {before}")
                                print(f"    after:  {after}")
                except Exception as e:
                    print(f"  ERR {algo}/{lang}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"skip {algo}: {e}", file=sys.stderr)

    print("\n=== SYMBOLIC Audit Summary ===\n")
    print(f"  {'param:':<22} {totals['param']:>6}  (always resolves at call time)")
    print(
        f"  {'caught_exception:':<22} {totals['caught_exception']:>6}  (always resolves in catch handler)"
    )
    print(
        f"  {'unsupported:':<22} {totals['unsupported']:>6}  (genuine frontend incompleteness)"
    )
    print(f"  {'other:':<22} {totals['other']:>6}")
    print(f"  {'no_hint:':<22} {totals['no_hint']:>6}")
    total = sum(totals.values())
    print(f"  {'TOTAL:':<22} {total:>6}")

    if unresolved:
        print(f"\n=== Non-param/caught_exception SYMBOLICs ({len(unresolved)}) ===\n")
        for entry in unresolved:
            print(
                f"  [{entry['algo']}/{entry['lang']}] {entry['category']}: {entry['inst']}"
            )
    else:
        print("\n✓ No unsupported/other SYMBOLIC instructions found in Rosetta corpus.")

    print(
        f"\nConclusion: {totals['param']} param + {totals['caught_exception']} caught_exception = "
        f"{totals['param'] + totals['caught_exception']} SYMBOLICs that always resolve concretely."
    )
    if totals["unsupported"] + totals["other"] + totals["no_hint"] == 0:
        print("Zero unresolved SYMBOLIC instructions across entire corpus.")


if __name__ == "__main__":
    main()
