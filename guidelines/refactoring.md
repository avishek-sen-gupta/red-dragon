## Refactoring

### Replacing a primitive with a type

Map the blast radius first, and find every construction site structurally (`ast-grep`) rather than by reading.

- **Push the wrapping to the origin.** Wrap where the value is created — factory, parse boundary, external response — not at every intermediate consumer. If the factory returns the domain type, nothing downstream needs to re-wrap.
- **No coercion validators.** Never add a validator or post-construction hook that quietly converts a string into the type. It hides the call sites that should have been updated. If validation rejects a value, the caller is wrong — fix the caller.
- **No defensive type checks.** A runtime type test that falls back to constructing the type means the callers disagree. Fix the callers.
- **Validate at construction, not at use.** Reject invalid values — double-wrapping especially — where they are constructed, so the failure lands at the construction site rather than at some distant consumer.
- **Domain methods over raw extraction.** Add methods to the type instead of pulling the primitive back out and operating on it.
- **Carry the class, not its rendering.** Holding a type reference deletes the serialise-parse round trip and moves serialisation to the wire, where it belongs.
- **Keep what parsing produced.** If you have already parsed a value you have the object — don't discard it and store the raw text for something downstream to parse again.
- **A constraint belongs on the field.** A declared pattern, default or description is visible to callers *before* they call; a hand-rolled check in the function body can only report afterwards.
- **Name the field after what it holds.** A vague name invites a wrong value.
- **Separate name generation from typed generation.** A factory used for both typed values and plain unique names should be two factories.
- **A type parameter can be scoped but not stored.** A generic type cannot be the element type of a heterogeneous registry when its parameter is contravariant. A generic *function* keeps the parameter in scope and hands back an erased value.
- **Domain types are not directly serialisable.** Every serialisation path needs primitive conversion at the boundary — check all of them after migrating. (See the boundary rules in `guardrails.md`.)

### Before committing a migration

- **Grep for the old shape.** A rename the type checker accepts can still leave string literals behind: map keys, fixtures, reflective lookups, config entries. Search for the old name as text, not just as a symbol.
- **Search for bare-primitive comparisons.** A domain type whose equality rejects the raw primitive fails silently rather than loudly.
- **Watch for re-nulling fallbacks.** An expression that converts a falsy or absent sentinel back to null breaks the null-object pattern. Use direct pass-through.
- **Check map-literal arguments separately.** Literals in fixtures are not caught by the same search as keyword arguments. Fixtures feeding serialisation keep primitives; those feeding direct API calls need domain types.

### Working across the codebase

- **Bridge removal is its own commit.** Migrate all callers, verify the tests pass, then delete the bridge conversion in a follow-up. This isolates failures.
- **Prove the change catches what it claims.** Break the thing your new guard or type protects, and confirm the failure lands where you said it would. An error reported against a distant collection is worse than one reported at the class.
- **File issues for the next ring.** After propagating the type into its immediate adjacents, file issues for the next ring rather than doing everything in one session.
