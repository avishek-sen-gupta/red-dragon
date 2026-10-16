"""A linked file written by one process runs in a fresh one."""

import subprocess
import sys
from pathlib import Path

from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import compile_cobol
from tests.covers import NotLanguageFeature, covers

_PROGRAM = (
    b"       IDENTIFICATION DIVISION.\n"
    b"       PROGRAM-ID. ADDER.\n"
    b"       DATA DIVISION.\n"
    b"       WORKING-STORAGE SECTION.\n"
    b"       01 WS-N PIC 9(4) VALUE 5.\n"
    b"       PROCEDURE DIVISION.\n"
    b"           ADD 37 TO WS-N.\n"
    b"           DISPLAY WS-N.\n"
    b"           GOBACK.\n"
)

_RUNNER = """
import sys
from pathlib import Path
from interpreter.project.ir_codec import IrCodec
from interpreter.project.linked_codec import LinkedCodec
from interpreter.project.entry_point import EntryPoint
from interpreter.run import initial_vm_state, run_linked
from interpreter.vm.builtins import core_builtins
linked = LinkedCodec(IrCodec()).read(Path(sys.argv[1]))
run_linked(linked, EntryPoint.function(lambda ref: ref.label == linked.entry_func_label), builtins=core_builtins(), initial_vm=initial_vm_state(), max_steps=10_000)
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linked_file_runs_in_a_fresh_process(tmp_path):
    compile_cobol(_PROGRAM, parser=make_cobol_parser(), work_dir=tmp_path)
    (linked_file,) = tmp_path.glob("*.linked.json")
    runner = tmp_path / "runner.py"
    runner.write_text(_RUNNER)
    result = subprocess.run(
        [sys.executable, str(runner), str(linked_file)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.stdout.strip() == "0042"
