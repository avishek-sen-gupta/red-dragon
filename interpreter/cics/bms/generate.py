"""Stage-0 BMS generation: .bms sources -> symbolic COBOL copybooks via bms-tools.

Runs the external pipeline `hlasm_export <map>.bms | bms-copybook-gen` once per
.bms file, writing <out_dir>/<stem>.cpy. The pipeline is an external, locally
built toolchain (see tests/integration/cics/bms_tools_helpers.py); callers gate
on its availability. No fallback parser — a failure is surfaced loudly.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_symbolic_copybooks(
    *,
    bms_dir: Path,
    out_dir: Path,
    hlasm_export_bin: str,
    bms_copybook_gen_src: str,
) -> list[Path]:
    """Generate one symbolic copybook per .bms file in bms_dir into out_dir.

    Returns the list of written .cpy paths. Raises on any tool failure (no
    silent empty output).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    env = dict(os.environ)
    env["PYTHONPATH"] = bms_copybook_gen_src + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    for bms_file in sorted(bms_dir.glob("*.bms")):
        export = subprocess.run(
            [hlasm_export_bin, str(bms_file)],
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
        out_path = out_dir / (bms_file.stem + ".cpy")
        out_path.write_bytes(gen.stdout)
        written.append(out_path)
        logger.info("BMS: generated %s from %s", out_path.name, bms_file.name)
    return written
