# Continuous Integration

`.github/workflows/ci.yml` runs on every push and pull request to `master`.

| Job | Runs | Local equivalent |
| --- | --- | --- |
| `web` | `pnpm install --frozen-lockfile`, codegen, build, Biome lint, type-check, tests | `make web:build web:lint web:typecheck web:test` |
| `services` | Build and test every Go service | `make build:v2 test:v2` |
| `build-and-push` | After both pass, on `master` pushes only | `make <service>:docker-build` |

`build-and-push` builds 13 images and pushes them to GHCR as
`ghcr.io/nolannguyen1212/<image>:<sha>` and `:latest`: one app image for
`web`, `hermes`, `identity`, `billing`, `media`, `content`, `conductor`, and
`conductor-worker`, plus one Flyway migration image for each service that owns
a database. The `web` image is built with
`VITE_HERMES_URL=https://medianotes.api.bbmonster.online`. The job uses the
workflow's `GITHUB_TOKEN` with `packages: write`; every other job is
read-only.

## Not covered yet

- Buf lint and breaking-change checks (`make proto:lint` runs locally only).
- Python worker tests (`make worker:test` runs locally only).
- Integration tests (`make test:v2-integration`, Docker required).
- Deployment. Releases happen in the separate `k8s-deploy` GitOps
  repository: a commit there bumps the image tags and ArgoCD syncs the
  cluster (see the root README's Deployment section). CI does not bump the
  tags.
