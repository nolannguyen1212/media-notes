# Manual test guides

Step-by-step gRPC test scripts (`grpcurl`/`grpcui`) for each implemented
service, with real captured request/response pairs — not illustrative
examples. Written for a developer verifying a local build by hand, as a
complement to the automated unit/integration tests under each
`services/<name>/internal/**/*_test.go`.

| Service | Guide |
| --- | --- |
| Identity | [identity/manual.md](identity/manual.md) |
| Billing | [billing/manual.md](billing/manual.md) |
| Media | [media/manual.md](media/manual.md) |
| Content | [content/manual.md](content/manual.md) |

`hermes`, `conductor`, and `conductor-worker` have no guide: hermes is
GraphQL, and the other two are driven by Kafka. See
[`docs/services/`](../services/) for every service's design.
