# NIST CCVS conformance report, 2026-10-18

Point-in-time snapshot of `make nist-report` over the whole suite at red-dragon 88fd34c7 plus the typed harness (4fa3880d). Categories and the pass % definition are in [README.md](README.md).

| Module | Pass | Fail | Skip | Total | Pass % |
|---|---:|---:|---:|---:|---:|
| CM | 0 | 0 | 9 | 9 | 0.0 |
| DB | 0 | 10 | 5 | 15 | 0.0 |
| EX | 0 | 0 | 1 | 1 | 0.0 |
| IC | 12 | 13 | 0 | 25 | 48.0 |
| IF | 40 | 2 | 3 | 45 | 88.9 |
| IX | 28 | 11 | 3 | 42 | 66.7 |
| NC | 92 | 0 | 3 | 95 | 96.8 |
| OB | 5 | 2 | 0 | 7 | 71.4 |
| RL | 32 | 0 | 3 | 35 | 91.4 |
| RW | 0 | 6 | 0 | 6 | 0.0 |
| SG | 4 | 6 | 3 | 13 | 30.8 |
| SM | 10 | 5 | 2 | 17 | 58.8 |
| SQ | 73 | 9 | 3 | 85 | 85.9 |
| ST | 27 | 6 | 7 | 40 | 67.5 |
| Overall | 323 | 70 | 42 | 435 | 74.3 |

## Categories

### pass (323)

IC101A, IC103A, IC106A, IC108A, IC112A, IC114A, IC116M, IC201A, IC207A, IC209A, IC213A, IC216A, IF101A, IF102A, IF103A, IF104A, IF106A, IF107A, IF108A, IF109A, IF110A, IF111A, IF112A, IF113A, IF114A, IF115A, IF116A, IF117A, IF118A, IF119A, IF120A, IF121A, IF122A, IF123A, IF124A, IF125A, IF126A, IF128A, IF129A, IF130A, IF131A, IF132A, IF133A, IF134A, IF135A, IF136A, IF137A, IF138A, IF139A, IF140A, IF141A, IF142A, IX101A, IX102A, IX103A, IX104A, IX105A, IX106A, IX107A, IX108A, IX109A, IX110A, IX111A, IX112A, IX113A, IX114A, IX115A, IX116A, IX117A, IX118A, IX119A, IX120A, IX121A, IX201A, IX202A, IX203A, IX204A, IX216A, IX217A, IX218A, NC101A, NC102A, NC103A, NC104A, NC105A, NC106A, NC107A, NC108M, NC109M, NC110M, NC111A, NC112A, NC113M, NC114M, NC115A, NC116A, NC117A, NC118A, NC119A, NC120A, NC121M, NC122A, NC123A, NC124A, NC125A, NC126A, NC127A, NC131A, NC132A, NC133A, NC134A, NC135A, NC136A, NC137A, NC138A, NC139A, NC140A, NC141A, NC170A, NC171A, NC172A, NC173A, NC174A, NC175A, NC176A, NC177A, NC201A, NC202A, NC203A, NC204M, NC205A, NC206A, NC207A, NC208A, NC209A, NC210A, NC211A, NC214M, NC215A, NC216A, NC217A, NC218A, NC219A, NC220M, NC221A, NC222A, NC223A, NC224A, NC225A, NC231A, NC232A, NC233A, NC234A, NC235A, NC236A, NC237A, NC238A, NC239A, NC240A, NC241A, NC242A, NC243A, NC244A, NC245A, NC246A, NC247A, NC248A, NC250A, NC251A, NC252A, NC253A, NC254A, OBIC1A, OBSQ1A, OBSQ3A, OBSQ4A, OBSQ5A, RL101A, RL102A, RL103A, RL104A, RL105A, RL106A, RL107A, RL108A, RL109A, RL110A, RL111A, RL112A, RL113A, RL114A, RL115A, RL116A, RL117A, RL118A, RL119A, RL201A, RL202A, RL203A, RL204A, RL205A, RL206A, RL207A, RL208A, RL209A, RL210A, RL211A, RL212A, RL213A, SG101A, SG104A, SG105A, SG106A, SM101A, SM102A, SM103A, SM104A, SM105A, SM106A, SM107A, SM201A, SM203A, SM205A, SQ101M, SQ102A, SQ103A, SQ104A, SQ105A, SQ106A, SQ107A, SQ108A, SQ112A, SQ113A, SQ114A, SQ115A, SQ116A, SQ117A, SQ121A, SQ122A, SQ125A, SQ126A, SQ127A, SQ128A, SQ129A, SQ130A, SQ131A, SQ132A, SQ133A, SQ134A, SQ135A, SQ136A, SQ137A, SQ138A, SQ139A, SQ140A, SQ141A, SQ142A, SQ143A, SQ144A, SQ146A, SQ147A, SQ148A, SQ149A, SQ150A, SQ151A, SQ152A, SQ153A, SQ154A, SQ155A, SQ156A, SQ202A, SQ203A, SQ204A, SQ205A, SQ206A, SQ207M, SQ211A, SQ212A, SQ213A, SQ214A, SQ215A, SQ216A, SQ217A, SQ218A, SQ219A, SQ220A, SQ221A, SQ222A, SQ223A, SQ224A, SQ225A, SQ226A, SQ227A, SQ228A, SQ229A, SQ230A, ST101A, ST103A, ST104A, ST105A, ST106A, ST107A, ST108A, ST109A, ST112M, ST114M, ST115A, ST117A, ST118A, ST119A, ST121A, ST122A, ST125A, ST126A, ST127A, ST132A, ST133A, ST134A, ST135A, ST136A, ST139A, ST140A, ST146A

### incomplete (1)

OBNC1M

### summary-failures (30)

IC203A, IF105A, IX205A, IX206A, IX207A, IX208A, IX209A, IX210A, IX211A, IX212A, IX213A, IX214A, IX215A, OBNC2M, SG103A, SG201A, SG202A, SG204A, SM204A, SM207A, SM208A, SQ111A, SQ123A, SQ124A, ST111A, ST124A, ST131A, ST137A, ST144A, ST147A

### step-budget-exhausted (5)

IF127A, SG102A, SG203A, SQ109M, SQ110M

### error (34)

DB101A, DB102A, DB103M, DB104A, DB105A, DB201A, DB202A, DB203A, DB204A, DB205A, IC222A, IC223A, IC224A, IC225A, IC226A, IC227A, IC228A, IC233A, IC234A, IC235A, IC237A, IC401M, RW101A, RW102A, RW103A, RW104A, RW301M, RW302M, SM202A, SM206A, SQ201M, SQ208M, SQ209M, SQ210M

### fips-flagger (28)

CM303M, CM401M, DB301M, DB302M, DB303M, DB304M, DB305M, IF401M, IF402M, IF403M, IX301M, IX302M, IX401M, NC302M, NC303M, NC401M, RL301M, RL302M, RL401M, SG302M, SG303M, SG401M, SM301M, SM401M, SQ302M, SQ303M, SQ401M, ST301M

### no-print-file (6)

ST102A, ST110A, ST113M, ST116A, ST120A, ST123A

### unsupported (8)

CM101M, CM102M, CM103M, CM104M, CM105M, CM201M, CM202M, EXEC85

## First failure line per program

- DB101A (error): UndeclaredDataNameError: line 222: data name 'DEBUG-LINE' is not declared in the DATA DIVISION
- DB102A (error): UndeclaredDataNameError: line 216: data name 'DEBUG-LINE' is not declared in the DATA DIVISION
- DB103M (error): UndeclaredDataNameError: line 214: data name 'DEBUG-LINE' is not declared in the DATA DIVISION
- DB104A (error): UndeclaredDataNameError: line 287: data name 'DEBUG-LINE' is not declared in the DATA DIVISION
- DB105A (error): UndeclaredDataNameError: line 513: data name 'DEBUG-NAME' is not declared in the DATA DIVISION
- DB201A (error): UndeclaredDataNameError: line 233: data name 'DEBUG-LINE' is not declared in the DATA DIVISION
- DB202A (error): UndeclaredDataNameError: line 259: data name 'DEBUG-LINE' is not declared in the DATA DIVISION
- DB203A (error): UndeclaredDataNameError: line 276: data name 'DEBUG-LINE' is not declared in the DATA DIVISION
- DB204A (error): UndeclaredDataNameError: line 287: data name 'DEBUG-LINE' is not declared in the DATA DIVISION
- DB205A (error): ValueError: Unknown COBOL statement type: 'DISABLE'
- IC203A (summary-failures): IC203A: CCVS summary reports 13 failed test(s).
- IC222A (error): UnresolvedProgramError: CALL to __entry_IC222A-1, but nothing in this run unit is registered under it
- IC223A (error): UnresolvedProgramError: CALL to __entry_IC223A-1, but nothing in this run unit is registered under it
- IC224A (error): UnresolvedProgramError: CALL to __entry_IC224A-1, but nothing in this run unit is registered under it
- IC225A (error): UnresolvedProgramError: CALL to __entry_IC225A-1, but nothing in this run unit is registered under it
- IC226A (error): UnresolvedProgramError: CALL to __entry_IC226A-1, but nothing in this run unit is registered under it
- IC227A (error): UnresolvedProgramError: CALL to __entry_IC227A-1, but nothing in this run unit is registered under it
- IC228A (error): UnresolvedProgramError: CALL to __entry_IC228A-1, but nothing in this run unit is registered under it
- IC233A (error): UnresolvedProgramError: CALL to __entry_IC233A-1, but nothing in this run unit is registered under it
- IC234A (error): UnresolvedProgramError: CALL to __entry_IC234A-1, but nothing in this run unit is registered under it
- IC235A (error): UnresolvedProgramError: CALL to __entry_IC235A-2, but nothing in this run unit is registered under it
- IC237A (error): UnresolvedProgramError: CALL to __entry_IC237A-1, but nothing in this run unit is registered under it
- IC401M (error): UnresolvedProgramError: CALL to __entry_NESTEDPROG, but nothing in this run unit is registered under it
- IF105A (summary-failures): IF105A: CCVS summary reports 6 failed test(s).
- IF127A (step-budget-exhausted): IF127A: step budget of 2000000 exhausted before the program ended.
- IX205A (summary-failures): IX205A: CCVS summary reports 4 failed test(s).
- IX206A (summary-failures): IX206A: CCVS summary reports 3 failed test(s).
- IX207A (summary-failures): IX207A: CCVS summary reports 3 failed test(s).
- IX208A (summary-failures): IX208A: CCVS summary reports 9 failed test(s).
- IX209A (summary-failures): IX209A: CCVS summary reports 13 failed test(s).
- IX210A (summary-failures): IX210A: CCVS summary reports 9 failed test(s).
- IX211A (summary-failures): IX211A: CCVS summary reports 4 failed test(s).
- IX212A (summary-failures): IX212A: CCVS summary reports 15 failed test(s).
- IX213A (summary-failures): IX213A: CCVS summary reports 16 failed test(s).
- IX214A (summary-failures): IX214A: CCVS summary reports 9 failed test(s).
- IX215A (summary-failures): IX215A: CCVS summary reports 19 failed test(s).
- OBNC1M (incomplete): OBNC1M: did not run to completion — 'END OF TEST' banner absent (49 record(s) written). Program halted before its summary.
- OBNC2M (summary-failures): OBNC2M: CCVS summary reports 16 failed test(s).
- RW101A (error): ValueError: Unknown COBOL statement type: 'INITIATE'
- RW102A (error): ValueError: Unknown COBOL statement type: 'INITIATE'
- RW103A (error): ValueError: Unknown COBOL statement type: 'INITIATE'
- RW104A (error): ValueError: Unknown COBOL statement type: 'INITIATE'
- RW301M (error): ValueError: Unknown COBOL statement type: 'INITIATE'
- RW302M (error): ValueError: Unknown COBOL statement type: 'INITIATE'
- SG102A (step-budget-exhausted): SG102A: step budget of 2000000 exhausted before the program ended.
- SG103A (summary-failures): SG103A: CCVS summary reports 1 failed test(s).
- SG201A (summary-failures): SG201A: CCVS summary reports 48 failed test(s).
- SG202A (summary-failures): SG202A: CCVS summary reports 2 failed test(s).
- SG203A (step-budget-exhausted): SG203A: step budget of 2000000 exhausted before the program ended.
- SG204A (summary-failures): SG204A: CCVS summary reports 6 failed test(s).
- SM202A (error): CobolAmbiguousReferenceError: *** Guru Meditation Error #00A18105.C0BF1E1D ***
- SM204A (summary-failures): SM204A: CCVS summary reports 4 failed test(s).
- SM206A (error): UndeclaredDataNameError: line 435: data name 'WRK-DS-05V00-O005-00-3' is not declared in the DATA DIVISION
- SM207A (summary-failures): SM207A: CCVS summary reports 1 failed test(s).
- SM208A (summary-failures): SM208A: CCVS summary reports 2 failed test(s).
- SQ109M (step-budget-exhausted): SQ109M: step budget of 2000000 exhausted before the program ended.
- SQ110M (step-budget-exhausted): SQ110M: step budget of 2000000 exhausted before the program ended.
- SQ111A (summary-failures): SQ111A: CCVS summary reports 1 failed test(s).
- SQ123A (summary-failures): SQ123A: CCVS summary reports 2 failed test(s).
- SQ124A (summary-failures): SQ124A: CCVS summary reports 12 failed test(s).
- SQ201M (error): UndeclaredDataNameError: line 363: data name 'LINAGE-COUNTER' is not declared in the DATA DIVISION
- SQ208M (error): UndeclaredDataNameError: line 572: data name 'LINAGE-COUNTER' is not declared in the DATA DIVISION
- SQ209M (error): UndeclaredDataNameError: line 412: data name 'LINAGE-COUNTER' is not declared in the DATA DIVISION
- SQ210M (error): UndeclaredDataNameError: line 354: data name 'LINAGE-COUNTER' is not declared in the DATA DIVISION
- ST111A (summary-failures): ST111A: CCVS summary reports 7 failed test(s).
- ST124A (summary-failures): ST124A: CCVS summary reports 7 failed test(s).
- ST131A (summary-failures): ST131A: CCVS summary reports 6 failed test(s).
- ST137A (summary-failures): ST137A: CCVS summary reports 4 failed test(s).
- ST144A (summary-failures): ST144A: CCVS summary reports 1 failed test(s).
- ST147A (summary-failures): ST147A: CCVS summary reports 12 failed test(s).
