"""Synchronisation Google Health -> PostgreSQL."""
import asyncio
import logging
from datetime import date, datetime, timedelta

import httpx

from . import config, google_health as gh, store

log = logging.getLogger("healthsync")
_lock = asyncio.Lock()
_TIME_KEYS = {"civilStartTime", "civilEndTime", "startTime", "endTime", "dataSource", "interval"}


def flatten(obj, prefix: str) -> dict[str, float]:
    """Aplatit les valeurs numériques : {"countSum": "3822"} -> {"steps.countSum": 3822.0}.

    Les int64 arrivent en chaînes dans l'API Google, d'où la conversion.
    """
    out: dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}"))
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out[prefix] = float(obj)
    elif isinstance(obj, str):
        try:
            out[prefix] = float(obj)
        except ValueError:
            pass
    return out


def rollup_rows(data_type: str, points: list[dict]) -> list[tuple[date, str, float]]:
    rows = []
    for p in points:
        d = p.get("civilStartTime", {}).get("date")
        if not d:
            continue
        day = date(d["year"], d["month"], d["day"])
        for key, value in p.items():
            if key in _TIME_KEYS:
                continue
            for metric, v in flatten(value, data_type).items():
                rows.append((day, metric, v))
    return rows


def sleep_rows(points: list[dict]) -> list[dict]:
    rows = []
    for p in points:
        s = p.get("sleep") or {}
        interval = s.get("interval") or {}
        if not interval.get("startTime") or not interval.get("endTime"):
            continue
        summary = s.get("summary") or {}
        stages = {st.get("type"): int(st.get("minutes", 0)) for st in summary.get("stagesSummary", [])}
        rows.append(
            {
                "id": p.get("name") or f"{interval['startTime']}",
                "start": store.parse_ts(interval["startTime"]),
                "end": store.parse_ts(interval["endTime"]),
                "asleep": int(summary["minutesAsleep"]) if "minutesAsleep" in summary else None,
                "awake": int(summary["minutesAwake"]) if "minutesAwake" in summary else None,
                "deep": stages.get("DEEP"),
                "light": stages.get("LIGHT"),
                "rem": stages.get("REM"),
                "main": (s.get("metadata") or {}).get("main"),
            }
        )
    return rows


async def run_sync(full: bool = False) -> dict:
    """Synchronise. full=True force le rattrapage historique (BACKFILL_DAYS)."""
    if _lock.locked():
        return {"status": "already_running"}
    async with _lock:
        today = datetime.now(config.TZ).date()
        backfill = full or not await store.has_data()
        days = config.BACKFILL_DAYS if backfill else config.RECENT_DAYS
        start = today - timedelta(days=days - 1)
        result: dict = {"from": start.isoformat(), "to": today.isoformat(), "types": {}}
        errors = 0
        async with httpx.AsyncClient(timeout=60) as client:
            for dtype in config.ROLLUP_TYPES:
                try:
                    rows = rollup_rows(dtype, await gh.daily_rollup(client, dtype, start, today))
                    await store.upsert_metrics(rows)
                    await store.log(dtype, True, len(rows))
                    result["types"][dtype] = len(rows)
                except gh.NotConnected:
                    await store.log("_run", False, 0, "Compte Google non connecté")
                    return {"status": "not_connected"}
                except gh.ApiError as e:
                    errors += 1
                    # 400/404 : type non disponible pour ce compte ou cet appareil
                    log.warning("%s : %s", dtype, e)
                    await store.log(dtype, False, 0, str(e))
                    result["types"][dtype] = f"erreur {e.status}"
            if config.SYNC_SLEEP:
                try:
                    flt = f'sleep.interval.civil_end_time >= "{start.isoformat()}"'
                    rows = sleep_rows(await gh.list_points(client, "sleep", flt))
                    await store.upsert_sleep(rows)
                    await store.log("sleep", True, len(rows))
                    result["types"]["sleep"] = len(rows)
                except gh.NotConnected:
                    await store.log("_run", False, 0, "Compte Google non connecté")
                    return {"status": "not_connected"}
                except gh.ApiError as e:
                    errors += 1
                    await store.log("sleep", False, 0, str(e))
                    result["types"]["sleep"] = f"erreur {e.status}"
        msg = f"{len(result['types']) - errors} type(s) OK, {errors} en erreur"
        await store.log("_run", errors == 0, 0, msg)
        result["status"] = "ok" if errors == 0 else "partial"
        return result


async def loop() -> None:
    while True:
        try:
            await run_sync()
        except Exception:  # la boucle ne doit jamais mourir
            log.exception("Échec de synchronisation")
        await asyncio.sleep(config.SYNC_INTERVAL_MIN * 60)
