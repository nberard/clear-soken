"""Connecteur Health Connect (Android) : reçoit les envois de l'appli « HC Webhook ».

Google Fit, Samsung Health, les montres, etc. écrivent dans Health Connect sur le
téléphone ; l'appli HC Webhook (github.com/mcnaveen/health-connect-webhook) les
pousse en JSON vers POST /ingest/health-connect.

Les envois sont incrémentaux (seulement les nouveaux enregistrements) : on garde
donc les enregistrements bruts (table hc_records) et on recalcule le total des
jours touchés, écrit dans daily_metrics avec la source « health-connect ».
Format : docs/webhook.md du dépôt HC Webhook.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from . import config, store

SOURCE = "health-connect"

# Types gérés -> clé de la valeur utile dans chaque enregistrement
_INTERVAL_TYPES = {"steps", "distance", "total_calories", "active_calories", "exercise"}
_INSTANT_TYPES = {"heart_rate", "resting_heart_rate", "heart_rate_variability", "weight"}
SUPPORTED = _INTERVAL_TYPES | _INSTANT_TYPES | {"sleep"}

# Constantes AndroidX SleepSessionRecord.STAGE_TYPE_*
_STAGE_INT = {1: "AWAKE", 2: "SLEEPING", 3: "OUT_OF_BED", 4: "LIGHT", 5: "DEEP", 6: "REM", 7: "AWAKE_IN_BED"}


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = store.parse_ts(value)
    if dt.tzinfo is None:  # par sécurité : sans fuseau, on suppose l'heure locale
        dt = dt.replace(tzinfo=config.TZ)
    return dt


def _local_day(dt: datetime) -> date:
    return dt.astimezone(config.TZ).date()


def _num(rec: dict, *keys: str) -> float | None:
    for k in keys:
        v = rec.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def _record_id(dtype: str, rec: dict) -> str | None:
    """Id stable : metadata.id, sinon type + heure (agrégats N minutes / jour)."""
    rid = (rec.get("metadata") or {}).get("id")
    if rid:
        return str(rid)
    t = rec.get("start_time") or rec.get("time")
    return f"{dtype}@{t}" if t else None


def parse_records(payload: dict) -> list[dict]:
    """Enregistrements bruts à stocker : type, id, jour local, heures, valeurs utiles."""
    out = []
    for dtype in (_INTERVAL_TYPES | _INSTANT_TYPES) & payload.keys():
        for rec in payload.get(dtype) or []:
            if not isinstance(rec, dict):
                continue
            start = _ts(rec.get("start_time") or rec.get("time"))
            rid = _record_id(dtype, rec)
            if not start or not rid:
                continue
            values = {
                k: v
                for k, v in rec.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            }
            out.append(
                {
                    "type": dtype,
                    "rid": rid,
                    "day": _local_day(start),
                    "start": start,
                    "end": _ts(rec.get("end_time")),
                    "values": values,
                }
            )
    return out


def _stage_name(raw) -> str:
    if isinstance(raw, int) or (isinstance(raw, str) and raw.isdigit()):
        return _STAGE_INT.get(int(raw), "UNKNOWN")
    s = str(raw or "").upper()
    for name in ("AWAKE_IN_BED", "OUT_OF_BED", "AWAKE", "DEEP", "LIGHT", "REM", "SLEEPING"):
        if name in s:
            return name
    return "UNKNOWN"


def parse_sleep(payload: dict) -> list[dict]:
    """Nuits au format de sleep_sessions (même table que Google Health)."""
    rows = []
    for rec in payload.get("sleep") or []:
        end = _ts(rec.get("session_end_time") or rec.get("end_time"))
        if not end:
            continue
        stages = rec.get("stages") or []
        starts = [_ts(s.get("start_time")) for s in stages if s.get("start_time")]
        duration = _num(rec, "duration_seconds")
        start = _ts(rec.get("start_time")) or (min(starts) if starts else None)
        if not start and duration is not None:
            start = end - timedelta(seconds=duration)
        if not start:
            continue

        minutes: dict[str, float] = defaultdict(float)
        for s in stages:
            secs = _num(s, "duration_seconds")
            if secs is None:
                a, b = _ts(s.get("start_time")), _ts(s.get("end_time"))
                secs = (b - a).total_seconds() if a and b else 0
            minutes[_stage_name(s.get("stage"))] += secs / 60

        total = (duration if duration is not None else (end - start).total_seconds()) / 60
        if stages:
            asleep = sum(minutes[k] for k in ("LIGHT", "DEEP", "REM", "SLEEPING"))
            awake = sum(minutes[k] for k in ("AWAKE", "AWAKE_IN_BED", "OUT_OF_BED"))
        else:
            asleep, awake = total, 0

        rid = (rec.get("metadata") or {}).get("id") or rec.get("session_end_time")
        rows.append(
            {
                "id": f"hc:{rid}",
                "start": start,
                "end": end,
                "asleep": round(asleep),
                "awake": round(awake),
                "deep": round(minutes["DEEP"]) if stages else None,
                "light": round(minutes["LIGHT"]) if stages else None,
                "rem": round(minutes["REM"]) if stages else None,
                "main": None,
            }
        )
    return rows


def daily_metrics(dtype: str, records: list[dict]) -> dict[str, float]:
    """Totaux d'un jour pour un type, avec les noms de métriques de Google Health
    (le tableau de bord et l'applet les affichent sans modification)."""
    vals = [r["values"] for r in records]
    if not vals:
        return {}

    def total(*keys):
        xs = [_num(v, *keys) for v in vals]
        return sum(x for x in xs if x is not None)

    if dtype == "steps":
        return {"steps.countSum": total("count")}
    if dtype == "distance":
        return {"distance.millimetersSum": total("meters") * 1000}
    if dtype == "total_calories":
        return {"total-calories.kcalSum": total("calories")}
    if dtype == "active_calories":
        return {"active-calories.kcalSum": total("calories")}
    if dtype == "exercise":
        return {"exercise.minutesSum": total("duration_seconds") / 60}
    if dtype == "heart_rate":
        avgs = [x for x in (_num(v, "avg", "bpm") for v in vals) if x is not None]
        maxs = [x for x in (_num(v, "max", "bpm") for v in vals) if x is not None]
        mins = [x for x in (_num(v, "min", "bpm") for v in vals) if x is not None]
        if not avgs:
            return {}
        return {
            "heart-rate.beatsPerMinuteAvg": sum(avgs) / len(avgs),
            "heart-rate.beatsPerMinuteMax": max(maxs),
            "heart-rate.beatsPerMinuteMin": min(mins),
        }
    if dtype == "resting_heart_rate":
        xs = [x for x in (_num(v, "bpm") for v in vals) if x is not None]
        return {"daily-resting-heart-rate.beatsPerMinute": sum(xs) / len(xs)} if xs else {}
    if dtype == "heart_rate_variability":
        xs = [x for x in (_num(v, "avg", "rmssd_millis") for v in vals) if x is not None]
        return {"daily-heart-rate-variability.rmssdMillis": sum(xs) / len(xs)} if xs else {}
    if dtype == "weight":
        last = max(records, key=lambda r: r["start"])
        kg = _num(last["values"], "kilograms")
        return {"weight.kilograms": kg} if kg is not None else {}
    return {}


async def ingest(payload: dict) -> dict:
    """Stocke un envoi HC Webhook et recalcule les jours touchés."""
    records = parse_records(payload)
    sleep = parse_sleep(payload)
    deleted = [d for d in payload.get("deleted") or [] if isinstance(d, dict) and d.get("id")]

    touched: set[tuple[str, date]] = {(r["type"], r["day"]) for r in records}
    await store.upsert_hc_records(records)
    for d in deleted:
        dtype, rid = str(d.get("type")), str(d["id"])
        if dtype == "sleep":
            await store.delete_sleep(f"hc:{rid}")
        else:
            day = await store.delete_hc_record(dtype, rid)
            if day:
                touched.add((dtype, day))
    await store.upsert_sleep(sleep, source=SOURCE)

    for dtype, day in sorted(touched, key=lambda t: (t[0], t[1])):
        metrics = daily_metrics(dtype, await store.hc_records_for(dtype, day))
        await store.replace_source_metrics(day, dtype_prefixes(dtype), metrics, SOURCE)

    ignored = sorted(
        k for k, v in payload.items()
        if isinstance(v, list) and k not in SUPPORTED and k != "deleted"
    )
    counts = defaultdict(int)
    for r in records:
        counts[r["type"]] += 1
    if sleep:
        counts["sleep"] = len(sleep)
    msg = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "aucune donnée"
    if deleted:
        msg += f" ; {len(deleted)} suppression(s)"
    await store.log(SOURCE, True, len(records) + len(sleep), msg)
    return {
        "ok": True,
        "records": dict(counts),
        "deleted": len(deleted),
        "days_updated": len(touched),
        "ignored_types": ignored,
    }


def dtype_prefixes(dtype: str) -> list[str]:
    """Métriques que produit un type (pour effacer celles d'un jour devenu vide)."""
    return {
        "steps": ["steps."],
        "distance": ["distance."],
        "total_calories": ["total-calories."],
        "active_calories": ["active-calories."],
        "exercise": ["exercise."],
        "heart_rate": ["heart-rate."],
        "resting_heart_rate": ["daily-resting-heart-rate."],
        "heart_rate_variability": ["daily-heart-rate-variability."],
        "weight": ["weight."],
    }.get(dtype, [])
