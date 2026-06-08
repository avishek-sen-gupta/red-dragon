"""Stage-0 BMS generation: .bms sources -> symbolic COBOL copybooks via bms-tools.

Runs the external pipeline `hlasm_export <map>.bms --syslib <macros> | bms-copybook-gen`
once per .bms file, writing <out_dir>/<stem>.cpy. The pipeline is an external,
locally built toolchain (see tests/integration/cics/bms_tools_helpers.py);
callers gate on its availability. No fallback parser — a failure is surfaced
loudly.

`hlasm_export` only recognises the BMS macros (DFHMSD/DFHMDI/DFHMDF) when their
HLASM definitions are on the assembler SYSLIB. We author minimal prototype
macros (just enough to capture each invocation's label + keyword operands) and
ship them in ``macros/`` beside this module; that dir is the default syslib.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Bundled DFHMSD/DFHMDI/DFHMDF prototype macros — the default assembler SYSLIB.
DEFAULT_MACRO_DIR = Path(__file__).parent / "macros"


def generate_symbolic_copybooks(
    *,
    bms_dir: Path,
    out_dir: Path,
    hlasm_export_bin: str,
    bms_copybook_gen_src: str,
    syslib_dirs: list[Path] | None = None,
) -> list[Path]:
    """Generate one symbolic copybook per .bms file in bms_dir into out_dir.

    Returns the list of written .cpy paths. ``syslib_dirs`` are passed to
    ``hlasm_export`` as ``--syslib`` so the BMS macros resolve; defaults to the
    bundled ``macros/`` dir. Raises on any tool failure, and on an empty
    generated copybook (which would otherwise silently shadow a real one).
    """
    syslib = syslib_dirs if syslib_dirs is not None else [DEFAULT_MACRO_DIR]
    syslib_args: list[str] = []
    for d in syslib:
        syslib_args += ["--syslib", str(d)]

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    env = dict(os.environ)
    env["PYTHONPATH"] = bms_copybook_gen_src + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    for bms_file in sorted(bms_dir.glob("*.bms")):
        export = subprocess.run(
            [hlasm_export_bin, str(bms_file), *syslib_args],
            capture_output=True,
            check=True,
        )
        gen = subprocess.run(
            ["python", "-m", "bms_copybook_gen"],
            input=export.stdout,
            capture_output=True,
            check=True,
            env=env,
        )
        if not gen.stdout.strip():
            raise RuntimeError(
                f"bms-tools produced an empty copybook for {bms_file.name}; "
                f"a BMS macro keyword is likely undeclared in {syslib}"
            )
        out_path = out_dir / (bms_file.stem + ".cpy")
        out_path.write_bytes(gen.stdout)
        written.append(out_path)
        logger.info("BMS: generated %s from %s", out_path.name, bms_file.name)
    return written
