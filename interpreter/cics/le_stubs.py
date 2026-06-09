"""Minimal COBOL stubs for IBM Language Environment (LE) callable services.

Some CardDemo programs CALL LE services that have no COBOL source in the
application (they are supplied by the z/OS LE runtime). To let those programs
run end to end under RedDragon, we provide small COBOL stand-ins that are linked
exactly like any other CALLed subprogram (via the project linker, see
``interpreter.cics.bootstrap.compile_cics_program``).

Currently provided
-------------------
``CEEDAYS`` — convert a date string to Lilian days and set a feedback code.
    CSUTLDTC.cbl calls it as::

        CALL "CEEDAYS" USING WS-DATE-TO-TEST   (Vstring: S9(4) BINARY len + text)
                             WS-DATE-FORMAT     (Vstring: S9(4) BINARY len + text)
                             OUTPUT-LILLIAN     (S9(9) BINARY)
                             FEEDBACK-CODE      (12-byte LE feedback token)

    CSUTLDTC only cares about the feedback *severity*: it moves
    ``SEVERITY OF FEEDBACK-CODE`` (the first ``S9(4) BINARY`` halfword of the
    token) into a ``PIC 9(4)`` and the caller (COTRN02C) tests
    ``CSUTLDTC-RESULT-SEV-CD = '0000'``. The LE convention is that an all-zero
    feedback token means success (severity 0); CSUTLDTC's ``FC-INVALID-DATE``
    88-level (``VALUE X'00...00'``) maps to the "Date is valid" branch.

    This stub validates the date assuming the standard CardDemo picture string
    ``YYYY-MM-DD`` (the only format COTRN02C passes, via WS-DATE-FORMAT). On a
    valid Gregorian date it sets the whole feedback token to zero (severity 0)
    and the Lilian-days output; on an invalid date it sets severity 12 (a
    nonzero LE-style severity) so the caller's ``SEV-CD = '0000'`` test fails and
    the date-validation error path runs.

Scope / deferrals
-----------------
  * Only the ``YYYY-MM-DD`` picture string is honoured; other LE picture strings
    (e.g. ``MM/DD/YYYY``, Julian, era forms) are not parsed — any non-numeric or
    out-of-range component yields severity 12. CardDemo's transaction-add flow
    always passes ``YYYY-MM-DD``.
  * The Lilian-days output is computed as days since 1600-12-31 (reusing the
    existing ``INTEGER-OF-DATE`` semantics) rather than the true LE Lilian epoch
    of 1582-10-14. CSUTLDTC discards the Lilian value for its valid/invalid
    decision (only the severity gates the flow), so the absolute epoch is
    immaterial to the programs that consume it here.
  * The specific message-number tokens CSUTLDTC distinguishes (insufficient
    data, bad era, etc.) are not reproduced; valid → severity 0, invalid →
    severity 12. COTRN02C's secondary ``MSG-NUM = '2513'`` check is only
    consulted when severity is nonzero, and treats any non-2513 as a hard error
    — which is the correct outcome for a genuinely invalid date.
"""

from __future__ import annotations

# CEEDAYS LE-service stub. Fixed-format COBOL (cols 8+); the bootstrap pre-passes
# and links it like any other CALLed subprogram.
CEEDAYS_STUB_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CEEDAYS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-YYYY        PIC 9(4) VALUE 0.
       01 WS-MM          PIC 9(2) VALUE 0.
       01 WS-DD          PIC 9(2) VALUE 0.
       01 WS-YYYYMMDD    PIC 9(8) VALUE 0.
       01 WS-MAX-DAY     PIC 9(2) VALUE 0.
       01 WS-VALID       PIC X VALUE 'Y'.
       01 WS-R4          PIC 9(4) VALUE 0.
       01 WS-R100        PIC 9(4) VALUE 0.
       01 WS-R400        PIC 9(4) VALUE 0.
       LINKAGE SECTION.
       01 LS-DATE-VS.
          05 LS-DATE-LEN   PIC S9(4) BINARY.
          05 LS-DATE-TXT   PIC X(256).
       01 LS-FMT-VS.
          05 LS-FMT-LEN    PIC S9(4) BINARY.
          05 LS-FMT-TXT    PIC X(256).
       01 LS-LILIAN        PIC S9(9) BINARY.
       01 LS-FEEDBACK.
          05 LS-FB-SEV     PIC S9(4) BINARY.
          05 LS-FB-MSG     PIC S9(4) BINARY.
          05 FILLER        PIC X(8).
       PROCEDURE DIVISION USING LS-DATE-VS LS-FMT-VS
                                LS-LILIAN LS-FEEDBACK.
           MOVE 'Y' TO WS-VALID
           MOVE 0   TO LS-FB-SEV
           MOVE 0   TO LS-FB-MSG
           MOVE 0   TO LS-LILIAN

      *    Expect the YYYY-MM-DD picture string (the only form CardDemo uses).
           IF LS-DATE-TXT(1:4) IS NOT NUMERIC
               MOVE 'N' TO WS-VALID
           END-IF
           IF LS-DATE-TXT(6:2) IS NOT NUMERIC
               MOVE 'N' TO WS-VALID
           END-IF
           IF LS-DATE-TXT(9:2) IS NOT NUMERIC
               MOVE 'N' TO WS-VALID
           END-IF

           IF WS-VALID = 'Y'
               MOVE LS-DATE-TXT(1:4) TO WS-YYYY
               MOVE LS-DATE-TXT(6:2) TO WS-MM
               MOVE LS-DATE-TXT(9:2) TO WS-DD

               IF WS-MM < 1 OR WS-MM > 12
                   MOVE 'N' TO WS-VALID
               END-IF
               IF WS-DD < 1
                   MOVE 'N' TO WS-VALID
               END-IF

               EVALUATE WS-MM
                   WHEN 1
                   WHEN 3
                   WHEN 5
                   WHEN 7
                   WHEN 8
                   WHEN 10
                   WHEN 12
                       MOVE 31 TO WS-MAX-DAY
                   WHEN 4
                   WHEN 6
                   WHEN 9
                   WHEN 11
                       MOVE 30 TO WS-MAX-DAY
                   WHEN 2
                       COMPUTE WS-R4 =
                           WS-YYYY - (WS-YYYY / 4 * 4)
                       COMPUTE WS-R100 =
                           WS-YYYY - (WS-YYYY / 100 * 100)
                       COMPUTE WS-R400 =
                           WS-YYYY - (WS-YYYY / 400 * 400)
                       IF WS-R400 = 0
                           MOVE 29 TO WS-MAX-DAY
                       ELSE
                           IF WS-R100 = 0
                               MOVE 28 TO WS-MAX-DAY
                           ELSE
                               IF WS-R4 = 0
                                   MOVE 29 TO WS-MAX-DAY
                               ELSE
                                   MOVE 28 TO WS-MAX-DAY
                               END-IF
                           END-IF
                       END-IF
                   WHEN OTHER
                       MOVE 0 TO WS-MAX-DAY
               END-EVALUATE

               IF WS-DD > WS-MAX-DAY
                   MOVE 'N' TO WS-VALID
               END-IF
           END-IF

           IF WS-VALID = 'Y'
               COMPUTE WS-YYYYMMDD =
                   (WS-YYYY * 10000) + (WS-MM * 100) + WS-DD
               COMPUTE LS-LILIAN =
                   FUNCTION INTEGER-OF-DATE(WS-YYYYMMDD)
               MOVE 0  TO LS-FB-SEV
               MOVE 0  TO LS-FB-MSG
           ELSE
               MOVE 12 TO LS-FB-SEV
               MOVE 1  TO LS-FB-MSG
           END-IF

           EXIT PROGRAM.
"""


def le_service_stub_sources() -> dict[str, bytes]:
    """Pre-passed LE-service stub sources, keyed by program name.

    Suitable to pass as ``extra_subprogram_sources`` to
    :func:`interpreter.cics.bootstrap.compile_cics_program` /
    :func:`run_carddemo_region` so CALLs to these LE services resolve.
    """
    from interpreter.cics.preprocessor import apply_cics_prepass

    return {"CEEDAYS": apply_cics_prepass(CEEDAYS_STUB_SOURCE).encode()}
