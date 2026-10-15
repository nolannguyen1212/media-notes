# ADR 0006: Data Retention and Deletion

- Status: Accepted
- Date: 2026-07-25
- Decision owners: Media Notes maintainers
- Related design: [architecture.md](../architecture.md)

## Context

Media Notes stores account data, billing records, source media, generated
content, workflow state, and copies of media-derived bytes in independently
owned services and object storage. Deleting only the public media row would
leave inaccessible content, workflow records, or objects behind. Letting one
service delete another service's rows would violate service ownership and make
independent migration unsafe.

The initial product has no verified contractual or regulatory requirement for
a longer domain-data retention period. Billing records may require a different
period based on the deployment jurisdiction and payment-provider agreement.
Those requirements must be confirmed before production launch rather than
encoded as an unsupported legal assumption.

## Decision

Each service deletes only the data and objects it owns. Cross-service deletion
is coordinated through versioned Kafka commands and durable status events.
Deletion is asynchronous, idempotent, observable, and recoverable from partial
failure.

### Retention classes

| Data | Owner | Launch retention |
| --- | --- | --- |
| Active account and session data | `identity` | Until account deletion |
| Source-media metadata, processing requests, derivatives metadata | `media` | Until media or account deletion |
| Uploaded media and derivative bytes | `media` | Until media or account deletion |
| Transcript and generated content | `content` | Until media or account deletion |
| Summary-audio metadata and bytes | `content` | Until media or account deletion |
| Workflow, step, and attempt state | `conductor` | 90 days after terminal state |
| Inbox deduplication records | Consuming service | At least Kafka retention plus 7 days, initially 14 days |
| Outbox records | Producing service | 7 days after confirmed publication |
| Application logs | Telemetry platform | 30 days |
| Distributed traces | Telemetry platform | 7 days |
| Aggregated metrics | Telemetry platform | 13 months |
| Billing ledger, subscription, and provider evidence | `billing` | Deployment policy; no shorter than an applicable legal or contractual requirement |
| Kafka domain events | Kafka | Per ADR 0003; not a domain archive |

Retention durations are configuration with the values above as launch
defaults. A deployment may lengthen them after security, cost, and legal
review. It must not shorten inbox retention below the replay window or billing
retention below an applicable obligation.

Backups expire through the backup lifecycle and are not edited in place.
Deleted records may therefore remain in encrypted, access-controlled backups
until those backups expire. A restore procedure must reapply deletion
tombstones before restored data becomes externally accessible.

### User-visible media deletion

`media` owns the deletion lifecycle for a media item:

1. An authenticated command atomically changes the media state to
   `deletion_pending`, records a stable `deletion_id`, and writes an outbox
   command.
2. The item is immediately excluded from normal list, detail, playback, and
   processing operations. A workflow cannot be started or retried after this
   transition.
3. `media` publishes `mn.media.deletion.requested.v1` keyed by `media_id`.
   The event contains identifiers, reason, and timestamp only.
4. `content` and `conductor` independently delete or anonymize their
   owned records and publish idempotent completion events keyed by
   `deletion_id`.
5. `media` cancels outstanding upload sessions, deletes its owned object
   keys and rows, and waits for all required service completions.
6. After every required owner reports completion, `media` retains a minimal
   tombstone containing `media_id`, owner ID hash, `deletion_id`, completion
   time, and non-sensitive audit status for 90 days.

Object deletion uses exact keys recorded in owned metadata; implementations
must not construct a broad recursive prefix from untrusted input. Versioned
objects and incomplete multipart uploads are included. A missing row or object
is treated as an idempotent success.

### Account deletion

`identity` coordinates account deletion because it owns the account
lifecycle:

1. It revokes sessions and changes the account to `deletion_pending`.
2. It writes and publishes `mn.identity.account.deletion.requested.v1` with a
   stable `deletion_id`.
3. `media` starts deletion for every media item owned by the account.
   `content`, `conductor`, and `billing` delete or anonymize any
   directly indexed account data they own.
4. Each service records inbox state and publishes completion only after its
   durable deletion or anonymization work is committed.
5. `identity` completes deletion after all required owners report
   completion, then keeps a non-reversible account tombstone for 90 days.

The billing service may retain ledger or provider evidence that policy requires
but replaces direct identity fields with a deployment-scoped irreversible
reference wherever the obligation allows. Retained billing evidence is not
available through normal product queries.

### Failure, concurrency, and recovery

- A deletion command and every service completion are deduplicated by
  `deletion_id` and owner.
- Concurrent delete requests return the existing operation. Mutation,
  processing, and regeneration commands reject `deletion_pending` resources.
- Coordinators persist required participants and per-owner state. They do not
  rely on an in-memory join.
- Delivery retries use bounded exponential backoff with jitter. After the
  configured attempt limit, the command moves to a deletion DLQ and the
  operation remains `deletion_pending` for operator recovery.
- No partial failure restores product access. Operators may retry or reconcile
  missing owners, but cannot roll a partially executed deletion back to active.
- A scheduled reconciler scans a bounded page of overdue operations and
  republishes only missing work. It uses a lease or compare-and-set transition
  so replicas do not create an unbounded retry loop.
- In-flight workers check the authoritative media state before committing a
  result. Late results for a pending or completed deletion are rejected or
  immediately scheduled for deletion.

Deletion commands contain no media bytes, transcript, generated content, object
credentials, or billing details.

### API and observability

The public API returns a deletion operation ID and one of `pending`,
`completed`, or `failed_attention_required`. It does not claim immediate
physical erasure.

Metrics cover operations started, age of the oldest pending operation,
per-owner latency and failures, DLQ depth, reconciler outcomes, and object
deletion failures. Logs and traces include `deletion_id` and non-sensitive
resource IDs but no deleted content or identity fields. An alert fires when an
operation remains pending for more than 24 hours.

## Rollout and Rollback

Deletion is introduced behind a server-side feature flag. The rollout
first runs in dry-run mode to enumerate exact owned rows and object keys without
deleting them. Production enablement requires restore testing, tombstone replay
testing, DLQ recovery, and confirmation of billing and backup retention policy.

Before any owner performs physical deletion, rollback disables new deletion
requests and leaves recorded operations pending. After physical deletion
starts, rollback means stopping new work and recovering the workflow, not
restoring product access. Recovery from backup is reserved for operational
disaster and must not violate an acknowledged user deletion.

## Alternatives

| Alternative | Reason rejected |
| --- | --- |
| One service directly deletes all schemas | Violates ownership and couples credentials and migrations |
| Rely on database cascades across services | Requires cross-schema foreign keys and cannot cover object storage |
| Publish a fire-and-forget event without durable join state | Cannot prove completion or recover missing participants |
| Delete synchronously in the public request | Couples user latency to every service and object store |
| Retain all domain data indefinitely | Increases security exposure and storage cost without a requirement |

## Consequences

- Product access is removed promptly while physical deletion converges
  asynchronously.
- Every owner remains independently deployable and can apply its own legal
  retention behavior.
- Tombstones, inboxes, outboxes, retries, reconciliation, and operational
  tooling add storage and implementation work.
- Account deletion cannot promise a fixed physical-erasure deadline until
  billing and backup obligations are confirmed for the deployment.

## Validation

The deletion implementation must include:

- unit tests for state transitions, concurrent requests, terminal-state
  rejection, exact object enumeration, and idempotent missing data;
- integration tests for successful media and account deletion, duplicate and
  reordered events, one unavailable owner, late worker results, and DLQ retry;
- a fault test that restarts every coordinator and participant between request
  and completion;
- dry-run reconciliation comparing enumerated rows and objects with the
  expected ownership inventory;
- backup restore testing that proves tombstones are replayed before access;
- an operational exercise recovering an operation pending for more than
  24 hours without re-exposing partially deleted data.
