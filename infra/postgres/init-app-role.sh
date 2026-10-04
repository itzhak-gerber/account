#!/bin/sh
# Local development only: create the non-owner role the app connects as.
# Row-level security does not apply to table owners or superusers, so the app must not use them.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE invoice_app LOGIN PASSWORD '${APP_DB_PASSWORD:-invoice_app}';
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO invoice_app;
SQL
