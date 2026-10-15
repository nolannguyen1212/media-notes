# Billing

Go gRPC and Kafka service owning quotes, credit balances, reservations, the
append-only ledger, subscriptions, and the Polar integration. No other
service changes balances or reads its tables. Pricing and settlement follow
[ADR 0008](../adr/0008-credit-pricing-and-settlement.md).

## Structure

```text
cmd/api/main.go
internal/app/            config, logging, health
internal/quote/          catalog-backed pricing and quotes
internal/credit/         reserve, settle, release, ledger
internal/subscription/   subscription state for summaries and webhooks
internal/provider/       Polar webhooks and outbound Polar API client
internal/grpc/           gRPC server and error mapping
internal/events/         outbox relay, credit-command consumer
internal/store/          PostgreSQL repositories
migrations/              V1 init, V2 subscriptions.updated_at, V3 launch-v2 catalog
```

## Data

Database `billing`, schema `billing`: `billing_accounts`,
`catalog_versions`, `credit_accounts`, `quotes`, `credit_reservations`,
`credit_ledger`, `subscriptions`, `webhook_events`, `inbox_events`,
`outbox_events`.

- `credit_ledger` is append-only, and each entry has a unique
  `idempotency_key`.
- `credit_accounts` holds the current `available` and `reserved` balance,
  guarded by optimistic locking and `CHECK (>= 0)` constraints.
- The active catalog is `launch-v2` (`V3`): `transcribe` 2,
  `summarize` 2, `extract_keywords` 2, `extract_keypoints` 2,
  `generate_notes` 5, `generate_audio_summary` 5 credits.

## gRPC API

`media_notes.billing.v1.BillingService`, read-only plus checkout:

- `GetQuote`, `GetPriceCatalog`, `GetBillingSummary`, `ListCreditLedger`
- `ListPlans`, `ListCreditPacks`, `CreateCheckoutSession`, `CancelSubscription`

Credit is never changed over gRPC. Reserve and settle arrive only as Kafka
commands.

## Credit flow

- **Quote:** prices the selected options against the active catalog.
  `generate_audio_summary` requires `summarize`. A quote is valid for
  15 minutes (`BILLING_QUOTE_TTL`).
- **Reserve** (`mn.billing.credit.reserve.v1`): moves the quoted amount from
  available to reserved and appends a ledger row. It is idempotent per
  workflow. Insufficient credit or an unknown or expired quote commits a
  `rejected` result instead of retrying.
- **Settle** (`mn.billing.credit.settle.v1`): `settle_item` charges one
  completed step at the price stored on the quote, never a new price;
  `release_remainder` returns whatever is still reserved.
- **Results** go out on `mn.billing.credit.reserved.v1` and
  `mn.billing.credit.settled.v1`, both keyed by `user_id`.

## Polar

- **Plans and credit packs** are read live from Polar: recurring products
  are plans, and one-time products with a positive `metadata.credits` are
  credit packs. Nothing is configured locally.
- **Checkout:** `CreateCheckoutSession` stamps `metadata.userId`, which every
  later webhook uses to find the user.
- **Webhooks** arrive at `POST /webhooks/polar` (Standard Webhooks
  headers). One quirk was verified against real Polar deliveries: the HMAC
  key is the literal `BILLING_POLAR_WEBHOOK_SECRET` string including its
  `whsec_` prefix, not the base64-decoded value. Timestamps more than
  5 minutes off are rejected.
- **`order.created`** grants `product.metadata.credits` to the user, for both
  top-ups and subscription renewals. It is deduplicated by a hash of the
  payload. `metadata.credits` can arrive as a JSON number, so metadata
  values are decoded as `any`.
- **`subscription.*`** upserts the billing account and the subscription,
  keyed by Polar's subscription ID.
- `BILLING_POLAR_SERVER` selects `sandbox` (the default) or `production`.

## Not implemented

- A sweep that expires or renews reservations (`expires_at` is stored, with
  a 24-hour TTL).
- Operator refunds; the `refund` ledger entry type exists but nothing issues
  it.
- A billing/conductor reconciliation job.
- Billing for standalone audio jobs.

## Runtime

HTTP on 8082 (`/health/live`, `/health/ready`, `POST /webhooks/polar`), gRPC
on 9093.
