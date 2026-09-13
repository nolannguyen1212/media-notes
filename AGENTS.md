# Media Notes Project Instructions

These instructions apply to the entire repository. More specific `AGENTS.md`
files may refine them for a service or package.

## Priorities

1. Preserve correctness, compatibility, and data integrity.
2. Preserve the service and storage boundaries in
   `docs/adr/0001-service-and-data-ownership.md`.
3. Prefer clear, direct designs over clever abstractions.
4. Measure before optimizing and compare results after optimizing.
5. Keep changes small, reviewable, and independently verifiable.

## Required context

Before consequential changes, read the relevant sources:

- `proposal/mn2_design.md` for the Media Notes 2 target design.
- `proposal/mn2_brainstorm.md` for decisions, alternatives, and open questions.
- `docs/adr/` for accepted architecture decisions.
- `services/README.md` for Go service boundaries.
- Jira project `KAN` for implementation phase, blockers, and acceptance criteria.

Do not start a Jira ticket while an unresolved `is blocked by` relationship
exists unless the user explicitly changes the plan.

## Working agreement

- State assumptions when requirements or system behavior are unclear.
- Keep APIs, protocols, persisted data, events, and configuration backward
  compatible unless the task explicitly changes their contract.
- Make ownership, lifecycle, concurrency, cancellation, timeouts, retries, and
  failure behavior explicit where relevant.
- Avoid unbounded queues, goroutines, retries, caches, and resource usage.
- Add comments only for non-obvious constraints or decisions.
- Run the smallest relevant checks first, followed by broader project checks.
- Never report a check as passed unless it was run successfully.
- Keep Jira status and implementation evidence synchronized when work is
  performed against a Jira ticket.

## Service boundaries

- A service may not import another service's implementation or `internal`
  packages.
- A service may not read or write another service's database schema.
- Cross-service synchronous communication uses versioned gRPC contracts.
- Cross-service asynchronous communication uses versioned Kafka events.
- Media bytes and long-form generated content must not travel through Kafka.
- Shared libraries are limited to technical infrastructure such as
  observability, messaging envelopes, middleware, configuration, and test
  utilities.

## Skills

Use the project skills under `.agents/skills` when their descriptions match the
task:

- `system-design` for architecture, service boundaries, contracts, storage,
  distributed workflows, and migrations.
- `golang-development` for Go source, tests, modules, APIs, concurrency, and
  performance-sensitive Go components.
- `typescript-development` for the Web application.
- `testing-strategy` for test planning and implementation.
- `systematic-debugging` before fixing any bug, failure, or unexpected behavior.
- `performance-engineering` for evidence-based performance work.
- `nolan-code-style` for implementation and review work.
- `verification-before-completion` before any completion or passing claim.
- `nolan-git-commit` only when the user asks to commit, prepare a pull
  request, or manage commit structure.

When multiple skills apply, combine the language-specific skill with
`nolan-code-style`, `testing-strategy` where tests change, and
`verification-before-completion` before handoff.

## Verification

Use the checks relevant to the changed area:

```sh
make test:v2
make build:v2
make web:test
make web:typecheck
make web:lint
git diff --check
```

Do not run every check mechanically when a smaller check provides credible
evidence, but run cross-project checks when contracts or shared infrastructure
change.

## Design and operations

- Document meaningful tradeoffs and rejected alternatives for consequential
  system changes.
- Consider observability, security, rollout, rollback, and operational failure
  modes.
- Treat benchmarks and profiles as evidence rather than assumptions.
- Database migrations and destructive data operations require a tested rollback
  strategy.

## Git

- Follow `.agents/skills/nolan-git-commit/SKILL.md` for commits and pull
  requests.
- Commit messages must be exactly one line, with no body or footer.
- Never include secrets, generated local state, co-author trailers, or unrelated
  changes.
- Do not commit, push, create a branch, or open a pull request unless the user
  explicitly requests it.
