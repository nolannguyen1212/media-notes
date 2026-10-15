# Database Migrations

Each stateful service owns one PostgreSQL database, role, and migration
history. Services never share a database or a schema; on the shared local
server, `deploy/postgres/init/` creates one role and database per service so
a service credential cannot connect to another service's database.

| Service | Database | Schema | Migrations |
| --- | --- | --- | --- |
| `identity` | `identity` | `public` | `V1`–`V2` |
| `billing` | `billing` | `billing` | `V1`–`V3` |
| `media` | `media` | `public` | `V1`–`V5` |
| `content` | `content` | `public` | `V1`–`V3` |
| `conductor` | `workflow` | `public` | `V1`–`V4` |

`hermes` and `conductor-worker` are stateless and own no migrations.

## Tooling

Migrations use [Flyway](https://flywaydb.org) 11 and live in
`services/<name>/migrations/V<n>__<description>.sql`. Flyway runs outside the
service binary:

- Locally: `make <service>:migrate` runs the `flyway/flyway:11` container
  against the infra Compose network.
- In Compose: each service has a `<service>-migrate` container.
- In CI: each service has a migration image (`<service>-migrate.dockerfile`)
  pushed to GHCR.

At startup a service only checks that `flyway_schema_history` exists
(`internal/store.CheckMigrated`) and exits if it does not. It never migrates
itself.

## Rollback

Flyway Community has no `undo`. Every migration has a hand-written reverse
script in `services/<name>/rollback/U<n>__<description>.sql`, applied
manually with `psql` in reverse order.

## Writing a migration

- Never edit an applied migration; Flyway checksums every applied file. Add a
  new one instead.
- Keep changes backward compatible with the running code. For a destructive
  change: ship code that no longer uses the old shape, wait for it to roll
  out, then drop the old object in a later migration.
- Add the matching `U<n>` rollback script in the same change.
