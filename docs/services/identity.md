# Identity

Go gRPC service owning users, credentials, sessions, per-user prompt
settings, and account deletion. Only `hermes` calls it; other services hold
plain `user_id` UUIDs.

## Structure

```text
cmd/api/main.go
internal/app/              config, logging, health
internal/account/          registration, profile, deletion state machine
internal/session/          session issue, validation, revoke
internal/promptsettings/   per-user custom LLM prompts
internal/grpc/             gRPC server and error mapping
internal/store/            PostgreSQL repositories
internal/events/           outbox relay, deletion-completion inbox, reconciler
migrations/                V1 init, V2 prompt settings
```

## Data

Database `identity`, schema `public`.

| Table | Holds |
| --- | --- |
| `users` | profile, normalized email, state (`active`, `deletion_pending`, `tombstoned`) |
| `accounts` | provider account and bcrypt credential hash |
| `sessions` | token hash, expiry, revocation |
| `verification_records`, `user_roles` | verification tokens and roles |
| `account_deletions` | deletion operation and per-participant state |
| `user_prompt_settings` | custom prompt per user and section, at most 500 characters |
| `inbox_events`, `outbox_events` | event deduplication and transactional outbox |

Raw passwords and session tokens are never stored or logged; only their
hashes are.

## gRPC API

`media_notes.identity.v1.IdentityService`:

- `RegisterAccount`, `Authenticate`, `ValidateSession`, `RevokeSession`
- `GetUser`, `UpdateUser`
- `GetPromptSettings`, `UpsertPromptSetting`
- `RequestAccountDeletion`, `GetAccountDeletionStatus`

Authentication is email and password. Prompt-setting sections are the
options that reach an LLM: `summarize`, `extract_keywords`,
`extract_keypoints`, and `generate_notes`.

## Account deletion

<img src="../diagrams/deletion.svg" alt="Deletion" width="560">

1. `RequestAccountDeletion` revokes all sessions, sets the user to
   `deletion_pending`, and writes `mn.identity.account.deletion.requested.v1`
   to the outbox in one transaction. Repeated requests return the same
   operation.
2. `media` consumes the event and deletes the user's media.
3. Completion events are consumed only from the topics listed in
   `IDENTITY_DELETION_COMPLETION_TOPICS`. The variable is empty by default,
   so the operation stays `deletion_pending`.
4. A reconciler republishes requests that stay pending too long.

## Runtime

HTTP on 8081 (`/health/live`, `/health/ready`), gRPC on 9091. Readiness
requires a reachable database with Flyway migrations applied.
