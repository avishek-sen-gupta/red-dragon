"""
06_structural_class_groups.py
------------------------------
For each Rosetta algorithm, prints the structural class groupings
(which languages share the same (blocks, edges) shape) in a format
suitable for the paper's Section 5.3 analysis.

Run from the red-dragon repo root:
    poetry run python3 scripts/06_structural_class_groups.py [algo]

If algo is given, shows only that algorithm.
Otherwise shows all algorithms.

Output: grouped view of languages by shape, ordered by group size.
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

LANGS = sorted(SUPPORTED_DETERMINISTIC_LANGUAGES)


def load_shapes(algo_filter=None):
    shapes = {}
    for path in sorted(glob.glob("tests/unit/rosetta/test_rosetta_*.py")):
        modname = os.path.basename(path)[:-3]
        algo = modname.replace("test_rosetta_", "")
        if algo_filter and algo != algo_filter:
            continue
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
    algo_filter = sys.argv[1] if len(sys.argv) > 1 else None
    all_shapes = load_shapes(algo_filter)

    for algo in sorted(all_shapes):
        d = all_shapes[algo]
        groups = {}
        for lang, shape in d.items():
            groups.setdefault(shape, []).append(lang)
        shape_list = sorted(groups.keys(), key=lambda s: -len(groups[s]))
        n_classes = len(shape_list)
        dom = shape_list[0]
        dom_pct = int(100 * len(groups[dom]) / len(d))

        print(
            f"{algo} — {len(d)} languages, {n_classes} structural class{'es' if n_classes > 1 else ''}:"
        )
        for shape in shape_list:
            langs = sorted(groups[shape])
            label = chr(65 + shape_list.index(shape))
            print(
                f"  Class {label} ({shape[0]}B/{shape[1]}E) [{len(langs)} langs]: {' '.join(langs)}"
            )
        print(f"  Dominant class covers {dom_pct}% of languages")
        print()


if __name__ == "__main__":
    main()
