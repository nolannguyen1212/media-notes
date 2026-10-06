FROM flyway/flyway:11
COPY services/conductor/migrations /flyway/sql
