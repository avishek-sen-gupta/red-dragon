## Design Principles

- **Use existing infrastructure before adding new abstractions.** Ask: "does the system already have something that solves this?" The answer is usually yes.
- **Start from the simplest possible mechanism.** Add complexity only when the simple one is proven insufficient.
- **Build features from existing constructs** rather than threading a new convention through multiple layers.
- **No speculative code without tests.** Every code path must have a test that exercises it.
- **Stay consistent with established patterns.** When the codebase has a way of doing something, use it.
- **Never mask bugs with workaround guards.** Don't add null checks to make tests pass. Fix the root cause.
- **Pass decisions through data, don't re-derive downstream.** If a decision was made upstream, attach it to the data rather than re-detecting it via fragile lookups.
- **Do not encode information in string representations.** Never use string prefixes, patterns, or regex to deduce what a value represents — use a typed object and a type test.
