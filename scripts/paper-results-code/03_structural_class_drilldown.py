"""
03_structural_class_drilldown.py
---------------------------------
For a given algorithm, prints the block structure and full IR for each
language, grouped by structural class. Useful for understanding *why*
a particular language has a distinct shape.

Run from the red-dragon repo root:
    uv run python3 scripts/03_structural_class_drilldown.py <algorithm> [lang1 lang2 ...]

Examples:
    uv run python3 scripts/03_structural_class_drilldown.py factorial_rec
    uv run python3 scripts/03_structural_class_drilldown.py classes lua c go python java
    uv run python3 scripts/03_structural_class_drilldown.py fibonacci python java

If no languages are specified, all languages are shown.
"""

import importlib
import os
import sys

sys.path.insert(0, "tests/unit/rosetta")

from interpreter.cfg import build_cfg
from interpreter.frontends import (
    SUPPORTED_DETERMINISTIC_LANGUAGES,
    get_deterministic_frontend,
)
from interpreter.cli_output import emit

LANGS = sorted(SUPPORTED_DETERMINISTIC_LANGUAGES)


def main():
    if len(sys.argv) < 2:
        emit(__doc__)
        sys.exit(1)

    algo = sys.argv[1]
    requested_langs = sys.argv[2:] if len(sys.argv) > 2 else LANGS

    modname = f"test_rosetta_{algo}"
    try:
        mod = importlib.import_module(modname)
    except ModuleNotFoundError:
        emit(f"Error: no Rosetta module '{modname}'")
        emit(
            f"Available: {sorted(os.path.basename(p).replace('test_rosetta_','').replace('.py','') for p in __import__('glob').glob('tests/unit/rosetta/test_rosetta_*.py'))}"
        )
        sys.exit(1)

    programs = getattr(mod, "PROGRAMS", {})

    # Compute shapes and group
    shapes = {}
    lang_data = {}
    for lang in requested_langs:
        if lang not in programs:
            emit(f"  [{lang}] not in corpus for {algo}")
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

    emit(f"Algorithm: {algo}")
    emit(f"Structural classes: {len(shape_list)}")
    for i, s in enumerate(shape_list):
        label = shape_label[s]
        langs = sorted(shapes[s])
        emit(f"  Class {label} ({s[0]}B/{s[1]}E): {' '.join(langs)}")
    emit()

    for lang in requested_langs:
        if lang not in lang_data:
            continue
        ir, cfg, shape = lang_data[lang]
        label = shape_label[shape]
        edges = sum(len(b.successors) for b in cfg.blocks.values())

        emit(f"=== [{lang}] Class {label} ({len(cfg.blocks)}B/{edges}E) ===")
        emit(f"  Blocks: {list(cfg.blocks.keys())}")
        emit("  Successors:")
        for blk_label, block in cfg.blocks.items():
            if block.successors:
                emit(f"    {blk_label} -> {[str(s) for s in block.successors]}")
        emit(f"  IR ({len(ir)} instructions):")
        for i, inst in enumerate(ir):
            emit(f"    {i:>3}  {inst}")
        emit()


if __name__ == "__main__":
    main()
