"""One frontend, one recorder, two programs — the sidecar must not collide.

``CollectingRecorder.effects`` is keyed by ``InstructionId``. The recorder is
held at FRONTEND level, but ``_lower_asg`` builds a FRESH ``EmitContext`` per
program. If the id counter lives in the context it restarts at 0, so program
two's instruction 0 overwrites program one's, and ``_substitute`` then hands a
``LoadRegion`` an extent belonging to an entirely different program. Nothing
raises: its ``AssertionError`` only fires for a NON-region instruction, and
both colliding instructions are region accesses. The result is wrong or
missing dependency edges with no error anywhere — the exact failure this
analysis exists to prevent.

Every other test lowers one program per frontend, so none of them can see it.
"""

from __future__ import annotations

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.memory_effects import CollectingRecorder
from tests.covers import NotLanguageFeature, covers

_ALPHA = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ALPHA.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  ALPHA-SRC   PIC X(10).
       01  ALPHA-DST   PIC X(10).
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 'HELLO' TO ALPHA-SRC.
           MOVE ALPHA-SRC TO ALPHA-DST.
           STOP RUN.
"""

_BETA = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BETA.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  BETA-SRC    PIC X(4).
       01  BETA-MID    PIC X(4).
       01  BETA-DST    PIC X(4).
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 'WXYZ' TO BETA-SRC.
           MOVE BETA-SRC TO BETA-MID.
           MOVE BETA-MID TO BETA-DST.
           STOP RUN.
"""


def _lower_alone(source: bytes) -> CollectingRecorder:
    recorder = CollectingRecorder()
    CobolFrontend(make_cobol_parser(), recorder=recorder).lower(source)
    return recorder


def _field_names(recorder: CollectingRecorder) -> set[str]:
    return {effect.extent.field_name for effect in recorder.effects.values()}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_two_programs_through_one_frontend_keep_both_sidecars():
    alpha_alone = _lower_alone(_ALPHA)
    beta_alone = _lower_alone(_BETA)

    shared = CollectingRecorder()
    frontend = CobolFrontend(make_cobol_parser(), recorder=shared)
    frontend.lower(_ALPHA)
    frontend.lower(_BETA)

    # Nothing overwritten: the shared sidecar is the exact sum of the two.
    assert len(shared.effects) == len(alpha_alone.effects) + len(beta_alone.effects)

    # And both programs' fields are still described, not just the last one's.
    names = _field_names(shared)
    assert _field_names(alpha_alone) <= names
    assert _field_names(beta_alone) <= names
    assert {"ALPHA-SRC", "ALPHA-DST", "BETA-SRC", "BETA-DST"} <= names


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_instruction_ids_do_not_restart_for_the_second_program():
    """The mechanism behind the guarantee above, asserted directly.

    Stated as a property of the emitted IR rather than of the recorder, so it
    still fails if a future change makes the recorder tolerant of collisions
    instead of keeping ids unique.
    """
    frontend = CobolFrontend(make_cobol_parser(), recorder=CollectingRecorder())
    alpha_ids = {inst.id for inst in frontend.lower(_ALPHA)}
    beta_ids = {inst.id for inst in frontend.lower(_BETA)}

    assert alpha_ids & beta_ids == set()
    assert min(beta_ids) > max(alpha_ids)
