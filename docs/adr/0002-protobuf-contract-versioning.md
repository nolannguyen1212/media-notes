# ADR 0002: Protobuf Contract Versioning

- Status: Accepted
- Date: 2026-07-25
- Decision owners: Media Notes maintainers
- Related design: [architecture.md](../architecture.md)

## Context

Media Notes services are deployed independently. A producer and consumer can
therefore run different revisions of a gRPC contract during rollout, rollback,
local development, or a partial deployment.

Keeping Protobuf files beside one service implementation would obscure
cross-service compatibility and make coordinated changes difficult to validate.
Publishing generated clients before contract ownership and generation targets
are stable would add dependency-management overhead too early.

## Decision

All synchronous service contracts live in one Buf module under
`contracts/proto`. Packages use the form `media_notes.<domain>.v1`, and the
directory hierarchy matches the package name.

Buf `STANDARD` lint rules define the repository style baseline. Comment-based
lint suppression is disabled so exceptions require an explicit configuration
change and review. Buf `FILE` breaking rules protect package, file, message,
field, enum, service, and method compatibility.

Changes within a package version are backward compatible and additive.
Incompatible changes require a new package version. Removed field and enum
numbers and names are reserved rather than reused.

The contract repository begins without code-generation configuration.
Generation targets and pinned plugins will be added with the first domain
service contract, when the required Go and Python outputs are concrete. It also
begins without speculative shared messages; tracing, identity, request IDs, and
similar transport context use gRPC metadata and interceptors.

## Consequences

### Positive

- Contract changes can be reviewed independently from implementations.
- Lint and breaking checks apply consistently across domains.
- Services can roll forward and backward while compatible versions overlap.
- A future Buf Schema Registry integration does not require reorganizing source
  files.

### Costs

- Compatibility must be considered even inside a monorepo.
- Major-version migrations temporarily maintain more than one package.
- Semantic compatibility still requires review because wire-safe changes can
  break application behavior or generated source code.

## Rejected Alternatives

- **Contracts inside each service:** makes shared review and cross-service
  compatibility checks harder.
- **One unversioned package per domain:** provides no safe namespace for
  intentional breaking changes.
- **Generate every language immediately:** introduces plugin and artifact
  decisions before the first domain API establishes actual consumers.
- **Use wire-only breaking checks:** permits source-level changes that are too
  risky for independently deployed internal clients.
