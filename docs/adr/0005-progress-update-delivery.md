# ADR 0005: Progress Update Delivery

- Status: Accepted
- Date: 2026-07-25
- Decision owners: Media Notes maintainers
- Related design: [architecture.md](../architecture.md)

## Context

Media processing is asynchronous and may take minutes. The Web application
needs timely status updates on the queue and detail pages without exposing
Kafka, workflow internals, or another service's database.

`hermes` is the public GraphQL boundary and `media` owns the user-facing
media status projection. Hermes does not have a streaming GraphQL runtime or
cross-instance connection fan-out. Initial concurrent-user and
active-workflow traffic is not measured.

The launch mechanism must remain correct across duplicate Kafka delivery,
missed intermediate transitions, browser suspension, Hermes restarts, and
horizontally scaled stateless instances.

## Decision

Media Notes uses adaptive GraphQL polling. The Web polls a dedicated
batched progress query every three seconds only while visible media items are
non-terminal.

Polling reads the latest durable projection, so it does not require delivery
of every intermediate transition. `media` remains authoritative for
user-facing status; `conductor` remains authoritative for workflow state.
The `mn.media.status.changed.v1` consumer updates the media projection
idempotently before the new state is observable through GraphQL.

### Public query

Hermes exposes a query shaped like:

```graphql
mediaProgress(ids: [ID!]!): [MediaProgress!]!
```

The initial contract has these bounds:

- One request contains 1–50 unique media IDs.
- Hermes derives the owner from the authenticated context; ownership is never
  accepted from query input.
- Hermes calls one batched `GetMediaProgress` media gRPC method rather than
  issuing one call per ID.
- Results include `mediaId`, media `status`, processing-request `status`,
  `currentStep`, `completedSteps`, `totalSteps`, `updatedAt`, and a monotonic
  projection `version`.
- Unknown and unauthorized IDs are both omitted so the API does not reveal
  whether another user's media exists.
- The query returns metadata only. It never returns media bytes, transcript
  text, generated long-form content, object credentials, or Kafka records.

The progress percentage is derived from completed required steps over total
required steps. It is a workflow-stage indicator, not an estimate of elapsed
compute time. The Web must not invent fractional progress inside a running AI
step.

### Client behavior

1. A list or detail query supplies the initial durable status.
2. The Web collects non-terminal IDs currently represented on screen and polls
   `mediaProgress` every three seconds.
3. A response updates matching normalized cache entries only when its
   projection version is newer.
4. Terminal media IDs are removed from subsequent polls.
5. Polling pauses while the document is hidden or the browser is offline.
6. The client immediately refetches after visibility or connectivity returns.
7. When no represented media item is active, the timer stops.

Filters and cursor pages are not reloaded on every interval. A transition that
changes membership in the current filtered view invalidates the relevant list
query once; it does not trigger continuous full-list polling.

Failures use exponential backoff with jitter, starting at three seconds and
capped at 30 seconds. A successful response restores the three-second
interval. `429` responses honor `Retry-After`. Authentication failures stop
polling and follow the normal session-expiry flow.

### Service and deployment behavior

- Each polling request is independent, authenticated, cancellable, and safe to
  route to any Hermes instance.
- Hermes applies the media-read traffic guardrails from ADR 0004.
- Hermes sets a gRPC deadline and cancels the downstream call when the client
  disconnects.
- Media returns one consistent projection per row; a poll may observe
  different committed versions across different media IDs.
- No Redis Pub/Sub, sticky sessions, WebSocket gateway, or in-memory
  subscription registry is introduced.
- Polling is a read operation and creates no domain event or idempotency
  record.

### Delivery objective and capacity

The launch objective is for a foreground client to observe a committed status
transition within five seconds at p95. This combines the three-second interval
with request and projection latency; it is not a guarantee for suspended or
offline browsers.

At the maximum batch size, one active foreground client produces 20 progress
requests per minute regardless of whether 1 or 50 represented media items are
active. Dashboards measure active polling clients, batch-size distribution,
request rate, p95 latency, media gRPC latency, errors, and projection age.

Revisit the transport when representative measurements show any of:

- progress polling consumes more than 10% of sustained Hermes request
  capacity;
- more than 10,000 clients poll concurrently for sustained periods;
- the product requires a sub-two-second update objective;
- progress updates must be delivered while the application is not foreground;
- repeated reads materially increase database or network cost.

These are investigation triggers, not rules for switching transport
automatically. If a push
transport becomes necessary, SSE is the preferred next candidate because the
flow is server-to-client and does not require bidirectional WebSocket
semantics.

## Alternatives

| Mechanism | Benefits | Launch costs and risks | Decision |
| --- | --- | --- | --- |
| Adaptive polling | Stateless Hermes instances, durable-state recovery, simple authentication, natural batching | Repeated reads and update latency bounded by interval | Selected |
| Server-Sent Events | One-way push over HTTP, native browser reconnect | Long-lived connections, cross-instance fan-out, replay cursor, proxy timeout handling | Defer until measurements justify push |
| GraphQL subscriptions | Typed push API and one GraphQL surface | WebSocket/SSE subscription runtime, connection auth lifecycle, fan-out, greater client and operational complexity | Rejected for launch |

## Consequences

### Positive

- Every refresh recovers from missed transitions by reading authoritative
  durable state.
- Hermes remains stateless and horizontally scalable.
- The implementation reuses the current client behavior while avoiding
  repeated list and content queries.
- Batching bounds downstream calls and prevents GraphQL N+1 behavior.

### Costs and risks

- Active foreground clients generate reads when no status changed.
- Users observe transitions after an interval rather than immediately.
- The media projection must expose enough progress detail without leaking
  conductor-owned workflow internals.
- Projection versioning adds a field and update invariant to the media read
  model.

## Rejected Alternatives

- **Poll the entire queue and detail payload:** repeatedly loads pagination,
  derivatives, transcript, and generated content that progress does not need.
- **Consume Kafka from Hermes:** gives the public edge domain-event ownership,
  requires replay and fan-out state, and bypasses media's durable
  projection.
- **Use Redis Pub/Sub as the source of truth:** messages can be missed during
  disconnects and Redis does not own media status.
- **Start with GraphQL subscriptions for future flexibility:** adds operational
  complexity before a measured requirement exists.

## Validation

The polling implementation must include:

- client tests with controlled time covering start, terminal stop, hidden and
  offline pause, resume refetch, newer-version updates, backoff, `Retry-After`,
  and authentication failure;
- GraphQL and gRPC integration tests covering 1 and 50 IDs, duplicate IDs,
  mixed terminal states, unknown IDs, unauthorized IDs, and downstream
  deadline or failure;
- a projection test proving stale or duplicate Kafka status events cannot
  replace a newer version;
- a load test at the expected concurrent-client profile and maximum batch size;
- dashboards and an alert for the five-second p95 observation objective;
- rollout behind a client configuration switch so the three-second interval
  can be increased without redeploying every service.
