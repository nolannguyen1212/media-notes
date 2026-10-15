# Services

Each directory is an independently buildable and deployable service. A
service never imports another service's code or reads another service's
database.

| Service | Language | Role | Design |
| --- | --- | --- | --- |
| `web` | TypeScript, React | Browser app; talks only to `hermes` | — |
| `hermes` | Go | Public GraphQL gateway | [hermes](../docs/services/hermes.md) |
| `identity` | Go | Users, sessions, prompt settings, account deletion | [identity](../docs/services/identity.md) |
| `billing` | Go | Quotes, credit reservation and settlement, Polar checkout | [billing](../docs/services/billing.md) |
| `media` | Go | Uploads, media metadata, trash, processing requests | [media](../docs/services/media.md) |
| `content` | Go | Transcripts, generated content, standalone audio jobs | [content](../docs/services/content.md) |
| `conductor` | Go | Processing workflows: steps, retries, timeouts, joins | [conductor](../docs/services/conductor.md) |
| `worker` | Python | `conductor-worker`: runs Whisper, LLM, TTS, and thumbnail steps | [worker](../docs/services/worker.md) |

## Rules

- Synchronous calls use the versioned gRPC contracts in `contracts/proto`.
- Asynchronous communication uses versioned Kafka topics
  (`mn.<domain>.<event>.v1`).
- Media bytes and long-form text never travel through Kafka; they stay in
  MinIO or the owning service's database.
- Every Go service exposes `GET /health/live` and `GET /health/ready` on its
  HTTP port.

## Ports

| Service | HTTP | gRPC |
| --- | --- | --- |
| `identity` | 8081 | 9091 |
| `billing` | 8082 | 9093 |
| `media` | 8083 | 19095 |
| `content` | 8084 | 9095 |
| `conductor` | 8085 | — |
| `hermes` | 8086 (GraphQL at `/graphql`) | — |
| `web` | 5173 (dev server) | — |
