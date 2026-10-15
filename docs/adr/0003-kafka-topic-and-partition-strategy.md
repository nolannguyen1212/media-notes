# ADR 0003: Kafka Topic and Partition Strategy

- Status: Accepted
- Date: 2026-07-25
- Decision owners: Media Notes maintainers
- Related design: [architecture.md](../architecture.md)

## Context

Media Notes uses Kafka to connect independently deployed domain services and
a horizontally scaled executor pool. Delivery is at least once, workflow steps
may complete in parallel, and billing mutations must remain ordered for one
account.

The initial traffic profile is not yet measured. The topic layout therefore
needs useful parallelism without encoding speculative infrastructure or making
ordering guarantees broader than the workflows require.

## Decision

### Topic inventory

Each business event or command has a versioned topic. Topics use the form
`mn.<domain>.<event>.v1`; a breaking payload or semantic change requires a new
topic version.

| Topic | Record key | Producer | Consumer group | Purpose |
| --- | --- | --- | --- | --- |
| `mn.media.processing.requested.v1` | `media_id` | `media` | `conductor-processing` | Start one processing workflow |
| `mn.processing.step.requested.v1` | `media_id` | `conductor` | `conductor-worker-steps` | Dispatch an executable workflow step |
| `mn.processing.step.completed.v1` | `media_id` | `content` | `conductor-step-results` | Advance a workflow after durable output |
| `mn.processing.step.failed.v1` | `media_id` | `conductor-worker` | `conductor-step-results` | Apply retry or terminal-failure policy |
| `mn.media.derivative.ready.v1` | `media_id` | `media` | `conductor-derivatives` | Record a durable derivative result |
| `mn.media.status.changed.v1` | `media_id` | `conductor` | `media-status` | Project workflow state into media state |
| `mn.billing.credit.reserve.v1` | `user_id` | `conductor` | `billing-credit-commands` | Reserve workflow credit |
| `mn.billing.credit.reserved.v1` | `user_id` | `billing` | `conductor-credit-results` | Continue or reject a workflow start |
| `mn.billing.credit.settle.v1` | `user_id` | `conductor` | `billing-credit-commands` | Capture or release reserved credit |
| `mn.processing.dlq.v1` | original record key | retry owner | operations tooling | Retain an exhausted record and failure context |

The two step-result topics share a consumer-group name intentionally. Consumer
groups are scoped by topic, so this gives the conductor one operational name
without combining success and failure schemas.

### Keys and ordering

Keys are canonical lowercase UUID strings encoded as UTF-8. Producers must
reject an empty or malformed key before publishing.

- Media and processing records use `media_id`.
- Billing records use `user_id`.
- A DLQ record preserves the original key and topic.

Kafka ordering is guaranteed only within one topic partition. The application
relies on ordering only for records with the same key in the same topic.
Cross-topic order is never assumed. Consumers still validate workflow version,
step attempt, and idempotency key because retries and concurrent producers can
make an older record arrive after a newer state transition.

### Partition counts

Initial non-production topics use six partitions for media and processing
traffic and three partitions for billing traffic. The DLQ uses three
partitions.

| Topic class | Initial partitions | Reason |
| --- | ---: | --- |
| Media and processing | 6 | Allows six active consumers while preserving per-media order |
| Billing | 3 | Billing volume is lower while still allowing independent users to progress concurrently |
| DLQ | 3 | Supports operational replay without matching peak processing throughput |

Production uses replication factor three and `min.insync.replicas=2`.
Single-broker local development uses replication factor one. Partition counts
may increase after measuring consumer lag, processing duration, and key skew;
they must not decrease in place. Increasing partitions changes the
key-to-partition mapping, so consumers must never depend on partition identity
or order across the resize boundary.

### Retention and record size

Business topics use `cleanup.policy=delete` and seven-day retention. This gives
operators time to recover a consumer without treating Kafka as the system of
record. The DLQ retains records for 30 days. PostgreSQL and object storage
remain authoritative for domain state and durable content.

Application publishers enforce a 256 KiB serialized-record limit. Broker topic
configuration keeps the standard 1 MiB ceiling as a secondary guard. Messages
contain identifiers, state, object keys, timestamps, error codes, and small
metadata only. Media bytes, transcripts, and long-form generated content are
never published.

### Delivery, retry, and replay

- Database state and an outgoing record are committed through a transactional
  outbox.
- Consumers commit offsets only after their durable state transition succeeds.
- Inbox uniqueness or a domain idempotency key makes duplicate delivery safe.
- `conductor` owns workflow retry policy. It persists the retry decision and
  publishes a new `processing.step.requested.v1` command with an incremented
  attempt and a new event ID.
- Broker redelivery handles transient consumer interruption; it is not the
  workflow retry scheduler.
- Exhausted or non-decodable records are copied to `mn.processing.dlq.v1` with
  the original topic, partition, offset, key, event ID, attempt, error code,
  and failure timestamp.
- DLQ replay uses operations tooling and republishes to the original topic only
  after the cause is corrected. Consumers apply normal idempotency checks.

### Observability and provisioning

Deployments provision topics explicitly; broker auto-creation is disabled
outside disposable local environments. Alerts cover consumer lag, oldest
outbox age, publish failures, DLQ growth, and partitions without an in-sync
replica. Logs and traces include topic, partition, offset, event ID,
correlation ID, workflow ID, and attempt without logging full payloads.

## Consequences

### Positive

- Per-media and per-user ordering matches actual domain invariants.
- Independent topics make ownership, access control, retention, and schema
  evolution explicit.
- A shared step-command topic keeps the first worker deployment simple while
  still supporting horizontal scaling.
- Retry decisions remain durable in the service that owns workflow state.

### Costs and risks

- Six long-running step commands can occupy all initial processing partitions;
  lag and step-duration metrics determine when to add partitions.
- A partition increase temporarily weakens ordering across the resize boundary,
  so consumer state validation remains mandatory.
- Separate event topics increase provisioning and monitoring work.
- The initial counts are capacity assumptions and must be revisited with
  production measurements.

## Rejected Alternatives

- **One topic for every step type:** enables capability-specific scaling but
  adds routing, provisioning, and consumer deployments before measurements show
  that Whisper, Gemini, and TTS need separate pools.
- **One topic for every domain:** mixes commands and events with different
  schemas, owners, retention needs, and consumers.
- **Key all workflow records by `workflow_id`:** weakens the required ordering
  between media lifecycle events before a workflow ID exists.
- **Use retry topics as the workflow scheduler:** splits retry ownership between
  Kafka timing conventions and `conductor` durable state.
- **Enable log compaction for status events:** consumers need transitions, while
  current state already lives in the owning PostgreSQL service.

## Validation

Before production rollout:

- Provision the inventory with the selected partition, replication, retention,
  and record-size settings.
- Verify records for one key remain ordered within each topic.
- Run duplicate-delivery and stale-attempt integration tests.
- Stop and restart a consumer while publishing, then confirm lag recovery.
- Exercise exhausted retry, DLQ inspection, correction, and replay.
- Load test representative step durations and revise partition counts from
  measured lag and key distribution.
