"""
01_cfg_shape_summary.py
-----------------------
Generates a summary of CFG shapes (block count, edge count, IR length,
SYMBOLIC counts) across all Rosetta algorithms and all 15 languages.

Run from the red-dragon repo root:
    poetry run python3 scripts/01_cfg_shape_summary.py

Output: one line per algorithm with min/max blocks, edges, IR length,
        number of distinct structural variants, and unresolved SYMBOLIC count.
"""

import sys
import os
import importlib
import glob

sys.path.insert(0, "tests/unit/rosetta")

from interpreter.cfg import build_cfg
from interpreter.frontends import (
    get_deterministic_frontend,
    SUPPORTED_DETERMINISTIC_LANGUAGES,
)
from interpreter.ir import Opcode

LANGS = sorted(SUPPORTED_DETERMINISTIC_LANGUAGES)


def load_all_rosetta():
    results = {}
    for path in sorted(glob.glob("tests/unit/rosetta/test_rosetta_*.py")):
        modname = os.path.basename(path)[:-3]
        algo = modname.replace("test_rosetta_", "")
        try:
            mod = importlib.import_module(modname)
            programs = getattr(mod, "PROGRAMS", None)
            if not programs or len(programs) < 8:
                continue
            results[algo] = {}
            for lang in LANGS:
                if lang not in programs:
                    continue
                try:
                    fe = get_deterministic_frontend(lang)
                    ir = fe.lower(programs[lang].encode())
                    cfg = build_cfg(ir)
                    edges = sum(len(b.successors) for b in cfg.blocks.values())
                    param_syms = sum(
                        1
                        for i in ir
                        if i.opcode == Opcode.SYMBOLIC
                        and any("param:" in str(op) for op in i.operands)
                    )
                    other_syms = sum(
                        1
                        for i in ir
                        if i.opcode == Opcode.SYMBOLIC
                        and not any(
                            "param:" in str(op) or "caught_exception:" in str(op)
                            for op in i.operands
                        )
                    )
                    results[algo][lang] = {
                        "blocks": len(cfg.blocks),
                        "edges": edges,
                        "ir_len": len(ir),
                        "param_syms": param_syms,
                        "other_syms": other_syms,
                    }
                except Exception as e:
                    results[algo][lang] = {"error": str(e)[:80]}
        except Exception as e:
            print(f"skip {modname}: {e}")
    return results


def main():
    print("Loading Rosetta corpus...")
    data = load_all_rosetta()
    print(f"Loaded {len(data)} algorithms: {sorted(data.keys())}\n")

    fmt = "{:<22} {:>4} {:>5} {:>5} {:>6} {:>6} {:>9} {:>10}"
    print(
        fmt.format(
            "algorithm", "lang", "minB", "maxB", "minE", "maxE", "variants", "unres_sym"
        )
    )
    print("-" * 85)

    for algo in sorted(data):
        good = {l: v for l, v in data[algo].items() if "error" not in v}
        if not good:
            continue
        blocks = [v["blocks"] for v in good.values()]
        edges = [v["edges"] for v in good.values()]
        other = [v["other_syms"] for v in good.values()]
        variants = len(set(zip(blocks, edges)))
        print(
            fmt.format(
                algo,
                len(good),
                min(blocks),
                max(blocks),
                min(edges),
                max(edges),
                variants,
                max(other),
            )
        )

    print()
    print("Column notes:")
    print("  lang      = number of languages with programs")
    print("  minB/maxB = min/max basic block count across languages")
    print("  minE/maxE = min/max CFG edge count")
    print("  variants  = number of distinct (blocks, edges) structural classes")
    print(
        "  unres_sym = max unresolved SYMBOLIC instructions (param/caught_exception excluded)"
    )


if __name__ == "__main__":
    main()
