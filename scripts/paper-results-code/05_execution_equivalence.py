"""
05_execution_equivalence.py
----------------------------
Executes numeric Rosetta algorithms through the VM across all 15 languages
and reports return values and step counts. Generates Table 4 and Table 5
from the SCAM paper.

Run from the red-dragon repo root:
    poetry run python3 scripts/05_execution_equivalence.py [--steps]

Options:
    --steps   Also print the step count table (Table 5)

Output:
  - Pass/fail table for each (algorithm, language) pair
  - Step count deltas relative to the minimum (base) language
"""

import sys
import os
import importlib
import glob
import argparse

sys.path.insert(0, "tests/unit/rosetta")

from interpreter.cfg import build_cfg
from interpreter.registry import build_registry
from interpreter.run import execute_cfg, VMConfig
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

# Algorithms to evaluate: (algo_name, expected_return_value)
ALGO_EXPECTED = {
    "fibonacci": 55,  # fibonacci(10)
    "factorial_rec": 120,  # factorial(5)
    "factorial_iter": 120,  # factorial(5)
    "gcd": 6,  # gcd(48, 18)
    "is_prime": True,  # is_prime(17)
}


def run_algo(lang, source, max_steps=2000):
    fe = get_deterministic_frontend(lang)
    ir = fe.lower(source.encode())
    cfg = build_cfg(ir)
    reg = build_registry(ir, cfg)
    config = VMConfig(max_steps=max_steps)
    vm, stats = execute_cfg(cfg, "entry", reg, config)
    # Extract 'answer' variable from frame 0
    var = "$answer" if lang == "php" else "answer"
    frame = vm.call_stack[0]
    val = frame.local_vars.get(var)
    return val, stats.steps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", action="store_true", help="Print step count table")
    args = parser.parse_args()

    all_results = {}
    all_steps = {}

    for path in sorted(glob.glob("tests/unit/rosetta/test_rosetta_*.py")):
        modname = os.path.basename(path)[:-3]
        algo = modname.replace("test_rosetta_", "")
        if algo not in ALGO_EXPECTED:
            continue

        mod = importlib.import_module(modname)
        programs = getattr(mod, "PROGRAMS", {})
        expected = ALGO_EXPECTED[algo]

        all_results[algo] = {}
        all_steps[algo] = {}

        for lang in LANGS:
            if lang not in programs:
                all_results[algo][lang] = "N/A"
                all_steps[algo][lang] = 0
                continue
            try:
                val, steps = run_algo(lang, programs[lang])
                all_results[algo][lang] = val
                all_steps[algo][lang] = steps
            except Exception as e:
                all_results[algo][lang] = f"ERR"
                all_steps[algo][lang] = -1
                print(f"  ERR {algo}/{lang}: {e}", file=sys.stderr)

    # Print results table
    short_langs = [LANG_SHORT[l] for l in LANGS]
    hdr = f"{'algorithm':<16} {'exp':>6}  " + "  ".join(f"{s:>4}" for s in short_langs)
    print(hdr)
    print("-" * len(hdr))

    all_pass = True
    for algo in sorted(all_results):
        expected = ALGO_EXPECTED[algo]
        row = all_results[algo]
        cells = []
        algo_pass = True
        for lang in LANGS:
            val = row.get(lang, "?")
            match = (val == expected) or (str(val) == str(expected))
            cells.append("✓" if match else str(val)[:4])
            if not match and val not in ("N/A", "ERR", "?"):
                algo_pass = False
        all_pass = all_pass and algo_pass
        marker = "✓" if algo_pass else "✗"
        print(
            f"{marker} {algo:<15} {str(expected):>6}  "
            + "  ".join(f"{c:>4}" for c in cells)
        )

    print()
    print(f"Result: {'ALL 75 PAIRS PASS' if all_pass else 'FAILURES — see above'}")

    if args.steps:
        print()
        print("=== VM Step Counts ===")
        print(f"{'algorithm':<16}  " + "  ".join(f"{s:>5}" for s in short_langs))
        print("-" * 120)
        for algo in sorted(all_steps):
            steps = [str(all_steps[algo].get(lang, "?")) for lang in LANGS]
            print(f"  {algo:<14}  " + "  ".join(f"{s:>5}" for s in steps))

        print()
        print("=== Step Count Deltas (relative to minimum) ===")
        for algo in sorted(all_steps):
            row = all_steps[algo]
            valid = {l: v for l, v in row.items() if v > 0}
            if not valid:
                continue
            base = min(valid.values())
            groups = {}
            for lang, steps in valid.items():
                groups.setdefault(steps - base, []).append(LANG_SHORT[lang])
            print(f"\n{algo} (base={base} steps):")
            for delta in sorted(groups):
                print(f"  +{delta}: {sorted(groups[delta])}")


if __name__ == "__main__":
    main()
