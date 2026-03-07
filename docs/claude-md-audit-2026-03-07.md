# CLAUDE.md Compliance Audit — 2026-03-07

## HIGH Severity

### 1. Relative imports (`from .`) — 107 instances
All in `interpreter/` directory. Should use fully qualified `from interpreter.` imports.

Key files:
- `interpreter/run.py` (18 relative imports)
- `interpreter/api.py` (14)
- `interpreter/executor.py` (8)
- `interpreter/frontends/_base.py` (6)
- `interpreter/vm.py` (5)
- `interpreter/cfg.py` (3)
- `interpreter/backend.py` (3)
- `interpreter/registry.py` (3)
- `interpreter/llm_frontend.py` (3)
- `interpreter/chunked_llm_frontend.py` (3)
- `interpreter/frontend.py` (3)
- `interpreter/dataflow.py` (3)
- `interpreter/frontends/__init__.py` (4)
- All frontend implementations in `interpreter/frontends/*/`

### 2. `print()` in production code — 23 instances
All in `interpreter/run.py`. Logger already imported but unused for these calls.

- Line 103: `print(f"  [{tag}] {update.reasoning}")` (in `_log_update`)
- Line 105: `print(f"    {reg} = {_format_val(val)}")`
- Line 107: `print(f"    ${var} = {_format_val(val)}")`
- Line 109: `print(f"    heap[{hw.obj_addr}].{hw.field} = {_format_val(hw.value)}")`
- Line 111: `print(f"    new {obj.type_hint} @ {obj.addr}")`
- Line 113: `print(f"    → {update.next_label}")`
- Line 115: `print(f"    path: {update.path_condition}")`
- Line 116: `print()`
- Line 159: `print(f"[step {step}] Top-level return/throw. Stopping.")`
- Line 164: `print(f"[step {step}] Top-level return/throw. Stopping.")`
- Line 179: `print(f"[step {step}] No return label. Stopping.")`
- Line 229: `print(...)` (multiline)
- Line 238: `print(f"[step {step}] {current_label}:{ip}  {instruction}")`
- Line 316: `print(f"\n({stats.steps} steps, {stats.llm_calls} LLM calls)")`
- Line 367: `print(...)` (multiline)
- Line 376: `print(f"[step {step}] {current_label}:{ip}  {instruction}")`
- Line 462: `print(f"\n({stats.steps} steps, {stats.llm_calls} LLM calls)")`
- Line 541: `print("═══ IR ═══")`
- Line 543: `print(f"  {inst}")`
- Line 544: `print()`
- Line 553: `print("═══ CFG ═══")`
- Line 554: `print(cfg)`
- Line 601: `print()`
- Line 602: `print(stats.report())`

### 3. Broad `except Exception:` — 4 instances
- `interpreter/vm.py:289` — in `eval_binop()`
- `interpreter/vm.py:309` — in `eval_unop()`
- `interpreter/unresolved_call.py:216` — in `resolve_call()`
- `interpreter/unresolved_call.py:243` — in `resolve_method()`

### 4. Functions >50 lines — 18+ functions
- `interpreter/run.py`: `execute_cfg` (136L), `execute_cfg_traced` (150L), `run` (132L)
- `interpreter/executor.py`: `_handle_call_function` (85L)
- `interpreter/cobol/ir_encoders.py`: 7 functions (84–152L each)
- `interpreter/frontends/kotlin/expressions.py`: `lower_kotlin_store_target` (110L)
- `interpreter/frontends/python/expressions.py`: `_lower_comprehension_loop` (90L)
- `interpreter/frontend.py`: `get_frontend` (88L)
- `interpreter/chunked_llm_frontend.py`: `lower` (83L)
- `interpreter/frontends/pascal/control_flow.py`: `lower_pascal_for` (84L)
- `interpreter/cobol/data_layout.py`: `_flatten_field` (85L)

## MEDIUM Severity

### 5. Parameter `= None` defaults — 4 instances
- `interpreter/backend.py:151` — `client: Any = None`
- `interpreter/frontend.py:55` — `llm_client: Any = None`
- `interpreter/run.py:481` — `llm_client: Any = None`
- `interpreter/cobol/emit_context.py:53` — `observer: Any = None`

### 6. Defensive `if x is None` guards — 4 instances
- `interpreter/run.py:257` — lazy LLM init
- `interpreter/run.py:395` — lazy LLM init (duplicate)
- `interpreter/vm.py:285` — binop table lookup
- `interpreter/run.py:175` — return_ip ternary

### 7. Multiple classes per file — ~8 files
- `interpreter/unresolved_call.py` (3 classes)
- `interpreter/backend.py` (2 classes)
- `interpreter/chunked_llm_frontend.py` (4 classes)
- `interpreter/llm_client.py` (3 classes)
- `interpreter/parser.py` (3 classes)
- `interpreter/llm_frontend.py` (3 classes)
- `interpreter/registry.py` (3 classes)
- `interpreter/cobol/pic_parser.py` (2 classes)

### 8. Post-construction mutation — 5+ locations
- `interpreter/cobol/pic_parser.py` — visitor fields mutated in visit methods
- `interpreter/executor.py:85-88` — closure env fields set after creation
- `interpreter/executor.py` (multiple) — `sym.constraints` set after creation
- `interpreter/unresolved_call.py:72,92` — `sym.constraints` set after creation

### 9. For loops with `.pop(0)` — 4 instances
- `interpreter/cfg.py:191` — BFS queue (should use `deque`)
- `interpreter/cobol/io_provider.py:171,194,222` — stub I/O queues

## LOW Severity

### 10. Magic strings — many instances
Tree-sitter field names repeated heavily in frontend code:
- `"body"` (161x), `"identifier"` (92x), `"type"` (87x), `"condition"` (49x), `"parameters"` (40x)
- Could be extracted to a `TreeSitterFields` constants class

## Clean Areas
- No `@staticmethod` decorators
- No deeply nested if/else (3+ levels)
- No `return None` with non-None return type annotations
