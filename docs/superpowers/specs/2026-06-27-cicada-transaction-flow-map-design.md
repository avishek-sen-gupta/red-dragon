# Cicada Transaction Flow Map — Design Spec

**Date:** 2026-06-27  
**Status:** Approved

## Goal

Build a static-analysis feature for Cicada that extracts a transaction flow map from a CICS project: which programs are invoked at what points during conversational and pseudo-conversational flows, with connections to BMS screen elements and field-level input/output direction. Output is a list of JSON-serialisable objects, one per transaction.

## Approach

Observer hook in `CicsLoweringStrategy` (Approach B). The flow map falls out of lowering naturally — as each EXEC CICS verb is parsed and its operands resolved, a `CicsFlowObserver` is notified. A standalone builder function `extract_transaction_flow_map()` wires the observer into compilation and composes the output with CSD and BMS metadata.

**Invariant:** No changes to `compile_cics_program()`, `compile_cobol()`, the linker, the resolver, or any other compile pipeline internals. The only change to the compile pipeline is passing an `observer` argument into `CicsLoweringStrategy.__init__`. All existing call sites continue to use `NullCicsFlowObserver` by default.

## Scope

- Input: CSD source, parsed BMS mapsets, COBOL program sources (bytes)
- Output: JSON-serialisable list (NDJSON-friendly), one object per transaction
- Coverage: full CSD (all transactions)
- BMS detail level: map-level flow edges + field names with input/output direction
- Invocation: Python API only; CLI exposure deferred

## Data Model

`cicada/cics/flow_observer.py` (new file):

```python
@dataclass(frozen=True)
class CicsVerb:
    verb: str            # "SEND_MAP", "RECEIVE_MAP", "XCTL", "RETURN_TRANSID", "LINK"
    program: str         # PROGRAM-ID of the containing program
    map_name: str | None
    mapset_name: str | None
    xctl_target: str | None   # PROGRAM operand of XCTL or LINK
    transid: str | None       # TRANSID operand of RETURN

class CicsFlowObserver(Protocol):
    def on_verb(self, verb: CicsVerb) -> None: ...

class NullCicsFlowObserver:
    def on_verb(self, verb: CicsVerb) -> None: ...   # no-op
```

### Verb coverage

| EXEC CICS verb | `CicsVerb.verb` | Fields populated |
|---|---|---|
| `SEND MAP` | `"SEND_MAP"` | `map_name`, `mapset_name` |
| `RECEIVE MAP` | `"RECEIVE_MAP"` | `map_name`, `mapset_name` |
| `XCTL` | `"XCTL"` | `xctl_target` |
| `RETURN TRANSID` | `"RETURN_TRANSID"` | `transid` |
| `LINK` | `"LINK"` | `xctl_target` |

## Hook Site

`CicsLoweringStrategy.__init__` gains `observer: CicsFlowObserver = NullCicsFlowObserver()`. Inside `lower()`, after each EXEC CICS verb is parsed and operands extracted — before IR is emitted — `self._observer.on_verb(CicsVerb(...))` fires. Operands are fully resolved string literals or identifier names at this point; no additional resolution is needed.

## Flow Map Builder API

`cicada/cics/flow_map.py` (new file):

```python
def extract_transaction_flow_map(
    csd_source: str,
    bms_mapsets: dict[str, BmsMapSet],   # mapset_name → parsed model
    cobol_sources: dict[str, bytes],      # program_name → source bytes
    *,
    copybook_dirs: list[Path] = [],
    cics_text_parser: Any = None,
) -> list[dict]
```

Steps:
1. Parse CSD → `{transid: program_name}` using existing `cics_parser` logic.
2. For each transaction, compile its entry program via `compile_cics_program()` with a `CicsFlowObserver` injected into `CicsLoweringStrategy`. The observer accumulates `CicsVerb` events across the transitive call chain.
3. Enrich `SEND_MAP`/`RECEIVE_MAP` verbs with field metadata from `bms_mapsets`: for each map, add `fields: [{name, direction}]` where `direction` is `"input"` for unprotected fields, `"output"` for protected/display-only.
4. Return NDJSON-serialisable list — one object per transaction.

### Output shape

```json
{
  "transid": "VACV",
  "entry_program": "COACTVWC",
  "flow": [
    {
      "verb": "RECEIVE_MAP",
      "program": "COACTVWC",
      "map": "CACTVWA",
      "mapset": "COACTVW",
      "fields": [{"name": "ACCTSIDI", "direction": "input"}]
    },
    {
      "verb": "SEND_MAP",
      "program": "COACTVWC",
      "map": "CACTVWA",
      "mapset": "COACTVW",
      "fields": [{"name": "ACCTNAMEO", "direction": "output"}]
    },
    {
      "verb": "XCTL",
      "program": "COACTVWC",
      "xctl_target": "COSGN00C",
      "map": null,
      "mapset": null,
      "fields": []
    }
  ]
}
```

## Files

| File | Change |
|------|--------|
| `cicada/cics/flow_observer.py` | **New** — `CicsVerb`, `CicsFlowObserver`, `NullCicsFlowObserver` |
| `cicada/cics/flow_map.py` | **New** — `extract_transaction_flow_map()` |
| `cicada/cics/strategy.py` | **Modify** — add `observer` param to `CicsLoweringStrategy.__init__`; fire `on_verb()` after each EXEC CICS parse |
| `tests/unit/cicada/test_flow_observer.py` | **New** — unit tests for data model and null observer |
| `tests/integration/cicada/test_flow_map.py` | **New** — integration tests with synthetic fixtures |

No other files are modified.

## Testing

**Unit** (`tests/unit/cicada/test_flow_observer.py`):
- `CicsVerb` is a frozen dataclass (immutable)
- `NullCicsFlowObserver.on_verb()` is a no-op (does not raise)
- Field direction classification: unprotected field → `"input"`, display-only → `"output"`

**Integration** (`tests/integration/cicada/test_flow_map.py`):
- Synthetic COBOL + synthetic BMS mapset → expected verb sequence and field metadata in output
- `XCTL` edge: `xctl_target` populated even when target program is not compiled (literal operand only)
- `RETURN TRANSID` edge: `transid` propagated to flow entry
- Multi-program chain: XCTL A→B, B does SEND MAP → verbs from both programs in one transaction's flow

No CardDemo dependency — synthetic fixtures only.

## Out of Scope

- Computed XCTL targets (data-name operands): `xctl_target` will be the identifier name, not a resolved value
- CLI exposure (deferred until feature matures)
- Runtime/dynamic flow tracing
- Connection types beyond the five listed EXEC CICS verbs
