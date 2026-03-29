---
name: migration-planner
description: Injects domain-type migration strategies during brainstorming and planning phases. Auto-triggers when the task involves replacing primitives (str, int) with domain types across a codebase, propagating wrapper types through dict keys and function signatures, or any large-scale type migration. Use this whenever you see keywords like "migrate", "domain type", "replace str with", "wrapper type", "propagate type", "rename across codebase", or when a brainstorming/planning session involves changing a field type on a widely-used class. Even if the user doesn't mention "migration" explicitly, trigger if the task is structurally a type propagation (e.g., "make field names typed", "add a CodeLabel wrapper").
---

# Domain Type Migration Planner

You are planning a migration that replaces a primitive type (usually `str`) with a domain type across a codebase. This skill provides a decision framework during brainstorming and a plan structure during implementation planning. The patterns here come from hard-won experience across multiple successful migrations.

## When This Skill Activates

This skill provides guidance at two points:
1. **During brainstorming** — surfaces the right questions, trade-offs, and strategy options
2. **During plan writing** — provides the commit structure and checklist for the chosen strategy

## Phase 1: Scope Discovery (Before Choosing a Strategy)

Before recommending a strategy, the agent MUST quantify the migration scope. Do not estimate — count.

### Discovery Checklist

Run these searches and report the counts:

1. **Construction sites** — How many places create the target instruction/class with the primitive field?
   - Count per directory (frontends, handlers, VM, tests)
   - Note multi-line constructors that single-line grep misses (use ast-grep if available)

2. **Consumption dicts** — How many `dict[str, ...]` use the primitive as a key where the domain type should be used?
   - List each dict by name, file, and line number
   - Note the dict's purpose (lookup table, registry, cache)

3. **Pydantic/validated boundaries** — Are any of these dicts inside Pydantic BaseModel classes?
   - Pydantic validates key types strictly — a non-str-subclass domain type will be rejected
   - This is the #1 source of unexpected failures in migrations

4. **Test assertions** — How many test files access these dicts with string keys?
   - Count `.field["X"]` and `.get("X")` patterns in tests
   - Note test helper functions (conftest, utility functions) that abstract dict access — fixing one helper can fix hundreds of tests

5. **String operations on the field** — Does any code do `.split()`, `.startswith()`, `.replace()`, regex, or other string operations on the value?
   - Each operation needs a domain method or an explicit `str()` unwrap at that boundary

6. **Cross-domain boundaries** — Does the primitive value flow into other domain types?
   - e.g., a function name used as a variable name for scope lookup (FuncName → VarName)
   - e.g., a variable name used as a field name for implicit-this resolution (VarName → FieldName)
   - Each crossing is an explicit `str()` unwrap + re-wrap

7. **Serialization boundaries** — Where does the value get serialized to JSON, displayed in logs, or passed to external systems?
   - Each is a `str()` unwrap point

Report these counts before proceeding. The totals drive the strategy choice.

## Phase 2: Strategy Selection

### Size Classification

| Size | Construction Sites | Consumption Dicts | Recommended Strategy |
|------|-------------------|-------------------|---------------------|
| **Small** | < 30 | 0-1 | Direct (no bridge) |
| **Medium** | 30-200 | 1-3 | No bridge, split commits |
| **Large** | 200+ | 4+ | Accessor pattern |

### Strategy A: Direct (Small migrations)

Change the type, fix everything in 1-2 commits. Appropriate when:
- Few construction sites
- At most one dict to migrate
- Blast radius is containable in a single review

**Commit sequence:**
1. Define type + tests
2. Change field types + fix all sites + fix tests

### Strategy B: No Bridge, Split Commits (Medium migrations)

No `__eq__(str)` bridge on the domain type. Fix all construction AND consumption sites in one pass, but split into logical commits.

**Commit sequence:**
1. Define type + tests
2. Change field types + wrap construction sites
3. Fix handler/VM consumption sites + Pydantic boundaries
4. Fix test assertions
5. Verify clean

**When to choose this:** The domain type touches 1-3 dicts. The blast radius is large but the consumption surface is bounded. Every commit may not be independently green — commits 2-4 are logically one unit.

**Key risk:** With no bridge, changing the field type immediately breaks all consumption sites. If the blast radius is underestimated, you end up chasing failures across many files. Mitigate by doing thorough scope discovery first.

### Strategy C: Accessor Pattern (Large migrations)

Add accessor methods to each dict owner. Callers migrate to accessors. Then change dict keys one at a time. Every commit is independently green.

**Commit sequence:**
1. Define type + tests
2. Add accessor methods to all dict owners (unwrap with `str()` internally)
3. Migrate all callers from direct dict access to accessors
4. Wrap construction sites + change instruction/class field types
5. Per dict: change key type to domain type + remove `str()` from accessor
6. Fix test assertions
7. Verify clean — no direct dict access bypassing accessors

**When to choose this:** The domain type is used as a key in 4+ dicts across different modules. Direct migration would require fixing everything simultaneously. The accessor pattern decouples the migration.

**Key advantage:** Every commit is independently green. You can stop after any commit and the codebase works. The accessors become the permanent API — callers never access the underlying dicts directly.

**Key design principle:** The accessor is not temporary scaffolding — it's the final architecture. After migration, the dict is private, the accessor is the only way in. This is better encapsulation regardless of the migration.

## Phase 3: Domain Type Design Patterns

### Type Definition Checklist

Every domain type should have:

- `__post_init__` — reject double-wrapping: `DomainType(DomainType("x"))` should raise `TypeError`
- `__str__` — return the wrapped value for display/serialization
- `__hash__` and `__eq__` — identity semantics (no str bridge unless explicitly chosen)
- `__lt__` — for sorting
- `is_present()` → `True`
- Null object (`NoXxx` subclass) with `is_present()` → `False` and `eq=False` on the dataclass
- Domain methods for any string operations callers need (`.startswith()`, `.__contains__()`)

### Bridge Decision

| Approach | When to Use | Trade-off |
|----------|------------|-----------|
| **No bridge** (recommended) | Accessor pattern, or small/medium scope | Forces all consumption sites to be fixed upfront. Harder initially, less total work. |
| **str subclass** (e.g., `str, Enum`) | The domain type IS a string variant (like operator enums) | Free compatibility, but no type separation — can't prevent interchange |
| **`__eq__(str)` bridge** | Only if you need incremental green commits WITHOUT the accessor pattern | Makes str-keyed dict lookups work during migration. But bugs hide behind the bridge and surface only at removal — removal is the hardest part |

The bridge-then-remove approach costs more total work than going strict from day one. The accessor pattern achieves incremental green commits without a bridge.

### Boundary Analysis

Enumerate every point where the domain type enters or exits the typed domain:

| Direction | Pattern | Action |
|-----------|---------|--------|
| **Wrap (origin)** | AST node text, constant, parsed value | `DomainType(str_value)` — wrap as early as possible |
| **Unwrap (serialization)** | JSON output, log messages, display | `str(domain_value)` — unwrap as late as possible |
| **Unwrap (foreign dict)** | Symbol table, external API, unmigrated registry | `str(domain_value)` — explicit boundary crossing |
| **Cross-domain** | FuncName → VarName, VarName → FieldName | `OtherType(str(this_value))` — unwrap + re-wrap |
| **Temporary tech debt** | Hacks that will be removed by a follow-up issue | Mark explicitly in spec and plan |

**Principle:** The domain type stays as the domain type through the entire pipeline. Wrap at origin, unwrap at boundary, never in between.

## Phase 4: Estimation and Risk

### Blast Radius Multiplier

The actual number of changes is always larger than the construction site count. Use these multipliers:

| Component | Multiplier | Why |
|-----------|-----------|-----|
| Construction sites | 1x | Direct count |
| Handler/VM consumption | 0.3x-0.5x of construction sites | Each dict lookup, membership check, iteration |
| Test assertions | 0.5x-1.5x of construction sites | Tests access the same dicts, often through aliases |
| Pydantic boundaries | High impact, low count | Each Pydantic model field change can cascade |
| Conftest/helper fixes | Low count, high leverage | One fix can resolve hundreds of test failures |

### Common Traps

1. **Python 3.11+ `str(SomeEnum.X)` returns `"SomeEnum.X"` not the value.** Use `.value` or `getattr(x, "value", x)` when you need the underlying string from a `str, Enum`.

2. **Pydantic BaseModel fields validate key types strictly.** A `dict[str, Any]` field rejects non-str keys. You must change the field type annotation to accept the domain type.

3. **Test files use many aliases for the same dict.** `local_vars`, `locals_`, `vars_`, `lv`, `result` may all refer to the same VarName-keyed dict. A regex fix script that only handles `local_vars["X"]` misses the aliases.

4. **Multi-line constructor calls are missed by single-line grep.** Use ast-grep for structural patterns, or write a multi-line-aware scanner.

5. **Conftest helpers affect thousands of tests.** Fix these first — one fix in `extract_answer()` can resolve 200+ test failures.

6. **Domain types that are NOT str subclasses break `in` checks and dict lookups against str-keyed dicts.** Every `"x" in some_dict` and `some_dict["x"]` fails if the dict keys are now DomainType objects.

7. **Follow-up issues are cheap to file and expensive to forget.** After propagating the type into the immediate adjacents, file issues for the next ring. Include file paths, line numbers, and constraints.

## Phase 5: Plan Template

When writing the implementation plan, use this structure:

```markdown
## Task 1: Define [TypeName] type + tests
- Create type file with full checklist (post_init, eq, hash, lt, null object)
- Create unit tests

## Task 2: [If accessor pattern] Add accessor methods
- Add accessors to each dict owner (unwrap with str() internally)
- Write accessor tests

## Task 3: [If accessor pattern] Migrate callers to accessors
- Replace all direct dict[key] access with accessor calls
- Callers wrap str values with DomainType() when calling accessors

## Task 4: Wrap construction sites + change field types
- Change class field types
- Wrap all construction sites (parallel subagents by module group)
- Update _to_typed converters
- Update test constructions

## Task 5+: Per-dict key migration [if accessor pattern]
- Change dict key type
- Remove str() from accessor
- One commit per dict

## Final Task: Verify + close
- Grep for remaining direct dict access
- Grep for remaining str() unwraps that should have been removed
- Run full test suite
- File follow-up issues for next ring
```

Each task should specify: files to modify (with line numbers), exact changes, expected test count, and commit message.
