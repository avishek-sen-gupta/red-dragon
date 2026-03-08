"""
03_structural_class_drilldown.py
---------------------------------
For a given algorithm, prints the block structure and full IR for each
language, grouped by structural class. Useful for understanding *why*
a particular language has a distinct shape.

Run from the red-dragon repo root:
    poetry run python3 scripts/03_structural_class_drilldown.py <algorithm> [lang1 lang2 ...]

Examples:
    poetry run python3 scripts/03_structural_class_drilldown.py factorial_rec
    poetry run python3 scripts/03_structural_class_drilldown.py classes lua c go python java
    poetry run python3 scripts/03_structural_class_drilldown.py fibonacci python java

If no languages are specified, all languages are shown.
"""

import sys
import os
import importlib

sys.path.insert(0, "tests/unit/rosetta")

from interpreter.cfg import build_cfg
from interpreter.frontends import (
    get_deterministic_frontend,
    SUPPORTED_DETERMINISTIC_LANGUAGES,
)

LANGS = sorted(SUPPORTED_DETERMINISTIC_LANGUAGES)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    algo = sys.argv[1]
    requested_langs = sys.argv[2:] if len(sys.argv) > 2 else LANGS

    modname = f"test_rosetta_{algo}"
    try:
        mod = importlib.import_module(modname)
    except ModuleNotFoundError:
        print(f"Error: no Rosetta module '{modname}'")
        print(
            f"Available: {sorted(os.path.basename(p).replace('test_rosetta_','').replace('.py','') for p in __import__('glob').glob('tests/unit/rosetta/test_rosetta_*.py'))}"
        )
        sys.exit(1)

    programs = getattr(mod, "PROGRAMS", {})

    # Compute shapes and group
    shapes = {}
    lang_data = {}
    for lang in requested_langs:
        if lang not in programs:
            print(f"  [{lang}] not in corpus for {algo}")
            continue
        fe = get_deterministic_frontend(lang)
        ir = fe.lower(programs[lang].encode())
        cfg = build_cfg(ir)
        edges = sum(len(b.successors) for b in cfg.blocks.values())
        shape = (len(cfg.blocks), edges)
        shapes.setdefault(shape, []).append(lang)
        lang_data[lang] = (ir, cfg, shape)

    shape_list = sorted(shapes.keys(), key=lambda s: -len(shapes[s]))
    shape_label = {s: chr(65 + i) for i, s in enumerate(shape_list)}

    print(f"Algorithm: {algo}")
    print(f"Structural classes: {len(shape_list)}")
    for i, s in enumerate(shape_list):
        label = shape_label[s]
        langs = sorted(shapes[s])
        print(f"  Class {label} ({s[0]}B/{s[1]}E): {' '.join(langs)}")
    print()

    for lang in requested_langs:
        if lang not in lang_data:
            continue
        ir, cfg, shape = lang_data[lang]
        label = shape_label[shape]
        edges = sum(len(b.successors) for b in cfg.blocks.values())

        print(f"=== [{lang}] Class {label} ({len(cfg.blocks)}B/{edges}E) ===")
        print(f"  Blocks: {list(cfg.blocks.keys())}")
        print(f"  Successors:")
        for blk_label, block in cfg.blocks.items():
            if block.successors:
                print(f"    {blk_label} -> {block.successors}")
        print(f"  IR ({len(ir)} instructions):")
        for i, inst in enumerate(ir):
            print(f"    {i:>3}  {inst}")
        print()


if __name__ == "__main__":
    main()
