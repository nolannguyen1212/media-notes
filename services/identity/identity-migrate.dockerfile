FROM flyway/flyway:11
COPY services/identity/migrations /flyway/sql
