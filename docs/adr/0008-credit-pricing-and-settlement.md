# ADR 0008: Credit Pricing and Settlement

- Status: Accepted
- Date: 2026-07-25
- Decision owners: Media Notes maintainers
- Related design: [architecture.md](../architecture.md)

## Context

Media Notes displays a fixed credit cost for each selected processing option.
Parallel outputs, retries, cancellation, and partial completion mean pricing
cannot simply deduct the full total up front: credit reservation must remain
predictable to users while duplicate delivery and retries must not charge
more than once.

Provider and infrastructure cost per job is not yet measured across the
allowed media-duration distribution. The launch prices are therefore a fixed
product contract, not a claim that one credit maps directly to a token,
compute-second, or currency amount.

## Decision

The launch catalog uses additive per-option pricing:

| Price item | Credits | Durable outcome |
| --- | ---: | --- |
| `transcribe` | 10 | Transcript and ordered segments committed |
| `summarize` | 20 | Summary and citations committed |
| `extract_keywords` | 5 | Ordered keywords committed |
| `extract_keypoints` | 10 | Ordered keypoints and references committed |
| `generate_notes` | 15 | Notes committed |
| `generate_audio_summary` | 30 | Audio object and metadata committed |

The maximum initial quote is 90 credits when every option is selected.

Pricing is represented by an immutable, versioned catalog owned by
`billing`. The initial catalog version is `launch-v1`. A processing
request stores:

- catalog version;
- selected price-item identifiers;
- price per item;
- quoted maximum;
- currency-independent credit unit;
- quote timestamp.

Changing catalog prices creates a new version. Existing requests, retries, and
regeneration attempts keep their stored quote. Catalog rollout and rollback
change the active version for new quotes only.

### Quote and reservation

1. `hermes` asks `billing` for a quote using canonical option identifiers.
2. The Web displays that quote; it does not calculate an authoritative price
   from a bundled constant.
3. `media` stores the accepted quote snapshot with the processing request.
4. `conductor` requests one reservation for the quoted maximum before
   publishing the first billable step.
5. `billing` atomically moves the amount from available to reserved credit
   and appends a ledger entry.

The reservation idempotency key is derived from billing account and workflow
ID. A duplicate command returns the existing reservation. Insufficient credit
rejects workflow admission without publishing a processing step.

The accepted quote has a 15-minute lifetime before workflow admission. Once a
reservation succeeds, the snapshot remains valid for that workflow. A
reservation expires after 24 hours without workflow activity; active workflows
renew it through an idempotent command. Expiry and renewal are bounded
scheduled operations in `billing`.

### Settlement

Credits settle per selected durable outcome, not per provider call or retry:

- A completion event settles that price item exactly once.
- Provider retries, duplicate commands, stale attempts, and replayed
  completion events do not add a charge.
- An unselected internal step has no price item.
- Failed, cancelled, or skipped items release their reserved amount.
- When the workflow becomes terminal, all unsettled reservation remainder is
  released.
- A completed outcome remains charged if a later optional outcome fails.

`generate_audio_summary` depends on a durable summary. If audio summary is
selected, `summarize` must also be selected and quoted; the API rejects an
invalid option set rather than hiding a prerequisite charge.

A regeneration request for a previously absent output receives a new quote
and reservation for only the newly requested items. Regenerating or replacing
an already completed output is a new billable operation only when the user
explicitly accepts a new quote. Automatic repair and platform-initiated replay
are never newly billable.

### Refunds and corrections

Settlement and release are append-only ledger entries. No service directly
rewrites a balance or another service's billing rows.

An operator or product-policy refund appends a compensating credit entry
referencing the original settlement and a unique idempotency key. Refunds do
not reopen the original reservation. Chargeback or subscription corrections
use separate ledger entry types and preserve the audit chain.

### Arithmetic and bounds

Credits are non-negative integers. Available and reserved balances use signed
64-bit storage with checked arithmetic; commands that would overflow or make a
balance negative fail atomically.

A processing request contains at most one item of each known price identifier.
Unknown identifiers, duplicate identifiers, negative prices, mismatched quote
totals, expired quotes, and unsupported catalog versions are rejected.

## Ownership and Events

`billing` owns catalogs, quotes, balances, reservations, settlements,
releases, refunds, and the append-only ledger. `conductor` owns workflow
state and decides when an outcome is durable or terminal. Neither service
reads or writes the other's schema.

Billing commands are keyed and ordered by the canonical `user_id`, matching
ADR 0003. Commands and results carry workflow ID, reservation ID, price item,
catalog version, amount, attempt-independent idempotency key, and correlation
metadata. They contain no transcript, generated content, media bytes, provider
response, or payment credentials.

Every balance mutation and outgoing result event commits through one database
transaction and transactional outbox. Consumers use inbox uniqueness.

## Observability

Metrics cover quote totals, reservation success and rejection, reserved age,
settled and released credits by price item, duplicate-command outcomes,
renewal/expiry, refunds, and reconciliation differences. Logs and traces carry
reservation, workflow, and idempotency identifiers without user content or
provider credentials.

A reconciler compares terminal workflow billing summaries with reservation
state through versioned contracts. It reports mismatches and issues only
idempotent missing settlement or release commands; it never edits another
service's database.

## Rollout and Review

The server quote is authoritative; a client-displayed estimate that
mismatches it blocks submission with a refreshed quote.

New billing behavior rolls out in shadow mode first: quote and reservation
decisions are computed and compared without mutating balances, and
enforcement starts only after additive totals and insufficient-balance
outcomes are verified correct. Catalog changes use a versioned catalog: a new
version takes effect for new quotes only, and rollback routes new work to the
previous active catalog while already-accepted workflows finish using their
snapshots.

Review product prices after 30 days of representative production traffic using
measured media duration, provider usage, GPU time, storage, retry rate,
completion rate, refunds, and purchased-credit economics. A later
duration-based or usage-based model requires a new catalog and explicit public
contract; it does not reinterpret existing quotes.

## Alternatives

| Alternative | Reason rejected |
| --- | --- |
| Deduct the full quote at request creation | Charges failed outputs and makes cancellation correction harder |
| Charge every provider attempt | Makes retries user-visible and rewards platform failure |
| Recalculate price at settlement | Allows catalog changes to alter an accepted user quote |
| Let `conductor` mutate balances | Violates billing ownership and bypasses the ledger |
| Price directly from tokens or GPU seconds now | Cost distribution and user contract are not yet measured |
| Change launch prices while introducing reservation and settlement | Conflates a pricing change with a mechanism change without a separate product decision |

## Validation

Implementation must include:

- quote tests for every option, all options, aliases, invalid dependencies,
  unknown and duplicate items, expiry, and catalog changes;
- concurrent reservation tests proving available credit cannot be overspent;
- duplicate, stale, reordered, and replayed settlement/release event tests;
- partial-success, cancellation, retry exhaustion, reservation expiry/renewal,
  regeneration, refund, overflow, and insufficient-credit tests;
- property tests that available plus reserved plus net settled movement
  reconciles with the append-only ledger;
- a shadow-mode comparison of quote and reservation decisions before
  enforcement is enabled;
- an operational reconciliation exercise that repairs missing idempotent
  commands without direct cross-service database access.
