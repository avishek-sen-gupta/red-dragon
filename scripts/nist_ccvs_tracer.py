"""CCVS failure tracer for the NIST-85 COBOL conformance suite.

Every CCVS program funnels each failing sub-test through the boilerplate FAIL
paragraph, which does ADD 1 TO ERROR-COUNTER after the test code has set the
standard work fields PAR-NAME, FEATURE, RE-MARK (and COMPUTED-*/CORRECT-*).

This tool hooks ``apply_update`` and, whenever a region write lands on
ERROR-COUNTER's offset, snapshots those fields straight from the working-storage
region — so we get, per failing assertion, *which* paragraph/feature failed and
the human-readable RE-MARK. Aggregating RE-MARK+FEATURE across programs surfaces
the shared root causes behind the "completes-but-fails" backlog (red-dragon-m0oa).

Usage: poetry run python scripts/nist_ccvs_tracer.py [PROG ...]
       (no args = every SQ/IX/RL program in the NIST corpus)
Requires PROLEAP_BRIDGE_JAR to be set.
"""

from __future__ import annotations

import collections
import importlib
import sys
import tempfile
from pathlib import Path

from interpreter.constants import FRONTEND_COBOL, Language
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.frontend import get_frontend
from tests.nist.conftest import NIST_DIR, make_provider

_runmod = importlib.import_module("interpreter.run")
_ALPHA = ("PAR-NAME", "FEATURE", "RE-MARK")


def _alpha(region: bytearray, off: int, ln: int) -> str:
    raw = bytes(region[off : off + ln])
    try:
        return EbcdicTable.ebcdic_to_ascii(raw).decode("latin-1").strip()
    except Exception:
        return raw.decode("latin-1", "replace").strip()


def trace(prog: str, max_steps: int = 400_000) -> list[dict] | None:
    """Return one snapshot dict per failing assertion, or None if not traceable."""
    src = (NIST_DIR / f"{prog}.CBL").read_text()
    fe = get_frontend(Language.COBOL, frontend_type=FRONTEND_COBOL)
    fe.lower(src.encode())
    layout = fe.data_layout
    ec = layout.get("ERROR-COUNTER")
    if not ec:
        return None
    alpha = [n for n in _ALPHA if n in layout]
    fails: list[dict] = []
    tmp = Path(tempfile.mkdtemp())
    provider, _ = make_provider(src, tmp)
    orig = _runmod.apply_update

    def patched(vm, update, *a, **k):
        r = orig(vm, update, *a, **k)
        for rw in update.region_writes:
            if rw.offset == ec["offset"]:
                reg = vm.region_get(rw.region_addr)
                if reg is None:
                    continue
                snap = {
                    n: _alpha(reg, layout[n]["offset"], layout[n]["length"])
                    for n in alpha
                }
                # Skip the ERROR-COUNTER initialization write (all work fields blank).
                if any(snap.get(n) for n in alpha):
                    fails.append(snap)
        return r

    _runmod.apply_update = patched
    try:
        _runmod.run(src, language="cobol", io_provider=provider, max_steps=max_steps)
    except Exception as exc:  # keep going; record the abort
        fails.append(
            {
                "FEATURE": f"<run aborted: {type(exc).__name__}>",
                "RE-MARK": "",
                "PAR-NAME": "",
            }
        )
    finally:
        _runmod.apply_update = orig
    return fails


def _corpus() -> list[str]:
    progs = sorted(
        p.stem for p in NIST_DIR.glob("*.CBL") if p.stem[:2] in ("SQ", "IX", "RL")
    )
    return progs


def main() -> None:
    progs = sys.argv[1:] or _corpus()
    remark_counts: collections.Counter = collections.Counter()
    feature_counts: collections.Counter = collections.Counter()
    per_prog: dict[str, int] = {}
    for prog in progs:
        fails = trace(prog)
        if not fails:
            continue
        per_prog[prog] = len(fails)
        for f in fails:
            rm = f.get("RE-MARK", "").strip() or "(blank remark)"
            ft = f.get("FEATURE", "").strip() or "(blank feature)"
            remark_counts[rm] += 1
            feature_counts[ft] += 1
    total = sum(per_prog.values())
    print(
        f"\n=== {len(per_prog)} programs with traced failures, {total} failing assertions ==="
    )
    print("\n--- top RE-MARK clusters ---")
    for rm, c in remark_counts.most_common(25):
        print(f"  {c:4}  {rm}")
    print("\n--- top FEATURE clusters ---")
    for ft, c in feature_counts.most_common(25):
        print(f"  {c:4}  {ft}")


if __name__ == "__main__":
    main()
