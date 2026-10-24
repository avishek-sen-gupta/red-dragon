# HLASM wave 3: system services, binder and COBOL linkage

Extends `2026-10-21-hlasm-frontend-design.md` for wave 3, which runs after wave 4
(`2026-10-23-hlasm-macro-wave-design.md`). It fixes the data shapes first: what a unit
carries, how modules are bound, how control and arguments cross modules and languages,
and the state each service keeps. Evidence: a survey of the code and IBM's manuals, and
an adversarial review of a first draft. Manual references: z/OS MVS Assembler Services
Guide (linkage conventions), Assembler Services Reference, DFSMS Macro Instructions for
Data Sets, MVS System Codes, Enterprise COBOL Programming Guide and Language Reference.

## Where things stand

- One assembly is one unit, always at `__main__.asm`. Start-up IR is rebuilt from the AST
  at link and sets the entry registers for that one program. V-constants assemble to
  zero, ENTRY is not exported, and nothing registers an HLASM program for a COBOL `CALL`.
- The VM has one flat address space. A COBOL `{region, offset}` already holds the region's
  base address, so COBOL and HLASM addresses are the same integers. No translation table
  is needed.
- `SVC` dispatches through a static number table (WTO 35, ABEND 13). Our maclib holds
  WTO and ABEND.
- The VM's allocator never aligns. A mixed image breaks the doubleword alignment that
  HLASM sections get today only from allocation order.
- Branch lowering does not record whether an instruction linked: BAL, BALR, BAS, BASR,
  BRAS and BRASL all end in the same branch.

## Decisions

### 1. The unit carries an object module

An HLASM unit carries a typed `ObjectModule` field (a null object for other languages;
the unit file format moves up). Its records follow the object-module format:

- **ESD**: control sections (SD, private code), common sections (CM), ENTRY labels (LD,
  as section and offset), external references (ER, WX), and external dummy sections
  (PR/XD) with length and alignment.
- **TXT**: each section's constant images (today's placed pieces).
- **RLD**: (section, offset, length, kind) → target, sign and addend. The kind is
  ADDRESS (A, V), PR_OFFSET (Q), CLASS_LENGTH (J) or PR_TOTAL (CXD, no target). The
  enum is defined in full in .8; .96 implements the last three.
- **END**: the entry point, named or default.

Start-up IR is no longer regenerated from the AST at link. The bridge exports ENTRY
statements. Each assembly gets its own module path, and names are qualified by module,
so private code and same-named helpers in two modules do not collide.

### 2. Link is a binder

- Each module is laid out as **one region**, its sections at aligned offsets in ESD
  order. The region is over-allocated so the module starts doubleword aligned. CM
  sections are merged by name at the largest length.
- Every RLD is applied once every module is laid out, since a V-constant may point at a later module.
- The binder builds the name → address map and the far-branch table (decision 3), whose
  entries are (low, high, owner); the owner is a module, a COBOL program or an
  unresolved name.
- **Start-up** does machine allocation, layout and RLD only, once. Each HLASM entry name
  gets a **job-step trampoline**, and the image's `programs` maps the name to it. The
  trampoline sets R1 (the PARM list), R13 (a fresh save area), R14 (the return sentinel)
  and R15 (the entry address), then enters the module. A run chooses the trampoline with
  `ProgramEntry` exactly as it chooses a COBOL program.
- **Job-step PARM.** R1 points to a one-entry VL list whose word points to a halfword
  length and the PARM text. The text is a run input; unsupplied, it is empty (as
  `&SYSPARM`, R57). No CLI flag this wave.
- **Unresolved names.** An unresolved WXTRN is 0, since programs test it with LTR. Each
  unresolved EXTRN gets its own stub address in a link-allocated range, recorded by name,
  and is logged as a warning. A branch to a stub issues `CallWithMemory` on the literal
  `__entry_<NAME>`, so it follows exactly the path of a static COBOL `CALL 'NAME'` to a
  missing program: the unresolved-call strategy when unresolved targets are permitted,
  `UnresolvedProgramError` otherwise. The result goes to R15 and control returns to R14.
  LINK `EP=` to a missing name takes the same path; LOAD abends 806 (or takes ERRET),
  since it must produce an address. Running incomplete programs is RedDragon's purpose.
- **Duplicate names.** A name defined twice in the image (an SD, an LD or a COBOL
  PROGRAM-ID) is refused before link, naming both units, as COBOL already refuses
  duplicate programs.

### 3. Control crosses modules through addresses

- One IR function per module. It starts by dispatching on a target address, so any entry
  works: CSECT start, ENTRY label, the address LOAD returned, `CALL (15)`.
- Each activation declares (`DeclVar`) its return address from R14 and the set of modules
  below it on the stack: its caller's set plus its caller's module. A COBOL frame starts
  an empty set.
- A branch inside the module stays local. A branch whose masked target equals the
  activation's masked return address returns R15's low word. The dispatch and BSM/BASSM
  use the same comparison, so the mode bit a linking instruction sets does not matter.
- A branch outside the module made by a **linking instruction** (BAL, BALR, BAS, BASR,
  BRAS, BRASL, BASSM) is a **call**: the far branch finds the owner in the table and
  calls it with `CallWithMemory`. Linking branches get their own dispatch entry; .8 fixes
  that IR shape, since every branch lowering emits it.
- Any other branch outside the module is a **return** when its owning module has an
  activation further down the stack: the activation returns, and the one below
  re-dispatches on the target. So `B 4(,14)` and a return that skips a level both work.
  Otherwise it is a call (`LA 14,RET; L 15,=V(X); BR 15`).
- An address owned by nothing abends S0C1. Today's `0xFF0` sentinel becomes the job-step
  trampoline's R14.
- Registers stay machine state shared by every activation, as on the hardware.

### 4. Arguments between COBOL and HLASM

- Each CSECT and ENTRY name registers `__entry_<NAME>` as a short trampoline into one
  shared conversion function. It turns the COBOL argument array into a standard R1 list
  (VL bit on the last entry), gives R13 a fresh 72-byte save area, and sets R14 to the
  return marker and R15 to the entry address.
- Each COBOL program gets a stub address (an owner in the far-branch table). A call to it
  builds the argument array from the R1 list, saves R14–R12 at 12(R13) and restores them
  after, sets R15 to RETURN-CODE and returns.
- **The argument element** gains its passing mode and byte length; both construction
  sites change (`lower_call` and the harness's `call_arguments`). BY VALUE puts the value
  in the list, as IBM does, not the address of a copy. BY VALUE items are 1, 2, 4 or 8
  bytes. OMITTED is a zero word, or X'80000000' in last position.
- **The COBOL program record exposes its USING signature**: one (mode, byte length) per
  position. The HLASM→COBOL conversion walks the R1 list by that signature, treats the VL
  bit as the end only at a BY REFERENCE or BY CONTENT position, and caps the walk at the
  signature length.
- The slot layout of 1-, 2- and 8-byte BY VALUE values, and whether COBOL sets VL after a
  trailing BY VALUE, are not settled by the manuals at hand; .15 settles them from IBM's
  documentation before writing tests.
- COBOL `CANCEL` of an HLASM program does nothing.

### 5. Services

- **Reaching a primitive.** Our macros issue `SVC n` with the z/OS register protocol, and
  lowering dispatches by number in IR. Numbers: GETMAIN/FREEMAIN R form 10 (GETMAIN
  when R1 is negative); RU/RC form and STORAGE 120; LINK 6; LOAD 8; DELETE 9; OPEN 19;
  CLOSE 20; TIME 11. GET and PUT have no SVC on z/OS, so they take 200 and 201.
  Hand-coded `L 15,48(,1); BALR 14,15` into a DCB's GET routine is a documented gap.
  A builtin appears only where the work leaves the program: the file provider, and
  declaring a file at OPEN (below).
- **SAVE, RETURN and CALL** are instructions only (STM, LM, BALR). RETURN T sets X'FF'
  at offset 12 of the save area. Save areas are the 72-byte format-0 area only, since the
  machine stays in AMODE 31.
- **GETMAIN, FREEMAIN, STORAGE.** One region per request, doubleword aligned (page
  aligned for BNDRY=PAGE), length rounded up to 8. A run-unit allocation table maps
  address to (length, subpool). FREEMAIN and STORAGE RELEASE check it and abend on a bad
  free (A0A for SVC 10, A78 for SVC 120). Storage is always obtained; GETMAIN RC and
  `STORAGE COND=YES` set R15 to 0. Freed storage is not reused (a documented gap).
- **LINK, LOAD, DELETE.** One image holds every module. LINK and LOAD look the name up in
  the binder's map. LOAD returns the entry address in R0 (bit 0 set for AMODE 31) and, in
  R1, 0 in the high byte and the module's region length in doublewords. LOAD returns the
  same copy every time; there is no fresh copy for non-reusable modules (a documented
  gap). DELETE does nothing but succeed.
- **TIME** (SVC 11) reads the run's existing TOD clock.
- **DCB.** Our DCB macro lays out a 96-byte block at IBM's offsets (DSORG 26, EODAD 32,
  RECFM 36, DDNAME 40, OFLGS 48, MACRF 50, SYNAD 56, BLKSIZE 62, LRECL 82). OPEN, GET,
  PUT and CLOSE read the fields from storage on each call; DDNAME stays at offset 40 after
  OPEN. EODAD, SYNAD and EXLST are 24-bit; an address at or above 2^24 is refused when the
  DCB is assembled.
  - **DD definitions** are a run input: per DDNAME, a path and optionally RECFM, LRECL and
    BLKSIZE. OPEN fills any zero DCB field from the DD, writes the merged values into the
    DCB, then declares the file through `__hlasm_declare_file(ddname, variable, lrecl)`,
    a builtin because the file frame is built from run-time values. A DD with no file
    leaves DCBOFOPN off and sets R15 to 8; it does not abend.
  - OPEN takes the mode from the low four bits of the option byte (INPUT 0, OUTPUT 15,
    EXTEND 14, …) and sets DCBOFOPN.
  - GET in move mode copies the record to R0's area; in locate mode (MACRF=GL) OPEN
    obtains an LRECL buffer per DCB and GET returns its address in R1. End of data
    branches to EODAD, or abends 337 without one. RECFM V records carry their RDW.
  - The file provider is the COBOL one, which finds files by name, so a COBOL file and an HLASM DDNAME
    share one namespace in a mixed image (a documented gap).
- **Macros in our maclib**, written by us (copying IBM's is ruled out): SAVE, RETURN,
  CALL, GETMAIN, FREEMAIN, STORAGE, LINK, LOAD, DELETE, TIME, DCB, DCBD, OPEN, CLOSE,
  GET, PUT, YREGS.
- **Abends** halt the whole run unit, COBOL callers included. COBOL has no abend model a
  caller could observe.

## Not in this wave

XCTL, EXIT, ATTACH, ESTAE; F4SA/F5SA save areas (they wait for AMODE 64, .75); FREEMAIN
of part of an area; DCBE and exit lists; BSAM, VSAM and EXCP; separate load modules.

## Units, in order

1. **.11** SAVE, RETURN and YREGS macros.
2. **.12** GETMAIN, FREEMAIN, STORAGE: SVC 10 and 120, the allocation table, explicit
   alignment. TIME.
3. **.8** The object module and the binder (decisions 1 and 2): one region per module,
   module-qualified names, ENTRY export, per-assembly paths, multi-module images, the
   linking-branch dispatch entry, job-step trampolines and PARM, unresolved stubs,
   duplicate refusal.
4. **.13** Far branch and return (decision 3); CALL, LINK, LOAD, DELETE.
5. **.15** COBOL ↔ HLASM (decision 4): the mixed COBOL and HLASM image (its link and the
   order of the two start-ups), the argument element and USING signature.
6. **.14** DCB, DCBD, OPEN, CLOSE, GET, PUT, DD definitions. It can start any time after
   .12.
7. **.96** Q, J, CXD/DXD and complex-relocatable A-constants on the binder.

Every unit runs its programs through the VM and against z390 where z390 supports the
service; IBM's manuals win where they disagree.

## Bead updates

.11–.14 say "lowered to builtins": services are lowered in IR by SVC number, with
builtins only for provider calls and file declaration. .15 says an HLASM abend must be
visible to a COBOL caller as a COBOL abend is: an abend ends the run unit instead.
