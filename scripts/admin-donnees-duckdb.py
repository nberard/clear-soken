#!/usr/bin/env python3
"""Espace admin sans Google Cloud : exporte les marts Instagram d'une base DuckDB de clearmind-tools en JSON.

    # dans clearmind-tools/data-platform : python ingestion/load_bronze.py --demo --target duckdb, puis dbt build
    python3 scripts/admin-donnees-duckdb.py ../clearmind-tools/data-platform/local/clearmind.duckdb admin-donnees/
    ADMIN_DONNEES_DIR=admin-donnees make dev-api

Un fichier par mart (mart_instagram_publications.json…), lu par l'API à la place de BigQuery.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

MARTS = {
    "mart_instagram_publications": "order by published_at desc",
    "mart_instagram_comptes": "order by pct_faux desc, reels_likes desc limit 5000",
    "mart_instagram_qualite": "",
    "mart_audience_pays": "where platform = 'instagram' order by abonnes desc",
}


def jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def main(base: str, sortie: str, schema: str = "dbt_local_or") -> None:
    con = duckdb.connect(base, read_only=True)
    out = Path(sortie)
    out.mkdir(parents=True, exist_ok=True)
    for mart, suite in MARTS.items():
        cur = con.execute(f"select * from {schema}.{mart} {suite}")
        cols = [d[0] for d in cur.description]
        lignes = [{c: jsonable(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
        (out / f"{mart}.json").write_text(json.dumps(lignes, ensure_ascii=False), encoding="utf-8")
        print(f"{mart:<30} {len(lignes)} lignes")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
