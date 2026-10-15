# Hermes

Go GraphQL gateway. It owns the public schema, authentication context,
request limits, and response aggregation. It owns no database; Redis holds
only rate-limit counters.

## Structure

```text
cmd/hermes/main.go
internal/app/        config, logging, health
internal/auth/       session-token extraction and validation through identity
internal/clients/    gRPC client wrappers for identity, billing, media, content
internal/graphql/    schema.graphqls, resolvers, gqlgen output
internal/http/       server and middleware
internal/limits/     body-size and Redis rate limits (ADR 0004)
```

## API

GraphQL at `POST /graphql` (port 8086).

| Area | Queries | Mutations |
| --- | --- | --- |
| Account | `me`, `promptSettings` | `register`, `login`, `logout`, `requestAccountDeletion`, `updatePromptSetting` |
| Media | `mediaList`, `mediaDetail`, `mediaProgress`, `trashedMedia` | `createUploadSession`, `confirmUpload`, `updateMedia`, `requestProcessing`, `requestThumbnailUpload`, `setThumbnail`, `trashMedia`, `restoreMedia`, `deleteMediaPermanently` |
| Content | `contentDetail` | — |
| Audio | `audioJob`, `audioJobs` | `draftAudioScript`, `generateStandaloneAudio` |
| Billing | `quote`, `priceCatalog`, `billingSummary`, `plans`, `creditPacks`, `creditLedgerHistory` | `createCheckoutSession`, `cancelSubscription` |

## Behavior

- **Authentication:** the session token comes from `Authorization: Bearer`
  or a cookie and is validated once per request through identity's
  `ValidateSession`.
- **Ownership:** any resolver that takes a bare ID (`updateMedia`,
  `requestProcessing`, `audioJob`, and similar) fetches the resource first and
  compares its owner to the caller. Owner IDs never come from query input.
- **Prompt overrides:** `confirmUpload` and `requestProcessing` read the
  caller's saved prompt settings from identity and forward them to media as
  `prompt_overrides`, which reach the worker through the workflow.
- **Deadlines:** every downstream gRPC call gets `HERMES_DOWNSTREAM_TIMEOUT`
  (5s by default).
- **Limits:** GraphQL bodies are capped at 1 MiB. Per-user rate limits from
  ADR 0004 return HTTP 429 with `Retry-After`.
- **Errors:** gRPC status codes map to safe GraphQL errors; transport details
  are never returned to the client.

## Not implemented

- Media recommendations. The web "Recommended" shelf shuffles the caller's
  own `mediaList` client-side.
- Billing for standalone audio jobs.
