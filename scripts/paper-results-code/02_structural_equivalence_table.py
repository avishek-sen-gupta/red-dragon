"""
02_structural_equivalence_table.py
-----------------------------------
Generates the full CFG structural equivalence class table (Table 2 in the
SCAM paper). For each algorithm, groups languages by (blocks, edges) shape
and assigns class labels A, B, C, ... in descending size order.

Run from the red-dragon repo root:
    poetry run python3 scripts/02_structural_equivalence_table.py [--csv]

Options:
    --csv   Output as CSV instead of plain text

Output: one row per algorithm, one column per language, cell = label(B/E).
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

LANGS = sorted(SUPPORTED_DETERMINISTIC_LANGUAGES)

LANG_SHORT = {
    "c": "C",
    "cpp": "C++",
    "csharp": "C#",
    "go": "Go",
    "java": "Java",
    "javascript": "JS",
    "kotlin": "Kt",
    "lua": "Lua",
    "pascal": "Pas",
    "php": "PHP",
    "python": "Py",
    "ruby": "Rb",
    "rust": "Rs",
    "scala": "Sc",
    "typescript": "TS",
}


def load_shapes():
    shapes = {}
    for path in sorted(glob.glob("tests/unit/rosetta/test_rosetta_*.py")):
        modname = os.path.basename(path)[:-3]
        algo = modname.replace("test_rosetta_", "")
        try:
            mod = importlib.import_module(modname)
            programs = getattr(mod, "PROGRAMS", None)
            if not programs or len(programs) < 8:
                continue
            shapes[algo] = {}
            for lang in LANGS:
                if lang not in programs:
                    continue
                fe = get_deterministic_frontend(lang)
                ir = fe.lower(programs[lang].encode())
                cfg = build_cfg(ir)
                edges = sum(len(b.successors) for b in cfg.blocks.values())
                shapes[algo][lang] = (len(cfg.blocks), edges)
        except Exception as e:
            print(f"skip {modname}: {e}", file=sys.stderr)
    return shapes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    args = parser.parse_args()

    print("Loading shapes...", file=sys.stderr)
    all_shapes = load_shapes()

    sep = "," if args.csv else " | "

    # Header
    header = ["algorithm"] + [LANG_SHORT[l] for l in LANGS] + ["classes", "dom%"]
    if args.csv:
        print(",".join(header))
    else:
        print(
            f"{'algorithm':<22}"
            + " ".join(f"{LANG_SHORT[l]:>7}" for l in LANGS)
            + "  classes  dom%"
        )
        print("-" * 120)

    for algo in sorted(all_shapes):
        d = all_shapes[algo]
        # Group by shape, sort by descending count
        groups = {}
        for lang, shape in d.items():
            groups.setdefault(shape, []).append(lang)
        shape_list = sorted(groups.keys(), key=lambda s: -len(groups[s]))
        shape_label = {s: chr(65 + i) for i, s in enumerate(shape_list)}

        cells = []
        for lang in LANGS:
            if lang not in d:
                cells.append("--")
            else:
                s = d[lang]
                cells.append(f"{shape_label[s]}({s[0]}/{s[1]})")

        n_classes = len(groups)
        dom_pct = int(100 * len(groups[shape_list[0]]) / len(d))

        if args.csv:
            print(",".join([algo] + cells + [str(n_classes), str(dom_pct)]))
        else:
            print(
                f"{algo:<22}"
                + " ".join(f"{c:>7}" for c in cells)
                + f"  {n_classes:>7}  {dom_pct:>3}%"
            )

    print()
    print(
        "Shape label key: A = dominant class (most languages), B/C/... = minority variants"
    )
    print(
        "Format: label(blocks/edges). '--' = language not in corpus for this algorithm."
    )


if __name__ == "__main__":
    main()
