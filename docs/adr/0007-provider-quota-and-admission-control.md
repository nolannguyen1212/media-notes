# ADR 0007: Provider Quota and Admission Control

- Status: Accepted
- Date: 2026-07-25
- Decision owners: Media Notes maintainers
- Related design: [architecture.md](../architecture.md)

## Context

Gemini enrichment and text-to-speech are externally limited resources.
Increasing Kafka partitions or worker replicas must not allow aggregate calls
to exceed a provider project's quota.

The Gemini Developer API evaluates requests per minute, input tokens per
minute, and requests per day per project rather than per API key. Limits vary
by model, usage tier, billing history, and account status. Google directs
deployments to view active limits in AI Studio and states that listed capacity
is not guaranteed:

- <https://ai.google.dev/gemini-api/docs/rate-limits>

Local development and tests use `edge-tts`, a third-party Python client for
Microsoft Edge's online TTS service without an API key:

- <https://github.com/rany2/edge-tts>

That integration provides no project quota, production SLA, contractual
capacity, or supported quota-increase path. It is not a safe production
dependency.

## Decision

Provider capacity is deployment configuration backed by verified provider
account limits. Media Notes does not encode public documentation values as
guaranteed quota.

### Gemini

Each deployment records, per provider project and model:

- requests per minute;
- input tokens per minute;
- requests per day;
- maximum concurrent requests;
- request timeout;
- model context and output bounds;
- cost budget and alert thresholds.

Production enablement requires copying the active project limits from AI
Studio, recording the verification timestamp, and setting operational limits
no higher than 80% of the lowest applicable provider limit. Preview model IDs
are not production defaults.

`conductor` owns durable admission because it owns step scheduling. Before
publishing a Gemini step, it reserves bounded request and estimated-input-token
capacity in its own schema. Reservations use a database transaction and
expire after a configured timeout. The estimate includes the complete prompt
and transcript; requests that exceed the model or deployment input bound fail
before publication.

Every worker also applies a local concurrency semaphore and timeout. Local
limits protect process resources but do not replace aggregate admission across
replicas.

Actual provider usage reconciles the reservation after each response. A
successful result, terminal error, cancellation, or timeout releases
concurrency. Minute and daily usage remain in their bounded windows until
expiry.

Provider `429 RESOURCE_EXHAUSTED` responses are normalized as retriable step
failures and honor `Retry-After` when present. `conductor`, not the worker,
persists the retry time and applies bounded exponential backoff with jitter.
Authentication, invalid request, safety rejection, and unsupported model
errors are terminal unless explicitly classified otherwise.

### Text-to-speech

Production summary audio uses a supported TTS provider configured with
authenticated project or account credentials, documented commercial use,
quota visibility, and a quota-increase or capacity-provisioning path.
`edge-tts` is limited to local development and tests.

The production TTS configuration records characters or tokens per period,
requests per period, concurrency, maximum input length, timeout, voice and
locale availability, cost budget, and data-processing region where applicable.
`conductor` applies the same durable reservation pattern before publishing a
TTS step. Workers apply local concurrency and reject text above the configured
bound before calling the provider.

No automatic provider fallback occurs within an attempt. A fallback can change
voice, quality, cost, data handling, and idempotency behavior. Changing provider
requires a new persisted attempt with the selected provider and voice recorded.

### Backpressure and failure behavior

- When capacity is unavailable, a step remains durably scheduled with a
  bounded next-admission time; it is not published into an unbounded in-memory
  queue.
- Admission scans use bounded pages and leases so multiple conductor replicas
  do not oversubscribe capacity.
- Worker cancellation cancels the provider request where supported, but the
  reservation remains conservative until reconciliation or expiry.
- A circuit breaker pauses new admission for repeated provider availability
  failures. It does not open for user-input or safety errors.
- Exhausted workflow retries use the existing processing DLQ and terminal
  failure policy. Provider quota errors do not create a separate retry owner.

Kafka messages contain provider and model identifiers, attempt number, and
small usage estimates only. Prompts, transcripts, generated text, audio bytes,
credentials, and provider responses do not travel through Kafka.

## Observability

Metrics are partitioned by provider, model, operation, and status, with
credential and project identifiers excluded:

- admitted, deferred, active, completed, and rejected calls;
- estimated and actual input/output units;
- remaining minute and daily budget;
- `429`, timeout, availability, safety, authentication, and invalid-input
  failures;
- provider latency, reservation age, Kafka lag, and oldest scheduled step;
- cost estimate and circuit-breaker state.

Alerts cover sustained 80% minute or daily utilization, any authentication
failure, repeated `429` responses below the configured budget, circuit-breaker
open duration, and oldest scheduled step above its objective.

## Rollout and Rollback

Admission launches in shadow mode: it computes decisions and usage without
blocking publication. Production enforcement starts at 50% of verified quota,
then increases to at most 80% after dashboards show correct reconciliation and
no oversubscription.

Rollback lowers limits or disables provider-backed optional outputs. It does
not bypass admission. TTS cannot be enabled in production while only
`edge-tts` is configured.

## Alternatives

| Alternative | Reason rejected |
| --- | --- |
| Limit only each worker replica | Aggregate calls grow whenever replicas scale |
| Use Kafka partition count as quota | Partitions bound consumers, not RPM, tokens, daily usage, or retries |
| Retry `429` immediately in workers | Creates retry storms and splits retry ownership from `conductor` |
| Hard-code published Gemini limits | Active limits vary by project and tier and are not guaranteed |
| Use `edge-tts` in production | No authenticated project quota, SLA, or supported capacity path |
| Silently fall back between providers | Changes output and policy without a durable workflow decision |

## Validation

Implementation must include:

- admission tests at minute and daily boundaries, concurrent reservations,
  expiry, cancellation, and reconciliation;
- tests proving replica count and duplicate commands cannot exceed aggregate
  configured concurrency;
- fault tests for `429` with and without `Retry-After`, timeout, terminal
  provider errors, circuit breaking, and conductor restart;
- shadow-mode comparison of estimated and actual usage;
- a load test at the verified deployment limits with dashboards and alerts;
- a production readiness check recording current provider limits, supported
  TTS contract, cost budget, and rollback configuration.
