# C Ternary Operator Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add unit and integration test coverage for the existing C frontend ternary operator (`lower_ternary`) to close the `TERNARY_OPERATOR` feature gap.

**Architecture:** No production code changes are needed. The work consists entirely of writing test fixtures (`@covers(CFeature.TERNARY_OPERATOR)`) in `tests/unit/test_c_frontend.py` that parse simple C snippets and assert the generated CFG and VM execution behavior.

**Tech Stack:** pytest, Python, RedDragon VM

---

### Task 1: Basic Unit Test for Ternary Operator

**Files:**
- Modify: `tests/unit/test_c_frontend.py`

- [ ] **Step 1: Write the basic ternary test**

Add this test to `TestCFrontend` in `tests/unit/test_c_frontend.py`:

```python
    @covers(CFeature.TERNARY_OPERATOR)
    def test_c_ternary_operator(self, c_frontend: CFrontend) -> None:
        source = b'''
        int test_func(int condition) {
            int result = condition ? 42 : 99;
            return result;
        }
        '''
        cfg = c_frontend.build_cfg(source, "test_func")
        
        # Verify the structure: conditional branch and a merge point
        branch_block = cfg.get_block_by_label(CodeLabel("entry"))
        branch_inst = branch_block.instructions[-1]
        assert isinstance(branch_inst, BranchIf)
        
        true_label, false_label = branch_inst.branch_targets
        assert true_label.name.startswith("ternary_true")
        assert false_label.name.startswith("ternary_false")
        
        true_block = cfg.get_block_by_label(true_label)
        false_block = cfg.get_block_by_label(false_label)
        
        # Verify both branches merge
        assert len(true_block.successors) == 1
        assert len(false_block.successors) == 1
        merge_label = true_block.successors[0]
        assert merge_label == false_block.successors[0]
        assert merge_label.name.startswith("ternary_end")
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/unit/test_c_frontend.py::TestCFrontend::test_c_ternary_operator -v`
Expected: PASS (since the implementation already exists)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_c_frontend.py
git commit -m "test(c): add basic unit test for ternary operator CFG structure"
```

---

### Task 2: Nested and Complex Ternary Unit Test

**Files:**
- Modify: `tests/unit/test_c_frontend.py`

- [ ] **Step 1: Write the nested ternary test with complex expressions**

Add this test to `TestCFrontend` in `tests/unit/test_c_frontend.py`:

```python
    @covers(CFeature.TERNARY_OPERATOR)
    def test_c_complex_nested_ternary(self, c_frontend: CFrontend) -> None:
        source = b'''
        int compute(int x);
        int test_complex(int a, int b) {
            int result = (a > 5) ? (b ? compute(a) * 2 : a + b) : compute(b) - 1;
            return result;
        }
        '''
        cfg = c_frontend.build_cfg(source, "test_complex")
        
        # Verify we have multiple BranchIf instructions
        branch_ifs = [
            inst for block in cfg.blocks.values()
            for inst in block.instructions
            if isinstance(inst, BranchIf)
        ]
        assert len(branch_ifs) == 2
        
        # Verify we have both CallFunction (compute) and Binop instructions
        calls = [
            inst for block in cfg.blocks.values()
            for inst in block.instructions
            if isinstance(inst, CallFunction)
        ]
        assert len(calls) == 2
        
        binops = [
            inst for block in cfg.blocks.values()
            for inst in block.instructions
            if isinstance(inst, Binop)
        ]
        # At least one > for the condition, one * for compute(a)*2, one + for a+b, one - for compute(b)-1
        assert len(binops) >= 4 
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/unit/test_c_frontend.py::TestCFrontend::test_c_complex_nested_ternary -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_c_frontend.py
git commit -m "test(c): add unit test for complex nested ternary operators"
```

---

### Task 3: Integration Test for Execution

**Files:**
- Modify: `tests/unit/test_c_frontend.py`

- [ ] **Step 1: Write the integration test**

Add this test to `TestCFrontend` in `tests/unit/test_c_frontend.py`:

```python
    @covers(CFeature.TERNARY_OPERATOR)
    def test_c_ternary_operator_execution(self, c_frontend: CFrontend, registry: Registry) -> None:
        source = b'''
        int compute(int val) {
            return val * 10;
        }
        int main() {
            int a = 6;
            int b = 0;
            // a > 5 is true
            // b (0) is false, so it takes the 'a + b' branch = 6 + 0 = 6
            int result1 = (a > 5) ? (b ? compute(a) * 2 : a + b) : compute(b) - 1;
            
            // a < 5 is false, so it evaluates compute(b) - 1 = compute(0) - 1 = -1
            int result2 = (a < 5) ? 100 : compute(b) - 1;
            
            return result1 + result2;
        }
        '''
        registry.register_function(
            FuncName("compute"),
            c_frontend.build_cfg(source, "compute")
        )
        cfg = c_frontend.build_cfg(source, "main")
        final_state, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))
        
        # Expected return: result1 (6) + result2 (-1) = 5
        assert final_state.status == RunStatus.COMPLETED
        assert final_state.return_value is not None
        assert final_state.return_value.value == 5
```

- [ ] **Step 2: Check imports**
Ensure `execute_cfg`, `Registry`, `VMConfig`, `RunStatus`, and `FuncName` are imported in `test_c_frontend.py`. If missing, add them.

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/unit/test_c_frontend.py::TestCFrontend::test_c_ternary_operator_execution -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_c_frontend.py
git commit -m "test(c): add end-to-end integration test for complex ternary execution"
```
