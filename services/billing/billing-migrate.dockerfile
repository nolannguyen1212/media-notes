FROM flyway/flyway:11
COPY services/billing/migrations /flyway/sql
