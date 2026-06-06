# CICS Emulation Layer — Master Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each sub-project plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emulate the online transactional tier of `aws-mainframe-carddemo` end-to-end via red-dragon's VM.

**Architecture:** Five sub-projects with an explicit dependency chain. Each sub-project produces independently testable software. A text pre-pass prepares COBOL source for ProLeap; an injectable strategy routes EXEC CICS verbs to typed builtins; a dispatcher loop drives pseudo-conversational execution.

**Tech Stack:** Python 3.12, ProLeap (Java bridge), sortedcontainers, PyYAML, bms-tools (git submodule), poetry, pytest, black

---

## Dependency Graph

```
A (Parse Strategy)
    └── B (CICS Runtime / EIB + System Builtins)
            ├── C (Transaction Dispatcher)
            ├── D (VSAM File Engine)
            └── E (BMS Screen Engine)
                     └── (integration: sign-on flow milestone)
```

Sub-projects C, D, E are independent of each other and can be worked in parallel once B is done.

---

## Beads Story Mapping

| Sub-project | Beads Story | Description |
|---|---|---|
| A | `red-dragon-pz9g.3` | CICS command translator + service builtins |
| B | `red-dragon-pz9g.1` | EIB fields + system copybooks |
| C | `red-dragon-pz9g.2` | Pseudo-conversational dispatch driver |
| D | `red-dragon-pz9g.4` | VSAM/KSDS file model |
| E | `red-dragon-pz9g.5` | BMS map runtime model |
| Integration | `red-dragon-pz9g.6` | Sign-on → menu flow end-to-end |

Epic: `red-dragon-pz9g` — Run CardDemo online tier

### Implementation Order (authoritative)

The plan text below is the authoritative ordering. Implement sub-projects strictly A → B → (C, D, E in any order) → integration milestone (pz9g.6).

---

## Sub-Project Plans

Implement in this order (each plan is self-contained):

1. **[Sub-project A — Parse Strategy](2026-06-06-cics-A-parse-strategy.md)**
   - Bridge serialization of ExecCicsStatement
   - Pre-pass text transformer (DFHEIBLK injection, DFHRESP substitution)
   - IBM copybooks (DFHEIBLK.cpy, DFHAID.cpy, DFHBMSCA.cpy)
   - ExecCicsStatement Python type + CICS verb parser
   - ExecCicsStrategy protocol + CobolFrontend injection

2. **[Sub-project B — CICS Runtime / EIB](2026-06-06-cics-B-runtime-eib.md)** *(depends on A)*
   - CicsContext, DispatchResult, DispatchKind types
   - EIB procedure-entry initialization hook
   - System service builtins (ASSIGN, ASKTIME, FORMATTIME, INQUIRE, WRITEQ TD, HANDLE ABEND, ABEND)

3. **[Sub-project C — Transaction Dispatcher](2026-06-06-cics-C-dispatcher.md)** *(depends on B)*
   - Flow control lowering (RETURN, RETURN TRANSID, XCTL, ABEND)
   - run_cics() + COMMAREA injection
   - CSD parsing + eager compilation + dispatcher loop

4. **[Sub-project D — VSAM File Engine](2026-06-06-cics-D-vsam.md)** *(depends on B)*
   - FCT YAML config
   - SortedDict-backed engine (point + browse operations)
   - VSAM builtins + lowering

5. **[Sub-project E — BMS Screen Engine](2026-06-06-cics-E-bms.md)** *(depends on B)*
   - bms-tools submodule + BMS map loader
   - SEND MAP / RECEIVE MAP / SEND TEXT builtins + lowering
   - Integration test: sign-on → main menu flow

---

## Full Codebase Layout (target)

```
interpreter/cics/
    __init__.py
    preprocessor.py            # text pre-pass
    cics_parser.py             # parse exec_cics_text → (verb, options)
    strategy.py                # ExecCicsStrategy protocol, CatchAll, CicsLowering skeleton
    dispatcher.py              # run_cics(), dispatcher loop, CicsContext, DispatchResult
    types.py                   # CicsContext, DispatchKind, DispatchResult
    copybooks/
        DFHEIBLK.cpy
        DFHAID.cpy
        DFHBMSCA.cpy
    builtins/
        __init__.py
        flow.py                # __cics_set_return_context, __cics_set_xctl_context, __cics_abend
        system.py              # assign, asktime, formattime, inquire, writeq_td, handle_abend
        vsam.py                # all VSAM builtins
        screen.py              # send_map, receive_map, send_text
    vsam/
        __init__.py
        engine.py              # SortedDict VSAM engine
        fct.py                 # FCT config dataclass + YAML loading
    bms/
        __init__.py
        loader.py              # load .bms files via bms-tools
vendor/bms-tools/              # git submodule

tests/unit/cics/
    __init__.py
    test_preprocessor.py
    test_cics_parser.py
    test_system_builtins.py
    test_vsam_engine.py
    test_bms_loader.py
tests/integration/cics/
    __init__.py
    test_sign_on_flow.py
```

---

## Test Commands

```bash
# Run all CICS tests
poetry run python -m pytest tests/unit/cics/ tests/integration/cics/ -v

# Format before committing
poetry run python -m black .

# Full suite (must stay green)
poetry run python -m pytest
```
