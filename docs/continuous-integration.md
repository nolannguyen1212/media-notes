# Continuous Integration

`.github/workflows/ci.yml` tests every push and pull request to `master`.
Each service has its own release workflow that builds and deploys it.

| Job | Runs | Local equivalent |
| --- | --- | --- |
| `web` | `pnpm install --frozen-lockfile`, codegen, build, Biome lint, type-check, tests | `make web:build web:lint web:typecheck web:test` |
| `services` | Build and test every Go service | `make build:v2 test:v2` |

## Releases

Each service has a workflow in `.github/workflows/` named after it:
`identity`, `billing`, `media`, `content`, `conductor`, `hermes`, `worker`,
and `web`. It runs on pushes to `master` that change the service's directory,
and manually with `workflow_dispatch`. Go services also run when
`contracts/gen/go/` changes, `worker` when `contracts/gen/python/` changes,
and `web` when hermes's GraphQL schema changes. Each one calls the shared
`release-service.yml`:

1. `build` pushes the app image, and the Flyway migration image when the
   service has a database, to GHCR as
   `ghcr.io/nolannguyen1212/<image>:<sha>` and `:latest`. Each image has its
   own build cache. The `web` image is built with the repository variable
   `VITE_HERMES_URL`.
2. `bump` opens a pull request in `k8s-deploy` that sets those images' tags
   to the new commit SHA and renames the service's migration Job, whose name
   ends in the SHA. It needs the repository secret `K8S_DEPLOY_TOKEN`, a token
   with contents and pull request write access to `k8s-deploy`.

Merging that pull request is the release. A push that touches several
services opens one pull request per service.

Release workflows do not wait for the `ci.yml` tests, because they run after
the merge. Pull requests are gated by `ci.yml` instead.

## Not covered yet

- Buf lint and breaking-change checks (`make proto:lint` runs locally only).
- Python worker tests (`make worker:test` runs locally only).
- Integration tests (`make test:v2-integration`, Docker required).
