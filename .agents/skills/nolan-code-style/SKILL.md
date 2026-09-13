---
name: nolan-code-style
description: Apply Nolan Nguyen's preferred coding style when writing, modifying, refactoring, or reviewing source code. Use for implementation work across languages when code should be clean, concise, explicit, easy to follow, minimally commented, and free of unnecessary abstractions. Combine with project-specific formatters, linters, tests, and repository conventions.
---

# Nolan Code Style

Optimize first for correctness and readability, then for brevity. Never shorten code at the cost of hiding behavior.

## Write clear code

1. Keep functions focused on one responsibility.
2. Use precise names that reveal intent without explanatory comments.
3. Prefer straightforward control flow, guard clauses, and early returns over deep nesting.
4. Make inputs, outputs, state changes, errors, and side effects explicit.
5. Keep related logic together and separate unrelated concerns.
6. Reuse an existing abstraction when it fits; create a new one only after a concrete repeated need appears.

## Keep code concise

1. Remove duplication, dead code, redundant wrappers, unnecessary branches, and needless temporary variables.
2. Prefer the smallest implementation that fully handles the required behavior and relevant edge cases.
3. Avoid speculative extensibility, premature generalization, clever one-liners, and compressed expressions that require rereading.
4. Follow the repository's established patterns unless they create a correctness or maintainability problem.

## Comment sparingly

1. Prefer expressive code over comments.
2. Add a comment only when it explains a non-obvious reason, constraint, invariant, compatibility issue, or safety concern.
3. Keep comments short, direct, and complete enough to preserve the reasoning.
4. Do not narrate what the next line already says.
5. Remove stale, redundant, commented-out, or misleading comments.

## Preserve quality

1. Handle errors at the appropriate boundary; do not silently swallow failures.
2. Preserve type safety and data invariants.
3. Add or update focused tests for changed behavior.
4. Run the relevant formatter, linter, type checker, and tests defined by the repository.
5. Review the final diff and simplify once more without expanding scope.

## Review checklist

- Can a maintainer understand the main path in one pass?
- Is every abstraction justified by current behavior?
- Are names clear enough that most comments are unnecessary?
- Are edge cases and errors visible rather than hidden?
- Is there any shorter implementation that remains equally clear and correct?
