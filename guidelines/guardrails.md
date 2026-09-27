## Guardrails

These override defaults and are not negotiable.

- **No gold plating.** Build what was asked for and nothing more — no abstraction layers, extension points, configuration knobs, or generality no current caller needs.
- **No unilateral decisions.** Never invent a switch, a flag, or a default policy to avoid asking. If something has to be decided, the user decides it. Adding an option so that both answers are available is the same mistake twice.
- **No comments.** The only permitted comment is a one-line header on a class or module stating its purpose. A comment anywhere else means the code failed to explain itself — rewrite the code. No per-function doc comments, no inline explanations, no section dividers, no TODOs.
- **Fully typed, no escape hatches.** The type checker runs in its strictest mode and must pass with zero errors:
  - The language's "any" type is banned. If a type is hard to express, use an interface, a generic parameter, or a union; if it is genuinely unknown at a boundary, parse it into a concrete type there.
  - Every generic is parameterised. The element type is part of the contract, not decoration.
  - No untyped blobs. A generic "object" annotation or a hand-rolled recursive JSON alias is the "any" type with extra steps — it defers the contract instead of stating it.

  An escape-hatch type in a signature means the contract was never worked out.
- **State types for the checker, not just for the reader.** Where a language offers both structural and nominal conformance, declare the nominal relationship: the error then lands on the broken class rather than on the distant collection where the objects meet the annotation, and implementations stay navigable from the contract. Contracts satisfied by types outside your codebase stay structural, since they cannot inherit anything of yours.
- **Text is a boundary, never a carrier.**
  1. Anything arriving from an external system is parsed into a concrete type on arrival. Past that line no strings hold structure and no objects are untyped — only instances.
  2. Anything leaving is serialised at the last possible moment, in the adapter, where the wire actually needs text. Serialising early and parsing back later is the same defect written twice.
  3. Anything read from a structured file becomes a typed object immediately. Never index a parsed map. If a typed reader exists use it; if not, write it.
  4. Nowhere else does data live in a string. A field named `*_json` is either the single validated boundary or a bug. Prose bound for a prompt is text; a record with fields is not.

  One exception: a value whose type is unknowable until runtime may cross **one** boundary as text, parsed the instant the type is known. One hop, never two.
- **Few tests, each covering a whole behaviour.** One test per coherent behaviour, asserting everything that behaviour implies — not one test per assertion. A module with eight behaviours gets eight tests, not eighty.
