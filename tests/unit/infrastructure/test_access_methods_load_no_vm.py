import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_importing_the_drivers_leaves_the_vm_unloaded():
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys, infrastructure.zos.access_methods.file_drivers, infrastructure.zos.access_methods.alternate_index_driver, infrastructure.zos.access_methods.variable_sequential_driver; print(sorted(m for m in sys.modules if m.startswith('interpreter')))",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.stdout == "[]\n"
