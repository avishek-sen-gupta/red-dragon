# Red Dragon — Paper Evaluation Scripts

Scripts used to generate the empirical data in the SCAM 2026 paper:
**"Red Dragon: A Language-Agnostic Intermediate Representation for Cross-Language Program Analysis"**

All scripts run from the `red-dragon` repo root using Poetry:

```bash
poetry run python3 scripts/<script>.py [options]
```

---

## Scripts

### 01_cfg_shape_summary.py
One-line summary per algorithm: min/max blocks, min/max edges, number of structural variants, unresolved SYMBOLIC count.

```bash
poetry run python3 scripts/01_cfg_shape_summary.py
```

**Generates:** Overview table used as input for Tables 1–2 in the paper.

---

### 02_structural_equivalence_table.py
Full 15-language × 13-algorithm structural equivalence table (Table 2). Groups languages by (blocks, edges) shape and assigns class labels A, B, C...

```bash
poetry run python3 scripts/02_structural_equivalence_table.py
poetry run python3 scripts/02_structural_equivalence_table.py --csv  # CSV output
```

**Generates:** Table 2 in the paper.

---

### 03_structural_class_drilldown.py
For a given algorithm, prints the full IR and block structure for each language, grouped by structural class. Used to explain *why* a language has a particular shape.

```bash
poetry run python3 scripts/03_structural_class_drilldown.py factorial_rec
poetry run python3 scripts/03_structural_class_drilldown.py classes lua c go python java
poetry run python3 scripts/03_structural_class_drilldown.py fibonacci python java
```

**Generates:** Explanatory analysis for Sections 5.3 and 5.4, worked example in Section 3.4.

---

### 04_symbolic_audit.py
Audits every SYMBOLIC instruction across the entire Rosetta corpus. Classifies into param, caught_exception, unsupported, and other. Reports zero unresolved SYMBOLICs.

```bash
poetry run python3 scripts/04_symbolic_audit.py
poetry run python3 scripts/04_symbolic_audit.py --verbose  # full detail
```

**Generates:** Section 6.3 claim (zero unresolved SYMBOLIC residuals).

---

### 05_execution_equivalence.py
Executes five numeric algorithms through the VM across all 15 languages. Reports pass/fail (Table 4) and optionally step counts with deltas (Table 5).

```bash
poetry run python3 scripts/05_execution_equivalence.py
poetry run python3 scripts/05_execution_equivalence.py --steps  # include step count tables
```

**Generates:** Tables 4 and 5 in the paper.

---

### 06_structural_class_groups.py
Grouped view of structural classes per algorithm — which languages share each shape, in descending group size. Used for the Section 5.3 four-causes analysis.

```bash
poetry run python3 scripts/06_structural_class_groups.py            # all algorithms
poetry run python3 scripts/06_structural_class_groups.py classes    # one algorithm
```

**Generates:** Supporting analysis for Sections 5.3–5.4.

---

## Reproducing all paper tables

```bash
# Table 2 (structural equivalence classes)
poetry run python3 scripts/02_structural_equivalence_table.py

# Table 4 (execution equivalence)
poetry run python3 scripts/05_execution_equivalence.py

# Table 5 (step counts)
poetry run python3 scripts/05_execution_equivalence.py --steps

# Section 5.3 four-causes analysis
poetry run python3 scripts/06_structural_class_groups.py

# Section 3.2 SYMBOLIC audit (zero unresolved)
poetry run python3 scripts/04_symbolic_audit.py
```

All scripts are deterministic (zero LLM calls) and complete in under 60 seconds on a 2023-era laptop.
