# `@@wf` Workflow Sentinel — Design Spec

**Date:** 2026-04-01
**Status:** Approved

---

## Problem

`classify-prompt.sh` (the `UserPromptSubmit` hook) uses keyword matching to decide whether to inject design/testing/refactoring context. The keyword list is broad enough that many ordinary prompts trigger injection, consuming tokens unnecessarily.

---

## Solution

Add an explicit opt-in sentinel `@@wf` to the prompt. The hook injects context only when `@@wf` is present. Absent the sentinel, the hook exits immediately with no output.

---

## Implementation

**File:** `.claude/classify-prompt.sh`

After extracting `$PROMPT`, add:

```sh
# Require explicit workflow sentinel; inject nothing otherwise
printf '%s' "$PROMPT" | grep -q '@@wf' || exit 0
```

Update the `LOWER` derivation to strip the sentinel before keyword matching:

```sh
LOWER=$(printf '%s' "$PROMPT" | sed 's/@@wf//g' | tr '[:upper:]' '[:lower:]')
```

No other changes. All keyword matching and section injection logic is unchanged.

---

## Usage

Prefix any prompt with `@@wf` to trigger context injection:

```
@@wf implement the list_opcodes handler
@@wf fix the type error in cfg.py
@@wf refactor the VarName migration
```

Prompts without the sentinel inject nothing.

---

## Sentinel Choice

`@@wf` chosen over `/wf` (intercepted by Claude Code as an unknown skill command) and bare `@@` (less readable). `@@wf` is unambiguous, fast to type, and will not appear naturally in prompts.

---

## Out of Scope

- Compressing the content of the conditional files — separate decision
- Adding new keyword categories — unchanged
