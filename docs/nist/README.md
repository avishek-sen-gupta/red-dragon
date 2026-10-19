# NIST CCVS conformance

The NIST COBOL-85 test suite (CCVS) is red-dragon's COBOL conformance measure. Its
programs live in `proleap-bridge/proleap-cobol-parser/src/test/resources/gov/nist/`, one
`.CBL` per program, and run under `tests/nist/` with the `nist` marker, which the default
test run excludes.

## Running it

```bash
make nist-report                          # the whole suite
make nist-report PYTEST_ARGS="-k 'SQ1'"   # a subset; any pytest arguments pass through
```

Each run writes a timestamped directory under `nist-reports/` (gitignored) holding
`report.md` and `junit.xml`, and prints the module table and category counts.
`uv run python -m pytest tests/nist -m nist` runs the same tests without the report.

## What the harness does to the programs

The sources run unedited. The harness (`tests/nist/conftest.py`) does what the CCVS kit's
EXEC85 step does at an installation:

- substitutes the implementor parameters (X-cards) as whole words in columns 7-72,
  X-63 and X-64 (the native collating sequence, ascending and descending) in EBCDIC
  order, red-dragon's native sequence,
- maps each `ASSIGN TO XXXXX0nn` to a file in the test's directory,
- supplies the program's input deck as 80-column records,
- links its SUBRTN subprograms and runs the run units its job runs before it.

Each program gets a step budget of 2,000,000.

## Verdicts and categories

A program passes only when it writes the CCVS end-of-test banner, its summary reports no
failed tests, and no detail line carries `FAIL*`. Every program ends in exactly one
category, decided by the type the harness raised, never by matching message text:

| Category | Verdict | Meaning |
|---|---|---|
| `pass` | pass | Ran to its banner with a clean summary. |
| `summary-failures` | fail | Ran to its banner; the summary reports failed tests. |
| `inline-failures` | fail | A detail line carries `FAIL*`. |
| `incomplete` | fail | Wrote a report but stopped before the end-of-test banner. |
| `no-summary` | fail | Wrote the banner but no `TEST(S) FAILED` summary line. |
| `step-budget-exhausted` | fail | The run used its whole step budget. |
| `error` | fail | Compiling or running raised; the report names the exception type. |
| `fips-flagger` | skip | A FIPS flagger program: its verdict is compile-time flagging messages, which red-dragon does not produce. Header and flag total are checked against the source. |
| `no-print-file` | skip | The program wrote no report at all. |
| `source-missing` | skip | The program's source is not in the corpus. |
| `unsupported` | skip | A module red-dragon does not provide (CM needs a message control system; EXEC85 needs files the corpus lacks). |

**Pass %** is pass divided by all programs in the module, skips included, so a skip never
raises the rate.

## Reports

Dated snapshots of a full run, oldest first:

- [2026-10-18](2026-10-18-conformance-report.md)
