# ADR 0001: Service and Data Ownership Boundaries

- Status: Accepted
- Date: 2026-07-25
- Decision owners: Media Notes maintainers
- Related design: [architecture.md](../architecture.md)

## Context

Media Notes is built as independently deployable services with an explicit
asynchronous workflow, rather than one server handling public API,
authentication, billing, media management, job publication, result
consumption, and persistence together. Without strict ownership rules, the
services could still behave as a distributed monolith by sharing tables,
domain models, or internal implementations.

## Decision

Media Notes uses the following application-service boundaries:

| Service | Owns | Does not own |
| --- | --- | --- |
| `hermes` | Public GraphQL schema, request authentication context, batching, response aggregation | Domain records or domain database tables |
| `identity` | Users, accounts, sessions, verification records, roles | Media, content, workflow, or billing records |
| `billing` | Billing accounts, subscriptions, credit balances, reservations, ledger entries, Polar webhook state | Media processing state or generated content |
| `media` | Upload sessions, source-media metadata, processing requests, media derivatives | Transcripts, generated content, workflow attempts, or credit balances |
| `content` | Transcripts, transcript segments, summaries, citations, keywords, keypoints, notes, summary-audio metadata | Source-media lifecycle, workflow decisions, or billing |
| `conductor` | Workflows, steps, dependencies, attempts, retry decisions, timeouts, and joins | AI execution, media bytes, generated content, or credit ledger entries |
| `conductor-worker` | Stateless execution of Whisper, Gemini, FFmpeg, and TTS commands | Durable workflow or domain state |

Kafka, PostgreSQL, MinIO/S3, Redis, and OpenTelemetry are infrastructure rather
than application services.

## Database Rules

1. Each stateful service owns a dedicated PostgreSQL database and
   credential — not just a dedicated schema in a shared database.
2. A service may read or write only its own database.
3. Cross-service identifiers are UUID values without cross-database foreign
   keys.
4. Cross-service reads use versioned gRPC contracts.
5. Cross-service state changes use gRPC commands or versioned Kafka events.
6. Consumers use inbox records or idempotency keys for at-least-once delivery.
7. Database writes coupled to event publication use a transactional outbox.
8. Migrations are packaged and executed independently per service.

One PostgreSQL server may host multiple service databases during the initial
deployment. Sharing a server does not relax service ownership: each service
credential can connect only to its own database.

## Storage Rules

PostgreSQL stores queryable text and structured state, including transcripts,
segments, summaries, citations, notes, keywords, keypoints, workflow state, and
billing records.

Object storage stores:

- Uploaded audio and video.
- Generated thumbnails, cover images, and waveform previews.
- Generated summary-audio bytes.

Kafka messages contain identifiers, idempotency keys, state, object keys,
attempt numbers, timestamps, error codes, and small metadata. Media bytes,
complete transcripts, and long-form generated content must not be transported
through Kafka.

## Source-Code Boundaries

Services may share small technical libraries for:

- Observability bootstrap.
- Correlation and trace propagation.
- Kafka message envelopes.
- gRPC middleware.
- Configuration loading.
- Test utilities.

Services must not share:

- Domain entities or database models.
- Repository implementations.
- Migration files.
- Business rules.
- Another service's `internal` package.

Protobuf and event schemas live in a shared, versioned contracts area. Generated
clients are the allowed compile-time dependency; server implementations remain
private to their owning service.

## Consistency Model

Cross-service workflows are eventually consistent. Exactly-once business
behavior is achieved through idempotent state transitions, inbox deduplication,
unique idempotency keys, and transactional outboxes—not by assuming a message
is delivered only once.

Generated content is durable before `processing.step.completed.v1` is
published. A worker acknowledges a command only after the owning service has
accepted the durable result, or after an object and its metadata are durable.

## Enforcement

The repository and CI will enforce these boundaries through:

- A separate Go module and migration directory for each Go service.
- No imports from another service's `internal` tree.
- Contract compatibility checks for Protobuf and event schemas.
- Path-scoped builds and tests for independently deployable artifacts.
- Integration tests that access services through public contracts.
- Separate database credentials in local and deployed environments.

## Consequences

### Positive

- Ownership and operational responsibility are explicit.
- Services can be deployed, scaled, and evolved independently.
- Workflow recovery does not depend on worker process lifetime.
- Contract and integration testing can detect incompatible changes.
- A future repository split remains possible without redesigning domain
  boundaries.

### Costs

- Cross-domain queries require aggregation in `hermes`.
- Workflows must handle eventual consistency and duplicate delivery.
- Contract evolution and deployment compatibility require deliberate
  versioning.
- Local development needs multiple databases, services, and infrastructure
  dependencies.

## Rejected Alternatives

- **Shared database access across services:** creates hidden coupling and makes
  independent migrations unsafe.
- **A shared domain-model package:** couples service releases and transfers
  ownership into a common library.
- **Full transcripts in Kafka or object storage:** weakens queryability and
  creates inefficient broker payloads.
- **One repository per service immediately:** adds coordination overhead before
  separate team ownership or release cadence exists.

## Follow-up Decisions

Separate ADRs will define:

- Protobuf and event-schema compatibility policy.
- Kafka topic and partition strategy.
- Credit pricing and reservation calculation.
- Progress delivery through polling, SSE, or GraphQL subscriptions.
- Data retention and cross-service deletion.
