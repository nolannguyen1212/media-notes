# Local Infrastructure

`docker-compose.yml` runs the infrastructure every service needs. Start it
with `make infra:up`, then create the Kafka topics with
`make infra:kafka-topics`.

| Service | Host address | Credentials |
| --- | --- | --- |
| PostgreSQL | `localhost:5432` | `admin` / `password`; one role per service, password equal to its name |
| Kafka (KRaft, single node) | `localhost:9092` (`kafka:29092` inside Compose) | none |
| Kafka UI | `http://localhost:8080` | none |
| Redis | `localhost:6379` | password `redisadmin` (`REDIS_PASSWORD`) |
| MinIO API | `localhost:9002` | `minioadmin` / `minioadmin` (`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`) |
| MinIO console | `http://localhost:9001` | same as the API |

The Compose `app` profile also runs every service and its migration
container (`docker compose --profile app up --build`). Those services use
host networking, so they reach the infrastructure at the host addresses
above.

## Commands

| Command | Effect |
| --- | --- |
| `make infra:up` | Start the infrastructure containers |
| `make infra:kafka-topics` | Create the Kafka topics (idempotent) |
| `make infra:down` | Stop the containers, keep the volumes |
| `make infra:purge` | Remove the project's containers and volumes, then run `docker system prune -a -f` and `docker volume prune -a -f` |

`make infra:purge` also prunes Docker images and volumes from other projects
on the machine.

PostgreSQL runs `deploy/postgres/init/` only on first start against an empty
volume. To recreate the service roles and databases, purge the volume first.

Kafka auto-creates topics locally, and all listeners are plaintext. These
settings and the default credentials are for local development only.
