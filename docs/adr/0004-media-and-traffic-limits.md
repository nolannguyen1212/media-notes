# ADR 0004: Media and Traffic Limits

- Status: Accepted
- Date: 2026-07-25
- Decision owners: Media Notes maintainers
- Related design: [architecture.md](../architecture.md)

## Context

Media Notes accepts user-controlled audio and video, stores source bytes in
object storage, and schedules expensive transcription and generation work.
The product rejects files larger than 500 MiB in the Web client and API, but
duration limits, concurrent-upload policy, and traffic budget must be defined
before upload sessions and worker capacity are implemented.

Limits must protect storage, provider quota, and database connections without
transporting media bytes through `hermes`, gRPC, or Kafka. Initial production
traffic is not measured, so these values are launch guardrails rather than
capacity claims.

## Decision

### Accepted media

| Property | Launch limit |
| --- | ---: |
| Source object size | 500 MiB (524,288,000 bytes) |
| Media duration | 4 hours (14,400,000 ms) |
| Files per upload session | 1 |
| Active upload sessions per user | 3 |
| Upload-session lifetime | 60 minutes |
| Playback URL lifetime | 15 minutes |

Accepted containers and MIME types remain MP4, MOV, MKV, WebM, MP3, WAV, and
M4A. MIME type is an early filter, not proof of content. A worker probes the
container before processing and rejects unreadable, encrypted, empty, or
unsupported media.

The 500 MiB ceiling preserves the existing product contract. A four-hour
duration supports long meetings and lectures while bounding transcription
cost. Size and duration are independent: highly compressed media must still
pass the duration check.

### Enforcement

Limits are enforced at more than one boundary because all client-supplied
metadata is untrusted.

1. `web` performs MIME-type and size checks for immediate feedback.
2. `hermes` rate-limits the authenticated request, but never receives media
   bytes.
3. `media` checks the requested MIME type, declared size, active-session
   count, and account policy before creating a session.
4. The presigned object-storage policy constrains the object key, maximum
   content length, and expiry.
5. On confirmation, `media` reads authoritative object metadata and rejects
   a missing, empty, oversized, or key-mismatched object before creating a
   processing request.
6. `conductor-worker` probes the source before expensive work and reports the
   actual MIME/container, duration, and media streams. `media` records the
   measured duration. A source over four hours fails permanently with
   `MEDIA_DURATION_EXCEEDED`.

An upload that fails confirmation or probing is not published as a processing
request. Its object is marked for deletion. Expired incomplete sessions and
their objects are removed by a lifecycle job.

### API traffic guardrails

Rate limits use a token bucket backed by Redis and are keyed by authenticated
user ID. The edge or load balancer also applies a coarser IP-based limit before
authentication. Limits return `429 Too Many Requests` with `Retry-After`.

| Operation class | Per-user limit | Burst |
| --- | ---: | ---: |
| Create or confirm upload session | 10/minute | 3 |
| Create processing or generation request | 10/minute | 3 |
| Sign playback or derivative URLs | 60/minute | 10 |
| Media list and detail reads | 120/minute | 20 |
| Other authenticated GraphQL operations | 120/minute | 20 |
| Authentication attempts | 10/15 minutes per account and IP | 5 |

The three-session concurrency limit is durable state in `media`, not only a
rate-limit counter. Retries with the same idempotency key return the existing
result and do not consume another logical mutation.

Provider concurrency is controlled separately from request rate. Workers do
not start more Whisper, Gemini, or TTS calls than the configured provider and
compute semaphores allow. Kafka lag absorbs admitted asynchronous work; it does
not bypass account entitlement, credit reservation, or provider quotas.

### Payload and pagination limits

- GraphQL request bodies are limited to 1 MiB.
- gRPC messages are limited to 1 MiB unless a contract documents a smaller
  bound.
- Kafka publishers retain the 256 KiB application limit from ADR 0003.
- Media list pages default to 20 items and allow at most 100.
- Object keys, checksums, IDs, state, and small metadata may cross service
  boundaries. Media bytes, transcript text, and generated long-form content
  may not.

### Capacity assumptions and revision

Launch dashboards distinguish rejected traffic from exhausted capacity.
Operators measure:

- upload sessions created, confirmed, expired, and rejected by reason;
- source bytes and measured duration distributions at p50, p95, and maximum;
- active uploads, upload completion time, and object-storage error rate;
- admitted processing requests, Kafka lag, and oldest-message age;
- worker step duration, provider throttling, CPU/GPU saturation, and storage
  throughput;
- per-operation request rate, p95 latency, and rate-limit rejections.

Review the limits after 30 days of representative production traffic, or
earlier if more than 1% of legitimate requests are rejected, p95 queue wait
exceeds the product objective, provider throttling persists, or storage and
compute budgets change. Raising a product limit requires a load test using the
proposed maximum; it is not an emergency response to queue lag.

## Consequences

### Positive

- Upload and processing tickets have concrete validation rules and error
  semantics.
- Direct-to-object-storage uploads keep large bytes away from application
  servers and Kafka.
- Durable concurrency and idempotency controls limit duplicate expensive work.
- Measured duration prevents compressed long-form media from bypassing cost
  controls.

### Costs and risks

- Duration is known only after probing, so some invalid objects are uploaded
  before rejection.
- A 60-minute upload-session lifetime keeps abandoned object keys valid for up
  to an hour before cleanup.
- Redis rate limiting requires a defined fail-open or fail-closed policy per
  operation during implementation.
- Launch values may be too strict or too permissive until production
  distributions are available.

## Rejected Alternatives

- **Send uploads through `hermes`:** increases application bandwidth and memory
  pressure without adding domain safety.
- **Trust declared file size or duration:** clients can forge both values.
- **Use only a daily upload quota:** does not protect short traffic spikes or
  concurrent provider consumption.
- **Put full transcripts or generated documents in Kafka:** violates the
  persistence boundary and broker record-size policy.
- **Allow unlimited duration under the size ceiling:** highly compressed media
  can create unbounded processing cost.

## Validation

Before production rollout:

- Test the exact size boundary, empty objects, oversized objects, expired
  sessions, key mismatch, and three-versus-four active sessions.
- Probe media immediately below and above four hours and verify the permanent
  error and cleanup path.
- Verify idempotent retries do not create sessions, processing requests, or
  rate-limit charges twice.
- Load test each operation class at its steady and burst limits.
- Confirm media bytes never appear in GraphQL, gRPC, Kafka, logs, or traces.
- Exercise Redis failure and provider-throttling behavior.

## Implementation status

As of 2026-10-15:

- Enforced: the 500 MiB declared and stored size, three active upload
  sessions, 60-minute sessions, 15-minute playback URLs, the MIME allowlist,
  1–50 IDs per progress request, and Redis-backed per-user rate limits in
  `hermes` that return 429 with `Retry-After`.
- Not enforced: the four-hour duration limit. `media` has a `MaxDurationMs`
  setting, but nothing probes the source file, so `MEDIA_DURATION_EXCEEDED`
  is never raised.
