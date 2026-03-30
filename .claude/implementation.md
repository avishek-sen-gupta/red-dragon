## Implementation Guidelines

- When implementing features for multiple languages, verify each language's actual capabilities against VM/frontend source code. Don't assume.
- When adding a language feature, consult existing frontend/VM documentation and implementation as reference before deciding on approach.
- When the user asks to scope to a specific subdirectory or module, scope precisely. Don't run on the broader repo.
- When working with LLM APIs, start with small test inputs before processing large datasets.
- Review subagent output for workaround guards (`is not None` checks that mask bugs).

## Interaction Style

- When interrupted or cancelled, immediately proceed with the new instruction. No clarifying questions — treat interruptions as implicit redirects.
- **Brainstorm collaboratively.** When thinking through approaches, present options and trade-offs to the user and actively incorporate their input before proceeding. Do not pick an approach and start implementing without discussion. The user's judgment on complexity/correctness trade-offs overrides the agent's default.
- **Stop and consult when patching.** If an implementation requires more than one corrective patch (fix-on-fix), stop. The design is wrong. Re-brainstorm the approach with the user before adding more patches. Accumulating compensating transforms is a sign the underlying model doesn't match reality.

## Python Introspection

- Write temporary scripts to `/tmp/*.py` and execute with `poetry run python /tmp/script.py`.
- Clean up temp files after use.
- Do not use `python -c` with multiline strings.

## Talisman (Secret Detection)

- If Talisman detects a potential secret, **stop** and prompt for guidance before updating `.talismanrc`.
- Don't overwrite existing `.talismanrc` entries — add at the end.
