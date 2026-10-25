"""Client minimal de la Google Health API (v4)."""
import asyncio
from datetime import date, timedelta

import httpx

from . import config, oauth


class NotConnected(Exception):
    pass


class ApiError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


async def _request(client: httpx.AsyncClient, method: str, path: str, **kw) -> dict:
    """Requête authentifiée avec backoff exponentiel sur 429 / 5xx."""
    delay = 2.0
    for attempt in range(5):
        token = await oauth.get_access_token()
        if not token:
            raise NotConnected()
        r = await client.request(
            method,
            f"{config.API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            **kw,
        )
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            await asyncio.sleep(delay)
            delay *= 2
            continue
        if r.status_code == 401:
            raise NotConnected()
        if r.status_code >= 400:
            raise ApiError(r.status_code, r.text)
        return r.json() if r.content else {}
    raise ApiError(429, "trop de tentatives")


def _civil(d: date) -> dict:
    return {
        "date": {"year": d.year, "month": d.month, "day": d.day},
        "time": {"hours": 0, "minutes": 0, "seconds": 0, "nanos": 0},
    }


async def identity(client: httpx.AsyncClient) -> dict:
    return await _request(client, "GET", "/identity")


async def daily_rollup(client: httpx.AsyncClient, data_type: str, start: date, end: date) -> list[dict]:
    """Agrégats quotidiens sur [start, end] inclus, découpés en tranches."""
    points: list[dict] = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=config.CHUNK_DAYS - 1), end)
        body = {
            "range": {"start": _civil(cur), "end": _civil(chunk_end + timedelta(days=1))},
            "windowSizeDays": 1,
        }
        data = await _request(
            client, "POST", f"/dataTypes/{data_type}/dataPoints:dailyRollUp", json=body
        )
        points.extend(data.get("rollupDataPoints", []))
        cur = chunk_end + timedelta(days=1)
    return points


async def list_points(client: httpx.AsyncClient, data_type: str, filter_expr: str) -> list[dict]:
    points: list[dict] = []
    page_token = None
    while True:
        params = {"filter": filter_expr, "pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        data = await _request(client, "GET", f"/dataTypes/{data_type}/dataPoints", params=params)
        points.extend(data.get("dataPoints", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            return points
