# IR Lowering Gaps

Known gaps in tree-sitter frontend IR lowering, discovered via cross-language type inference integration tests (2026-03-06). Each gap has a corresponding `xfail` marker in `tests/integration/test_type_inference.py`.

---

## GAP-001: Scala — `this.field` in getter lowered as `LOAD_VAR` instead of `LOAD_FIELD`

**Affected frontend:** `interpreter/frontends/scala.py`

**Symptom:** In a Scala class method, `this.age` access produces `load_var age` rather than `load_field %reg age`. The setter path (`this.age = 5`) correctly produces `STORE_FIELD`.

**Example source:**
```scala
class Dog {
    var age: Int = 0
    def setAge(): Unit = { this.age = 5 }   // STORE_FIELD ✓
    def getAge(): Int = this.age             // LOAD_VAR ✗ (should be LOAD_FIELD)
}
```

**Impact:** Field type tracking cannot propagate store-to-load through `this` in Scala getters. Type inference for `LOAD_FIELD` results is blocked.

**Test marker:** `TestFieldTypeTrackingOOP` — `xfail` for `scala`

---

## GAP-002: Ruby — implicit return does not wire expression value to `RETURN`

**Affected frontend:** `interpreter/frontends/ruby.py`

**Symptom:** Ruby methods use implicit return (last expression is the return value). The frontend generates `LOAD_FIELD` for `@age` but the `RETURN` instruction uses `const None` instead of the loaded register.

**Example source:**
```ruby
class Dog
    def initialize
        @age = 5
    end
    def get_age
        @age       # LOAD_FIELD %7 age — correct
    end            # RETURN %8 (const None) — should be RETURN %7
end
```

**IR produced:**
```
func_get_age_4:
  %5 = symbolic param:self
  store_var self %5
  %6 = load_var self
  %7 = load_field %6 age     # value loaded correctly
  %8 = const None             # but None returned instead
  return %8
```

**Impact:** Return backfill cannot infer return type from implicit returns. CALL_METHOD result typing is blocked for Ruby methods that rely on implicit return (which is idiomatic Ruby).

**Workaround:** Use explicit `return @age` in Ruby methods for type inference to work.

**Test marker:** `TestCallMethodReturnTypesOOP` — `xfail` for `ruby`

---

## GAP-003: Kotlin/Scala — expression-bodied functions do not wire return value

**Affected frontends:** `interpreter/frontends/kotlin.py`, `interpreter/frontends/scala.py`

**Symptom:** Expression-bodied functions (`fun f() = 42` in Kotlin, `def f() = 42` in Scala) compute the expression but do not wire it to the RETURN instruction.

**Kotlin `fun f() = 42`:**
```
func_f_0:
  %0 = const 42    # value computed
  %1 = const None   # but None returned
  return %1
```

**Scala `def f() = 42`:**
```
func_f_0:
  %0 = const ()     # literal not even captured
  return %0
```

**Impact:** Return backfill cannot infer return type for expression-bodied functions. Block-body functions with explicit `return` work correctly.

**Workaround:** Kotlin backfill tests use block body (`fun f() { return 42 }`). Scala excluded from return backfill tests entirely.

**Test coverage:** `TestReturnBackfillAllLanguages` — Kotlin uses block body workaround; Scala excluded.
