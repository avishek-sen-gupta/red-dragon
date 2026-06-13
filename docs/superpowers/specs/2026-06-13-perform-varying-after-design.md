# PERFORM VARYING AFTER — Design Spec

**Issue:** red-dragon-e93j
**Date:** 2026-06-13

## Problem

COBOL's multi-index PERFORM VARYING form uses AFTER subclauses to nest loop variables:

```cobol
PERFORM VARYING I FROM 1 BY 1 UNTIL I > 3
    AFTER J FROM 1 BY 1 UNTIL J > 3
        MOVE ZERO TO TABLE(I, J)
END-PERFORM
```

The ProLeap ASG models AFTER clauses via `VaryingClause.getAfters()`, but the bridge serializer ignores them. The Python dataclass has no field for them. The lowering emits no nested loops.

## Scope

Both TEST BEFORE (default) and TEST AFTER. All three fix layers: bridge serializer, Python dataclass, IR lowering.

---

## Semantics Reference

### TEST BEFORE (default) — VARYING I AFTER J AFTER K

```
I = FROM_I
outer_top:  if UNTIL_I → exit
            J = FROM_J
mid_top:      if UNTIL_J → incr_I
              K = FROM_K
inner_top:      if UNTIL_K → incr_J
                [body]
                K += BY_K  → inner_top
incr_J:       J += BY_J  → mid_top
incr_I:     I += BY_I  → outer_top
exit:
```

Key invariant: when an inner UNTIL fires, control jumps to the **parent's increment section** (not the whole-loop exit). The inner variable is re-initialized on every outer iteration because the init code is emitted inline between the parent's UNTIL check and the inner loop label.

### TEST AFTER — VARYING I AFTER J AFTER K

```
I = FROM_I;  J = FROM_J;  K = FROM_K
body:
  [body]
  K += BY_K;  if UNTIL_K → incr_J;  else → body
incr_J:
  J += BY_J;  if UNTIL_J → incr_I;  else → K=FROM_K → body
incr_I:
  I += BY_I;  if UNTIL_I → exit;    else → J=FROM_J; K=FROM_K → body
exit:
```

Key invariant: when an outer UNTIL does NOT fire (loop continues), all exhausted inner variables are reset to their FROM values.

---

## Layer 1 — Bridge (`StatementSerializer.java`)

After serializing the primary `VaryingPhrase` (~line 648), iterate `vc.getAfters()` and append:

```java
List<After> afters = vc.getAfters();
if (afters != null && !afters.isEmpty()) {
    JsonArray afterArr = new JsonArray();
    for (After after : afters) {
        VaryingPhrase ap = after.getVaryingPhrase();
        if (ap == null) continue;
        JsonObject aObj = new JsonObject();
        if (ap.getVaryingValueStmt() != null)
            aObj.addProperty("varying_var", extractValueStmtText(ap.getVaryingValueStmt()));
        if (ap.getFrom() != null && ap.getFrom().getFromValueStmt() != null)
            aObj.add("varying_from", serializeFromValue(ap.getFrom().getFromValueStmt()));
        if (ap.getBy() != null && ap.getBy().getByValueStmt() != null)
            aObj.addProperty("varying_by", extractValueStmtText(ap.getBy().getByValueStmt()));
        if (ap.getUntil() != null)
            serializeUntilFields(ap.getUntil(), aObj);
        afterArr.add(aObj);
    }
    obj.add("after_specs", afterArr);
}
```

No `test_before` in after-spec objects — it applies only at the statement level.

---

## Layer 2 — Dataclass (`cobol_statements.py`)

### `PerformVaryingSpec`

Add `after_specs` as the last field with an empty-tuple default so all existing construction sites remain valid:

```python
@dataclass(frozen=True)
class PerformVaryingSpec:
    varying_var: str
    varying_from: str | dict
    varying_by: str
    condition: dict
    test_before: bool = True
    after_specs: tuple[PerformVaryingSpec, ...] = field(default_factory=tuple)
```

`test_before` on inner specs (inside `after_specs`) is ignored by the lowering; it carries no semantic meaning there.

### `_parse_perform_spec`

```python
if perform_type == "VARYING":
    raw_afters = data.get("after_specs", [])
    after_specs = tuple(
        PerformVaryingSpec(
            varying_var=a.get("varying_var", ""),
            varying_from=a.get("varying_from", ""),
            varying_by=a.get("varying_by", ""),
            condition=a.get("until", {}),
        )
        for a in raw_afters
    )
    return PerformVaryingSpec(
        varying_var=data.get("varying_var", ""),
        varying_from=data.get("varying_from", ""),
        varying_by=data.get("varying_by", ""),
        condition=data.get("until", {}),
        test_before=data.get("test_before", True),
        after_specs=after_specs,
    )
```

### `_spec_to_dict`

```python
if isinstance(spec, PerformVaryingSpec):
    d = {
        "perform_type": "VARYING",
        "varying_var": spec.varying_var,
        "varying_from": spec.varying_from,
        "varying_by": spec.varying_by,
        "until": spec.condition,
        "test_before": spec.test_before,
    }
    if spec.after_specs:
        d["after_specs"] = [
            {
                "varying_var": a.varying_var,
                "varying_from": a.varying_from,
                "varying_by": a.varying_by,
                "until": a.condition,
            }
            for a in spec.after_specs
        ]
    return d
```

---

## Layer 3 — Lowering (`lower_perform.py`)

`lower_perform_varying` dispatches:

```python
def lower_perform_varying(ctx, stmt, materialised):
    spec = stmt.spec
    assert isinstance(spec, PerformVaryingSpec)
    all_specs = (spec,) + spec.after_specs  # outermost first

    if len(all_specs) == 1:
        # Existing single-variable path: keep the current body of lower_perform_varying
        # unchanged (guarded by this branch). No extraction needed.
        _lower_perform_varying_single(ctx, stmt, materialised)
    elif spec.test_before:
        exit_label = ctx.fresh_label("pv_exit")
        _init_varying_var(ctx, spec, materialised)
        _emit_test_before_level(ctx, all_specs, lambda: lower_perform_body(ctx, stmt, materialised), exit_label, materialised)
        ctx.emit_inst(Label_(exit_label))
    else:
        _emit_test_after_varying(ctx, all_specs, lambda: lower_perform_body(ctx, stmt, materialised), materialised)
```

### TEST BEFORE — recursive helper

```python
def _emit_test_before_level(ctx, specs, body_fn, when_done_label, materialised):
    spec = specs[0]
    loop_label = ctx.fresh_label("pv_loop")
    body_label = ctx.fresh_label("pv_body")
    incr_label = ctx.fresh_label("pv_incr")

    _init_varying_var(ctx, spec, materialised)
    ctx.emit_inst(Label_(loop_label))
    cond_reg = ctx.lower_condition(spec.condition, materialised)
    ctx.emit_inst(BranchIf(cond_reg=Register(str(cond_reg)),
                           branch_targets=(when_done_label, body_label)))
    ctx.emit_inst(Label_(body_label))

    if specs[1:]:
        _emit_test_before_level(ctx, specs[1:], body_fn, incr_label, materialised)
    else:
        body_fn()

    ctx.emit_inst(Label_(incr_label))
    emit_varying_increment(ctx, spec, materialised)
    ctx.emit_inst(Branch(label=loop_label))
```

The `when_done_label` for the outermost call is the loop's exit label. For each inner call it is the parent's `incr_label`, so a fired inner UNTIL cascades to the parent's increment — not to the exit.

### TEST AFTER — iterative

```python
def _emit_test_after_varying(ctx, specs, body_fn, materialised):
    n = len(specs)
    body_label = ctx.fresh_label("pv_body")
    exit_label = ctx.fresh_label("pv_exit")
    incr_labels = [ctx.fresh_label("pv_incr") for _ in range(n)]
    # continue_labels[i]: reset specs[i+1..n-1] to FROM, then jump to body
    # Only needed for levels 0..n-2 (outermost has all inners; innermost has none → use body_label)
    continue_labels = [ctx.fresh_label("pv_continue") for _ in range(n - 1)]

    # Initialize all vars
    for spec in specs:
        _init_varying_var(ctx, spec, materialised)

    # Body
    ctx.emit_inst(Label_(body_label))
    body_fn()
    # Falls through to innermost incr

    # Increment cascade: innermost (n-1) to outermost (0)
    for i in range(n - 1, -1, -1):
        spec = specs[i]
        ctx.emit_inst(Label_(incr_labels[i]))
        emit_varying_increment(ctx, spec, materialised)
        cond_reg = ctx.lower_condition(spec.condition, materialised)
        true_target = exit_label if i == 0 else incr_labels[i - 1]
        false_target = body_label if i == n - 1 else continue_labels[i]
        ctx.emit_inst(BranchIf(cond_reg=Register(str(cond_reg)),
                               branch_targets=(true_target, false_target)))

    # Continue blocks: reset exhausted inner vars and re-enter body
    for i in range(n - 2, -1, -1):
        ctx.emit_inst(Label_(continue_labels[i]))
        for j in range(i + 1, n):
            _init_varying_var(ctx, specs[j], materialised)
        ctx.emit_inst(Branch(label=body_label))

    ctx.emit_inst(Label_(exit_label))
```

### Shared helper

```python
def _init_varying_var(ctx, spec, materialised):
    """Write spec.varying_from into spec.varying_var in the heap."""
    if not ctx.has_field(spec.varying_var, materialised):
        return
    ref, rr = ctx.resolve_field_ref(spec.varying_var, materialised)
    from_reg = _eval_varying_from(ctx, spec.varying_from, materialised)
    str_reg = ctx.emit_to_string(from_reg)
    ctx.emit_encode_and_write(rr, ref.fl, str_reg, ref.offset_reg)
```

(The init logic already exists inline in `lower_perform_varying` — extract it into this helper and replace the existing callsite.)

---

## Testing

### Unit tests (`test_cobol_frontend.py`)

- `test_perform_varying_after_test_before_emits_nested_loops`: 2-level AFTER with TEST BEFORE; assert IR contains two nested loop/body/incr label clusters, and the inner BranchIf true-target is the outer's incr label (not exit).
- `test_perform_varying_after_test_after_emits_cascade`: 2-level AFTER with TEST AFTER; assert IR contains a body label, two incr labels (innermost first), and a continue block that resets the inner variable.

### Integration tests (`test_cobol_programs.py`)

**TEST BEFORE — 2×3 cell count:**
```cobol
01 WS-CNT PIC 9(4) VALUE 0.
01 WS-I   PIC 9(4).
01 WS-J   PIC 9(4).
PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 2
    AFTER WS-J FROM 1 BY 1 UNTIL WS-J > 3
        ADD 1 TO WS-CNT
END-PERFORM.
```
Assert `WS-CNT == 6`.

**TEST AFTER — same count, body-first ordering:**

Same loop with `TEST AFTER`. Assert `WS-CNT == 6`. Optionally use a sentinel field written on first body entry to confirm body runs before any UNTIL check.

**3-level smoke test (TEST BEFORE):**

VARYING I AFTER J AFTER K, all 1 BY 1 UNTIL > 2. Assert `WS-CNT == 8`.

### Feature enum

Add `PERFORM_VARYING_AFTER` to `CobolFeature` and attach it to the new integration tests.

---

## What does NOT change

- Single-variable `PERFORM VARYING` (no AFTER): existing code path untouched.
- `PERFORM UNTIL`, `PERFORM TIMES`: no changes.
- Out-of-line PERFORM (procedure-name variant): after_specs applies equally; `lower_perform_body` is already agnostic to inline vs. out-of-line.
