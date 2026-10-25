#!/bin/bash
# Exécuté une seule fois par Postgres à la création du volume.
# Crée le schéma et un rôle en lecture seule pour Grafana.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE TABLE IF NOT EXISTS daily_metrics (
    day        date             NOT NULL,
    metric     text             NOT NULL,
    value      double precision NOT NULL,
    updated_at timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (day, metric)
);
CREATE TABLE IF NOT EXISTS sleep_sessions (
    id             text PRIMARY KEY,
    start_time     timestamptz NOT NULL,
    end_time       timestamptz NOT NULL,
    minutes_asleep integer,
    minutes_awake  integer,
    minutes_deep   integer,
    minutes_light  integer,
    minutes_rem    integer,
    is_main        boolean,
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sync_log (
    id        bigserial PRIMARY KEY,
    at        timestamptz NOT NULL DEFAULT now(),
    data_type text        NOT NULL,
    ok        boolean     NOT NULL,
    rows      integer     NOT NULL DEFAULT 0,
    message   text
);

CREATE ROLE grafana_ro LOGIN PASSWORD '${GRAFANA_DB_PASSWORD}';
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
EOSQL
